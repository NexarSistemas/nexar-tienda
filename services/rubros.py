import os

DEFAULT_RUBRO = "tienda"
RUBROS_DISPONIBLES = (
    "tienda",
    "almacen",
    "kiosco",
    "regaleria",
    "libreria",
    "ferreteria",
)

UNIDADES_TIENDA = ("unidad", "paquete")
UNIDADES_ALMACEN = ("unidad", "paquete", "kg", "gramo", "litro", "ml", "docena")

UNIDADES_POR_RUBRO = {
    "tienda": UNIDADES_TIENDA,
    "almacen": UNIDADES_ALMACEN,
    "kiosco": UNIDADES_TIENDA,
    "regaleria": UNIDADES_TIENDA,
    "libreria": UNIDADES_TIENDA,
    "ferreteria": UNIDADES_TIENDA,
}

UNIDAD_LABELS = {
    "unidad": "Unidad",
    "paquete": "Paquete",
    "kg": "Kg",
    "gramo": "Gramo",
    "litro": "Litro",
    "ml": "Ml",
    "docena": "Docena",
}

UNIDAD_ALIASES = {
    "unidad": "unidad",
    "u": "unidad",
    "paquete": "paquete",
    "pack": "paquete",
    "kg": "kg",
    "kilo": "kg",
    "kilogramo": "kg",
    "gramo": "gramo",
    "gramos": "gramo",
    "gr": "gramo",
    "litro": "litro",
    "litros": "litro",
    "lt": "litro",
    "ml": "ml",
    "docena": "docena",
    "docenas": "docena",
}


def get_rubros_disponibles():
    return list(RUBROS_DISPONIBLES)


def normalizar_rubro(value):
    rubro = str(value or "").strip().lower()
    return rubro if rubro in RUBROS_DISPONIBLES else DEFAULT_RUBRO


def get_rubro_actual(config=None):
    env_rubro = os.getenv("NEXAR_RUBRO", "").strip()
    if env_rubro:
        return normalizar_rubro(env_rubro)
    if config:
        return normalizar_rubro(config.get("rubro_negocio"))
    return DEFAULT_RUBRO


def es_almacen(config=None):
    return get_rubro_actual(config=config) == "almacen"


def get_unidades_disponibles(rubro=None):
    rubro_normalizado = normalizar_rubro(rubro or DEFAULT_RUBRO)
    return list(UNIDADES_POR_RUBRO.get(rubro_normalizado, UNIDADES_TIENDA))


def normalizar_unidad(value, rubro=None):
    unidad = str(value or "").strip().lower()
    if not unidad:
        return "unidad"
    unidad_normalizada = UNIDAD_ALIASES.get(unidad, unidad)
    unidades_rubro = set(get_unidades_disponibles(rubro))
    return unidad_normalizada if unidad_normalizada in unidades_rubro else unidad_normalizada


def get_unidad_label(value):
    unidad_normalizada = normalizar_unidad(value)
    if unidad_normalizada in UNIDAD_LABELS:
        return UNIDAD_LABELS[unidad_normalizada]
    return unidad_normalizada.replace("_", " ").capitalize()
