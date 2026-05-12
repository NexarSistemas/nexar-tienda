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
UNIDADES_ALMACEN = ("unidad", "paquete", "kg", "litro", "docena")

UNIDADES_POR_RUBRO = {
    "tienda": UNIDADES_TIENDA,
    "almacen": UNIDADES_ALMACEN,
    "kiosco": UNIDADES_TIENDA,
    "regaleria": UNIDADES_TIENDA,
    "libreria": UNIDADES_TIENDA,
    "ferreteria": UNIDADES_TIENDA,
}

CATEGORIAS_TIENDA = (
    "Bijouterie",
    "Marroquineria",
    "Bazar",
    "Peluches",
    "Regaleria",
    "Jugueteria",
    "Papeleria",
    "Decoracion",
    "Adornos",
    "Accesorios",
    "Productos de Temporada",
    "Navidad",
    "Dia de la Madre",
    "Dia del Padre",
    "Otros",
)

CATEGORIAS_ALMACEN = (
    "Bebidas",
    "Lacteos",
    "Fiambres",
    "Carniceria",
    "Verduleria",
    "Frutas",
    "Panaderia",
    "Limpieza",
    "Perfumeria",
    "Golosinas",
    "Galletitas",
    "Pastas",
    "Arroz y legumbres",
    "Conservas",
    "Aceites y condimentos",
    "Congelados",
    "Mascotas",
    "Huevos",
    "Cigarrillos",
    "Varios",
)

CATEGORIAS_POR_RUBRO = {
    "tienda": CATEGORIAS_TIENDA,
    "almacen": CATEGORIAS_ALMACEN,
    "kiosco": CATEGORIAS_TIENDA,
    "regaleria": CATEGORIAS_TIENDA,
    "libreria": CATEGORIAS_TIENDA,
    "ferreteria": CATEGORIAS_TIENDA,
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


def _get_rubro_confirmado_desde_config(config=None):
    if not config:
        return None
    confirmado = str(config.get("rubro_negocio_confirmado", "") or "").strip().lower()
    if confirmado not in {"1", "true", "yes", "si", "on"}:
        return None
    rubro = str(config.get("rubro_negocio", "") or "").strip().lower()
    return rubro if rubro in RUBROS_DISPONIBLES else None


def get_rubro_actual(config=None):
    rubro_db = _get_rubro_confirmado_desde_config(config)
    if rubro_db:
        return rubro_db
    if config is None:
        try:
            from database import get_rubro_configurado

            rubro_db = get_rubro_configurado()
        except Exception:
            rubro_db = None
        if rubro_db:
            return rubro_db
    env_rubro = os.getenv("NEXAR_RUBRO", "").strip()
    if env_rubro:
        return normalizar_rubro(env_rubro)
    return DEFAULT_RUBRO


def es_almacen(config=None):
    return get_rubro_actual(config=config) == "almacen"


def get_unidades_disponibles(rubro=None, config=None):
    rubro_normalizado = normalizar_rubro(rubro or get_rubro_actual(config=config))
    return list(UNIDADES_POR_RUBRO.get(rubro_normalizado, UNIDADES_TIENDA))


def get_categorias_disponibles(rubro=None, config=None):
    rubro_normalizado = normalizar_rubro(rubro or get_rubro_actual(config=config))
    return list(CATEGORIAS_POR_RUBRO.get(rubro_normalizado, CATEGORIAS_TIENDA))


def get_categoria_default(rubro=None, config=None):
    categorias = get_categorias_disponibles(rubro=rubro, config=config)
    return categorias[0] if categorias else "Otros"


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
