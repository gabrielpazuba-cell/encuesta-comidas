import flet as ft
import time
import threading
import requests
import unicodedata
import difflib
import os
from datetime import date, datetime, timedelta
from datetime import time as time_cls
from flet.auth.providers import GoogleOAuthProvider


# ==========================================================
# --- CONFIGURACIÓN Y VARIABLES MODIFICABLES ---
# ==========================================================
SUPABASE_BASE_URL = "https://szlifnbfpbzempsrltot.supabase.co/rest/v1"
# "encuesta_comidas" es la tabla propia de esta app. Ojo: en este mismo
# proyecto de Supabase también existe "resultados_encuesta", que pertenece
# a otra app (evaluación cognitiva semanal) y no hay que tocarla.
SUPABASE_URL = f"{SUPABASE_BASE_URL}/encuesta_comidas"
SUPABASE_USUARIOS_URL = f"{SUPABASE_BASE_URL}/usuarios"
SUPABASE_KEY = "sb_publishable_sCVlACuKjCXauLHPUwGT2A_9Jtq7t3y"
HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json"
}

# Login con Google (opcional): a diferencia de la clave de Supabase de
# arriba, esto SÍ es un secreto real, así que no va hardcodeado acá.
# Se configura poniendo estas 3 variables de entorno (en Render, o en tu
# compu si querés probarlo local). Si no están seteadas, el botón de
# "Iniciar sesión con Google" directamente no aparece y la app sigue
# funcionando con el login por mail de siempre.
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REDIRECT_URL = os.environ.get("GOOGLE_REDIRECT_URL", "")  # ej: https://tu-app.onrender.com/oauth_callback

COMIDAS_DEL_DIA = ["Desayuno", "Almuerzo", "Merienda", "Cena"]

# Horario habitual de cada comida: se usa como sugerencia inicial en el
# reloj, pero cada persona lo puede editar libremente antes de confirmar.
HORARIOS_SUGERIDOS = {
    "Desayuno": time_cls(8, 0),
    "Almuerzo": time_cls(13, 0),
    "Merienda": time_cls(17, 0),
    "Cena": time_cls(21, 0),
}

# ==========================================================
# --- CATÁLOGO DE COMIDAS/BEBIDAS Y SUS OPCIONES DE DETALLE ---
# ----------------------------------------------------------
# Para cada comida/bebida típica argentina, 10 formas habituales en que
# se suele acompañar/preparar. Cuando la persona escribe un item que
# coincide (aunque tenga errores de tipeo, mayúsculas distintas o esté
# en plural) con alguno de estos, el desplegable de detalle le muestra
# estas 10 opciones en vez de una lista genérica.
# ==========================================================
CATALOGO_DETALLE = {
    # --- Comidas de almuerzo/cena ---
    "milanesa": [
        "Con puré", "Con papas fritas", "Con arroz", "Con ensalada", "Con fideos",
        "A caballo (con huevo)", "A la napolitana (con salsa y queso)", "Sola, sin acompañamiento",
        "Con verduras salteadas", "Con arroz y huevo frito",
    ],
    "asado": [
        "Con chimichurri", "Con ensalada", "Con papas fritas", "Con pan", "Con puré",
        "Con achuras (chinchulín, morcilla, etc.)", "Con provoleta", "Con salsa criolla",
        "Con verduras a la parrilla", "Solo, sin acompañamiento",
    ],
    "pasta": [
        "Con tuco (salsa de tomate)", "Con salsa blanca", "Con manteca y queso", "Con pesto",
        "Con crema", "Con estofado", "Con salsa boloñesa", "Con salsa rosa",
        "Con aceite y ajo", "Con verduras",
    ],
    "pollo al horno": [
        "Con papas", "Con ensalada", "Con puré", "Con arroz", "Con batatas",
        "Con verduras al horno", "Con limón", "Con curry", "Entero", "En trozos/presas",
    ],
    "guiso": [
        "De lentejas", "De carne", "De mondongo", "De arroz", "De fideos",
        "Con verduras", "Con chorizo", "Con papa", "De calabaza", "De porotos",
    ],
    "pizza": [
        "Muzzarella", "Napolitana", "Fugazzeta", "De jamón y morrón", "Calabresa",
        "Con rúcula", "Cuatro quesos", "Especial", "De anchoas", "Con huevo",
    ],
    "empanadas": [
        "De carne", "De pollo", "De jamón y queso", "De humita", "De verdura",
        "De queso", "Criollas (picantes)", "Árabes", "De atún", "Fritas",
    ],
    "tarta": [
        "De verdura", "De jamón y queso", "De choclo", "De calabaza", "De acelga",
        "De cebolla y queso", "De zapallitos", "Pascualina", "Caprese", "De espinaca",
    ],
    "sandwich de miga": [
        "De jamón y queso", "Triple", "De lomito", "De pollo", "De atún",
        "De vegetales", "Tostado", "Común (sin tostar)", "Con lechuga y tomate", "Integral",
    ],

    # --- Comidas de desayuno/merienda ---
    "tostadas": [
        "Con manteca y mermelada", "Con dulce de leche", "Con queso crema", "Con palta",
        "Con manteca", "Con miel", "Con jamón y queso", "Integrales", "Con huevo", "Francesas",
    ],
    "medialunas": [
        "De manteca", "De grasa", "Rellenas de dulce de leche", "Con jamón y queso",
        "Con mermelada", "Solas", "Tostadas", "Glaseadas", "Integrales", "Con manteca y mermelada",
    ],
    "facturas": [
        "Vigilantes", "Cañoncitos", "Sacramentos", "Bolas de fraile", "Churros",
        "Tortitas negras", "Libritos", "Espirales", "Palmeritas", "Surtidas",
    ],
    "alfajores": [
        "De maicena", "De chocolate", "Triples", "Marplatenses", "De dulce de leche",
        "Con coco", "Glaseados", "Negros", "Blancos", "Artesanales",
    ],
    "torta": [
        "De chocolate", "De manzana", "De zanahoria", "De cumpleaños", "Marmolada",
        "Esponjosa", "Con dulce de leche", "De vainilla", "Con crema", "Con frutas",
    ],

    # --- Bebidas ---
    "cafe con leche": [
        "Con azúcar", "Sin azúcar", "Con edulcorante", "Cortado", "Con medialunas",
        "Con leche entera", "Con leche descremada", "Doble", "Con canela", "Con espuma",
    ],
    "te": [
        "Negro", "Verde", "De manzanilla", "Con leche", "Con limón",
        "Saborizado", "Con azúcar", "Con edulcorante", "De boldo", "Frío",
    ],
    "mate": [
        "Cebado con bombilla", "Dulce", "Amargo", "Con yuyos", "Cocido",
        "Con leche", "Con azúcar", "Con edulcorante", "Con hierbas", "Con jengibre",
    ],
    "jugo de naranja": [
        "Exprimido", "En polvo", "En caja/tetrabrik", "Natural", "Con agua",
        "Sin azúcar", "Con hielo", "De otra fruta", "Mixto", "Light",
    ],
    "chocolatada": [
        "Fría", "Caliente", "Con cacao", "Industrial (de caja)", "Casera",
        "Con menos azúcar", "Con leche entera", "Con leche descremada", "Con hielo", "Batida",
    ],
    "gaseosa": [
        "Cola", "Cola light/zero", "Lima-limón", "Naranja", "Pomelo",
        "Con hielo", "En lata", "En botella", "Sin azúcar", "Saborizada",
    ],
    "agua": [
        "Sin gas", "Con gas", "Saborizada", "Mineral", "De la canilla",
        "Fría", "Con hielo", "Con limón", "En botella", "Natural",
    ],
    "vino": [
        "Tinto", "Blanco", "Rosado", "Con hielo", "Espumante",
        "Dulce", "Seco", "Con soda (vino y soda)", "De la casa", "Malbec",
    ],
    "soda": [
        "Sola", "Con jugo", "Con vino", "Con hielo", "De sifón",
        "Con limón", "Natural", "Con gaseosa", "Fría", "En botella",
    ],
    "cerveza": [
        "Rubia", "Negra", "IPA", "Sin alcohol", "Con limón (shandy)",
        "En lata", "En botella", "Tirada/de barril", "Artesanal", "Helada",
    ],
}

# Sinónimos/variantes frecuentes -> nombre canónico del catálogo de arriba.
# (además del matching difuso, esto resuelve los casos más comunes al toque)
SINONIMOS_DETALLE = {
    "milanesas": "milanesa",
    "milaneza": "milanesa",
    "milanesa de pollo": "milanesa",
    "milanesa de carne": "milanesa",
    "fideos": "pasta",
    "ñoquis": "pasta",
    "ravioles": "pasta",
    "canelones": "pasta",
    "lasagna": "pasta",
    "lasaña": "pasta",
    "pastas": "pasta",
    "pollo": "pollo al horno",
    "pollo horneado": "pollo al horno",
    "estofado": "guiso",
    "guisos": "guiso",
    "empanada": "empanadas",
    "tostada": "tostadas",
    "medialuna": "medialunas",
    "factura": "facturas",
    "alfajor": "alfajores",
    "tortas": "torta",
    "sandwich": "sandwich de miga",
    "sanguche": "sandwich de miga",
    "sanguche de miga": "sandwich de miga",
    "cafe": "cafe con leche",
    "café": "cafe con leche",
    "café con leche": "cafe con leche",
    "te con leche": "te",
    "té": "te",
    "yerba": "mate",
    "mates": "mate",
    "jugo": "jugo de naranja",
    "jugo de fruta": "jugo de naranja",
    "chocolatadas": "chocolatada",
    "leche chocolatada": "chocolatada",
    "gaseosas": "gaseosa",
    "coca cola": "gaseosa",
    "coca": "gaseosa",
    "sprite": "gaseosa",
    "aguas": "agua",
    "cervezas": "cerveza",
    "vinos": "vino",
    "sodas": "soda",
}

# Si el item no coincide con nada del catálogo (ej: algo poco común o muy
# genérico), se le muestran estas opciones en vez de dejar el desplegable vacío.
OPCIONES_GENERICAS = [
    "Solo/a, sin acompañamiento", "Con pan", "Con ensalada", "Con guarnición",
    "Con salsa", "Frío/a", "Caliente", "Porción chica", "Porción grande", "Otro",
]


def _normalizar_texto(texto):
    """minúsculas, sin tildes, sin espacios de más (para poder comparar)."""
    texto = (texto or "").strip().lower()
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    return " ".join(texto.split())


def _sin_plural(texto):
    # Achica "milanesas" -> "milanesa", "facturas" -> "factura", para que el
    # match funcione aunque la persona haya escrito en plural.
    if texto.endswith("es") and len(texto) > 4:
        return texto[:-2]
    if texto.endswith("s") and len(texto) > 3:
        return texto[:-1]
    return texto


_CLAVES_NORMALIZADAS = {_normalizar_texto(clave): clave for clave in CATALOGO_DETALLE}
_SINONIMOS_NORMALIZADOS = {_normalizar_texto(k): v for k, v in SINONIMOS_DETALLE.items()}


def opciones_para_item(nombre_item):
    # Tolera mayúsculas/tildes distintas, plurales y errores de tipeo
    # comunes (ej: "milnesas", "Milanesa", "Milanesas" dan lo mismo).
    normalizado = _normalizar_texto(nombre_item)
    if not normalizado:
        return OPCIONES_GENERICAS

    candidatos = [normalizado, _sin_plural(normalizado)]

    # 1) Coincidencia exacta (con o sin plural) contra claves o sinónimos
    for candidato in candidatos:
        if candidato in _CLAVES_NORMALIZADAS:
            return CATALOGO_DETALLE[_CLAVES_NORMALIZADAS[candidato]]
        if candidato in _SINONIMOS_NORMALIZADOS:
            return CATALOGO_DETALLE[_SINONIMOS_NORMALIZADOS[candidato]]

    # 2) Coincidencia difusa (tolera errores de tipeo) contra claves y sinónimos
    universo = {**_CLAVES_NORMALIZADAS, **_SINONIMOS_NORMALIZADOS}
    for candidato in candidatos:
        parecidos = difflib.get_close_matches(candidato, universo.keys(), n=1, cutoff=0.72)
        if parecidos:
            return CATALOGO_DETALLE[universo[parecidos[0]]]

    return OPCIONES_GENERICAS

# ==========================================================
# --- IMÁGENES ---
# Poné acá los nombres de tus archivos PNG. Todos tienen que estar
# dentro de una carpeta llamada "assets" (al lado de este archivo).
# Si todavía NO tenés la imagen, dejá el valor en None y la app igual funciona.
# ==========================================================
FONDO = None                # Ej: "fondo.png"  -> fondo de todas las pantallas
IMAGEN_PLATO = None          # Ej: "plato.png" (archivo dentro de assets/). Mientras esté en None, se usa un ícono de relleno.


def main(page: ft.Page):
    page.title = "Registro Diario de Comidas"
    # El tamaño de ventana fijo solo tiene sentido en escritorio. En celular
    # (o en el navegador) la app tiene que ocupar la pantalla real del
    # dispositivo, no un recuadro de 400x750.
    if page.platform in (ft.PagePlatform.WINDOWS, ft.PagePlatform.MACOS, ft.PagePlatform.LINUX):
        page.window.width = 400
        page.window.height = 750
    page.vertical_alignment = ft.MainAxisAlignment.CENTER
    page.horizontal_alignment = ft.CrossAxisAlignment.CENTER
    page.theme_mode = ft.ThemeMode.LIGHT
    page.padding = 0

    # Ancho responsivo para inputs/botones: usa 300px como diseño base,
    # pero nunca más ancho que la pantalla disponible (con margen para el
    # padding/margin de la tarjeta), y nunca menos de 220px.
    def ancho_campo(base=300):
        disponible = (page.width or (base + 70)) - 70
        return max(220, min(base, disponible))

    # --- ESTADO DE LA APLICACIÓN ---
    estado = {
        "email": "",
        "usuario_id": None,
        "modo_local": False,              # True cuando se entra con el acceso piloto (no toca Supabase)
        "sesiones_historicas": 0,
        "ultima_fecha_completado": None,  # "YYYY-MM-DD" o None
        "_dashboard_token": None,         # controla el hilo de la cuenta regresiva

        "indice_comida": 0,
        "hora_ingresada": "",

        "items_temporales": [],
        "indice_item_actual": 0,

        "datos_finales": []
    }

    # ==========================================================
    # SISTEMA DE NAVEGACIÓN (para el botón "volver atrás")
    # ----------------------------------------------------------
    # historial: va guardando las pantallas por las que pasaste.
    # ir_a(pantalla): avanza a una pantalla nueva y la guarda en el historial.
    # volver(): retrocede a la pantalla anterior.
    # ==========================================================
    historial = []

    # Al rotar el celular o cambiar el tamaño de la ventana, volvemos a
    # dibujar la pantalla actual para que los anchos responsivos se recalculen.
    # OJO: en celular, cuando aparece/desaparece el teclado también se
    # dispara on_resize (cambia el alto, no el ancho). Si redibujáramos la
    # pantalla entera en ese momento, se perdía lo que la persona estaba
    # escribiendo y a veces los botones quedaban sin responder. Por eso acá
    # solo redibujamos si el ANCHO cambió de verdad (rotación de pantalla),
    # ignorando los cambios de alto por el teclado.
    _ultimo_ancho = {"valor": None}

    def _al_cambiar_tamano(e):
        ancho_actual = page.width
        ancho_previo = _ultimo_ancho["valor"]
        _ultimo_ancho["valor"] = ancho_actual
        if historial and ancho_previo is not None and ancho_actual is not None and abs(ancho_actual - ancho_previo) > 20:
            historial[-1]()

    page.on_resize = _al_cambiar_tamano

    def ir_a(pantalla_funcion):
        estado["_dashboard_token"] = None  # corta cualquier cuenta regresiva del dashboard anterior
        historial.append(pantalla_funcion)
        pantalla_funcion()

    def volver(e=None):
        if len(historial) > 1:
            estado["_dashboard_token"] = None
            historial.pop()          # saca la pantalla actual
            historial[-1]()          # dibuja la anterior

    # ==========================================================
    # DIBUJANTE DE PANTALLAS
    # ----------------------------------------------------------
    # Esta función arma cada pantalla: agrega el fondo, la "tarjeta"
    # blanca con el contenido y el botón de volver arriba a la izquierda.
    # Todas las pantallas la usan, así el diseño queda unificado.
    # ==========================================================
    def pantalla(*controles, mostrar_volver=True, overlays=None):
        page.controls.clear()
        page.overlay.clear()
        if overlays:
            page.overlay.extend(overlays)

        filas = []
        # Botón de volver (solo si hay una pantalla anterior a la que ir)
        if mostrar_volver and len(historial) > 1:
            filas.append(
                ft.Row(
                    [
                        ft.IconButton(
                            icon=ft.Icons.ARROW_BACK,
                            tooltip="Volver",
                            on_click=volver,
                            icon_color=ft.Colors.WHITE,
                            bgcolor=ft.Colors.BLUE_400,
                        )
                    ],
                    alignment=ft.MainAxisAlignment.START
                )
            )
        filas.extend(controles)

        columna = ft.Column(
            filas,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=15,
            scroll=ft.ScrollMode.AUTO,
            expand=True,
        )

        tarjeta = ft.Container(
            content=columna,
            padding=20,
            margin=15,
            border_radius=20,
            bgcolor=ft.Colors.with_opacity(0.92, ft.Colors.WHITE),  # blanco semitransparente
            expand=True,
        )

        if FONDO:
            # Fondo con imagen: la imagen ocupa toda la pantalla y la tarjeta va encima
            fondo = ft.Stack(
                [
                    ft.Image(src=FONDO, fit=ft.BoxFit.COVER, expand=True),
                    ft.Container(content=tarjeta, alignment=ft.Alignment.CENTER, expand=True),
                ],
                expand=True,
            )
            page.add(fondo)
        else:
            # Sin imagen de fondo: solo la tarjeta
            page.add(ft.Container(content=tarjeta, alignment=ft.Alignment.CENTER, expand=True))

        page.update()

    # ==========================================================
    # PANTALLA 1: LOGIN / REGISTRO POR EMAIL
    # ----------------------------------------------------------
    # Cada usuario se identifica con su mail. Si el mail no existe
    # todavía en Supabase se crea un registro nuevo (alta automática);
    # si ya existe, se recupera su histórico y su estado del día.
    # ==========================================================
    def buscar_o_crear_usuario(email):
        try:
            resp = requests.get(
                SUPABASE_USUARIOS_URL,
                headers=HEADERS,
                params={"email": f"eq.{email}", "select": "*"},
                timeout=10,
            )
            if not resp.ok:
                print(f"Error Supabase GET usuarios [{resp.status_code}]: {resp.text}")
                return None
            resultados = resp.json()
            if resultados:
                return resultados[0]

            resp = requests.post(
                SUPABASE_USUARIOS_URL,
                headers={**HEADERS, "Prefer": "return=representation"},
                json={"email": email},
                timeout=10,
            )
            if not resp.ok:
                print(f"Error Supabase POST usuarios [{resp.status_code}]: {resp.text}")
                return None
            creados = resp.json()
            return creados[0] if creados else None
        except Exception as e:
            print("Error de red (usuarios):", repr(e))
            return None

    # Acceso rápido para la prueba piloto: se salta la validación de mail
    # y entra directo con un usuario fijo. Sacar esto cuando termine el piloto.
    PILOTO_USUARIO = "gaby"
    PILOTO_CONTRASENA = "taekwondo"
    PILOTO_EMAIL = "gaby.piloto@test.local"

    def entrar_con_usuario(usuario, local=False):
        estado["email"] = usuario["email"]
        estado["usuario_id"] = usuario["id"]
        estado["sesiones_historicas"] = usuario.get("sesiones_historicas") or 0
        estado["ultima_fecha_completado"] = usuario.get("ultima_fecha_completado")
        estado["modo_local"] = local
        ir_a(mostrar_dashboard)

    # Login con Google: se configura solo si están las 3 variables de
    # entorno (ver arriba). El resultado llega de forma asíncrona al
    # evento page.on_login, no al click del botón.
    google_provider = None
    if GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET and GOOGLE_REDIRECT_URL:
        google_provider = GoogleOAuthProvider(
            client_id=GOOGLE_CLIENT_ID,
            client_secret=GOOGLE_CLIENT_SECRET,
            redirect_url=GOOGLE_REDIRECT_URL,
        )

    def _al_iniciar_sesion_google(e):
        if e.error:
            print("Error de login con Google:", e.error, e.error_description)
            return
        email_google = (page.auth.user.get("email") or "").strip().lower()
        if not email_google:
            return
        usuario = buscar_o_crear_usuario(email_google)
        if usuario:
            entrar_con_usuario(usuario, local=False)

    page.on_login = _al_iniciar_sesion_google

    def mostrar_login():
        async def iniciar_con_google(e):
            await page.login(google_provider)

        def iniciar_sesion(e):
            valor = (input_email.value or "").strip()
            contrasena = input_contrasena.value or ""

            es_piloto = valor.lower() == PILOTO_USUARIO and contrasena == PILOTO_CONTRASENA

            if es_piloto:
                # Modo local: no toca Supabase para nada, usa datos en memoria.
                usuario_local = {
                    "email": PILOTO_EMAIL,
                    "id": "local-piloto",
                    "sesiones_historicas": estado.get("sesiones_historicas", 0),
                    "ultima_fecha_completado": estado.get("ultima_fecha_completado"),
                }
                entrar_con_usuario(usuario_local, local=True)
                return

            email = valor.lower()
            if "@" not in email or "." not in email.split("@")[-1]:
                input_email.error_text = "Ingresá un email válido"
                page.update()
                return

            input_email.error_text = None
            texto_error.value = ""
            boton_ingresar.disabled = True
            boton_ingresar.text = "Ingresando..."
            page.update()

            usuario = buscar_o_crear_usuario(email)

            boton_ingresar.disabled = False
            boton_ingresar.text = "Ingresar"

            if usuario is None:
                texto_error.value = "No pudimos conectar. Revisá tu conexión e intentá de nuevo."
                page.update()
                return

            entrar_con_usuario(usuario, local=False)

        input_email = ft.TextField(label="Email", width=ancho_campo(), keyboard_type=ft.KeyboardType.EMAIL)
        input_contrasena = ft.TextField(label="Contraseña (solo piloto)", width=ancho_campo(), password=True, can_reveal_password=True)
        texto_error = ft.Text("", color=ft.Colors.RED)
        boton_ingresar = ft.ElevatedButton("Ingresar", on_click=iniciar_sesion, width=ancho_campo(), height=50)

        controles = [ft.Text("Bienvenido", size=30, weight=ft.FontWeight.BOLD)]

        if google_provider:
            controles.append(
                ft.ElevatedButton(
                    "Iniciar sesión con Google",
                    icon=ft.Icons.LOGIN,
                    on_click=iniciar_con_google,
                    width=ancho_campo(),
                    height=50,
                )
            )
            controles.append(ft.Text("— o —", color=ft.Colors.GREY_500))

        controles.extend([input_email, input_contrasena, texto_error, boton_ingresar])

        pantalla(*controles)

    # ==========================================================
    # PANTALLA 2: INICIO / DASHBOARD
    # ----------------------------------------------------------
    # La encuesta de hoy queda inhabilitada una vez completada, y
    # recién vuelve a habilitarse a la medianoche. Mientras tanto se
    # muestra un tilde verde y una cuenta regresiva en vivo.
    # ==========================================================
    def esta_habilitado_hoy():
        if estado["modo_local"]:
            # Acceso piloto: siempre habilitada, para poder probar el flujo
            # completo las veces que haga falta sin esperar al día siguiente.
            return True
        return estado["ultima_fecha_completado"] != date.today().isoformat()

    def tiempo_restante_texto():
        ahora = datetime.now()
        medianoche = datetime.combine(date.today() + timedelta(days=1), datetime.min.time())
        segundos = max(0, int((medianoche - ahora).total_seconds()))
        horas, resto = divmod(segundos, 3600)
        minutos, segundos = divmod(resto, 60)
        return f"{horas:02d}:{minutos:02d}:{segundos:02d}"

    def iniciar_countdown(texto_control, token):
        def loop():
            while estado.get("_dashboard_token") is token:
                time.sleep(1)
                if estado.get("_dashboard_token") is not token:
                    return
                if not esta_habilitado_hoy():
                    texto_control.value = tiempo_restante_texto()
                    try:
                        page.update()
                    except Exception:
                        return
                else:
                    # Cruzamos la medianoche: se volvió a habilitar, refrescamos el dashboard.
                    ir_a(mostrar_dashboard)
                    return

        threading.Thread(target=loop, daemon=True).start()

    def mostrar_dashboard():
        estado["indice_comida"] = 0
        estado["datos_finales"] = []

        habilitado = esta_habilitado_hoy()

        if habilitado:
            columna_hoy = ft.Column(
                [ft.Text("Hoy", weight=ft.FontWeight.BOLD), ft.Text("Disponible", size=16, color=ft.Colors.BLUE)],
                alignment=ft.MainAxisAlignment.CENTER,
            )
        else:
            texto_countdown = ft.Text(tiempo_restante_texto(), size=14, color=ft.Colors.GREY_700)
            columna_hoy = ft.Column(
                [
                    ft.Text("Hoy", weight=ft.FontWeight.BOLD),
                    ft.Icon(ft.Icons.CHECK_CIRCLE, color=ft.Colors.GREEN, size=28),
                    texto_countdown,
                ],
                alignment=ft.MainAxisAlignment.CENTER,
            )

        tarjeta_stats = ft.Card(
            content=ft.Container(
                padding=20,
                content=ft.Row(
                    controls=[
                        ft.Column([ft.Text("Histórico", weight=ft.FontWeight.BOLD), ft.Text(str(estado["sesiones_historicas"]), size=24)], alignment=ft.MainAxisAlignment.CENTER),
                        ft.Container(width=2, height=50, bgcolor=ft.Colors.GREY_300),
                        columna_hoy,
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_EVENLY
                )
            ),
            width=ancho_campo()
        )

        boton_comenzar = ft.ElevatedButton(
            "Registrar últimas 24 horas" if habilitado else "Ya completaste el registro de hoy",
            on_click=(lambda _: ir_a(mostrar_instrucciones)) if habilitado else None,
            disabled=not habilitado,
            width=ancho_campo(),
            height=50,
        )

        boton_resumen = ft.OutlinedButton(
            "Resumen",
            on_click=lambda _: ir_a(mostrar_resumen_historia),
            width=ancho_campo(),
            height=50,
        )

        pantalla(
            ft.Text(f"Hola, {estado['email']}!", size=24, weight=ft.FontWeight.BOLD),
            tarjeta_stats,
            ft.Divider(height=20, color=ft.Colors.TRANSPARENT),
            boton_comenzar,
            boton_resumen,
        )

        if not habilitado:
            token = object()
            estado["_dashboard_token"] = token
            iniciar_countdown(texto_countdown, token)

    # ==========================================================
    # PANTALLA: RESUMEN
    # ----------------------------------------------------------
    # Trae de Supabase todas las respuestas de este usuario y arma un
    # resumen agrupado por día (más reciente primero), mostrando qué
    # comió/bebió (o "no tuvo") en cada comida de cada día.
    # ==========================================================
    def obtener_registros_usuario(email):
        try:
            resp = requests.get(
                SUPABASE_URL,
                headers=HEADERS,
                params={"usuario": f"eq.{email}", "select": "*", "order": "fecha.desc"},
                timeout=10,
            )
            if not resp.ok:
                print(f"Error Supabase GET encuesta_comidas [{resp.status_code}]: {resp.text}")
                return None
            return resp.json()
        except Exception as e:
            print("Error de red (resumen):", repr(e))
            return None

    def mostrar_resumen_historia():
        pantalla(ft.ProgressRing(), ft.Text("Cargando resumen...", size=18, color=ft.Colors.BLUE), mostrar_volver=False)

        if estado["modo_local"]:
            pantalla(
                ft.Icon(ft.Icons.AUTO_STORIES, size=50, color=ft.Colors.BLUE_GREY),
                ft.Text("Resumen", size=22, weight=ft.FontWeight.BOLD, text_align=ft.TextAlign.CENTER),
                ft.Text(
                    "El acceso piloto no guarda historial en la base de datos. "
                    "Iniciá sesión con tu email para ver tu resumen real.",
                    text_align=ft.TextAlign.CENTER,
                ),
            )
            return

        registros = obtener_registros_usuario(estado["email"])

        if registros is None:
            pantalla(
                ft.Icon(ft.Icons.ERROR_OUTLINE, size=50, color=ft.Colors.RED),
                ft.Text("No pudimos cargar tu resumen. Revisá tu conexión e intentá de nuevo.", text_align=ft.TextAlign.CENTER),
            )
            return

        if not registros:
            pantalla(
                ft.Icon(ft.Icons.AUTO_STORIES, size=50, color=ft.Colors.BLUE_GREY),
                ft.Text("Todavía no completaste ninguna encuesta.", text_align=ft.TextAlign.CENTER),
            )
            return

        # Agrupamos las respuestas por día y, dentro de cada día, por comida.
        por_dia = {}
        for r in registros:
            dia = (r.get("fecha") or "")[:10]
            por_dia.setdefault(dia, {}).setdefault(r.get("momento_dia") or "", []).append(r)

        tarjetas = []
        for dia in sorted(por_dia.keys(), reverse=True):
            filas_dia = []
            for comida in COMIDAS_DEL_DIA:
                regs_comida = por_dia[dia].get(comida)
                if not regs_comida:
                    continue

                items = [r for r in regs_comida if r.get("tipo_registro") == "item"]
                sin_comida = any(
                    r.get("tipo_registro") == "comida_hora" and r.get("tuvo_comida") is False
                    for r in regs_comida
                )

                if items:
                    detalle = ", ".join(
                        f"{it.get('item_nombre')} ({it.get('item_detalle')}, {it.get('item_tamano')})"
                        for it in items
                    )
                    filas_dia.append(ft.Text(f"• {comida}: {detalle}"))
                elif sin_comida:
                    filas_dia.append(ft.Text(f"• {comida}: no tuvo"))

            if filas_dia:
                tarjetas.append(
                    ft.Card(
                        content=ft.Container(
                            padding=15,
                            content=ft.Column([ft.Text(dia, weight=ft.FontWeight.BOLD, size=16)] + filas_dia, spacing=5),
                        ),
                        width=ancho_campo(340),
                    )
                )

        pantalla(
            ft.Text("Resumen", size=22, weight=ft.FontWeight.BOLD, text_align=ft.TextAlign.CENTER),
            *tarjetas,
        )

    # ==========================================================
    # PANTALLA 3: INSTRUCCIONES Y VIDEO
    # ==========================================================
    def mostrar_instrucciones():
        texto_instrucciones = ft.Text(
            "Instrucciones:\nA continuación te haremos algunas preguntas sobre todo lo que consumiste en las últimas 24 horas. Por favor, mirá este video antes de comenzar.",
            text_align=ft.TextAlign.CENTER
        )

        caja_video = ft.Container(
            content=ft.Column(
                controls=[
                    ft.Row(
                        controls=[ft.Icon(ft.Icons.PLAY_CIRCLE_FILL, size=50, color=ft.Colors.WHITE)],
                        alignment=ft.MainAxisAlignment.CENTER
                    )
                ],
                alignment=ft.MainAxisAlignment.CENTER
            ),
            width=ancho_campo(), height=170, bgcolor=ft.Colors.BLACK87, border_radius=10
        )

        boton_comenzar = ft.ElevatedButton("Comenzar", on_click=lambda _: ir_a(mostrar_pregunta_hora), width=ancho_campo(), height=50)

        pantalla(texto_instrucciones, caja_video, ft.Divider(color=ft.Colors.TRANSPARENT), boton_comenzar)

    # ==========================================================
    # PANTALLA 4: HORA DE LA COMIDA
    # ==========================================================
    def avanzar_comida():
        estado["indice_comida"] += 1
        if estado["indice_comida"] < len(COMIDAS_DEL_DIA):
            ir_a(mostrar_pregunta_hora)
        else:
            ir_a(enviar_datos_y_mostrar_agradecimiento)

    def mostrar_pregunta_hora():
        estado["items_temporales"] = []
        comida_actual = COMIDAS_DEL_DIA[estado["indice_comida"]]
        inicio_pregunta = time.monotonic()

        titulo = ft.Text(f"En las últimas 24 horas, ¿tuviste {comida_actual.lower()}?\nSi tuviste, ¿a qué hora fue?", size=20, weight=ft.FontWeight.BOLD, text_align=ft.TextAlign.CENTER)

        # Sugerimos el horario habitual de esta comida, pero queda 100%
        # editable: basta con tocar el campo y elegir otra hora en el reloj.
        hora_sugerida = HORARIOS_SUGERIDOS.get(comida_actual)
        hora_sugerida_texto = hora_sugerida.strftime("%H:%M") if hora_sugerida else ""
        estado["hora_ingresada"] = hora_sugerida_texto

        input_hora = ft.TextField(
            label="Tocar para elegir hora",
            value=hora_sugerida_texto,
            read_only=True,
            width=ancho_campo(200),
            text_align=ft.TextAlign.CENTER,
        )

        def cambio_hora(e):
            input_hora.value = e.control.value.strftime("%H:%M")
            estado["hora_ingresada"] = input_hora.value
            page.update()

        reloj = ft.TimePicker(value=hora_sugerida, confirm_text="Aceptar", cancel_text="Cancelar", on_change=cambio_hora)

        def abrir_reloj(e):
            reloj.open = True
            page.update()

        input_hora.on_click = abrir_reloj

        # Registra la respuesta a "¿tuviste esta comida?" (incluido el "No tuve"),
        # con el tiempo que tardó en responder y la hora local de la respuesta.
        def registrar_respuesta_hora(tuvo, hora_consumo):
            clave = (estado["indice_comida"], "hora")
            registro = {
                "usuario": estado["email"],
                "fecha": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "momento_dia": comida_actual,
                "hora_consumo": hora_consumo,
                "item_nombre": None,
                "item_categoria": None,
                "item_detalle": None,
                "item_tamano": None,
                "tipo_registro": "comida_hora",
                "tuvo_comida": tuvo,
                "tiempo_respuesta_seg": round(time.monotonic() - inicio_pregunta, 1),
                "_clave": clave,
            }
            estado["datos_finales"] = [r for r in estado["datos_finales"] if r.get("_clave") != clave]
            estado["datos_finales"].append(registro)

        def no_tuve_click(e):
            registrar_respuesta_hora(False, None)
            avanzar_comida()

        boton_no_tuve = ft.OutlinedButton("No tuve", on_click=no_tuve_click, width=ancho_campo())

        def confirmar_hora(e):
            if input_hora.value:
                registrar_respuesta_hora(True, input_hora.value)
                ir_a(mostrar_ingreso_items)
            else:
                input_hora.error_text = "Elegí una hora"
                page.update()

        boton_cerca_horario = ft.ElevatedButton("Cerca de ese horario", on_click=confirmar_hora, width=ancho_campo())

        pantalla(
            titulo,
            input_hora,
            ft.Divider(height=20, color=ft.Colors.TRANSPARENT),
            boton_no_tuve,
            boton_cerca_horario,
            overlays=[reloj],
        )

    # ==========================================================
    # PANTALLA 5: INGRESO DE COMIDAS Y BEBIDAS
    # ==========================================================
    def mostrar_ingreso_items():
        comida_actual = COMIDAS_DEL_DIA[estado["indice_comida"]]
        hora = estado["hora_ingresada"]

        titulo = ft.Text(f"Decinos todo lo que tuviste para el {comida_actual.lower()} ({hora}).", size=18, weight=ft.FontWeight.BOLD, text_align=ft.TextAlign.CENTER)

        lista_ui = ft.Column()

        def actualizar_lista_ui():
            lista_ui.controls.clear()
            for i, item in enumerate(estado["items_temporales"]):
                icono = "🍔" if item["categoria"] == "Comida" else "🥤"
                lista_ui.controls.append(
                    ft.Row([
                        ft.Text(f"{icono} {item['nombre']}", expand=True),
                        ft.IconButton(ft.Icons.DELETE, on_click=lambda e, idx=i: eliminar_item(idx), icon_color=ft.Colors.RED)
                    ])
                )
            page.update()

        def eliminar_item(index):
            estado["items_temporales"].pop(index)
            actualizar_lista_ui()

        def agregar_comida(e):
            if input_comida.value.strip():
                estado["items_temporales"].append({"nombre": input_comida.value.strip(), "categoria": "Comida"})
                input_comida.value = ""
                actualizar_lista_ui()

        def agregar_bebida(e):
            if input_bebida.value.strip():
                estado["items_temporales"].append({"nombre": input_bebida.value.strip(), "categoria": "Bebida"})
                input_bebida.value = ""
                actualizar_lista_ui()

        # Además de apretar Enter, dejamos un botón "Agregar" explícito: en
        # varios celulares el teclado virtual no dispara el Enter/submit de
        # forma confiable, y sin botón la lista de abajo parecía no actualizarse.
        input_comida = ft.TextField(label="Escribí una comida", on_submit=agregar_comida, width=ancho_campo(220), expand=True)
        input_bebida = ft.TextField(label="Escribí una bebida", on_submit=agregar_bebida, width=ancho_campo(220), expand=True)

        def continuar(e):
            if len(estado["items_temporales"]) > 0:
                estado["indice_item_actual"] = 0
                ir_a(mostrar_detalle_item)
            else:
                avanzar_comida()

        boton_continuar = ft.ElevatedButton("Continuar", on_click=continuar, width=ancho_campo(), height=50)

        pantalla(
            titulo,
            ft.Text("Comida", weight=ft.FontWeight.BOLD),
            ft.Row([input_comida, ft.IconButton(icon=ft.Icons.ADD_CIRCLE, icon_color=ft.Colors.BLUE, tooltip="Agregar", on_click=agregar_comida)], width=ancho_campo()),
            ft.Text("Bebida", weight=ft.FontWeight.BOLD),
            ft.Row([input_bebida, ft.IconButton(icon=ft.Icons.ADD_CIRCLE, icon_color=ft.Colors.BLUE, tooltip="Agregar", on_click=agregar_bebida)], width=ancho_campo()),
            ft.Divider(),
            lista_ui,
            ft.Divider(color=ft.Colors.TRANSPARENT),
            boton_continuar,
        )

    # ==========================================================
    # PANTALLA 6: DETALLE DEL ITEM (DROPDOWN)
    # ==========================================================
    def mostrar_detalle_item():
        # Guarda de seguridad: si por algún motivo no hay items cargados,
        # volvemos a preguntar la hora de esta comida.
        if not estado["items_temporales"] or estado["indice_item_actual"] >= len(estado["items_temporales"]):
            mostrar_pregunta_hora()
            return

        item_actual = estado["items_temporales"][estado["indice_item_actual"]]
        if "_t_inicio" not in item_actual:
            item_actual["_t_inicio"] = time.monotonic()

        titulo = ft.Text(f"Detalle para: {item_actual['nombre']}", size=20, weight=ft.FontWeight.BOLD)

        opciones_detalle = opciones_para_item(item_actual["nombre"])

        dropdown = ft.Dropdown(
            label="Seleccioná la opción más adecuada",
            options=[ft.dropdown.Option(opt) for opt in opciones_detalle],
            value=item_actual.get("detalle"),   # recuerda lo elegido si volvés
            width=ancho_campo()
        )

        def guardar_detalle(e):
            if dropdown.value:
                item_actual["detalle"] = dropdown.value
                ir_a(mostrar_tamano_item)
            else:
                dropdown.error_text = "Seleccioná una opción"
                page.update()

        boton_continuar = ft.ElevatedButton("Siguiente", on_click=guardar_detalle, width=ancho_campo())

        pantalla(titulo, dropdown, boton_continuar)

    # ==========================================================
    # PANTALLA 7: TAMAÑO DEL PLATO
    # ==========================================================
    def mostrar_tamano_item():
        # Guarda de seguridad
        if not estado["items_temporales"] or estado["indice_item_actual"] >= len(estado["items_temporales"]):
            mostrar_pregunta_hora()
            return

        item_actual = estado["items_temporales"][estado["indice_item_actual"]]
        comida_del_dia = COMIDAS_DEL_DIA[estado["indice_comida"]]

        titulo = ft.Text(f"Tamaño de: {item_actual['nombre']}", size=20, weight=ft.FontWeight.BOLD)

        # Mapeo: valor del slider -> (Tamaño de la imagen, Nombre del texto)
        configuraciones = {
            0: (80, "Muy pequeño"),
            1: (130, "Pequeño"),
            2: (180, "Mediano"),
            3: (230, "Grande"),
            4: (280, "Muy grande")
        }

        # Área fija donde se dibuja el plato: su tamaño nunca cambia, así el
        # resto de la pantalla (título, texto, slider, botón) queda quieto.
        # Adentro va la imagen real si ya la configuraste en IMAGEN_PLATO, o
        # si no, un ícono de relleno que igual cambia de tamaño con el slider.
        AREA_DIBUJO = ancho_campo(280)

        if IMAGEN_PLATO:
            dibujo = ft.Image(src=IMAGEN_PLATO, width=180, height=180, fit=ft.BoxFit.CONTAIN)
        else:
            dibujo = ft.Icon(ft.Icons.RESTAURANT, size=180, color=ft.Colors.GREY_400)

        contenedor_dibujo = ft.Container(
            content=dibujo,
            width=AREA_DIBUJO,
            height=AREA_DIBUJO,
            alignment=ft.Alignment.CENTER,
        )

        texto_label = ft.Text("Mediano", size=16, weight=ft.FontWeight.BOLD)

        def slider_cambiado(e):
            idx = int(e.control.value)
            nuevo_tamano, nuevo_nombre = configuraciones[idx]
            if isinstance(dibujo, ft.Image):
                dibujo.width = nuevo_tamano
                dibujo.height = nuevo_tamano
            else:
                dibujo.size = nuevo_tamano
            texto_label.value = nuevo_nombre
            page.update()

        slider = ft.Slider(min=0, max=4, divisions=4, value=2, on_change=slider_cambiado)

        def guardar_tamano_y_avanzar(e):
            # Clave única para este item (comida + número de item).
            # Sirve para que, si volvés atrás y lo guardás de nuevo,
            # se reemplace el dato en vez de duplicarse.
            clave = (estado["indice_comida"], estado["indice_item_actual"])

            registro_final = {
                "usuario": estado["email"],
                "fecha": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "momento_dia": comida_del_dia,
                "hora_consumo": estado["hora_ingresada"],
                "item_nombre": item_actual["nombre"],
                "item_categoria": item_actual["categoria"],
                "item_detalle": item_actual["detalle"],
                "item_tamano": texto_label.value,
                "tipo_registro": "item",
                "tuvo_comida": True,
                "tiempo_respuesta_seg": round(time.monotonic() - item_actual.get("_t_inicio", time.monotonic()), 1),
                "_clave": clave,   # campo interno, se borra antes de enviar a Supabase
            }

            # Sacamos cualquier registro anterior con la misma clave y agregamos el nuevo
            estado["datos_finales"] = [r for r in estado["datos_finales"] if r.get("_clave") != clave]
            estado["datos_finales"].append(registro_final)

            estado["indice_item_actual"] += 1
            if estado["indice_item_actual"] < len(estado["items_temporales"]):
                ir_a(mostrar_detalle_item)
            else:
                avanzar_comida()

        boton_continuar = ft.ElevatedButton("Guardar", on_click=guardar_tamano_y_avanzar, width=ancho_campo())

        pantalla(titulo, contenedor_dibujo, texto_label, slider, boton_continuar)

    # ==========================================================
    # PANTALLA 8: ENVÍO A NUBE Y AGRADECIMIENTO
    # ==========================================================
    def marcar_usuario_completado_hoy():
        hoy = date.today().isoformat()
        nuevo_historico = estado["sesiones_historicas"] + 1

        if not estado["modo_local"]:
            try:
                resp = requests.patch(
                    f"{SUPABASE_USUARIOS_URL}?id=eq.{estado['usuario_id']}",
                    headers=HEADERS,
                    json={"sesiones_historicas": nuevo_historico, "ultima_fecha_completado": hoy},
                )
                resp.raise_for_status()
            except Exception as e:
                print("Error de red (actualizar usuario):", e)

        # Reflejamos el cambio localmente aunque el PATCH falle (o en modo
        # local directamente no haya PATCH), para no dejar la encuesta
        # habilitada de nuevo por un error de red pasajero.
        estado["sesiones_historicas"] = nuevo_historico
        estado["ultima_fecha_completado"] = hoy

    def enviar_datos_y_mostrar_agradecimiento():
        pantalla(ft.ProgressRing(), ft.Text("Subiendo datos...", size=20, color=ft.Colors.BLUE), mostrar_volver=False)

        exito = False
        if estado["modo_local"]:
            # Modo piloto local: no se manda nada a Supabase, se simula éxito.
            exito = True
        elif len(estado["datos_finales"]) > 0:
            # Sacamos el campo interno "_clave" antes de mandar a Supabase
            datos_a_enviar = [{k: v for k, v in r.items() if k != "_clave"} for r in estado["datos_finales"]]
            try:
                respuesta = requests.post(SUPABASE_URL, headers=HEADERS, json=datos_a_enviar)
                if respuesta.status_code == 201:
                    exito = True
            except Exception as e:
                print("Error de red:", e)
        else:
            exito = True

        if exito:
            marcar_usuario_completado_hoy()

        # Vaciamos el historial: al terminar, "volver" no debería revivir la encuesta
        historial.clear()

        if exito:
            pantalla(
                ft.Icon(ft.Icons.CHECK_CIRCLE, color=ft.Colors.GREEN, size=60),
                ft.Text("¡Muchas gracias!", size=24, weight=ft.FontWeight.BOLD),
                ft.Text("Volviendo al inicio...", size=14, color=ft.Colors.GREY_700),
                mostrar_volver=False,
            )

            def volver_a_inicio_luego():
                time.sleep(1.5)
                ir_a(mostrar_dashboard)

            threading.Thread(target=volver_a_inicio_luego, daemon=True).start()
        else:
            mensaje_error = ft.Text("Hubo un error al guardar los datos. Revisá tu conexión.", color=ft.Colors.RED)
            boton_volver_inicio = ft.ElevatedButton("Volver al Inicio", on_click=lambda _: ir_a(mostrar_dashboard))
            pantalla(mensaje_error, boton_volver_inicio, mostrar_volver=False)

    # Arranque de la app
    ir_a(mostrar_login)


# ==========================================================
# --- ARRANQUE ---
# ----------------------------------------------------------
# Local (tu compu): "python app.py" abre la ventana de escritorio, como
# siempre.
# Producción (Render): se define la variable de entorno FLET_WEB=1, y en
# ese caso este archivo expone "app" (una app ASGI) para que la sirva
# uvicorn con el comando: uvicorn app:app --host 0.0.0.0 --port $PORT
# ==========================================================
if os.environ.get("FLET_WEB", "").lower() in ("1", "true", "yes"):
    app = ft.app(target=main, assets_dir="assets", export_asgi_app=True)
else:
    ft.app(target=main, assets_dir="assets")