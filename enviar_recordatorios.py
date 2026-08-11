"""
Recordatorios diarios por mail para los participantes de la Encuesta de Comidas.

Este script NO es parte de la app: corre aparte, una vez por día, desde
GitHub Actions (ver .github/workflows/recordatorios.yml). Se hace así y no
dentro de la app porque en el plan Free de Render la instancia se suspende
por inactividad, y un recordatorio programado adentro no saldría de forma
confiable.

A quién le manda (tienen que cumplirse TODAS):
  - Ya hizo su primera carga (tiene fecha_primera_carga).
  - Todavía no llegó a las 5 cargas.
  - Está dentro de los primeros 5 días contados desde su primera carga.
  - Hoy todavía no completó el registro.

Variables de entorno que necesita:
  GMAIL_USER          dirección de la cuenta que envía
  GMAIL_APP_PASSWORD  contraseña de aplicación de Google (NO la de la cuenta)
  SUPABASE_URL        url base de la API REST del proyecto
  SUPABASE_KEY        clave de la API
  DRY_RUN             "1" para no enviar nada y solo mostrar el resumen

IMPORTANTE sobre la privacidad: los logs de GitHub Actions son públicos si el
repositorio es público, así que acá nunca se imprimen las direcciones de los
participantes completas (ver enmascarar()).
"""

import os
import smtplib
import ssl
import sys
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage

import requests

# --- Reglas del estudio (tienen que coincidir con las de app.py) ---
MAX_CARGAS = 5           # al llegar acá, la persona terminó y no recibe más recordatorios
DIAS_RECORDATORIO = 5    # cuántos días se manda, desde la primera carga

URL_APP = "https://encuesta-comidas.onrender.com"
ZONA_ARGENTINA = timezone(timedelta(hours=-3))

ASUNTO = "Recordatorio: tu registro de comidas de hoy"

CUERPO = """\
¡Hola{saludo}!

Te escribimos para recordarte que todavía no cargaste tu registro de comidas de hoy.

Son unos pocos minutos y podés hacerlo desde acá:
{url}

Gracias por sumarte a esta investigación: cada registro cuenta.

--
Este es un recordatorio automático. Vas a recibirlo durante los primeros {dias} días
de tu participación, y solo los días en que no hayas completado el registro.
"""


def enmascarar(email):
    """'juan.perez@gmail.com' -> 'j***@gmail.com'. Para poder loguear sin exponer."""
    if not email or "@" not in email:
        return "???"
    usuario, dominio = email.split("@", 1)
    return f"{usuario[:1]}***@{dominio}"


def solo_fecha(valor):
    """Acepta '2026-08-20' o '2026-08-20T12:34:56' y devuelve un date."""
    if not valor:
        return None
    try:
        return datetime.strptime(str(valor)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def traer_usuarios(supabase_url, supabase_key):
    resp = requests.get(
        f"{supabase_url}/usuarios",
        headers={"apikey": supabase_key, "Authorization": f"Bearer {supabase_key}"},
        params={"select": "email,nombre,sesiones_historicas,ultima_fecha_completado,fecha_primera_carga"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def le_toca_recordatorio(usuario, hoy):
    """Devuelve (True, None) si hay que mandarle, o (False, motivo) si no."""
    email = (usuario.get("email") or "").strip()
    if not email or "@" not in email:
        return False, "sin email válido"

    if (usuario.get("sesiones_historicas") or 0) >= MAX_CARGAS:
        return False, "ya completó el estudio"

    primera = solo_fecha(usuario.get("fecha_primera_carga"))
    if primera is None:
        return False, "todavía no hizo su primera carga"

    dias = (hoy - primera).days
    if dias < 0:
        return False, "fecha de primera carga en el futuro"
    if dias >= DIAS_RECORDATORIO:
        return False, "pasó la ventana de recordatorios"

    if solo_fecha(usuario.get("ultima_fecha_completado")) == hoy:
        return False, "ya cargó hoy"

    return True, None


def armar_mail(remitente, usuario):
    nombre = (usuario.get("nombre") or "").strip()
    mensaje = EmailMessage()
    mensaje["Subject"] = ASUNTO
    mensaje["From"] = remitente
    mensaje["To"] = usuario["email"]
    mensaje.set_content(
        CUERPO.format(
            saludo=f" {nombre}" if nombre else "",
            url=URL_APP,
            dias=DIAS_RECORDATORIO,
        )
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

    faltan = [
        nombre
        for nombre, valor in [
            ("GMAIL_USER", gmail_user),
            ("GMAIL_APP_PASSWORD", gmail_pass),
            ("SUPABASE_URL", supabase_url),
            ("SUPABASE_KEY", supabase_key),
        ]
        if not valor
    ]
    if faltan and not (dry_run and faltan == ["GMAIL_APP_PASSWORD"]):
        print(f"ERROR: faltan variables de entorno: {', '.join(faltan)}")
        return 1

    hoy = datetime.now(ZONA_ARGENTINA).date()
    print(f"Fecha (hora Argentina): {hoy}")
    if dry_run:
        print("MODO PRUEBA: no se envía ningún mail.\n")

    try:
        usuarios = traer_usuarios(supabase_url, supabase_key)
    except Exception as e:
        print(f"ERROR al leer usuarios de Supabase: {e!r}")
        return 1

    print(f"Usuarios en la base: {len(usuarios)}")

    destinatarios = []
    motivos = {}
    for usuario in usuarios:
        toca, motivo = le_toca_recordatorio(usuario, hoy)
        if toca:
            destinatarios.append(usuario)
        else:
            motivos[motivo] = motivos.get(motivo, 0) + 1

    for motivo, cuantos in sorted(motivos.items()):
        print(f"  - {cuantos} sin recordatorio: {motivo}")
    print(f"\nA notificar hoy: {len(destinatarios)}")

    if not destinatarios:
        print("No hay a quién mandarle. Listo.")
        return 0

    if dry_run:
        for usuario in destinatarios:
            print(f"  (prueba) mandaría a {enmascarar(usuario['email'])}")
        return 0

    enviados = 0
    fallidos = 0
    try:
        contexto = ssl.create_default_context()
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=contexto, timeout=60) as servidor:
            servidor.login(gmail_user, gmail_pass)
            for usuario in destinatarios:
                try:
                    servidor.send_message(armar_mail(gmail_user, usuario))
                    enviados += 1
                    print(f"  enviado a {enmascarar(usuario['email'])}")
                except Exception as e:
                    fallidos += 1
                    print(f"  FALLO con {enmascarar(usuario['email'])}: {e!r}")
    except smtplib.SMTPAuthenticationError:
        print(
            "ERROR de autenticación con Gmail.\n"
            "Revisá que GMAIL_APP_PASSWORD sea una CONTRASEÑA DE APLICACIÓN de 16 "
            "caracteres (no la contraseña normal de la cuenta) y que la cuenta "
            "tenga activada la verificación en dos pasos."
        )
        return 1
    except Exception as e:
        print(f"ERROR de conexión con Gmail: {e!r}")
        return 1

    print(f"\nResumen: {enviados} enviados, {fallidos} fallidos.")
    return 1 if fallidos else 0


if __name__ == "__main__":
    sys.exit(main())
