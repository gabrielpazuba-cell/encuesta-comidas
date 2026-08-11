import flet as ft
import asyncio
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

# Límites de participación en el estudio. Cuando se alcanza cualquiera de los
# dos, la persona ya no puede completar más encuestas ni entrar al resto de la
# app: solo ve la pantalla de agradecimiento correspondiente.
MAX_CARGAS = 5           # cargas completas por participante
DIAS_PARTICIPACION = 10  # días disponibles, contados desde la primera carga

# Horario habitual de cada comida: se usa como sugerencia inicial en el
# reloj, pero cada persona lo puede editar libremente antes de confirmar.
HORARIOS_SUGERIDOS = {
    "Desayuno": time_cls(8, 0),
    "Almuerzo": time_cls(13, 0),
    "Merienda": time_cls(17, 0),
    "Cena": time_cls(21, 0),
}


# Para armar frases naturales: "el desayuno", "la merienda", etc.
ARTICULO_COMIDA = {
    "Desayuno": "el desayuno",
    "Almuerzo": "el almuerzo",
    "Merienda": "la merienda",
    "Cena": "la cena",
}

# Verbos en pasado (vos) para la pregunta "¿[verbo]?" de cada comida.
VERBO_PASADO = {
    "Desayuno": "desayunaste",
    "Almuerzo": "almorzaste",
    "Merienda": "merendaste",
    "Cena": "cenaste",
}

# Además de las 4 comidas principales, la encuesta pregunta por "snacking"
# una sola vez, al final de las 4 comidas: ahí se pueden cargar todas las
# colaciones del día, cada una con su hora.
#
# Las dos primeras claves quedan de cuando el snacking se preguntaba también
# entre desayuno/almuerzo y entre merienda/cena: ya no se usan para cargar,
# pero se mantienen para que el resumen siga mostrando bien los registros
# viejos que quedaron guardados con esas etiquetas en Supabase.
ETIQUETAS_SNACK = {
    "desayuno_almuerzo": "Snack entre desayuno y almuerzo",
    "merienda_cena": "Snack entre merienda y cena",
    "final": "Snack en otro momento",
}

# ==========================================================
# --- DESPLEGABLES DE COMIDAS Y BEBIDAS ---
# ----------------------------------------------------------
# La carga de items arranca eligiendo de estas listas (con opción "Otra
# comida"/"Otra bebida"), y después un campo de texto libre donde la
# persona cuenta qué fue exactamente (preparación, si fue plato principal
# o guarnición, marca, etc.). Antes era al revés (texto libre primero y
# un desplegable condicionado a lo escrito), pero era muy difícil que el
# desplegable se alineara con lo que la persona había puesto.
# ==========================================================
OPCION_OTRA_COMIDA = "Otra comida"
OPCION_OTRA_BEBIDA = "Otra bebida"

OPCIONES_DESPLEGABLE_COMIDA = [
    "Milanesa",
    "Asado / carne",
    "Pastas (fideos, ñoquis, ravioles...)",
    "Pollo",
    "Guiso / estofado",
    "Pizza",
    "Empanadas",
    "Tarta",
    "Sándwich",
    "Hamburguesa",
    "Ensalada",
    "Sopa",
    "Tostadas",
    "Medialunas / facturas",
    "Galletitas",
    "Alfajor",
    "Torta / postre",
    "Fruta",
    "Yogur / cereales",
    "Huevos",
    OPCION_OTRA_COMIDA,
]

OPCIONES_DESPLEGABLE_BEBIDA = [
    "Agua / agua saborizada",
    "Mate / tereré",
    "Café / café con leche",
    "Té",
    "Chocolatada / leche",
    "Jugo",
    "Licuado",
    "Gaseosa",
    "Cerveza",
    "Vino",
    OPCION_OTRA_BEBIDA,
]

# Tamaño de la porción autodeclarado (antes era un slider con una imagen
# que se agrandaba/achicaba, pero como la imagen se modificaba completa
# —plato y contenido— era difícil establecer una proporción clara).
TAMANOS_PORCION = ["Pequeña", "Mediana", "Grande"]

# Emoji ilustrativo para cada opción de los desplegables de arriba.
EMOJI_DESPLEGABLE = {
    "Milanesa": "🍖",
    "Asado / carne": "🥩",
    "Pastas (fideos, ñoquis, ravioles...)": "🍝",
    "Pollo": "🍗",
    "Guiso / estofado": "🍲",
    "Pizza": "🍕",
    "Empanadas": "🥟",
    "Tarta": "🥧",
    "Sándwich": "🥪",
    "Hamburguesa": "🍔",
    "Ensalada": "🥗",
    "Sopa": "🍜",
    "Tostadas": "🍞",
    "Medialunas / facturas": "🥐",
    "Galletitas": "🍪",
    "Alfajor": "🍫",
    "Torta / postre": "🍰",
    "Fruta": "🍎",
    "Yogur / cereales": "🥣",
    "Huevos": "🥚",
    OPCION_OTRA_COMIDA: "🍽️",
    "Agua / agua saborizada": "💧",
    "Mate / tereré": "🧉",
    "Café / café con leche": "☕",
    "Té": "🍵",
    "Chocolatada / leche": "🥛",
    "Jugo": "🧃",
    "Licuado": "🥤",
    "Gaseosa": "🥤",
    "Cerveza": "🍺",
    "Vino": "🍷",
    OPCION_OTRA_BEBIDA: "🥤",
}

# ==========================================================
# --- CATÁLOGO DE COMIDAS/BEBIDAS TÍPICAS ---
# ----------------------------------------------------------
# Hoy solo se usa para reconocer nombres de comidas escritos a mano (con
# errores de tipeo, plurales, etc.) y asignarles un emoji cuando el item
# no vino de los desplegables de arriba (ej. datos viejos).
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


# ==========================================================
# --- EMOJI PARA CADA ITEM DE LA LISTA ---
# ----------------------------------------------------------
# En la lista de "comidas y bebidas cargadas" mostramos un emoji a modo
# ilustrativo. Los items ahora vienen de los desplegables, así que casi
# siempre alcanza con EMOJI_DESPLEGABLE (arriba); el matching difuso de
# abajo queda como red de seguridad para nombres escritos a mano.
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
    if nombre_item in EMOJI_DESPLEGABLE:
        return EMOJI_DESPLEGABLE[nombre_item]

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


AFIRMACIONES_INICIALES = [
    "A veces tiro basura en la calle o en parques.",
    "Siempre reconozco mis errores, incluso cuando hacerlo puede traerme problemas.",
    "Cuando manejo un auto, siempre soy amable y respetuoso con los otros usuarios de la vía pública.",
    "Siempre acepto otros puntos de vista, incluso cuando son diferentes de los míos.",
    "A veces me la agarro con los demás cuando estoy de mal humor.",
    "Alguna vez me aproveché de una situación perjudicando otra persona.",
    "Escucho atentamente y dejo que las demás personas terminen de hablar cuando converso.",
    "Nunca dudo en ayudar en una emergencia.",
    "Cumplo mis promesas a toda costa.",
    "A veces hablo mal de alguien cuando no está presente.",
    "Nunca dejaría que otra persona se ocupe de mí.",
    "Siempre mantengo un trato amable y cordial, incluso cuando estoy estresado.",
    "Siempre mantengo la calma y me atengo a los hechos cuando hay un desacuerdo.",
    "Alguna vez no devuelvo algo que me prestaron.",
    "Siempre mantengo una alimentación equilibrada.",
    "A veces ayudo a otros para recibir algo a cambio.",
]


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
        "fecha_primera_carga": None,      # "YYYY-MM-DD": desde acá se cuentan los DIAS_PARTICIPACION
        "_dashboard_token": None,         # controla el hilo de la cuenta regresiva
        "_latido_token": None,            # controla el hilo del latido (mantener viva la conexión)

        "tiene_password": True,    # False si entró solo con Google (no tiene contraseña propia)
        "pregunta_seguridad": "",  # solo el texto de la pregunta (no la respuesta), para precargarla en "Mi perfil"

        "nombre": "",       # cómo se lo saluda ("Hola, {nombre}!"); si está vacío se usa el email
        "edad": None,
        "genero": "",       # obligatorio al completar el perfil por primera vez
        "educacion": "",
        "ocupacion": "",
        "ubicacion": "",    # provincia donde vive
        "vio_instrucciones": False,  # si ya vio la pantalla de instrucciones/video alguna vez
        "preguntas_previas_completas": False,  # si ya respondió las dos preguntas previas a la checklist
        "encuesta_inicial_completa": False,  # si ya completó la checklist de afirmaciones (solo se hace una vez)

        "indice_comida": 0,
        "hora_ingresada": "",
        "_hora_snack_temp": None,  # hora elegida para el snack que se está por cargar (antes de confirmar)
        "_contexto_snack": None,   # None = comida principal; o una clave de ETIQUETAS_SNACK si se está en un bloque de snacks
        "_snacks_en_bloque": 0,    # cuántos snacks ya cargó en el bloque actual (cambia el texto de la pregunta)

        "items_temporales": [],
        "indice_item_actual": 0,

        # Datos acumulados en memoria durante la encuesta; se mandan todos
        # a Supabase de una sola vez al finalizar.
        "comidas": {i: {"tuvo": None, "hora": None, "items": []} for i in range(len(COMIDAS_DEL_DIA))},
        "snacks_pendientes": {k: [] for k in ETIQUETAS_SNACK},
    }

    # ==========================================================
    # SISTEMA DE NAVEGACIÓN (para el botón "volver atrás")
    # ----------------------------------------------------------
    # historial: va guardando las pantallas por las que pasaste.
    # historial_adelante: guarda las pantallas que se saltearon con "volver".
    # ir_a(pantalla): avanza a una pantalla nueva (limpia el adelante).
    # volver(): retrocede guardando la pantalla actual en historial_adelante.
    # adelantar(): avanza de nuevo si el usuario había vuelto atrás.
    # ==========================================================
    historial = []
    historial_adelante = []

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
        estado["_dashboard_token"] = None
        historial_adelante.clear()
        # Captura el contexto de navegación en el momento de la llamada.
        # Al volver atrás o adelante, se restaura este contexto antes de
        # redibujar la pantalla, para que cada pantalla siempre vea el
        # estado correcto (qué comida, qué hora, qué items estaban cargados).
        _idx   = estado["indice_comida"]
        _ctx   = estado["_contexto_snack"]
        _snk   = estado["_snacks_en_bloque"]
        _hora  = estado["hora_ingresada"]
        _items = estado["items_temporales"]  # referencia compartida (no copia)

        def entry():
            estado["indice_comida"]     = _idx
            estado["_contexto_snack"]   = _ctx
            estado["_snacks_en_bloque"] = _snk
            estado["hora_ingresada"]    = _hora
            estado["items_temporales"]  = _items
            pantalla_funcion()

        historial.append(entry)
        pantalla_funcion()

    def volver(e=None):
        if len(historial) > 1:
            estado["_dashboard_token"] = None
            historial_adelante.append(historial.pop())  # guarda la pantalla actual para poder volver
            historial[-1]()

    def adelantar(e=None):
        if historial_adelante:
            estado["_dashboard_token"] = None
            fn = historial_adelante.pop()
            historial.append(fn)
            fn()

    def avanzar_o_adelantar(fn_siguiente):
        """Al avanzar hacia adelante, si ya recorrimos estas pantallas antes
        (hay historial de avance), retomamos desde ahí en vez de crear una ruta
        nueva. Así los datos de comidas ya cargadas se mantienen intactos."""
        if historial_adelante:
            adelantar()
        else:
            ir_a(fn_siguiente)

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
        # Botones de navegación atrás / adelante
        if mostrar_volver:
            botones_nav = []
            if len(historial) > 1:
                botones_nav.append(
                    ft.IconButton(
                        icon=ft.Icons.ARROW_BACK,
                        tooltip="Volver",
                        on_click=volver,
                        icon_color=ft.Colors.WHITE,
                        bgcolor=ft.Colors.BLUE_400,
                    )
                )
            if historial_adelante:
                botones_nav.append(
                    ft.IconButton(
                        icon=ft.Icons.ARROW_FORWARD,
                        tooltip="Ir para adelante",
                        on_click=adelantar,
                        icon_color=ft.Colors.WHITE,
                        bgcolor=ft.Colors.BLUE_400,
                    )
                )
            if botones_nav:
                filas.append(ft.Row(botones_nav, alignment=ft.MainAxisAlignment.START, spacing=8))
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

    def secciones_iniciales_hechas(email):
        # Devuelve (hizo_preguntas_previas, hizo_encuesta_inicial) en una
        # sola consulta. Si la red falla asumimos que ya están hechas: es
        # preferible dejar entrar a la encuesta que hacer repetir una
        # sección que la persona ya completó.
        #
        # OJO: esto bloquea. Llamarla siempre desde un handler async con
        # asyncio.to_thread, nunca directo en un handler sincrónico.
        try:
            resp = requests.get(
                SUPABASE_URL,
                headers=HEADERS,
                params={
                    "usuario": f"eq.{email}",
                    "tipo_registro": "in.(preguntas_previas,encuesta_inicial)",
                    "select": "tipo_registro",
                },
                timeout=8,
            )
            if resp.ok:
                tipos = {r.get("tipo_registro") for r in resp.json()}
                return ("preguntas_previas" in tipos, "encuesta_inicial" in tipos)
            print(f"Error Supabase al verificar secciones iniciales [{resp.status_code}]: {resp.text}")
        except Exception as e:
            print("Error de red al verificar secciones iniciales:", repr(e))
        return (True, True)

    def entrar_con_usuario(usuario, local=False):
        estado["email"] = usuario["email"]
        estado["usuario_id"] = usuario["id"]
        estado["sesiones_historicas"] = usuario.get("sesiones_historicas") or 0
        estado["ultima_fecha_completado"] = usuario.get("ultima_fecha_completado")
        estado["fecha_primera_carga"] = usuario.get("fecha_primera_carga")
        estado["modo_local"] = local
        estado["tiene_password"] = usuario.get("password_hash") is not None
        estado["pregunta_seguridad"] = usuario.get("pregunta_seguridad") or ""
        estado["nombre"] = usuario.get("nombre") or ""
        estado["edad"] = usuario.get("edad")
        estado["genero"] = usuario.get("genero") or ""
        estado["educacion"] = usuario.get("educacion") or ""
        estado["ocupacion"] = usuario.get("ocupacion") or ""
        estado["ubicacion"] = usuario.get("ubicacion") or ""
        estado["vio_instrucciones"] = bool(usuario.get("vio_instrucciones"))
        # Al entrar arrancamos un historial nuevo: así "Atrás" desde el menú
        # principal no lleva de nuevo a la pantalla de login.
        historial.clear()
        # Acá NO va ninguna llamada de red. Flet ejecuta los handlers
        # sincrónicos (incluido el de login con Google) directamente sobre
        # el event loop de asyncio, sin hilo de por medio: un requests.get
        # bloqueante acá congela el loop, el WebSocket con el navegador deja
        # de atenderse y la pantalla se queda en blanco después de elegir la
        # cuenta de Google. Si hace falta consultar algo, va con handler
        # async + asyncio.to_thread (ver comenzar_encuesta).
        # Si ya terminó su participación, va directo al agradecimiento: no
        # tiene que pasar por el perfil ni por ningún otro formulario.
        fin = estado_participacion()
        if fin == "completo":
            ir_a(mostrar_participacion_completa)
        elif fin == "vencido":
            ir_a(mostrar_participacion_vencida)
        elif estado["nombre"]:
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

    def estado_participacion():
        # Devuelve None si la persona todavía puede participar, o el motivo
        # por el que ya no: "completo" (llegó a las MAX_CARGAS) o "vencido"
        # (pasaron los DIAS_PARTICIPACION desde su primera carga).
        #
        # El acceso piloto SÍ pasa por este corte, para poder probarlo. Como
        # sus contadores viven solo en memoria, alcanza con cerrar sesión y
        # volver a entrar para empezar de cero.
        if estado["sesiones_historicas"] >= MAX_CARGAS:
            return "completo"

        primera = estado.get("fecha_primera_carga")
        if primera:
            try:
                dia_inicio = datetime.strptime(str(primera)[:10], "%Y-%m-%d").date()
            except ValueError:
                # Fecha con formato inesperado: no cortamos el acceso por eso.
                return None
            # El día de la primera carga cuenta como día 1, así que quedan
            # disponibles DIAS_PARTICIPACION días en total.
            if (ahora_argentina().date() - dia_inicio).days >= DIAS_PARTICIPACION:
                return "vencido"

        return None

    def mostrar_participacion_completa():
        pantalla(
            ft.Icon(ft.Icons.CHECK_CIRCLE, size=56, color=ft.Colors.GREEN),
            ft.Text("¡Completaste el estudio!", size=24, weight=ft.FontWeight.BOLD, text_align=ft.TextAlign.CENTER),
            ft.Text(
                f"Ya registraste las {MAX_CARGAS} cargas. Muchas gracias por haber participado: "
                "la constancia día a día es justamente lo que hace posible este tipo de investigación.",
                text_align=ft.TextAlign.CENTER, color=ft.Colors.GREY_700,
            ),
            ft.Text(
                "Con esto tu participación queda terminada. No hace falta que vuelvas a entrar.",
                text_align=ft.TextAlign.CENTER, color=ft.Colors.GREY_700,
            ),
            ft.Divider(height=10, color=ft.Colors.TRANSPARENT),
            ft.TextButton("Cerrar sesión", on_click=cerrar_sesion),
            mostrar_volver=False,
        )

    def mostrar_participacion_vencida():
        pantalla(
            ft.Icon(ft.Icons.EVENT_AVAILABLE, size=56, color=ft.Colors.BLUE_GREY),
            ft.Text("Gracias por haber participado", size=24, weight=ft.FontWeight.BOLD, text_align=ft.TextAlign.CENTER),
            ft.Text(
                f"El período de participación de {DIAS_PARTICIPACION} días ya terminó, "
                "así que la encuesta no está más disponible.",
                text_align=ft.TextAlign.CENTER, color=ft.Colors.GREY_700,
            ),
            ft.Text(
                "Los registros que llegaste a cargar quedaron guardados y son un aporte "
                "para la investigación. ¡Gracias por el tiempo que le dedicaste!",
                text_align=ft.TextAlign.CENTER, color=ft.Colors.GREY_700,
            ),
            ft.Divider(height=10, color=ft.Colors.TRANSPARENT),
            ft.TextButton("Cerrar sesión", on_click=cerrar_sesion),
            mostrar_volver=False,
        )

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
    # Esto solo cubre las 4 comidas principales: si se fue a mitad de un
    # bloque de snacks, al volver se retoma desde la siguiente comida
    # principal pendiente (o desde el bloque final de snacks si ya
    # respondió las 4). No se pierde nada grave: la pregunta final de
    # "¿comiste algo más en algún otro momento?" cubre cualquier snack
    # que haya quedado sin cargar.
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
        estado["_contexto_snack"] = None
        estado["_snacks_en_bloque"] = 0
        estado["comidas"] = {i: {"tuvo": None, "hora": None, "items": []} for i in range(len(COMIDAS_DEL_DIA))}
        estado["snacks_pendientes"] = {k: [] for k in ETIQUETAS_SNACK}

    def ir_a_pregunta_o_items():
        if estado["indice_comida"] >= len(COMIDAS_DEL_DIA):
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
        estado["fecha_primera_carga"] = None
        estado["tiene_password"] = True
        estado["pregunta_seguridad"] = ""
        estado["nombre"] = ""
        estado["edad"] = None
        estado["genero"] = ""
        estado["educacion"] = ""
        estado["ocupacion"] = ""
        estado["ubicacion"] = ""
        page.logout()
        historial.clear()
        ir_a(mostrar_login)

    # ==========================================================
    # PANTALLA: PREGUNTAS PREVIAS (antes de la checklist)
    # ----------------------------------------------------------
    # Aparece una única vez, justo antes de la checklist.
    # Pregunta cuántas investigaciones previas tuvo la persona
    # y por qué quiere participar en este estudio.
    # ==========================================================
    def mostrar_preguntas_previas():
        OPCION_MAS_DE_10 = "Más de 10"
        opciones_investigaciones = [str(i) for i in range(11)] + [OPCION_MAS_DE_10]

        dropdown_investigaciones = ft.Dropdown(
            label="Elegí una opción",
            options=[ft.dropdown.Option(op) for op in opciones_investigaciones],
            width=ancho_campo(),
        )
        input_cantidad_exacta = ft.TextField(
            label="¿Cuántas exactamente?",
            hint_text="Escribí el número",
            width=ancho_campo(),
            visible=False,
            keyboard_type=ft.KeyboardType.NUMBER,
        )

        def on_dropdown_change(e):
            input_cantidad_exacta.visible = dropdown_investigaciones.value == OPCION_MAS_DE_10
            input_cantidad_exacta.error_text = None
            error_investigaciones.value = ""
            page.update()

        dropdown_investigaciones.on_change = on_dropdown_change

        input_motivacion = ft.TextField(
            label="¿Por qué te gustaría participar en este estudio?",
            hint_text="Contanos brevemente",
            width=ancho_campo(),
            multiline=True,
            min_lines=2,
            max_lines=4,
        )
        error_investigaciones = ft.Text("", color=ft.Colors.RED_700, size=12)
        error_motivacion = ft.Text("", color=ft.Colors.RED_700, size=12)
        enviando = {"valor": False}

        def guardar(e):
            if enviando["valor"]:
                return
            ok = True
            error_investigaciones.value = ""
            error_motivacion.value = ""
            input_cantidad_exacta.error_text = None

            if not dropdown_investigaciones.value:
                error_investigaciones.value = "Elegí una opción"
                ok = False
            elif dropdown_investigaciones.value == OPCION_MAS_DE_10:
                if not (input_cantidad_exacta.value or "").strip():
                    input_cantidad_exacta.error_text = "Escribí la cantidad"
                    ok = False

            if not (input_motivacion.value or "").strip():
                error_motivacion.value = "Contanos brevemente por qué"
                ok = False

            if not ok:
                page.update()
                return

            enviando["valor"] = True
            boton_continuar.disabled = True
            page.update()

            valor_investigaciones = dropdown_investigaciones.value
            if valor_investigaciones == OPCION_MAS_DE_10:
                valor_investigaciones = f"Más de 10: {input_cantidad_exacta.value.strip()}"

            fecha_str = ahora_argentina().strftime("%Y-%m-%dT%H:%M:%S")
            error = False
            for nombre_item, detalle_item in [
                ("investigaciones_previas", valor_investigaciones),
                ("motivacion_participacion", (input_motivacion.value or "").strip()),
            ]:
                registro = {
                    "usuario": estado["email"],
                    "fecha": fecha_str,
                    "tipo_registro": "preguntas_previas",
                    "momento_dia": "preguntas_previas",
                    "item_nombre": nombre_item,
                    "item_detalle": detalle_item,
                }
                exito, _ = enviar_o_actualizar_registro(registro, None)
                if not exito:
                    error = True
                    break

            if error:
                enviando["valor"] = False
                boton_continuar.disabled = False
                page.update()
                mostrar_error_guardado()
                return

            estado["preguntas_previas_completas"] = True
            historial.clear()
            ir_a(mostrar_encuesta_inicial)

        boton_continuar = ft.ElevatedButton("Continuar", on_click=guardar, width=ancho_campo(), height=50)

        pantalla(
            ft.Text("¿En cuántas investigaciones participaste en los últimos 12 meses?", size=16, weight=ft.FontWeight.BOLD),
            dropdown_investigaciones,
            input_cantidad_exacta,
            error_investigaciones,
            ft.Divider(color=ft.Colors.TRANSPARENT),
            ft.Text("¿Por qué te gustaría participar en este estudio?", size=16, weight=ft.FontWeight.BOLD),
            input_motivacion,
            error_motivacion,
            ft.Divider(color=ft.Colors.TRANSPARENT),
            boton_continuar,
            mostrar_volver=False,
        )

    # ==========================================================
    # PANTALLA: ENCUESTA INICIAL (CHECKLIST DE AFIRMACIONES)
    # ----------------------------------------------------------
    # Aparece una única vez, después del perfil y antes del menú
    # principal. Las respuestas se guardan en encuesta_comidas con
    # tipo_registro="encuesta_inicial" para poder detectar si ya
    # se completó en sesiones futuras.
    # ==========================================================
    def mostrar_encuesta_inicial():
        respuestas = {}  # idx -> "VERDADERO" | "FALSO"
        chips_por_fila = {}  # idx -> {"VERDADERO": Container, "FALSO": Container}
        fila_containers = {}  # idx -> Container (para resaltar errores)

        ANCHO_COL = 85

        def actualizar_chips_fila(idx):
            seleccionado = respuestas.get(idx)
            for opcion, chip in chips_por_fila[idx].items():
                activo = opcion == seleccionado
                chip.content = ft.Icon(
                    ft.Icons.CHECK_BOX if activo else ft.Icons.CHECK_BOX_OUTLINE_BLANK,
                    color=ft.Colors.BLUE_700 if activo else ft.Colors.GREY_400,
                    size=22,
                )
            if seleccionado:
                fila_containers[idx].bgcolor = None
            page.update()

        def on_chip(e, idx, opcion):
            respuestas[idx] = opcion
            actualizar_chips_fila(idx)

        enviando = {"valor": False}

        cabecera = ft.Row([
            ft.Container(expand=True),
            ft.Text("VERDADERO", size=11, weight=ft.FontWeight.BOLD,
                    width=ANCHO_COL, text_align=ft.TextAlign.CENTER, color=ft.Colors.GREY_700),
            ft.Text("FALSO", size=11, weight=ft.FontWeight.BOLD,
                    width=ANCHO_COL, text_align=ft.TextAlign.CENTER, color=ft.Colors.GREY_700),
        ], spacing=8)

        filas = [cabecera, ft.Divider()]
        for i, afirmacion in enumerate(AFIRMACIONES_INICIALES):
            chips_fila = {}
            chips_controles = []
            for opcion in ("VERDADERO", "FALSO"):
                activo = respuestas.get(i) == opcion
                chip = ft.Container(
                    content=ft.Icon(
                        ft.Icons.CHECK_BOX if activo else ft.Icons.CHECK_BOX_OUTLINE_BLANK,
                        color=ft.Colors.BLUE_700 if activo else ft.Colors.GREY_400,
                        size=22,
                    ),
                    width=ANCHO_COL,
                    alignment=ft.Alignment.CENTER,
                    on_click=lambda e, idx=i, op=opcion: on_chip(e, idx, op),
                )
                chips_fila[opcion] = chip
                chips_controles.append(chip)
            chips_por_fila[i] = chips_fila

            fila_container = ft.Container(
                content=ft.Row(
                    [ft.Text(afirmacion, size=13, expand=True), *chips_controles],
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=8,
                ),
                padding=ft.padding.symmetric(vertical=8, horizontal=4),
                border_radius=6,
            )
            fila_containers[i] = fila_container
            filas.append(fila_container)
            if i < len(AFIRMACIONES_INICIALES) - 1:
                filas.append(ft.Divider(height=1, color=ft.Colors.GREY_200))

        def guardar_encuesta_inicial(e):
            if enviando["valor"]:
                return
            falta = [i for i in range(len(AFIRMACIONES_INICIALES)) if i not in respuestas]
            if falta:
                for i in falta:
                    fila_containers[i].bgcolor = ft.Colors.RED_50
                page.update()
                return

            enviando["valor"] = True
            boton_continuar.disabled = True
            page.update()

            fecha_str = ahora_argentina().strftime("%Y-%m-%dT%H:%M:%S")
            error = False
            for i, afirmacion in enumerate(AFIRMACIONES_INICIALES):
                registro = {
                    "usuario": estado["email"],
                    "fecha": fecha_str,
                    "tipo_registro": "encuesta_inicial",
                    "momento_dia": "encuesta_inicial",
                    "item_nombre": f"afirmacion_{i + 1:02d}",
                    "item_detalle": respuestas[i],
                }
                exito, _ = enviar_o_actualizar_registro(registro, None)
                if not exito:
                    error = True
                    break

            if error:
                enviando["valor"] = False
                boton_continuar.disabled = False
                page.update()
                mostrar_error_guardado()
                return

            estado["encuesta_inicial_completa"] = True
            historial.clear()
            ir_a(mostrar_dashboard)

        boton_continuar = ft.ElevatedButton("Continuar", on_click=guardar_encuesta_inicial, width=ancho_campo(), height=50)

        titulo = ft.Text(
            "Leé atentamente cada afirmación e indicá si es VERDADERA o FALSA",
            size=17, weight=ft.FontWeight.BOLD, text_align=ft.TextAlign.CENTER,
        )
        subtitulo = ft.Text(
            "Esta sección se completa una sola vez.",
            size=13, color=ft.Colors.GREY_600, text_align=ft.TextAlign.CENTER,
        )

        pantalla(titulo, subtitulo, ft.Divider(), *filas, boton_continuar, mostrar_volver=False)

    def mostrar_dashboard():
        # Corte de participación: se chequea acá porque el menú es el paso
        # obligado para llegar a cualquier otra pantalla (encuesta, resumen,
        # perfil). Si ya terminó, solo ve el agradecimiento y "Cerrar sesión".
        fin = estado_participacion()
        if fin == "completo":
            mostrar_participacion_completa()
            return
        if fin == "vencido":
            mostrar_participacion_vencida()
            return

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

        # async + asyncio.to_thread: las consultas a Supabase son bloqueantes
        # y Flet corre los handlers sincrónicos sobre el event loop, así que
        # hacerlas directo congelaría la app. Con await, el loop sigue libre
        # y la pantalla responde mientras se consulta.
        async def comenzar_encuesta(e):
            boton_comenzar.disabled = True
            boton_comenzar.text = "Cargando..."
            page.update()

            if estado["modo_local"]:
                hizo_previas = hizo_inicial = True
            else:
                hizo_previas, hizo_inicial = await asyncio.to_thread(
                    secciones_iniciales_hechas, estado["email"]
                )

            boton_comenzar.disabled = False
            boton_comenzar.text = "Completar encuesta de hoy"

            if not hizo_previas:
                historial.clear()
                ir_a(mostrar_preguntas_previas)
                return
            if not hizo_inicial:
                historial.clear()
                ir_a(mostrar_encuesta_inicial)
                return

            estado["preguntas_previas_completas"] = True
            estado["encuesta_inicial_completa"] = True

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

    # ==========================================================
    # PANTALLA: MI PERFIL
    # ----------------------------------------------------------
    # El nombre que la persona cargue acá es el que usa la app para
    # saludarla ("Hola, {nombre}!") en el menú principal.
    # ==========================================================
    OPCIONES_EDUCACION = [
        "Primario", "Secundario", "Terciario", "Universitario", "Posgrado", "Otro",
    ]
    OPCIONES_GENERO = [
        "Mujer", "Varón", "Otra opción no listada", "Prefiero no decir",
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

    def guardar_perfil_supabase(nombre, edad, genero, educacion, ocupacion, ubicacion, pregunta_seguridad=None, respuesta_hash=None, respuesta_salt=None):
        datos = {
            "nombre": nombre, "edad": edad, "genero": genero,
            "educacion": educacion, "ocupacion": ocupacion, "ubicacion": ubicacion,
        }
        # Solo se tocan estos campos si la persona escribió una respuesta
        # nueva: si los dejó vacíos porque ya tenía una configurada de
        # antes, no hay que pisarla con nada.
        if pregunta_seguridad is not None:
            datos["pregunta_seguridad"] = pregunta_seguridad
            datos["respuesta_seguridad_hash"] = respuesta_hash
            datos["respuesta_seguridad_salt"] = respuesta_salt

        def _patch(cuerpo):
            return requests.patch(
                f"{SUPABASE_USUARIOS_URL}?id=eq.{estado['usuario_id']}",
                headers=HEADERS,
                json=cuerpo,
                timeout=10,
            )

        try:
            resp = _patch(datos)
            if resp.ok:
                return True

            # Red de seguridad: si todavía no se corrió
            # supabase_agregar_genero.sql, la columna "genero" no existe y
            # Supabase rechaza el PATCH entero (error PGRST204). En ese caso
            # guardamos el resto del perfil igual, para no dejar a la persona
            # trabada en esta pantalla sin poder avanzar.
            if "genero" in datos and "genero" in resp.text:
                print("Falta la columna 'genero' en la tabla usuarios: correr supabase_agregar_genero.sql")
                datos_sin_genero = {k: v for k, v in datos.items() if k != "genero"}
                resp2 = _patch(datos_sin_genero)
                if resp2.ok:
                    return True
                print(f"Error Supabase (guardar perfil sin genero) [{resp2.status_code}]: {resp2.text}")
                return False

            print(f"Error Supabase (guardar perfil) [{resp.status_code}]: {resp.text}")
            return False
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
        dropdown_genero = ft.Dropdown(
            label="Género",
            options=[ft.dropdown.Option(op) for op in OPCIONES_GENERO],
            value=estado["genero"] or None,
            width=ancho_campo(),
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
            dropdown_genero.error_text = None

            nombre_valor = (input_nombre.value or "").strip()
            edad_texto = (input_edad.value or "").strip()

            hay_error = False
            if not nombre_valor:
                input_nombre.error_text = "Ingresá tu nombre"
                hay_error = True
            if not edad_texto or not edad_texto.isdigit():
                input_edad.error_text = "Ingresá tu edad (solo números)"
                hay_error = True
            # El género es obligatorio (hay una opción "Prefiero no decir"
            # justamente para quien no quiera responderlo).
            if not dropdown_genero.value:
                dropdown_genero.error_text = "Elegí una opción"
                hay_error = True

            if hay_error:
                texto_error.value = "Revisá los campos marcados en rojo arriba."
                page.update()
                return

            edad_valor = int(edad_texto)
            genero_valor = dropdown_genero.value
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
            estado["genero"] = genero_valor
            estado["educacion"] = educacion_valor
            estado["ocupacion"] = ocupacion_valor
            estado["ubicacion"] = ubicacion_valor
            if pregunta_valor is not None:
                estado["pregunta_seguridad"] = pregunta_valor

            if not estado["modo_local"]:
                if not guardar_perfil_supabase(nombre_valor, edad_valor, genero_valor, educacion_valor, ocupacion_valor, ubicacion_valor, pregunta_valor, hash_respuesta, salt_respuesta):
                    texto_error.value = "No pudimos guardar los cambios. Revisá tu conexión e intentá de nuevo."
                    page.update()
                    return

            historial.clear()
            if es_primera_vez:
                ir_a(mostrar_preguntas_previas)
            else:
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
        controles.extend([input_nombre, input_edad, dropdown_genero, dropdown_educacion, input_ocupacion, dropdown_ubicacion])
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

        def _descripcion_item(it):
            partes = [p for p in (it.get("item_detalle"), it.get("item_tamano")) if p]
            extra = f" ({', '.join(partes)})" if partes else ""
            return f"{it.get('item_nombre')}{extra}"

        # Orden cronológico de los momentos del día en el resumen.
        # "Snack" a secas es la etiqueta vieja (de antes de preguntar
        # snacking entre comidas), por si hay datos guardados de antes.
        orden_momentos = [
            "Desayuno",
            ETIQUETAS_SNACK["desayuno_almuerzo"],
            "Almuerzo",
            "Merienda",
            ETIQUETAS_SNACK["merienda_cena"],
            "Cena",
            ETIQUETAS_SNACK["final"],
            "Snack",
        ]

        tarjetas = []
        for dia in sorted(por_dia.keys(), reverse=True):
            filas_dia = []
            for comida in orden_momentos:
                regs_comida = por_dia[dia].get(comida)
                if not regs_comida:
                    continue

                items = [r for r in regs_comida if r.get("tipo_registro") == "item"]

                if comida not in COMIDAS_DEL_DIA:
                    # Snacks: cada uno tiene su propia hora (a diferencia
                    # de las comidas principales), así que la mostramos
                    # por item.
                    if items:
                        detalle = ", ".join(
                            f"{_descripcion_item(it)} a las {it.get('hora_consumo')}"
                            for it in items
                        )
                        filas_dia.append(ft.Text(f"• {comida}: {detalle}"))
                    continue

                sin_comida = any(
                    r.get("tipo_registro") == "comida_hora" and r.get("tuvo_comida") is False
                    for r in regs_comida
                )

                if items:
                    detalle = ", ".join(_descripcion_item(it) for it in items)
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
    def nombre_momento_actual():
        # Nombre del momento del día que se está cargando ahora mismo:
        # una de las 4 comidas principales, o la etiqueta del bloque de
        # snacks activo (entre comidas, o el cierre del final del día).
        if estado["_contexto_snack"] is not None:
            return ETIQUETAS_SNACK[estado["_contexto_snack"]]
        if estado["indice_comida"] < len(COMIDAS_DEL_DIA):
            return COMIDAS_DEL_DIA[estado["indice_comida"]]
        return ETIQUETAS_SNACK["final"]

    def avanzar_comida():
        if estado["_contexto_snack"] is not None:
            # Cerró un snack: guarda en snacks_pendientes y pregunta si hubo más.
            ctx = estado["_contexto_snack"]
            snk = estado["_snacks_en_bloque"]
            bloque = estado["snacks_pendientes"][ctx]
            datos_snack = {"hora": estado["hora_ingresada"] or None, "items": list(estado["items_temporales"])}
            if snk < len(bloque):
                bloque[snk] = datos_snack
            else:
                bloque.append(datos_snack)
            estado["_snacks_en_bloque"] += 1
            estado["items_temporales"] = []
            avanzar_o_adelantar(mostrar_pregunta_snack)
            return

        # Cerró una comida principal: guarda items (tuvo/hora ya seteados en
        # mostrar_pregunta_hora) y avanza a la próxima comida o bloque de snacks.
        idx = estado["indice_comida"]
        estado["comidas"][idx]["items"] = estado["items_temporales"]
        estado["items_temporales"] = []

        if historial_adelante:
            adelantar()
            return

        comida_cerrada = idx
        estado["indice_comida"] += 1
        # Los snacks se preguntan una sola vez, al final de las 4 comidas
        # principales (antes se preguntaba también entre desayuno/almuerzo
        # y entre merienda/cena).
        if comida_cerrada == len(COMIDAS_DEL_DIA) - 1:
            abrir_bloque_snack("final")
        else:
            ir_a(mostrar_pregunta_hora)

    def abrir_bloque_snack(contexto):
        estado["_contexto_snack"] = contexto
        estado["_snacks_en_bloque"] = 0
        ir_a(mostrar_pregunta_snack)

    def cerrar_bloque_snack():
        # Respondió "No" a la pregunta de snacks: seguimos con la próxima
        # comida principal, o cerramos la encuesta si era el bloque final.
        contexto = estado["_contexto_snack"]
        estado["_contexto_snack"] = None
        estado["_snacks_en_bloque"] = 0
        if contexto == "final":
            ir_a(enviar_datos_y_mostrar_agradecimiento)
        else:
            ir_a(mostrar_pregunta_hora)

    def volver_a_pregunta_inicial():
        # Guarda de seguridad de las pantallas de items/tamaño: si por
        # algún motivo no hay items cargados, volvemos a la pregunta
        # correspondiente (de una comida principal, o de snacks).
        if estado["_contexto_snack"] is not None or estado["indice_comida"] >= len(COMIDAS_DEL_DIA):
            mostrar_pregunta_snack()
        else:
            mostrar_pregunta_hora()

    def mostrar_pregunta_hora():
        # Guarda de seguridad: esta pantalla es solo para las 4 comidas
        # principales.
        if estado["indice_comida"] >= len(COMIDAS_DEL_DIA):
            mostrar_pregunta_snack()
            return

        estado["items_temporales"] = []
        comida_actual = COMIDAS_DEL_DIA[estado["indice_comida"]]
        inicio_pregunta = time.monotonic()
        verbo = VERBO_PASADO.get(comida_actual, f"tuviste {comida_actual.lower()}")

        titulo = ft.Text(
            f"En las últimas 24hs, ¿{verbo}?",
            size=22, weight=ft.FontWeight.BOLD, text_align=ft.TextAlign.CENTER,
        )

        hora_sugerida = HORARIOS_SUGERIDOS.get(comida_actual)
        hora_inicial = estado["hora_ingresada"] or (hora_sugerida.strftime("%H:%M") if hora_sugerida else "")
        if hora_inicial:
            estado["hora_ingresada"] = hora_inicial

        campo_hora = ft.TextField(
            value=hora_inicial,
            read_only=True,
            width=ancho_campo(200),
            text_align=ft.TextAlign.CENTER,
            text_size=26,
            hint_text="--:--",
        )

        def cambio_hora(e):
            campo_hora.value = e.control.value.strftime("%H:%M")
            estado["hora_ingresada"] = campo_hora.value
            campo_hora.error_text = None
            page.update()

        # entry_mode=INPUT: el reloj se abre directo en modo teclado, para
        # escribir la hora a mano, y trae el botoncito del relojito para
        # pasar a la esfera y elegirla ahí. Los dos modos en un solo control.
        reloj = ft.TimePicker(
            value=hora_sugerida,
            entry_mode=ft.TimePickerEntryMode.INPUT,
            confirm_text="Aceptar",
            cancel_text="Cancelar",
            help_text="Elegí la hora",
            hour_label_text="Hora",
            minute_label_text="Minutos",
            on_change=cambio_hora,
        )

        def abrir_reloj(e):
            reloj.open = True
            page.update()

        campo_hora.on_click = abrir_reloj

        def confirmar_hora(e):
            if not campo_hora.value:
                campo_hora.error_text = "Elegí una hora"
                page.update()
                return
            idx = estado["indice_comida"]
            estado["hora_ingresada"] = campo_hora.value
            estado["comidas"][idx]["tuvo"] = True
            estado["comidas"][idx]["hora"] = campo_hora.value
            avanzar_o_adelantar(mostrar_ingreso_items)

        boton_continuar = ft.ElevatedButton(
            "Continuar", on_click=confirmar_hora, width=ancho_campo(), height=50,
        )

        # Sección de hora: aparece solo después de tocar "Sí"
        seccion_hora = ft.Column([
            ft.Text("Alrededor de las...", size=15, color=ft.Colors.GREY_700),
            campo_hora,
            ft.Text("(tocá para escribirla o elegirla en el reloj)", size=12, color=ft.Colors.GREY_500),
            ft.Divider(height=12, color=ft.Colors.TRANSPARENT),
            boton_continuar,
        ], visible=False, spacing=8, horizontal_alignment=ft.CrossAxisAlignment.CENTER)

        def si_click(e):
            boton_si.visible = False
            boton_no.visible = False
            seccion_hora.visible = True
            page.update()

        def no_click(e):
            idx = estado["indice_comida"]
            estado["comidas"][idx]["tuvo"] = False
            estado["comidas"][idx]["hora"] = None
            avanzar_comida()

        boton_si = ft.ElevatedButton("Sí", on_click=si_click, width=ancho_campo() // 2 - 5, height=50)
        boton_no = ft.OutlinedButton("No", on_click=no_click, width=ancho_campo() // 2 - 5, height=50)

        pantalla(
            titulo,
            ft.Divider(height=20, color=ft.Colors.TRANSPARENT),
            ft.Row([boton_si, boton_no], alignment=ft.MainAxisAlignment.CENTER, spacing=10),
            seccion_hora,
            overlays=[reloj],
        )

    # ==========================================================
    # PANTALLA 5: INGRESO DE COMIDAS Y BEBIDAS
    # ==========================================================
    def mostrar_ingreso_items():
        momento = nombre_momento_actual()
        hora = estado["hora_ingresada"]

        if estado["_contexto_snack"] is not None:
            sufijo_hora = f" ({hora})" if hora else ""
            texto_titulo = f"Decinos qué comiste o tomaste en ese momento{sufijo_hora}."
        else:
            texto_titulo = f"Decinos todo lo que tuviste para {ARTICULO_COMIDA.get(momento, momento.lower())} ({hora})."
        titulo = ft.Text(texto_titulo, size=18, weight=ft.FontWeight.BOLD, text_align=ft.TextAlign.CENTER)

        # Mismo ancho que las filas de los inputs de abajo: sin un ancho
        # fijo, el ft.Text(expand=True) de cada fila estira la lista a todo
        # el ancho de la tarjeta y queda desalineada (pegada a la izquierda)
        # respecto de los campos, que sí van con ancho_campo().
        lista_comida_ui = ft.Column(width=ancho_campo(), spacing=0)
        lista_bebida_ui = ft.Column(width=ancho_campo(), spacing=0)

        def actualizar_lista_ui():
            lista_comida_ui.controls.clear()
            lista_bebida_ui.controls.clear()
            for i, item in enumerate(estado["items_temporales"]):
                icono = emoji_para_item(item["nombre"], item["categoria"])
                texto_item = f"{icono} {item['nombre']}"
                if item.get("detalle"):
                    texto_item += f": {item['detalle']}"
                fila = ft.Row([
                    ft.Text(texto_item, expand=True),
                    ft.IconButton(ft.Icons.DELETE, on_click=lambda e, idx=i: eliminar_item(idx), icon_color=ft.Colors.RED)
                ])
                if item["categoria"] == "Comida":
                    lista_comida_ui.controls.append(fila)
                else:
                    lista_bebida_ui.controls.append(fila)
            page.update()

        def eliminar_item(index):
            estado["items_temporales"].pop(index)
            actualizar_lista_ui()

        input_comida_detalle = ft.TextField(
            label="¿Qué comiste?",
            hint_text="Describí en detalle lo que comiste",
            width=ancho_campo(220),
            expand=True,
            multiline=True,
            min_lines=1,
            max_lines=3,
        )
        input_bebida_detalle = ft.TextField(
            label="¿Qué tomaste?",
            hint_text="Describí en detalle lo que tomaste",
            width=ancho_campo(220),
            expand=True,
            multiline=True,
            min_lines=1,
            max_lines=3,
        )

        def _agregar_item(input_campo, categoria):
            texto = (input_campo.value or "").strip()
            if not texto:
                return True
            estado["items_temporales"].append({"nombre": texto, "categoria": categoria, "detalle": None})
            input_campo.value = ""
            actualizar_lista_ui()
            return True

        def agregar_comida(e):
            _agregar_item(input_comida_detalle, "Comida")

        def agregar_bebida(e):
            _agregar_item(input_bebida_detalle, "Bebida")

        def continuar(e):
            _agregar_item(input_comida_detalle, "Comida")
            _agregar_item(input_bebida_detalle, "Bebida")

            if len(estado["items_temporales"]) > 0:
                avanzar_o_adelantar(mostrar_tamano_item)
            else:
                avanzar_comida()

        boton_continuar = ft.ElevatedButton("Continuar", on_click=continuar, width=ancho_campo(), height=50)

        pantalla(
            titulo,
            ft.Text("Comida", weight=ft.FontWeight.BOLD),
            lista_comida_ui,
            ft.Row([input_comida_detalle, ft.IconButton(icon=ft.Icons.ADD_CIRCLE, icon_color=ft.Colors.BLUE, tooltip="Agregar", on_click=agregar_comida)], width=ancho_campo()),
            ft.Divider(color=ft.Colors.TRANSPARENT),
            ft.Text("Bebida", weight=ft.FontWeight.BOLD),
            lista_bebida_ui,
            ft.Row([input_bebida_detalle, ft.IconButton(icon=ft.Icons.ADD_CIRCLE, icon_color=ft.Colors.BLUE, tooltip="Agregar", on_click=agregar_bebida)], width=ancho_campo()),
            ft.Divider(color=ft.Colors.TRANSPARENT),
            boton_continuar,
        )

    # ==========================================================
    # PANTALLA 7: TAMAÑO DE LA PORCIÓN (GRILLA ÚNICA POR ITEM)
    # ==========================================================
    def mostrar_tamano_item():
        if not estado["items_temporales"]:
            volver_a_pregunta_inicial()
            return

        chips_por_item = {}   # idx -> {opcion -> Container}
        error_por_item = {}   # idx -> Text

        def actualizar_chips(idx):
            seleccionado = estado["items_temporales"][idx].get("_tamano")
            for opcion, chip in chips_por_item[idx].items():
                activo = opcion == seleccionado
                chip.bgcolor = ft.Colors.BLUE_700 if activo else ft.Colors.GREY_300
                chip.content.color = ft.Colors.WHITE if activo else ft.Colors.BLACK
            if seleccionado:
                error_por_item[idx].value = ""
            page.update()

        def on_chip_click(e, idx, opcion):
            estado["items_temporales"][idx]["_tamano"] = opcion
            actualizar_chips(idx)

        filas_items = []
        for i, item in enumerate(estado["items_temporales"]):
            icono = emoji_para_item(item["nombre"], item["categoria"])
            label = ft.Text(f"{icono} {item['nombre']}", size=15)

            chips_item = {}
            chips_fila = []
            for opcion in TAMANOS_PORCION:
                activo = item.get("_tamano") == opcion
                chip = ft.Container(
                    content=ft.Text(opcion, size=13, color=ft.Colors.WHITE if activo else ft.Colors.BLACK),
                    bgcolor=ft.Colors.BLUE_700 if activo else ft.Colors.GREY_300,
                    border_radius=20,
                    padding=ft.padding.symmetric(horizontal=14, vertical=8),
                    on_click=lambda e, idx=i, op=opcion: on_chip_click(e, idx, op),
                )
                chips_item[opcion] = chip
                chips_fila.append(chip)
            chips_por_item[i] = chips_item

            error_text = ft.Text("", color=ft.Colors.RED_700, size=12)
            error_por_item[i] = error_text

            filas_items.append(ft.Column([
                label,
                ft.Row(chips_fila, spacing=8),
                error_text,
            ], spacing=6))

            if i < len(estado["items_temporales"]) - 1:
                filas_items.append(ft.Divider())

        def guardar_todos(e):
            falta_alguno = False
            for i, item in enumerate(estado["items_temporales"]):
                if not item.get("_tamano"):
                    error_por_item[i].value = "Elegí una opción"
                    falta_alguno = True
            if falta_alguno:
                page.update()
                return
            avanzar_comida()

        boton_guardar = ft.ElevatedButton("Guardar", on_click=guardar_todos, width=ancho_campo(), height=50)

        titulo = ft.Text(
            "¿Qué tan grande fue la porción de cada cosa?",
            size=18, weight=ft.FontWeight.BOLD, text_align=ft.TextAlign.CENTER,
        )

        pantalla(titulo, ft.Divider(color=ft.Colors.TRANSPARENT), *filas_items, ft.Divider(color=ft.Colors.TRANSPARENT), boton_guardar)

    # ==========================================================
    # PANTALLA 7.5: SNACKING (ENTRE COMIDAS Y AL FINAL DEL DÍA)
    # ----------------------------------------------------------
    # La encuesta pregunta por snacks en tres momentos: entre desayuno y
    # almuerzo, entre merienda y cena, y un cierre general al final del
    # día. En cada bloque se pueden cargar varios snacks, cada uno con su
    # propia hora (a diferencia de las comidas principales, acá la hora
    # se pregunta una vez por cada snack).
    # ==========================================================
    def mostrar_pregunta_snack():
        # Guarda de seguridad: si se llega acá sin un bloque abierto (ej.
        # al reanudar una encuesta con las 4 comidas ya respondidas),
        # usamos el bloque de cierre del final del día.
        if estado["_contexto_snack"] is None:
            estado["_contexto_snack"] = "final"
            estado["_snacks_en_bloque"] = 0

        # Cada vez que se pasa por acá es el punto de partida de un snack
        # nuevo (o el cierre del bloque): si había una hora tildada a
        # medias para un snack anterior que se abandonó, la descartamos.
        estado["_hora_snack_temp"] = None

        ya_cargo_snack = estado["_snacks_en_bloque"] > 0
        texto_pregunta = (
            "¿Comiste o tomaste algo más fuera de las comidas?"
            if ya_cargo_snack
            else "En las últimas 24hs, ¿comiste o tomaste algo fuera de las comidas?"
        )

        titulo = ft.Text(texto_pregunta, size=20, weight=ft.FontWeight.BOLD, text_align=ft.TextAlign.CENTER)
        subtitulo = ft.Text(
            "Por ejemplo, una colación o un snack en cualquier momento del día."
            if not ya_cargo_snack
            else "Podés cargar todos los que quieras, uno por vez.",
            size=13, color=ft.Colors.GREY_600, text_align=ft.TextAlign.CENTER,
        )

        # Mismo formato que las comidas principales: dos botones al lado,
        # solo "Sí" y "No".
        boton_agregar = ft.ElevatedButton(
            "Sí", on_click=lambda _: ir_a(mostrar_hora_snack),
            width=ancho_campo() // 2 - 5, height=50,
        )
        boton_terminar = ft.OutlinedButton(
            "No", on_click=lambda _: cerrar_bloque_snack(),
            width=ancho_campo() // 2 - 5, height=50,
        )

        pantalla(
            titulo,
            subtitulo,
            ft.Divider(height=20, color=ft.Colors.TRANSPARENT),
            ft.Row([boton_agregar, boton_terminar], alignment=ft.MainAxisAlignment.CENTER, spacing=10),
        )

    def mostrar_hora_snack():
        # Si esta pantalla se vuelve a dibujar sin haber confirmado el
        # snack (ej. al rotar el celular), no pisamos una hora que la
        # persona ya había elegido con el reloj.
        hora_texto_inicial = estado.get("_hora_snack_temp") or ahora_argentina().strftime("%H:%M")
        hora_sugerida_snack = datetime.strptime(hora_texto_inicial, "%H:%M").time()

        titulo = ft.Text("¿A qué hora fue?", size=20, weight=ft.FontWeight.BOLD, text_align=ft.TextAlign.CENTER)

        campo_hora = ft.TextField(
            value=hora_texto_inicial,
            read_only=True,
            width=ancho_campo(200),
            text_align=ft.TextAlign.CENTER,
            text_size=26,
        )

        def cambio_hora(e):
            campo_hora.value = e.control.value.strftime("%H:%M")
            estado["_hora_snack_temp"] = campo_hora.value
            page.update()

        # Igual que en las comidas principales: se abre en modo teclado para
        # escribirla, con el botoncito para pasar a la esfera del reloj.
        reloj = ft.TimePicker(
            value=hora_sugerida_snack,
            entry_mode=ft.TimePickerEntryMode.INPUT,
            confirm_text="Aceptar",
            cancel_text="Cancelar",
            help_text="Elegí la hora",
            hour_label_text="Hora",
            minute_label_text="Minutos",
            on_change=cambio_hora,
        )

        def abrir_reloj(e):
            reloj.open = True
            page.update()

        campo_hora.on_click = abrir_reloj

        def avanzar_con_hora(hora):
            estado["hora_ingresada"] = hora
            estado["_hora_snack_temp"] = None
            estado["items_temporales"] = []
            avanzar_o_adelantar(mostrar_ingreso_items)

        def continuar(e):
            avanzar_con_hora(campo_hora.value or "")

        def no_recuerdo(e):
            avanzar_con_hora("")

        boton_continuar = ft.ElevatedButton("Continuar", on_click=continuar, width=ancho_campo())
        boton_no_recuerdo = ft.OutlinedButton("No recuerdo la hora", on_click=no_recuerdo, width=ancho_campo())

        pantalla(
            titulo,
            campo_hora,
            ft.Text("(tocá para escribirla o elegirla en el reloj)", size=12, color=ft.Colors.GREY_500),
            ft.Divider(height=20, color=ft.Colors.TRANSPARENT),
            boton_continuar,
            boton_no_recuerdo,
            overlays=[reloj],
        )

    # ==========================================================
    # PANTALLA 8: ENVÍO A NUBE Y AGRADECIMIENTO
    # ==========================================================
    def marcar_usuario_completado_hoy():
        hoy = ahora_argentina().date().isoformat()
        nuevo_historico = estado["sesiones_historicas"] + 1
        # La primera carga marca el arranque de los DIAS_PARTICIPACION.
        es_primera_carga = not estado.get("fecha_primera_carga")

        if not estado["modo_local"]:
            datos = {"sesiones_historicas": nuevo_historico, "ultima_fecha_completado": hoy}
            if es_primera_carga:
                datos["fecha_primera_carga"] = hoy

            def _patch(cuerpo):
                return requests.patch(
                    f"{SUPABASE_USUARIOS_URL}?id=eq.{estado['usuario_id']}",
                    headers=HEADERS,
                    json=cuerpo,
                    timeout=10,
                )

            try:
                resp = _patch(datos)
                # Red de seguridad: si todavía no se corrió
                # supabase_agregar_fecha_primera_carga.sql, la columna no
                # existe y Supabase rechaza el PATCH entero. En ese caso
                # guardamos al menos el contador y la fecha del día, para no
                # perder la carga que la persona acaba de completar.
                if not resp.ok and "fecha_primera_carga" in datos and "fecha_primera_carga" in resp.text:
                    print("Falta la columna 'fecha_primera_carga' en usuarios: correr supabase_agregar_fecha_primera_carga.sql")
                    resp = _patch({k: v for k, v in datos.items() if k != "fecha_primera_carga"})
                if not resp.ok:
                    print(f"Error Supabase (actualizar usuario) [{resp.status_code}]: {resp.text}")
            except Exception as e:
                print("Error de red (actualizar usuario):", e)

        # Reflejamos el cambio localmente aunque el PATCH falle (o en modo
        # local directamente no haya PATCH), para no dejar la encuesta
        # habilitada de nuevo por un error de red pasajero.
        estado["sesiones_historicas"] = nuevo_historico
        estado["ultima_fecha_completado"] = hoy
        if es_primera_carga:
            estado["fecha_primera_carga"] = hoy

    def enviar_datos_y_mostrar_agradecimiento():
        texto_estado = ft.Text("Guardando tus respuestas...", size=15, color=ft.Colors.GREY_700)
        pantalla(
            ft.ProgressRing(width=48, height=48),
            texto_estado,
            mostrar_volver=False,
        )

        def _enviar():
            ahora_str = ahora_argentina().strftime("%Y-%m-%dT%H:%M:%S")
            registros = []

            for i, comida in enumerate(COMIDAS_DEL_DIA):
                datos = estado["comidas"][i]
                if datos["tuvo"] is None:
                    continue
                registros.append({
                    "usuario": estado["email"],
                    "fecha": ahora_str,
                    "momento_dia": comida,
                    "hora_consumo": datos["hora"],
                    "item_nombre": None,
                    "item_categoria": None,
                    "item_detalle": None,
                    "item_tamano": None,
                    "tipo_registro": "comida_hora",
                    "tuvo_comida": datos["tuvo"],
                    "tiempo_respuesta_seg": None,
                })
                for item in datos["items"]:
                    registros.append({
                        "usuario": estado["email"],
                        "fecha": ahora_str,
                        "momento_dia": comida,
                        "hora_consumo": datos["hora"],
                        "item_nombre": item["nombre"],
                        "item_categoria": item["categoria"],
                        "item_detalle": item.get("detalle") or None,
                        "item_tamano": item.get("_tamano"),
                        "tipo_registro": "item",
                        "tuvo_comida": True,
                        "tiempo_respuesta_seg": None,
                    })

            for ctx, bloques in estado["snacks_pendientes"].items():
                for bloque in bloques:
                    for item in bloque.get("items", []):
                        registros.append({
                            "usuario": estado["email"],
                            "fecha": ahora_str,
                            "momento_dia": ctx,
                            "hora_consumo": bloque.get("hora"),
                            "item_nombre": item["nombre"],
                            "item_categoria": item["categoria"],
                            "item_detalle": item.get("detalle") or None,
                            "item_tamano": item.get("_tamano"),
                            "tipo_registro": "item",
                            "tuvo_comida": True,
                            "tiempo_respuesta_seg": None,
                        })

            for reg in registros:
                exito, _ = enviar_o_actualizar_registro(reg, None)
                if not exito:
                    texto_estado.value = "Hubo un problema al guardar. ¿Reintentamos?"
                    boton_reintentar = ft.ElevatedButton("Reintentar", on_click=lambda e: ir_a(enviar_datos_y_mostrar_agradecimiento))
                    pantalla(
                        ft.Icon(ft.Icons.ERROR_OUTLINE, color=ft.Colors.RED_700, size=60),
                        ft.Text("No se pudieron guardar tus respuestas.", size=18, weight=ft.FontWeight.BOLD, text_align=ft.TextAlign.CENTER),
                        ft.Text("Fijate que tengas conexión a internet y tocá 'Reintentar'.", size=14, color=ft.Colors.GREY_700, text_align=ft.TextAlign.CENTER),
                        boton_reintentar,
                        mostrar_volver=False,
                    )
                    return

            marcar_usuario_completado_hoy()
            historial.clear()
            historial_adelante.clear()

            pantalla(
                ft.Icon(ft.Icons.CHECK_CIRCLE, color=ft.Colors.GREEN, size=60),
                ft.Text("¡Muchas gracias!", size=24, weight=ft.FontWeight.BOLD),
                ft.Text("Volviendo al menú de inicio...", size=14, color=ft.Colors.GREY_700),
                mostrar_volver=False,
            )
            time.sleep(1.5)
            ir_a(mostrar_dashboard)

        threading.Thread(target=_enviar, daemon=True).start()

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