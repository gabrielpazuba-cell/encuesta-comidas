"""
Respaldo automático de la base de datos de la Encuesta de Comidas.

Este script NO es parte de la app: corre aparte, una vez por día, desde
GitHub Actions (ver .github/workflows/respaldo.yml). Se baja las tablas
completas de Supabase, arma un CSV por tabla, los mete en un solo archivo
comprimido y lo manda por mail a la cuenta del estudio.

Por qué existe, si Supabase ya hace backups:
  - Los backups del plan Pro NO se pueden descargar: viven adentro de
    Supabase y solo guardan los últimos 7 días. Si alguien borra una tabla
    y nadie se da cuenta en una semana, no hay forma de recuperarla.
  - Si la cuenta se suspende (por ejemplo por un problema de facturación),
    se pierden los datos y los backups al mismo tiempo.
  La propia documentación de Supabase recomienda mantener exportaciones
  propias fuera de la plataforma. Esto es eso.

Variables de entorno que necesita (las mismas que ya usa
enviar_recordatorios.py, no hay que configurar ninguna nueva):
  GMAIL_USER          dirección de la cuenta que envía
  GMAIL_APP_PASSWORD  contraseña de aplicación de Google (NO la de la cuenta)
  SUPABASE_URL        url base de la API REST del proyecto (termina en /rest/v1)
  SUPABASE_KEY        clave de la API
  DRY_RUN             "1" para armar el respaldo y NO mandarlo por mail.
                      Igual muestra cuántas filas bajó y cuánto pesa, así se
                      puede probar que anda sin llenar la casilla de mails.
  DESTINO_RESPALDO    opcional: mandar a otra dirección en vez de la del
                      estudio. Sirve para probar sin tocar la casilla real.

IMPORTANTE sobre la privacidad: el repositorio es público, así que los logs
de GitHub Actions los puede leer cualquiera. Acá NUNCA se imprime el
contenido de las filas ni direcciones de participantes: solo cantidades y
tamaños. Los datos viajan únicamente adentro del mail.
"""

import ast
import csv
import io
import os
import smtplib
import ssl
import sys
import zipfile
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage

import requests

# Tablas que se respaldan. Si en el futuro se agrega una tabla nueva a la
# app, hay que sumarla acá o no va a quedar respaldada.
TABLAS = ["usuarios", "encuesta_comidas"]

# A dónde llega el respaldo. Es la misma casilla del botón "Contacto".
EMAIL_RESPALDO = "gamification.utdt@gmail.com"

# Supabase corta las respuestas de la API en 1000 filas. Con 200 registros
# hoy no haría falta paginar, pero el estudio va a crecer y sin esto el
# respaldo quedaría truncado en silencio, que es la peor forma de fallar.
FILAS_POR_PAGINA = 1000

ZONA_ARGENTINA = timezone(timedelta(hours=-3))


def traer_tabla(supabase_url, supabase_key, tabla):
    """Baja una tabla entera, de a páginas. Devuelve la lista de filas."""
    cabeceras = {"apikey": supabase_key, "Authorization": f"Bearer {supabase_key}"}
    filas = []
    desde = 0
    while True:
        resp = requests.get(
            f"{supabase_url}/{tabla}",
            headers=cabeceras,
            params={"select": "*", "limit": FILAS_POR_PAGINA, "offset": desde},
            timeout=60,
        )
        resp.raise_for_status()
        pagina = resp.json()
        filas.extend(pagina)
        # Si volvió menos de una página completa, ya no queda nada más.
        if len(pagina) < FILAS_POR_PAGINA:
            return filas
        desde += FILAS_POR_PAGINA


def armar_csv(filas, columnas_si_vacio=None):
    """Convierte una lista de filas en el texto de un CSV.

    `columnas_si_vacio` sirve para las planillas que todavía no tienen datos
    (por ejemplo la encuesta final, hasta que alguien complete las 5 cargas):
    en vez de un archivo vacío, que en Excel no se entiende, deja al menos la
    fila de encabezados para que se vea qué va a contener.
    """
    if not filas:
        if not columnas_si_vacio:
            return ""
        salida = io.StringIO()
        csv.DictWriter(salida, fieldnames=columnas_si_vacio).writeheader()
        return salida.getvalue()

    # Las columnas salen de recorrer todas las filas, no solo la primera:
    # si alguna fila tiene un campo que las demás no, igual se incluye.
    columnas = []
    for fila in filas:
        for clave in fila:
            if clave not in columnas:
                columnas.append(clave)

    salida = io.StringIO()
    escritor = csv.DictWriter(salida, fieldnames=columnas, extrasaction="ignore")
    escritor.writeheader()
    escritor.writerows(filas)
    return salida.getvalue()


def leer_lista_de_app(nombre_constante):
    """Saca una lista de enunciados de app.py, SIN importarlo.

    Los textos de las afirmaciones viven en el código (AFIRMACIONES_INICIALES
    y AFIRMACIONES_CIERRE en app.py), no en la base: en Supabase de cada
    respuesta solo queda 'afirmacion_07 = VERDADERO' o 'cierre_03 = 5'. Sin
    el texto, la planilla no se puede analizar sin tener el código al lado.

    Se lee con ast, que entiende el archivo pero no lo ejecuta: importar
    app.py desde acá arrancaría la aplicación entera.
    """
    ruta = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.py")
    try:
        with open(ruta, encoding="utf-8") as f:
            arbol = ast.parse(f.read())
    except Exception as e:
        print(f"  ATENCION: no se pudo leer app.py para los enunciados: {e!r}")
        return []

    for nodo in arbol.body:
        if isinstance(nodo, ast.Assign) and any(
            isinstance(d, ast.Name) and d.id == nombre_constante
            for d in nodo.targets
        ):
            return ast.literal_eval(nodo.value)

    print(f"  ATENCION: no se encontró {nombre_constante} en app.py.")
    return []


def armar_planilla_de_escala(filas, tipo_registro, prefijo, enunciados):
    """Planilla legible de una encuesta guardada como una fila por afirmación.

    Sirve igual para la encuesta inicial (verdadero/falso, item_nombre
    'afirmacion_07') que para la de cierre (escala 1 a 7, 'cierre_03'):
    cruza el número guardado con el texto real del enunciado.
    """
    legibles = []
    for fila in filas:
        if fila.get("tipo_registro") != tipo_registro:
            continue

        nombre = fila.get("item_nombre") or ""
        numero = None
        if nombre.startswith(prefijo):
            try:
                numero = int(nombre.rsplit("_", 1)[-1])
            except ValueError:
                numero = None

        # Si mañana se agregan o reordenan enunciados en el código, las
        # respuestas viejas pueden quedar apuntando a un número que ya no
        # existe. En ese caso se deja el texto vacío en vez de romper el
        # respaldo entero.
        texto = ""
        if numero is not None and 1 <= numero <= len(enunciados):
            texto = enunciados[numero - 1]

        legibles.append(
            {
                "usuario": fila.get("usuario"),
                "fecha": fila.get("fecha"),
                "numero": numero if numero is not None else nombre,
                "afirmacion": texto,
                "respuesta": fila.get("item_detalle"),
            }
        )

    legibles.sort(
        key=lambda r: (str(r["usuario"]), r["numero"] if isinstance(r["numero"], int) else 0)
    )
    return legibles


def armar_planilla_de_comidas(filas):
    """Los registros diarios de comida, más el consentimiento.

    Gabriel pidió que el consentimiento viaje en esta misma planilla. Se
    conserva la columna `tipo_registro` para poder separarlo en un filtro:
    las filas de consentimiento no son items consumidos y contarlas como
    tales inflaría cualquier total.
    """
    TIPOS = ("consentimiento", "comida_hora", "item")
    seleccionadas = [f for f in filas if f.get("tipo_registro") in TIPOS]
    seleccionadas.sort(key=lambda f: (str(f.get("usuario")), str(f.get("fecha")), f.get("id") or 0))
    return seleccionadas


def armar_zip(csvs_por_tabla):
    """Mete todos los CSV en un solo archivo comprimido, en memoria."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as z:
        for tabla, texto in csvs_por_tabla.items():
            # utf-8-sig (con BOM) para que Excel en Windows abra bien los
            # acentos y la ñ. Sin esto se ven como símbolos raros.
            z.writestr(f"{tabla}.csv", texto.encode("utf-8-sig"))
    return buffer.getvalue()


def armar_mail(remitente, destino, nombre_archivo, contenido_zip, resumen):
    mensaje = EmailMessage()
    mensaje["Subject"] = f"Respaldo Encuesta de Comidas - {nombre_archivo[-14:-4]}"
    mensaje["From"] = remitente
    mensaje["To"] = destino
    mensaje.set_content(
        "Respaldo automático de la base de datos de la Encuesta de Comidas.\n\n"
        f"{resumen}\n"
        "El adjunto es un .zip: descomprimilo y abrí cualquiera de las\n"
        "planillas con Excel, haciendo doble clic.\n\n"
        "  usuarios              -> los participantes y sus datos\n"
        "  1-encuesta-inicial    -> la encuesta de verdadero/falso\n"
        "  2-registros-de-comidas-> lo que comió cada uno los 5 días, y el\n"
        "                           consentimiento (columna tipo_registro)\n"
        "  3-encuesta-final      -> la encuesta de cierre, escala 1 a 7\n"
        "  copia-completa-...    -> copia técnica de la tabla entera, para\n"
        "                           restaurar la base si hiciera falta\n\n"
        "--\n"
        "Mail automático. Sale todos los días.\n"
        "Guardalo o dejalo en la casilla: mientras esté acá, hay una copia\n"
        "de los datos fuera de Supabase.\n"
    )
    mensaje.add_attachment(
        contenido_zip,
        maintype="application",
        subtype="zip",
        filename=nombre_archivo,
    )
    return mensaje


def main():
    gmail_user = os.environ.get("GMAIL_USER", "").strip()
    # Google muestra la contraseña de aplicación en grupos de 4 ("abcd efgh
    # ijkl mnop"), pero al usarla no van los espacios. Los sacamos acá para
    # que no falle si quedó copiada tal cual.
    gmail_pass = "".join(os.environ.get("GMAIL_APP_PASSWORD", "").split())
    supabase_url = os.environ.get("SUPABASE_URL", "").strip().rstrip("/")
    supabase_key = os.environ.get("SUPABASE_KEY", "").strip()
    dry_run = os.environ.get("DRY_RUN", "").strip() == "1"
    destino = os.environ.get("DESTINO_RESPALDO", "").strip() or EMAIL_RESPALDO

    obligatorias = [("SUPABASE_URL", supabase_url), ("SUPABASE_KEY", supabase_key)]
    if not dry_run:
        obligatorias += [("GMAIL_USER", gmail_user), ("GMAIL_APP_PASSWORD", gmail_pass)]

    faltan = [nombre for nombre, valor in obligatorias if not valor]
    if faltan:
        print(f"ERROR: faltan variables de entorno: {', '.join(faltan)}")
        return 1

    hoy = datetime.now(ZONA_ARGENTINA).date()
    print(f"Respaldo del {hoy} (hora Argentina)")
    if dry_run:
        print("MODO PRUEBA: se arma el respaldo pero NO se manda por mail.\n")

    datos = {}
    for tabla in TABLAS:
        try:
            filas = traer_tabla(supabase_url, supabase_key, tabla)
        except Exception as e:
            print(f"ERROR al bajar la tabla '{tabla}': {e!r}")
            return 1

        # Una tabla vacía no es necesariamente un error (puede ser una tabla
        # nueva), pero sí algo que conviene mirar, así que se avisa fuerte.
        if not filas:
            print(f"  ATENCION: la tabla '{tabla}' volvió VACIA.")
        datos[tabla] = filas
        print(f"  tabla {tabla}: {len(filas)} filas")

    filas_encuesta = datos.get("encuesta_comidas", [])

    # Una planilla por tipo de contenido, para no tener que filtrar a mano.
    #
    # La copia cruda de encuesta_comidas se conserva igual: es la que sirve
    # para restaurar la base si hiciera falta, y es además donde quedan las
    # respuestas de las preguntas previas, que no tienen planilla propia.
    COLUMNAS_ESCALA = ["usuario", "fecha", "numero", "afirmacion", "respuesta"]
    planillas = [
        ("usuarios", datos.get("usuarios", []), None),
        (
            "1-encuesta-inicial",
            armar_planilla_de_escala(
                filas_encuesta,
                "encuesta_inicial",
                "afirmacion_",
                leer_lista_de_app("AFIRMACIONES_INICIALES"),
            ),
            COLUMNAS_ESCALA,
        ),
        ("2-registros-de-comidas", armar_planilla_de_comidas(filas_encuesta), None),
        (
            "3-encuesta-final",
            armar_planilla_de_escala(
                filas_encuesta,
                "encuesta_cierre",
                "cierre_",
                leer_lista_de_app("AFIRMACIONES_CIERRE"),
            ),
            COLUMNAS_ESCALA,
        ),
        ("copia-completa-encuesta_comidas", filas_encuesta, None),
    ]

    csvs = {}
    lineas_resumen = []
    for nombre, filas, columnas_si_vacio in planillas:
        csvs[nombre] = armar_csv(filas, columnas_si_vacio)
        print(f"  {nombre}.csv: {len(filas)} filas")
        lineas_resumen.append(f"  - {nombre}.csv: {len(filas)} filas")

    contenido = armar_zip(csvs)
    nombre_archivo = f"respaldo-encuesta-comidas-{hoy}.zip"
    print(f"\nArchivo armado: {nombre_archivo} ({len(contenido) / 1024:.1f} KB)")

    resumen = "Contenido:\n" + "\n".join(lineas_resumen) + "\n"

    if dry_run:
        print("\nMODO PRUEBA: no se envía. Todo lo demás funcionó.")
        return 0

    try:
        contexto = ssl.create_default_context()
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=contexto, timeout=60) as servidor:
            servidor.login(gmail_user, gmail_pass)
            servidor.send_message(
                armar_mail(gmail_user, destino, nombre_archivo, contenido, resumen)
            )
    except smtplib.SMTPAuthenticationError:
        print(
            "ERROR de autenticación con Gmail.\n"
            "GMAIL_APP_PASSWORD tiene que ser una CONTRASEÑA DE APLICACIÓN de 16 "
            "caracteres (no la contraseña normal de la cuenta), y la cuenta tiene "
            "que tener activada la verificación en dos pasos."
        )
        return 1
    except Exception as e:
        print(f"ERROR al mandar el respaldo por mail: {e!r}")
        return 1

    print("Respaldo enviado.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
