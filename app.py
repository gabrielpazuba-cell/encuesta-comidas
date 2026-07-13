import flet as ft
import time
import threading
import requests
import unicodedata
import difflib
import os
import hashlib
from datetime import datetime, timedelta, timezone
from datetime import time as time_cls
from flet.auth.providers import GoogleOAuthProvider

# La habilitación diaria de la encuesta (y la hora que se guarda en cada
# respuesta) tiene que basarse siempre en el horario de Argentina, sin
# importar en qué huso horario esté corriendo el servidor (Render corre en
# UTC). Argentina no cambia de horario en el año (UTC-3 fijo), así que
# alcanza con este offset fijo, sin depender de una base de datos de husos
# horarios (zoneinfo) que no siempre está disponible en todos los entornos.
ZONA_ARGENTINA = timezone(timedelta(hours=-3))


def ahora_argentina():
    return datetime.now(ZONA_ARGENTINA)


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


def nombre_momento(indice_comida):
    # Después de las 4 comidas principales, la app deja agregar "snacks"
    # extra (podés cargar varios, cada uno con su propia hora). indice_comida
    # sigue subiendo de a uno para cada snack que se agrega, así que
    # cualquier índice más allá de las 4 comidas principales es un snack.
    if indice_comida < len(COMIDAS_DEL_DIA):
        return COMIDAS_DEL_DIA[indice_comida]
    return "Snack"

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


def clave_canonica_para_item(nombre_item):
    # Resuelve el nombre que escribió la persona (con errores de tipeo,
    # plurales, mayúsculas/tildes distintas) al nombre canónico del
    # catálogo de arriba, o None si no coincide con nada conocido.
    normalizado = _normalizar_texto(nombre_item)
    if not normalizado:
        return None

    candidatos = [normalizado, _sin_plural(normalizado)]

    # 1) Coincidencia exacta (con o sin plural) contra claves o sinónimos
    for candidato in candidatos:
        if candidato in _CLAVES_NORMALIZADAS:
            return _CLAVES_NORMALIZADAS[candidato]
        if candidato in _SINONIMOS_NORMALIZADOS:
            return _SINONIMOS_NORMALIZADOS[candidato]

    # 1.5) Coincidencia exacta de alguna palabra suelta dentro de la frase
    # (ej. "pizza de muzzarella" o "agua mineral" contienen una palabra que
    # sola sí es una clave o sinónimo conocido).
    for palabra in normalizado.split():
        palabra = _sin_plural(palabra)
        if palabra in _CLAVES_NORMALIZADAS:
            return _CLAVES_NORMALIZADAS[palabra]
        if palabra in _SINONIMOS_NORMALIZADOS:
            return _SINONIMOS_NORMALIZADOS[palabra]

    # 2) Coincidencia difusa (tolera errores de tipeo) contra claves y sinónimos
    universo = {**_CLAVES_NORMALIZADAS, **_SINONIMOS_NORMALIZADOS}
    for candidato in candidatos:
        parecidos = difflib.get_close_matches(candidato, universo.keys(), n=1, cutoff=0.72)
        if parecidos:
            return universo[parecidos[0]]

    return None


def opciones_para_item(nombre_item):
    clave = clave_canonica_para_item(nombre_item)
    if clave is None:
        return OPCIONES_GENERICAS
    return CATALOGO_DETALLE[clave]

# ==========================================================
# --- EMOJI PARA CADA ITEM DE LA LISTA ---
# ----------------------------------------------------------
# En la lista de "comidas y bebidas cargadas" mostramos un emoji a modo
# ilustrativo. Como hay infinitas comidas posibles, no hay un emoji para
# cada una: usamos el emoji del item del catálogo (arriba) si coincide, y
# si no, buscamos entre algunas palabras sueltas comunes que no forman
# parte del catálogo de 10 opciones (ensalada, fruta, huevo, etc.). Si no
# encontramos nada, mostramos un emoji genérico según la categoría.
# ==========================================================
EMOJI_CATALOGO = {
    "milanesa": "🍖", "asado": "🥩", "pasta": "🍝", "pollo al horno": "🍗",
    "guiso": "🍲", "pizza": "🍕", "empanadas": "🥟", "tarta": "🥧",
    "sandwich de miga": "🥪", "tostadas": "🍞", "medialunas": "🥐",
    "facturas": "🥐", "alfajores": "🍪", "torta": "🍰",
    "cafe con leche": "☕", "te": "🍵", "mate": "🧉", "jugo de naranja": "🧃",
    "chocolatada": "🥛", "gaseosa": "🥤", "agua": "🥛", "vino": "🍷",
    "soda": "🥤", "cerveza": "🍺",
}

# Ojo con el orden: las frases de más de una palabra van primero, para que
# "papas fritas" se detecte antes que la genérica "papa".
EMOJI_PALABRAS_EXTRA = {
    "papas fritas": "🍟",
    "ensalada": "🥗",
    "fruta": "🍎", "manzana": "🍎", "banana": "🍌", "naranja": "🍊",
    "pera": "🍐", "uva": "🍇", "frutilla": "🍓",
    "queso": "🧀", "huevo": "🥚", "sopa": "🍲", "pan": "🍞", "arroz": "🍚",
    "papa": "🥔", "yogur": "🥣", "yogurt": "🥣", "helado": "🍨",
}


def emoji_para_item(nombre_item, categoria):
    clave = clave_canonica_para_item(nombre_item)
    if clave in EMOJI_CATALOGO:
        return EMOJI_CATALOGO[clave]

    normalizado = _normalizar_texto(nombre_item)
    palabras = set(normalizado.split())
    palabras |= {_sin_plural(p) for p in palabras}
    for palabra, emoji in EMOJI_PALABRAS_EXTRA.items():
        if palabra in palabras or (len(palabra) >= 4 and palabra in normalizado):
            return emoji

    return "🍽️" if categoria == "Comida" else "🥤"

# ==========================================================
# --- IMÁGENES ---
# Poné acá los nombres de tus archivos PNG. Todos tienen que estar
# dentro de una carpeta llamada "assets" (al lado de este archivo).
# Si todavía NO tenés la imagen, dejá el valor en None y la app igual funciona.
# ==========================================================
FONDO = None                # Ej: "fondo.png"  -> fondo de todas las pantallas

# Ilustración que se muestra en la pantalla de "tamaño de la porción". Cada
# item del catálogo (arriba) tiene su propio dibujo; si la persona cargó
# algo que no reconocemos, usamos una ilustración genérica según el tipo
# (comida de desayuno/merienda, comida de almuerzo/cena, o bebida).
IMAGEN_CATALOGO = {
    "milanesa": "plato_comida.svg",
    "asado": "asado.svg",
    "pasta": "pasta.svg",
    "pizza": "pizza.svg",
    "empanadas": "empanada.svg",
    "pollo al horno": "pollo.svg",
    "guiso": "guiso.svg",
    "tarta": "tarta.svg",
    "sandwich de miga": "sandwich.svg",
    "tostadas": "plato_desayuno.svg",
    "medialunas": "plato_desayuno.svg",
    "facturas": "plato_desayuno.svg",
    "alfajores": "postre.svg",
    "torta": "postre.svg",
    "cafe con leche": "bebida_caliente.svg",
    "te": "bebida_caliente.svg",
    "mate": "mate.svg",
    "jugo de naranja": "bebida_fria.svg",
    "chocolatada": "bebida_fria.svg",
    "gaseosa": "bebida_fria.svg",
    "agua": "bebida_fria.svg",
    "soda": "bebida_fria.svg",
    "vino": "vino.svg",
    "cerveza": "cerveza.svg",
}


def imagen_para_item(categoria, comida_del_dia, nombre_item):
    clave = clave_canonica_para_item(nombre_item)
    if clave in IMAGEN_CATALOGO:
        return IMAGEN_CATALOGO[clave]

    if categoria == "Bebida":
        return "bebida_fria.svg"

    if comida_del_dia in ("Desayuno", "Merienda"):
        return "plato_desayuno.svg"
    return "plato_comida.svg"


# PBKDF2-HMAC-SHA256 con sal aleatoria por usuario y 600.000 iteraciones:
# recomendación vigente de OWASP (Password Storage Cheat Sheet) para que
# probar contraseñas por fuerza bruta sea lento incluso si la base de
# datos se filtrara.
PBKDF2_ITERACIONES = 600_000


def generar_salt():
    return os.urandom(16).hex()


def hash_contrasena(contrasena, salt_hex):
    salt = bytes.fromhex(salt_hex)
    derivado = hashlib.pbkdf2_hmac("sha256", contrasena.encode("utf-8"), salt, PBKDF2_ITERACIONES)
    return derivado.hex()


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
        "_latido_token": None,            # controla el hilo del latido (mantener viva la conexión)

        "tiene_password": True,    # False si entró solo con Google (no tiene contraseña propia)
        "pregunta_seguridad": "",  # solo el texto de la pregunta (no la respuesta), para precargarla en "Mi perfil"

        "nombre": "",       # cómo se lo saluda ("Hola, {nombre}!"); si está vacío se usa el email
        "edad": None,
        "educacion": "",
        "ocupacion": "",
        "ubicacion": "",    # provincia donde vive
        "vio_instrucciones": False,  # si ya vio la pantalla de instrucciones/video alguna vez

        "indice_comida": 0,
        "hora_ingresada": "",
        "_reanudar_items": False,   # si al reanudar hay que saltar directo a cargar items de esta comida
        "_ids_comida_hora": {},    # indice_comida -> id en Supabase (para poder corregir en vez de duplicar)
        "_historial_ancla_items": None,  # marca en el historial a la que volver entre items de una misma comida
        "_hora_snack_temp": None,  # hora elegida para el snack que se está por cargar (antes de confirmar)

        "items_temporales": [],
        "indice_item_actual": 0,
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
        _iniciar_latido()

    def mostrar_error_guardado():
        # Se usa cuando falla el guardado en Supabase (ej. corte de
        # conexión momentáneo): avisamos y NO avanzamos de pantalla, para
        # que la persona pueda tocar el botón de nuevo y reintentar sin
        # perder la respuesta que ya cargó.
        page.show_dialog(
            ft.SnackBar(
                ft.Text("No se pudo guardar. Revisá tu conexión y tocá el botón de nuevo."),
                bgcolor=ft.Colors.RED_400,
            )
        )

    # Late "latido" (heartbeat): en algunos casos Render corta la conexión
    # en vivo con la app si pasa un ratito sin que viaje ningún dato entre
    # el navegador y el servidor (a veces bastan varios segundos), y ahí
    # parece que la app "deslogueó" cuando en realidad se reconectó de
    # cero. Para evitarlo, mientras se está mostrando cualquier pantalla
    # mandamos una actualización liviana cada 20 segundos, así la conexión
    # nunca queda del todo quieta. Cada pantalla nueva cancela el latido
    # de la anterior (por eso el token), para no ir acumulando hilos.
    def _iniciar_latido():
        token = object()
        estado["_latido_token"] = token

        def loop():
            while estado.get("_latido_token") is token:
                time.sleep(20)
                if estado.get("_latido_token") is not token:
                    return
                try:
                    page.update()
                except Exception:
                    return

        threading.Thread(target=loop, daemon=True).start()

    # ==========================================================
    # PANTALLA 1: LOGIN / REGISTRO POR EMAIL
    # ----------------------------------------------------------
    # Cada usuario se identifica con su mail + contraseña. Si el mail no
    # existe todavía en Supabase se crea una cuenta nueva con esa
    # contraseña (alta automática); si ya existe, hay que acertar la
    # contraseña guardada (hasheada con sal, nunca en texto plano).
    # ==========================================================
    def mostrar_error(texto_control, mensaje):
        texto_control.value = mensaje
        page.update()

    def buscar_usuario_por_email(email):
        try:
            resp = requests.get(
                SUPABASE_USUARIOS_URL,
                headers=HEADERS,
                params={"email": f"eq.{email}", "select": "*"},
                timeout=10,
            )
            if not resp.ok:
                print(f"Error Supabase GET usuarios [{resp.status_code}]: {resp.text}")
                return None, False
            resultados = resp.json()
            return (resultados[0], True) if resultados else (None, True)
        except Exception as e:
            print("Error de red (usuarios):", repr(e))
            return None, False

    def crear_usuario(email, password_hash, password_salt=None):
        try:
            resp = requests.post(
                SUPABASE_USUARIOS_URL,
                headers={**HEADERS, "Prefer": "return=representation"},
                json={"email": email, "password_hash": password_hash, "password_salt": password_salt},
                timeout=10,
            )
            if not resp.ok:
                print(f"Error Supabase POST usuarios [{resp.status_code}]: {resp.text}")
                return None
            creados = resp.json()
            return creados[0] if creados else None
        except Exception as e:
            print("Error de red (crear usuario):", repr(e))
            return None

    def buscar_o_crear_usuario_google(email):
        # Usado solo por el login con Google: no pide/valida contraseña.
        usuario, ok = buscar_usuario_por_email(email)
        if not ok:
            return None
        if usuario:
            return usuario
        return crear_usuario(email, None)

    def actualizar_password_supabase(usuario_id, password_hash, password_salt):
        try:
            resp = requests.patch(
                f"{SUPABASE_USUARIOS_URL}?id=eq.{usuario_id}",
                headers=HEADERS,
                json={"password_hash": password_hash, "password_salt": password_salt},
                timeout=10,
            )
            resp.raise_for_status()
            return True
        except Exception as e:
            print("Error de red (actualizar password):", e)
            return False

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
        estado["tiene_password"] = usuario.get("password_hash") is not None
        estado["pregunta_seguridad"] = usuario.get("pregunta_seguridad") or ""
        estado["nombre"] = usuario.get("nombre") or ""
        estado["edad"] = usuario.get("edad")
        estado["educacion"] = usuario.get("educacion") or ""
        estado["ocupacion"] = usuario.get("ocupacion") or ""
        estado["ubicacion"] = usuario.get("ubicacion") or ""
        estado["vio_instrucciones"] = bool(usuario.get("vio_instrucciones"))
        # Al entrar arrancamos un historial nuevo: así "Atrás" desde el menú
        # principal no lleva de nuevo a la pantalla de login.
        historial.clear()
        if estado["nombre"]:
            ir_a(mostrar_dashboard)
        else:
            # Primera vez que entra este usuario: tiene que completar su
            # perfil antes de poder usar la encuesta.
            ir_a(mostrar_perfil)

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
        usuario = buscar_o_crear_usuario_google(email_google)
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
                    "nombre": estado.get("nombre", ""),
                    "edad": estado.get("edad"),
                    "educacion": estado.get("educacion", ""),
                    "ocupacion": estado.get("ocupacion", ""),
                    "ubicacion": estado.get("ubicacion", ""),
                }
                entrar_con_usuario(usuario_local, local=True)
                return

            email = valor.lower()
            if "@" not in email or "." not in email.split("@")[-1]:
                input_email.error_text = "Ingresá un email válido"
                page.update()
                return
            input_email.error_text = None

            if len(contrasena) < 6:
                input_contrasena.error_text = "La contraseña tiene que tener al menos 6 caracteres"
                page.update()
                return
            input_contrasena.error_text = None

            texto_error.value = ""
            boton_ingresar.disabled = True
            boton_ingresar.text = "Ingresando..."
            page.update()

            usuario, ok = buscar_usuario_por_email(email)

            if not ok:
                boton_ingresar.disabled = False
                boton_ingresar.text = "Ingresar"
                mostrar_error(texto_error, "No pudimos conectar. Revisá tu conexión e intentá de nuevo.")
                return

            if usuario is None:
                # Cuenta nueva: se registra con esta contraseña, con una
                # sal aleatoria propia (no derivada del email).
                salt_nueva = generar_salt()
                hash_nuevo = hash_contrasena(contrasena, salt_nueva)
                usuario = crear_usuario(email, hash_nuevo, salt_nueva)
                boton_ingresar.disabled = False
                boton_ingresar.text = "Ingresar"
                if usuario is None:
                    mostrar_error(texto_error, "No pudimos crear tu cuenta. Revisá tu conexión e intentá de nuevo.")
                    return
                entrar_con_usuario(usuario, local=False)
                return

            boton_ingresar.disabled = False
            boton_ingresar.text = "Ingresar"

            if usuario.get("password_hash") is None:
                mostrar_error(texto_error, "Esta cuenta fue creada con Google. Iniciá sesión con el botón de Google.")
                return

            salt_guardada = usuario.get("password_salt")
            if not salt_guardada:
                mostrar_error(texto_error, "Hubo un problema con tu cuenta. Contactanos para ayudarte a recuperarla.")
                return

            hash_ingresado = hash_contrasena(contrasena, salt_guardada)
            if usuario.get("password_hash") != hash_ingresado:
                mostrar_error(texto_error, "Contraseña incorrecta.")
                return

            entrar_con_usuario(usuario, local=False)

        input_email = ft.TextField(label="Email", width=ancho_campo(), keyboard_type=ft.KeyboardType.EMAIL)
        input_contrasena = ft.TextField(label="Contraseña", width=ancho_campo(), password=True, can_reveal_password=True)
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

        controles.extend([
            input_email,
            input_contrasena,
            texto_error,
            boton_ingresar,
            ft.TextButton("¿Olvidaste tu contraseña?", on_click=lambda _: ir_a(mostrar_recuperar_paso1)),
        ])

        pantalla(*controles)

    # ==========================================================
    # RECUPERAR CONTRASEÑA
    # ----------------------------------------------------------
    # Sin envío de mails (la app no tiene ese servicio configurado): se
    # verifica identidad con una pregunta de seguridad que la persona
    # eligió y respondió en "Mi perfil" (guardada con el mismo esquema de
    # hash+sal que la contraseña, nunca en texto plano). Si la cuenta es
    # de Google, o todavía no configuró una pregunta, se le avisa en vez
    # de dejarla en un callejón sin salida.
    # ==========================================================
    def mostrar_recuperar_paso1():
        input_email = ft.TextField(label="Tu email", width=ancho_campo(), keyboard_type=ft.KeyboardType.EMAIL)
        texto_error = ft.Text("", color=ft.Colors.RED)
        boton_continuar = ft.ElevatedButton("Continuar", width=ancho_campo(), height=50)

        def continuar(e):
            email = (input_email.value or "").strip().lower()
            if "@" not in email or "." not in email.split("@")[-1]:
                mostrar_error(texto_error, "Ingresá un email válido.")
                return

            boton_continuar.disabled = True
            boton_continuar.text = "Buscando..."
            page.update()

            usuario, ok = buscar_usuario_por_email(email)

            boton_continuar.disabled = False
            boton_continuar.text = "Continuar"

            if not ok:
                mostrar_error(texto_error, "No pudimos conectar. Revisá tu conexión e intentá de nuevo.")
                return
            if usuario is None:
                mostrar_error(texto_error, "No encontramos una cuenta con ese email.")
                return
            if usuario.get("password_hash") is None:
                mostrar_error(texto_error, "Esta cuenta fue creada con Google. Iniciá sesión con el botón de Google.")
                return
            if not usuario.get("pregunta_seguridad") or not usuario.get("respuesta_seguridad_hash"):
                mostrar_error(texto_error, "Esta cuenta todavía no tiene una pregunta de seguridad configurada. Contactanos para ayudarte a recuperarla.")
                return

            ir_a(lambda: mostrar_recuperar_paso2(usuario))

        boton_continuar.on_click = continuar

        pantalla(
            ft.Icon(ft.Icons.LOCK_RESET, size=44, color=ft.Colors.BLUE_400),
            ft.Text("Recuperar tu cuenta", size=22, weight=ft.FontWeight.BOLD, text_align=ft.TextAlign.CENTER),
            ft.Text(
                "Ingresá el email con el que te registraste.",
                color=ft.Colors.GREY_700,
                text_align=ft.TextAlign.CENTER,
            ),
            input_email,
            texto_error,
            boton_continuar,
            ft.TextButton("Volver a iniciar sesión", on_click=lambda _: ir_a(mostrar_login)),
            mostrar_volver=False,
        )

    def mostrar_recuperar_paso2(usuario):
        input_respuesta = ft.TextField(label="Tu respuesta", width=ancho_campo())
        texto_error = ft.Text("", color=ft.Colors.RED)

        def continuar(e):
            respuesta = (input_respuesta.value or "").strip()
            if not respuesta:
                mostrar_error(texto_error, "Escribí tu respuesta para poder seguir.")
                return
            respuesta_normalizada = _normalizar_texto(respuesta)
            hash_ingresado = hash_contrasena(respuesta_normalizada, usuario["respuesta_seguridad_salt"])
            if hash_ingresado != usuario["respuesta_seguridad_hash"]:
                mostrar_error(texto_error, "Esa no es la respuesta que tenemos guardada. Probá de nuevo.")
                return
            ir_a(lambda: mostrar_recuperar_paso3(usuario))

        pantalla(
            ft.Icon(ft.Icons.LOCK_RESET, size=44, color=ft.Colors.BLUE_400),
            ft.Text("Tu pregunta de seguridad", size=22, weight=ft.FontWeight.BOLD, text_align=ft.TextAlign.CENTER),
            ft.Text(usuario["pregunta_seguridad"], color=ft.Colors.GREY_700, text_align=ft.TextAlign.CENTER),
            input_respuesta,
            texto_error,
            ft.ElevatedButton("Continuar", on_click=continuar, width=ancho_campo(), height=50),
            ft.TextButton("Volver a iniciar sesión", on_click=lambda _: ir_a(mostrar_login)),
            mostrar_volver=False,
        )

    def mostrar_recuperar_paso3(usuario):
        input_nueva = ft.TextField(label="Nueva contraseña", width=ancho_campo(), password=True, can_reveal_password=True)
        texto_error = ft.Text("", color=ft.Colors.RED)
        boton_guardar = ft.ElevatedButton("Guardar nueva contraseña", width=ancho_campo(), height=50)

        def guardar(e):
            nueva = input_nueva.value or ""
            if len(nueva) < 6:
                mostrar_error(texto_error, "La contraseña tiene que tener al menos 6 caracteres.")
                return

            boton_guardar.disabled = True
            boton_guardar.text = "Guardando..."
            page.update()

            salt_nueva = generar_salt()
            hash_nuevo = hash_contrasena(nueva, salt_nueva)
            ok = actualizar_password_supabase(usuario["id"], hash_nuevo, salt_nueva)

            boton_guardar.disabled = False
            boton_guardar.text = "Guardar nueva contraseña"

            if not ok:
                mostrar_error(texto_error, "No pudimos guardar la contraseña nueva. Revisá tu conexión e intentá de nuevo.")
                return

            ir_a(mostrar_recuperar_listo)

        boton_guardar.on_click = guardar

        pantalla(
            ft.Icon(ft.Icons.LOCK_RESET, size=44, color=ft.Colors.BLUE_400),
            ft.Text("Elegí tu nueva contraseña", size=22, weight=ft.FontWeight.BOLD, text_align=ft.TextAlign.CENTER),
            input_nueva,
            texto_error,
            boton_guardar,
            mostrar_volver=False,
        )

    def mostrar_recuperar_listo():
        pantalla(
            ft.Icon(ft.Icons.CHECK_CIRCLE_OUTLINE, size=44, color=ft.Colors.GREEN),
            ft.Text("Listo, ya podés ingresar", size=22, weight=ft.FontWeight.BOLD, text_align=ft.TextAlign.CENTER),
            ft.Text(
                "Tu contraseña se actualizó. Iniciá sesión con la nueva.",
                color=ft.Colors.GREY_700,
                text_align=ft.TextAlign.CENTER,
            ),
            ft.ElevatedButton("Ir a iniciar sesión", on_click=lambda _: ir_a(mostrar_login), width=ancho_campo(), height=50),
            mostrar_volver=False,
        )

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
        return estado["ultima_fecha_completado"] != ahora_argentina().date().isoformat()

    def debe_mostrar_instrucciones():
        # Acceso piloto: siempre se muestra, para poder probar esa pantalla
        # las veces que haga falta.
        return estado["modo_local"] or not estado["vio_instrucciones"]

    def marcar_instrucciones_vistas():
        estado["vio_instrucciones"] = True
        if not estado["modo_local"]:
            try:
                requests.patch(
                    f"{SUPABASE_USUARIOS_URL}?id=eq.{estado['usuario_id']}",
                    headers=HEADERS,
                    json={"vio_instrucciones": True},
                    timeout=10,
                )
            except Exception as e:
                print("Error de red (marcar instrucciones vistas):", e)

    # ----------------------------------------------------------
    # Reanudar encuesta sin terminar: cada respuesta se manda a Supabase
    # apenas se confirma (ver enviar_o_actualizar_registro), así que si la
    # persona cierra la app a mitad de la encuesta, la próxima vez que
    # entra retomamos desde la comida donde se quedó en vez de empezar el
    # día de nuevo. Ojo: si ya había empezado a cargar items para una
    # comida pero se fue antes de guardar el tamaño de al menos uno, esos
    # items sueltos no quedan guardados y hay que volver a escribirlos
    # (solo se recuerda la comida y la hora, no la lista de items a medias).
    # Esto solo cubre las 4 comidas principales: si se fue a mitad de
    # cargar un snack, al volver arranca la parte de snacks de nuevo (no
    # hay problema, es opcional y se puede repetir las veces que haga falta).
    # ----------------------------------------------------------
    def obtener_registros_de_hoy():
        inicio = datetime.combine(ahora_argentina().date(), datetime.min.time()).strftime("%Y-%m-%dT%H:%M:%S")
        fin = datetime.combine(ahora_argentina().date() + timedelta(days=1), datetime.min.time()).strftime("%Y-%m-%dT%H:%M:%S")
        try:
            resp = requests.get(
                SUPABASE_URL,
                headers=HEADERS,
                params={"usuario": f"eq.{estado['email']}", "fecha": [f"gte.{inicio}", f"lt.{fin}"], "select": "*"},
                timeout=10,
            )
            if not resp.ok:
                print(f"Error Supabase GET progreso [{resp.status_code}]: {resp.text}")
                return None
            return resp.json()
        except Exception as e:
            print("Error de red (progreso):", repr(e))
            return None

    def aplicar_progreso_guardado():
        estado["indice_comida"] = 0
        estado["hora_ingresada"] = ""
        estado["items_temporales"] = []
        estado["indice_item_actual"] = 0
        estado["_reanudar_items"] = False
        estado["_ids_comida_hora"] = {}

        if estado["modo_local"]:
            # Acceso piloto: siempre arranca de cero, para poder probar el
            # flujo completo las veces que haga falta.
            return

        registros = obtener_registros_de_hoy()
        if registros is None:
            return  # error de red: arrancamos de cero como si no hubiera progreso

        for i, comida in enumerate(COMIDAS_DEL_DIA):
            regs_comida = [r for r in registros if r.get("momento_dia") == comida]
            hora_regs = [r for r in regs_comida if r.get("tipo_registro") == "comida_hora"]
            if not hora_regs:
                estado["indice_comida"] = i
                return

            hora_reg = hora_regs[0]
            if hora_reg.get("tuvo_comida") is False:
                continue  # esta comida ya quedó resuelta ("no tuve"), seguimos con la próxima

            item_regs = [r for r in regs_comida if r.get("tipo_registro") == "item"]
            if not item_regs:
                # Dijo que sí tuvo esta comida pero no llegó a guardar
                # ningún item: retomamos pidiendo los items directamente.
                estado["indice_comida"] = i
                estado["hora_ingresada"] = hora_reg.get("hora_consumo") or ""
                estado["_reanudar_items"] = True
                if hora_reg.get("id") is not None:
                    estado["_ids_comida_hora"][i] = hora_reg["id"]
                return
            # esta comida ya tiene items guardados: la damos por resuelta y seguimos

        # Las 4 comidas ya estaban respondidas (de esta sesión o de una
        # anterior que se cortó): seguimos directo a la parte de snacks en
        # vez de pedirle que responda todo el día de nuevo.
        estado["indice_comida"] = len(COMIDAS_DEL_DIA)

    def ir_a_pregunta_o_items():
        if estado.get("_reanudar_items"):
            estado["_reanudar_items"] = False
            ir_a(mostrar_ingreso_items)
        elif estado["indice_comida"] >= len(COMIDAS_DEL_DIA):
            # Ya respondió las 4 comidas principales (en esta sesión o en
            # una anterior que se cortó): seguimos con la parte de snacks.
            ir_a(mostrar_pregunta_snack)
        else:
            ir_a(mostrar_pregunta_hora)

    def enviar_o_actualizar_registro(registro, id_previo):
        # Guarda cada respuesta apenas se confirma (no al final de la
        # encuesta), para que se pueda reanudar si la persona se va a
        # mitad de camino. Si ya se había mandado esta misma respuesta
        # antes (ej. volvió atrás y la cambió), la actualiza en vez de
        # crear una fila duplicada.
        # Devuelve (exito, id): si exito es False, quien llama NO debe avanzar
        # de pantalla (para no perder en silencio la respuesta si hubo un
        # corte de conexión momentáneo).
        if estado["modo_local"]:
            return True, None
        try:
            if id_previo is not None:
                resp = requests.patch(
                    f"{SUPABASE_URL}?id=eq.{id_previo}",
                    headers=HEADERS,
                    json=registro,
                    timeout=10,
                )
                if not resp.ok:
                    print(f"Error Supabase PATCH encuesta_comidas [{resp.status_code}]: {resp.text}")
                    return False, id_previo
                return True, id_previo
            resp = requests.post(
                SUPABASE_URL,
                headers={**HEADERS, "Prefer": "return=representation"},
                json=registro,
                timeout=10,
            )
            if not resp.ok:
                print(f"Error Supabase POST encuesta_comidas [{resp.status_code}]: {resp.text}")
                return False, None
            creados = resp.json()
            return True, (creados[0]["id"] if creados else None)
        except Exception as e:
            print("Error de red (guardar respuesta):", repr(e))
            return False, id_previo

    def tiempo_restante_texto():
        ahora = ahora_argentina()
        medianoche = datetime.combine(ahora.date() + timedelta(days=1), datetime.min.time(), tzinfo=ZONA_ARGENTINA)
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

    def cerrar_sesion(e):
        estado["email"] = ""
        estado["usuario_id"] = None
        estado["modo_local"] = False
        estado["sesiones_historicas"] = 0
        estado["ultima_fecha_completado"] = None
        estado["tiene_password"] = True
        estado["pregunta_seguridad"] = ""
        estado["nombre"] = ""
        estado["edad"] = None
        estado["educacion"] = ""
        estado["ocupacion"] = ""
        estado["ubicacion"] = ""
        page.logout()
        historial.clear()
        ir_a(mostrar_login)

    def mostrar_dashboard():
        estado["indice_comida"] = 0

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

        def comenzar_encuesta(e):
            aplicar_progreso_guardado()
            # Arrancamos un historial nuevo para la encuesta: si no, al
            # reanudar directo en medio de una comida o en la parte de
            # snacks, "Atrás" quedaba con el menú principal debajo en la
            # pila y te mandaba ahí de un salto en vez de quedarse dentro
            # de la encuesta.
            historial.clear()
            if debe_mostrar_instrucciones():
                ir_a(mostrar_instrucciones)
            else:
                ir_a_pregunta_o_items()

        boton_comenzar = ft.ElevatedButton(
            "Completar encuesta de hoy" if habilitado else "Ya completaste el registro de hoy",
            on_click=comenzar_encuesta if habilitado else None,
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

        encabezado = ft.Row(
            [
                ft.IconButton(
                    icon=ft.Icons.PERSON,
                    tooltip="Mi perfil",
                    on_click=lambda _: ir_a(mostrar_perfil),
                    icon_color=ft.Colors.WHITE,
                    bgcolor=ft.Colors.BLUE_400,
                )
            ],
            alignment=ft.MainAxisAlignment.END,
        )

        nombre_mostrar = estado["nombre"] or estado["email"]

        pantalla(
            encabezado,
            ft.Text(f"Hola, {nombre_mostrar}!", size=24, weight=ft.FontWeight.BOLD),
            tarjeta_stats,
            ft.Divider(height=20, color=ft.Colors.TRANSPARENT),
            boton_comenzar,
            boton_resumen,
            ft.Divider(height=10, color=ft.Colors.TRANSPARENT),
            ft.TextButton("Cerrar sesión", on_click=cerrar_sesion),
        )

        if not habilitado:
            token = object()
            estado["_dashboard_token"] = token
            iniciar_countdown(texto_countdown, token)
        elif not estado["modo_local"]:
            # Si ya había respuestas guardadas de hoy (se fue y volvió a
            # entrar a mitad de la encuesta), el botón pasa a decir
            # "Continuar encuesta" en vez de "Completar". Se chequea en
            # segundo plano para no demorar el dibujado del menú.
            def verificar_progreso():
                if obtener_registros_de_hoy():
                    boton_comenzar.text = "Continuar encuesta"
                    try:
                        page.update()
                    except Exception:
                        pass

            threading.Thread(target=verificar_progreso, daemon=True).start()

    # ==========================================================
    # PANTALLA: MI PERFIL
    # ----------------------------------------------------------
    # El nombre que la persona cargue acá es el que usa la app para
    # saludarla ("Hola, {nombre}!") en el menú principal.
    # ==========================================================
    OPCIONES_EDUCACION = [
        "Primario", "Secundario", "Terciario", "Universitario", "Posgrado", "Otro",
    ]
    OPCIONES_PROVINCIAS = [
        "CABA (Ciudad Autónoma de Buenos Aires)", "Buenos Aires", "Catamarca", "Chaco",
        "Chubut", "Córdoba", "Corrientes", "Entre Ríos", "Formosa", "Jujuy", "La Pampa",
        "La Rioja", "Mendoza", "Misiones", "Neuquén", "Río Negro", "Salta", "San Juan",
        "San Luis", "Santa Cruz", "Santa Fe", "Santiago del Estero", "Tierra del Fuego",
        "Tucumán",
    ]
    # Rango de edad del público objetivo del estudio: fuera de este rango no
    # se continúa con la encuesta (ver mostrar_no_apto más abajo).
    EDAD_MINIMA = 18
    EDAD_MAXIMA = 22

    # Preguntas de seguridad para "¿Olvidaste tu contraseña?": la app no
    # tiene un servicio de mails configurado, así que la recuperación se
    # hace verificando esto en vez de mandar un link. La respuesta se
    # guarda con el mismo esquema de hash+sal que la contraseña (nunca en
    # texto plano), normalizada (sin acentos, en minúscula) para que no
    # se trabe por mayúsculas o tildes al volver a escribirla.
    PREGUNTAS_SEGURIDAD = [
        "¿Cuál fue el nombre de tu primera mascota?",
        "¿En qué ciudad naciste?",
        "¿Cuál es tu comida favorita?",
        "¿Cómo se llamaba tu mejor amigo/a de la infancia?",
        "¿Cuál es tu película favorita?",
    ]

    def guardar_perfil_supabase(nombre, edad, educacion, ocupacion, ubicacion, pregunta_seguridad=None, respuesta_hash=None, respuesta_salt=None):
        datos = {
            "nombre": nombre, "edad": edad, "educacion": educacion,
            "ocupacion": ocupacion, "ubicacion": ubicacion,
        }
        # Solo se tocan estos campos si la persona escribió una respuesta
        # nueva: si los dejó vacíos porque ya tenía una configurada de
        # antes, no hay que pisarla con nada.
        if pregunta_seguridad is not None:
            datos["pregunta_seguridad"] = pregunta_seguridad
            datos["respuesta_seguridad_hash"] = respuesta_hash
            datos["respuesta_seguridad_salt"] = respuesta_salt
        try:
            resp = requests.patch(
                f"{SUPABASE_USUARIOS_URL}?id=eq.{estado['usuario_id']}",
                headers=HEADERS,
                json=datos,
                timeout=10,
            )
            resp.raise_for_status()
            return True
        except Exception as e:
            print("Error de red (guardar perfil):", e)
            return False

    def mostrar_no_apto():
        # Pantalla de corte para quienes no están dentro del rango de edad
        # del estudio: no se guarda ningún dato de perfil de esta persona.
        pantalla(
            ft.Icon(ft.Icons.INFO_OUTLINE, size=50, color=ft.Colors.BLUE_GREY),
            ft.Text("¡Gracias por tu interés!", size=22, weight=ft.FontWeight.BOLD, text_align=ft.TextAlign.CENTER),
            ft.Text(
                f"Este estudio está dirigido a personas de entre {EDAD_MINIMA} y {EDAD_MAXIMA} años, "
                "así que en este momento no formás parte del público objetivo. ¡Gracias igual por sumarte a probarlo!",
                text_align=ft.TextAlign.CENTER,
            ),
        )

    def mostrar_perfil():
        # Si todavía no cargó su nombre, es la primera vez que entra: hay
        # que completar el perfil sí o sí antes de poder usar la encuesta.
        es_primera_vez = not estado["nombre"]

        input_nombre = ft.TextField(label="Nombre", value=estado["nombre"], width=ancho_campo())
        input_edad = ft.TextField(
            label="Edad",
            value=str(estado["edad"]) if estado["edad"] is not None else "",
            width=ancho_campo(),
            keyboard_type=ft.KeyboardType.NUMBER,
            input_filter=ft.NumbersOnlyInputFilter(),
        )
        dropdown_educacion = ft.Dropdown(
            label="Nivel educativo",
            options=[ft.dropdown.Option(op) for op in OPCIONES_EDUCACION],
            value=estado["educacion"] or None,
            width=ancho_campo(),
        )
        input_ocupacion = ft.TextField(label="Ocupación", value=estado["ocupacion"], width=ancho_campo())
        dropdown_ubicacion = ft.Dropdown(
            label="¿Dónde vivís?",
            options=[ft.dropdown.Option(op) for op in OPCIONES_PROVINCIAS],
            value=estado["ubicacion"] or None,
            width=ancho_campo(),
        )
        dropdown_pregunta_seguridad = ft.Dropdown(
            label="Pregunta de seguridad (para recuperar tu cuenta)",
            options=[ft.dropdown.Option(op) for op in PREGUNTAS_SEGURIDAD],
            value=estado.get("pregunta_seguridad") or None,
            width=ancho_campo(),
        )
        input_respuesta_seguridad = ft.TextField(
            label="Tu respuesta",
            hint_text=(
                "Dejalo vacío si no querés cambiarla"
                if estado.get("pregunta_seguridad")
                else "La vamos a usar solo si algún día te olvidás la contraseña"
            ),
            width=ancho_campo(),
        )
        texto_error = ft.Text("", color=ft.Colors.RED, text_align=ft.TextAlign.CENTER)

        def guardar(e):
            texto_error.value = ""
            input_nombre.error_text = None
            input_edad.error_text = None

            nombre_valor = (input_nombre.value or "").strip()
            edad_texto = (input_edad.value or "").strip()

            hay_error = False
            if not nombre_valor:
                input_nombre.error_text = "Ingresá tu nombre"
                hay_error = True
            if not edad_texto or not edad_texto.isdigit():
                input_edad.error_text = "Ingresá tu edad (solo números)"
                hay_error = True

            if hay_error:
                texto_error.value = "Revisá los campos marcados en rojo arriba."
                page.update()
                return

            edad_valor = int(edad_texto)
            educacion_valor = dropdown_educacion.value or ""
            ocupacion_valor = (input_ocupacion.value or "").strip()
            ubicacion_valor = dropdown_ubicacion.value or ""

            # El filtro de edad solo aplica al completar el perfil por primera
            # vez (no vuelve a echar a alguien que ya venía participando y
            # entra a editar su perfil).
            if es_primera_vez and not (EDAD_MINIMA <= edad_valor <= EDAD_MAXIMA):
                historial.clear()
                ir_a(mostrar_no_apto)
                return

            respuesta_valor = (input_respuesta_seguridad.value or "").strip()
            pregunta_valor = None
            hash_respuesta = None
            salt_respuesta = None
            if respuesta_valor and not dropdown_pregunta_seguridad.value:
                texto_error.value = "Elegí una pregunta de seguridad antes de escribir la respuesta."
                page.update()
                return
            if dropdown_pregunta_seguridad.value and not respuesta_valor:
                texto_error.value = "Escribí una respuesta para la pregunta de seguridad que elegiste."
                page.update()
                return
            if respuesta_valor and dropdown_pregunta_seguridad.value:
                pregunta_valor = dropdown_pregunta_seguridad.value
                salt_respuesta = generar_salt()
                hash_respuesta = hash_contrasena(_normalizar_texto(respuesta_valor), salt_respuesta)

            estado["nombre"] = nombre_valor
            estado["edad"] = edad_valor
            estado["educacion"] = educacion_valor
            estado["ocupacion"] = ocupacion_valor
            estado["ubicacion"] = ubicacion_valor
            if pregunta_valor is not None:
                estado["pregunta_seguridad"] = pregunta_valor

            if not estado["modo_local"]:
                if not guardar_perfil_supabase(nombre_valor, edad_valor, educacion_valor, ocupacion_valor, ubicacion_valor, pregunta_valor, hash_respuesta, salt_respuesta):
                    texto_error.value = "No pudimos guardar los cambios. Revisá tu conexión e intentá de nuevo."
                    page.update()
                    return

            historial.clear()
            ir_a(mostrar_dashboard)

        boton_guardar = ft.ElevatedButton("Guardar", on_click=guardar, width=ancho_campo(), height=50)

        controles = [ft.Text("Contanos sobre vos" if es_primera_vez else "Mi perfil", size=24, weight=ft.FontWeight.BOLD)]
        if es_primera_vez:
            controles.append(
                ft.Text(
                    "Antes de empezar necesitamos algunos datos tuyos.",
                    text_align=ft.TextAlign.CENTER,
                    color=ft.Colors.GREY_700,
                )
            )
        controles.extend([input_nombre, input_edad, dropdown_educacion, input_ocupacion, dropdown_ubicacion])
        if estado.get("tiene_password", True):
            # No tiene sentido pedir esto a alguien que entró con Google:
            # nunca va a necesitar "¿Olvidaste tu contraseña?" porque no
            # tiene una contraseña propia que recuperar.
            controles.extend([dropdown_pregunta_seguridad, input_respuesta_seguridad])
        controles.extend([texto_error, boton_guardar])

        pantalla(*controles, mostrar_volver=not es_primera_vez)

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
            for comida in COMIDAS_DEL_DIA + ["Snack"]:
                regs_comida = por_dia[dia].get(comida)
                if not regs_comida:
                    continue

                items = [r for r in regs_comida if r.get("tipo_registro") == "item"]

                if comida == "Snack":
                    # Cada snack tiene su propia hora (a diferencia de las
                    # comidas principales), así que la mostramos por item.
                    if items:
                        detalle = ", ".join(
                            f"{it.get('item_nombre')} a las {it.get('hora_consumo')} ({it.get('item_detalle')}, {it.get('item_tamano')})"
                            for it in items
                        )
                        filas_dia.append(ft.Text(f"• Snacks: {detalle}"))
                    continue

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

        def comenzar_click(e):
            marcar_instrucciones_vistas()
            ir_a_pregunta_o_items()

        boton_comenzar = ft.ElevatedButton("Comenzar", on_click=comenzar_click, width=ancho_campo(), height=50)

        pantalla(texto_instrucciones, caja_video, ft.Divider(color=ft.Colors.TRANSPARENT), boton_comenzar)

    # ==========================================================
    # PANTALLA 4: HORA DE LA COMIDA
    # ==========================================================
    def avanzar_comida():
        estado["indice_comida"] += 1
        estado["hora_ingresada"] = ""
        # Al cerrar una comida (o un snack), vaciamos el historial: "Atrás"
        # ya no debería poder cruzar hacia una comida anterior ya cerrada
        # (esas respuestas ya se guardaron). Dentro de la comida/snack que
        # sigue, "Atrás" vuelve a funcionar con normalidad entre sus propias
        # pantallas (hora -> items -> detalle -> tamaño).
        historial.clear()
        if estado["indice_comida"] < len(COMIDAS_DEL_DIA):
            ir_a(mostrar_pregunta_hora)
        else:
            # Terminadas las 4 comidas principales, ofrecemos cargar
            # snacks extra (uno o varios, cada uno con su propia hora).
            ir_a(mostrar_pregunta_snack)

    def volver_a_pregunta_inicial():
        # Guarda de seguridad de las pantallas de detalle/tamaño: si por
        # algún motivo no hay items cargados, volvemos a la pregunta
        # correspondiente (de una comida principal, o de snacks).
        if estado["indice_comida"] < len(COMIDAS_DEL_DIA):
            mostrar_pregunta_hora()
        else:
            mostrar_pregunta_snack()

    def mostrar_pregunta_hora():
        # Guarda de seguridad: esta pantalla es solo para las 4 comidas
        # principales. Si por algún motivo se llega acá ya pasado ese
        # rango (ej. algún camino de navegación inesperado), mandamos a
        # la pantalla de snacks en vez de romper con un índice inválido.
        if estado["indice_comida"] >= len(COMIDAS_DEL_DIA):
            mostrar_pregunta_snack()
            return

        estado["items_temporales"] = []
        comida_actual = COMIDAS_DEL_DIA[estado["indice_comida"]]
        inicio_pregunta = time.monotonic()

        titulo = ft.Text(f"En las últimas 24 horas, ¿tuviste {comida_actual.lower()}?\nSi tuviste, ¿a qué hora fue?", size=20, weight=ft.FontWeight.BOLD, text_align=ft.TextAlign.CENTER)

        # Sugerimos el horario habitual de esta comida, pero queda 100%
        # editable: basta con tocar el campo y elegir otra hora en el reloj.
        hora_sugerida = HORARIOS_SUGERIDOS.get(comida_actual)
        hora_sugerida_texto = hora_sugerida.strftime("%H:%M") if hora_sugerida else ""
        # Si esta pantalla se vuelve a dibujar sin haber cambiado de comida
        # (ej. al rotar el celular), no pisamos una hora que la persona ya
        # había elegido con el reloj.
        if not estado["hora_ingresada"]:
            estado["hora_ingresada"] = hora_sugerida_texto

        input_hora = ft.TextField(
            label="Tocar para elegir hora",
            value=estado["hora_ingresada"],
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
        # Se manda a Supabase apenas se confirma (no al final de la encuesta),
        # para poder reanudar si la persona cierra la app a mitad de camino.
        def registrar_respuesta_hora(tuvo, hora_consumo):
            registro = {
                "usuario": estado["email"],
                "fecha": ahora_argentina().strftime("%Y-%m-%dT%H:%M:%S"),
                "momento_dia": comida_actual,
                "hora_consumo": hora_consumo,
                "item_nombre": None,
                "item_categoria": None,
                "item_detalle": None,
                "item_tamano": None,
                "tipo_registro": "comida_hora",
                "tuvo_comida": tuvo,
                "tiempo_respuesta_seg": round(time.monotonic() - inicio_pregunta, 1),
            }
            id_previo = estado["_ids_comida_hora"].get(estado["indice_comida"])
            exito, nuevo_id = enviar_o_actualizar_registro(registro, id_previo)
            if nuevo_id is not None:
                estado["_ids_comida_hora"][estado["indice_comida"]] = nuevo_id
            return exito

        # Mientras se está mandando la respuesta a Supabase, deshabilitamos
        # los dos botones: si no, un doble toque (algo común en celulares o
        # cuando la conexión tarda) podía disparar dos guardados y crear una
        # fila duplicada para la misma comida.
        enviando = {"valor": False}

        def _bloquear_botones(bloqueado):
            boton_no_tuve.disabled = bloqueado
            boton_cerca_horario.disabled = bloqueado
            page.update()

        def no_tuve_click(e):
            if enviando["valor"]:
                return
            enviando["valor"] = True
            _bloquear_botones(True)
            if registrar_respuesta_hora(False, None):
                avanzar_comida()
            else:
                enviando["valor"] = False
                _bloquear_botones(False)
                mostrar_error_guardado()

        boton_no_tuve = ft.OutlinedButton("No tuve", on_click=no_tuve_click, width=ancho_campo())

        def confirmar_hora(e):
            if enviando["valor"]:
                return
            if not input_hora.value:
                input_hora.error_text = "Elegí una hora"
                page.update()
                return
            enviando["valor"] = True
            _bloquear_botones(True)
            if registrar_respuesta_hora(True, input_hora.value):
                ir_a(mostrar_ingreso_items)
            else:
                enviando["valor"] = False
                _bloquear_botones(False)
                mostrar_error_guardado()

        boton_cerca_horario = ft.ElevatedButton("Cerca de ese horario", on_click=confirmar_hora, width=ancho_campo())

        pantalla(
            titulo,
            input_hora,
            ft.Divider(height=20, color=ft.Colors.TRANSPARENT),
            boton_cerca_horario,
            boton_no_tuve,
            overlays=[reloj],
        )

    # ==========================================================
    # PANTALLA 5: INGRESO DE COMIDAS Y BEBIDAS
    # ==========================================================
    def mostrar_ingreso_items():
        comida_actual = nombre_momento(estado["indice_comida"])
        hora = estado["hora_ingresada"]

        titulo = ft.Text(f"Decinos todo lo que tuviste para el {comida_actual.lower()} ({hora}).", size=18, weight=ft.FontWeight.BOLD, text_align=ft.TextAlign.CENTER)

        lista_ui = ft.Column()

        def actualizar_lista_ui():
            lista_ui.controls.clear()
            for i, item in enumerate(estado["items_temporales"]):
                icono = emoji_para_item(item["nombre"], item["categoria"])
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
            # Si quedó algo escrito en los campos pero la persona nunca
            # tocó el "+" (o el Enter no disparó en su celular), lo
            # agregamos igual acá: si no, "Continuar" avanzaba de comida
            # sin guardar nada, dando la impresión de que se podía cargar
            # una comida sin completar detalle ni porción.
            agregar_comida(e)
            agregar_bebida(e)

            if len(estado["items_temporales"]) > 0:
                estado["indice_item_actual"] = 0
                # Marca el punto del historial al que hay que volver entre un
                # item y el siguiente (ver guardar_tamano_y_avanzar): "Atrás"
                # siempre tiene que volver a esta lista, nunca a la pantalla
                # de tamaño/detalle de OTRO item (esas pantallas se reusan
                # para todos los items y solo son válidas para el item actual).
                estado["_historial_ancla_items"] = len(historial)
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
            volver_a_pregunta_inicial()
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
            volver_a_pregunta_inicial()
            return

        item_actual = estado["items_temporales"][estado["indice_item_actual"]]
        comida_del_dia = nombre_momento(estado["indice_comida"])

        titulo = ft.Text(f"Tamaño de: {item_actual['nombre']}", size=20, weight=ft.FontWeight.BOLD)

        # Mapeo: valor del slider -> (Tamaño de la imagen, Nombre del texto)
        configuraciones = {
            0: (80, "Muy pequeño"),
            1: (130, "Pequeño"),
            2: (180, "Mediano"),
            3: (230, "Grande"),
            4: (280, "Muy grande")
        }

        # Área fija donde se dibuja la ilustración: su tamaño nunca cambia,
        # así el resto de la pantalla (título, texto, slider, botón) queda
        # quieto. La ilustración es orientativa según el tipo de
        # comida/bebida (ver imagen_para_item más arriba).
        AREA_DIBUJO = ancho_campo(280)

        imagen_src = imagen_para_item(item_actual["categoria"], comida_del_dia, item_actual["nombre"])

        # Si esta pantalla se vuelve a dibujar sin cambiar de item (ej. al
        # rotar el celular), arrancamos desde el tamaño que la persona ya
        # había elegido con el slider, no siempre desde "Mediano".
        idx_inicial = item_actual.get("_tamano_idx", 2)
        tamano_inicial, nombre_inicial = configuraciones[idx_inicial]

        dibujo = ft.Image(src=imagen_src, width=tamano_inicial, height=tamano_inicial, fit=ft.BoxFit.CONTAIN)

        contenedor_dibujo = ft.Container(
            content=dibujo,
            width=AREA_DIBUJO,
            height=AREA_DIBUJO,
            alignment=ft.Alignment.CENTER,
        )

        texto_label = ft.Text(nombre_inicial, size=16, weight=ft.FontWeight.BOLD)

        def slider_cambiado(e):
            idx = int(e.control.value)
            item_actual["_tamano_idx"] = idx
            nuevo_tamano, nuevo_nombre = configuraciones[idx]
            dibujo.width = nuevo_tamano
            dibujo.height = nuevo_tamano
            texto_label.value = nuevo_nombre
            page.update()

        slider = ft.Slider(min=0, max=4, divisions=4, value=idx_inicial, on_change=slider_cambiado)

        # Mientras se está mandando a Supabase, deshabilitamos el botón: un
        # doble toque (o una conexión lenta) podía disparar dos guardados y
        # crear una fila duplicada para el mismo item.
        enviando = {"valor": False}

        def guardar_tamano_y_avanzar(e):
            if enviando["valor"]:
                return
            enviando["valor"] = True
            boton_continuar.disabled = True
            page.update()

            # Se manda a Supabase apenas se confirma (no al final de la
            # encuesta), para poder reanudar si la persona cierra la app a
            # mitad de camino. Si ya se había mandado este mismo item antes
            # (ej. volvió atrás y cambió el detalle), se actualiza en vez
            # de crear una fila duplicada.
            registro_final = {
                "usuario": estado["email"],
                "fecha": ahora_argentina().strftime("%Y-%m-%dT%H:%M:%S"),
                "momento_dia": comida_del_dia,
                "hora_consumo": estado["hora_ingresada"],
                "item_nombre": item_actual["nombre"],
                "item_categoria": item_actual["categoria"],
                "item_detalle": item_actual["detalle"],
                "item_tamano": texto_label.value,
                "tipo_registro": "item",
                "tuvo_comida": True,
                "tiempo_respuesta_seg": round(time.monotonic() - item_actual.get("_t_inicio", time.monotonic()), 1),
            }
            exito, nuevo_id = enviar_o_actualizar_registro(registro_final, item_actual.get("_supabase_id"))
            if nuevo_id is not None:
                item_actual["_supabase_id"] = nuevo_id
            if not exito:
                enviando["valor"] = False
                boton_continuar.disabled = False
                page.update()
                mostrar_error_guardado()
                return

            estado["indice_item_actual"] += 1
            if estado["indice_item_actual"] < len(estado["items_temporales"]):
                # Volvemos el historial al punto marcado al entrar a este
                # item (ver mostrar_ingreso_items): así "Atrás" desde el
                # próximo item siempre lleva a la lista de items, nunca a
                # las pantallas de detalle/tamaño de un item ya cerrado
                # (esas pantallas se reusan y ya no representan ese item).
                ancla = estado.get("_historial_ancla_items")
                if ancla is not None:
                    del historial[ancla:]
                ir_a(mostrar_detalle_item)
            else:
                avanzar_comida()

        boton_continuar = ft.ElevatedButton("Guardar", on_click=guardar_tamano_y_avanzar, width=ancho_campo())

        pantalla(titulo, contenedor_dibujo, texto_label, slider, boton_continuar)

    # ==========================================================
    # PANTALLA 7.5: SNACKS EXTRA (FUERA DE LAS 4 COMIDAS PRINCIPALES)
    # ----------------------------------------------------------
    # Después de Desayuno/Almuerzo/Merienda/Cena, se puede cargar uno o
    # varios snacks extra, cada uno con su propia hora (a diferencia de las
    # comidas principales, acá la hora se pregunta una vez por cada snack).
    # ==========================================================
    def mostrar_pregunta_snack():
        # Cada vez que se pasa por acá es el punto de partida de un snack
        # nuevo (o el final de la encuesta): si había una hora tildada a
        # medias para un snack anterior que se abandonó, la descartamos.
        estado["_hora_snack_temp"] = None

        # indice_comida sube en 1 cada vez que se cierra un snack, así que
        # si ya pasamos del primero (índice > len(COMIDAS_DEL_DIA)) es
        # porque ya cargó al menos un snack en esta encuesta.
        ya_cargo_snack = estado["indice_comida"] > len(COMIDAS_DEL_DIA)

        texto_pregunta = (
            "¿Tuviste algún otro snack o comida extra?"
            if ya_cargo_snack
            else "¿Tuviste algún snack o comida extra, fuera de esas 4 comidas?\nPodés cargar varios, cada uno con su propio horario."
        )
        titulo = ft.Text(texto_pregunta, size=20, weight=ft.FontWeight.BOLD, text_align=ft.TextAlign.CENTER)

        boton_agregar = ft.ElevatedButton("Sí, agregar un snack", on_click=lambda _: ir_a(mostrar_hora_snack), width=ancho_campo())
        boton_terminar = ft.OutlinedButton("No, ya terminé", on_click=lambda _: ir_a(enviar_datos_y_mostrar_agradecimiento), width=ancho_campo())

        pantalla(titulo, ft.Divider(height=10, color=ft.Colors.TRANSPARENT), boton_agregar, boton_terminar)

    def mostrar_hora_snack():
        # Si esta pantalla se vuelve a dibujar sin haber confirmado el
        # snack (ej. al rotar el celular), no pisamos una hora que la
        # persona ya había elegido con el reloj.
        hora_texto_inicial = estado.get("_hora_snack_temp") or ahora_argentina().strftime("%H:%M")
        hora_sugerida = datetime.strptime(hora_texto_inicial, "%H:%M").time()

        titulo = ft.Text("¿A qué hora fue ese snack?", size=20, weight=ft.FontWeight.BOLD, text_align=ft.TextAlign.CENTER)

        input_hora = ft.TextField(
            label="Tocar para elegir hora",
            value=hora_texto_inicial,
            read_only=True,
            width=ancho_campo(200),
            text_align=ft.TextAlign.CENTER,
        )

        def cambio_hora(e):
            input_hora.value = e.control.value.strftime("%H:%M")
            estado["_hora_snack_temp"] = input_hora.value
            page.update()

        reloj = ft.TimePicker(value=hora_sugerida, confirm_text="Aceptar", cancel_text="Cancelar", on_change=cambio_hora)

        def abrir_reloj(e):
            reloj.open = True
            page.update()

        input_hora.on_click = abrir_reloj

        def continuar(e):
            if input_hora.value:
                estado["hora_ingresada"] = input_hora.value
                estado["_hora_snack_temp"] = None
                estado["items_temporales"] = []
                ir_a(mostrar_ingreso_items)
            else:
                input_hora.error_text = "Elegí una hora"
                page.update()

        boton_continuar = ft.ElevatedButton("Continuar", on_click=continuar, width=ancho_campo())

        pantalla(titulo, input_hora, ft.Divider(height=20, color=ft.Colors.TRANSPARENT), boton_continuar, overlays=[reloj])

    # ==========================================================
    # PANTALLA 8: ENVÍO A NUBE Y AGRADECIMIENTO
    # ==========================================================
    def marcar_usuario_completado_hoy():
        hoy = ahora_argentina().date().isoformat()
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
        # Cada respuesta ya se mandó a Supabase apenas se confirmó (ver
        # enviar_o_actualizar_registro), así que acá solo falta marcar el
        # día como completado.
        marcar_usuario_completado_hoy()

        # Vaciamos el historial: al terminar, "volver" no debería revivir la encuesta
        historial.clear()

        pantalla(
            ft.Icon(ft.Icons.CHECK_CIRCLE, color=ft.Colors.GREEN, size=60),
            ft.Text("¡Muchas gracias!", size=24, weight=ft.FontWeight.BOLD),
            ft.Text("Volviendo al menú de inicio...", size=14, color=ft.Colors.GREY_700),
            mostrar_volver=False,
        )

        def volver_a_inicio_luego():
            time.sleep(1.5)
            ir_a(mostrar_dashboard)

        threading.Thread(target=volver_a_inicio_luego, daemon=True).start()

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