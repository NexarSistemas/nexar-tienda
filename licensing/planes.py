import os


TECHNICAL_FULL_PLAN = "MENSUAL_FULL"
COMMERCIAL_FULL_LABEL = "FULL"

TIER_ALIASES = {
    "BASIC": "BASICA",
    "BASICO": "BASICA",
    "BASICA": "BASICA",
    "PRO": "PRO",
    "FULL": TECHNICAL_FULL_PLAN,
    "MENSUAL": TECHNICAL_FULL_PLAN,
    "MENSUAL_FULL": TECHNICAL_FULL_PLAN,
    "TDA_BASICA": "BASICA",
    "TDA_PRO": TECHNICAL_FULL_PLAN,
}


PLANES = {
    "DEMO": {"core"},
    "BASICA": {"core", "clientes", "proveedores", "pos", "stock", "caja"},
    "PRO": {
        "core",
        "clientes",
        "proveedores",
        "pos",
        "stock",
        "caja",
        "compras",
        "gastos",
        "historial",
        "reportes",
        "export",
        "multiusuario",
    },
    TECHNICAL_FULL_PLAN: {
        "core",
        "clientes",
        "proveedores",
        "pos",
        "stock",
        "caja",
        "compras",
        "gastos",
        "historial",
        "reportes",
        "export",
        "multiusuario",
        "temporadas",
        "multinegocio",
    },
}


def normalize_plan(plan: str | None = None, default: str = "DEMO") -> str:
    raw = (plan or default).strip().upper().replace("-", "_").replace(" ", "_")
    normalized = TIER_ALIASES.get(raw, raw)
    return normalized if normalized in PLANES else default


def normalizar_plan(valor: str | None = None, default: str = "DEMO") -> str:
    return normalize_plan(valor, default=default)


def get_plan_display_name(plan: str | None = None) -> str:
    normalized = normalize_plan(plan, default="DEMO")
    return COMMERCIAL_FULL_LABEL if normalized == TECHNICAL_FULL_PLAN else normalized


def get_plan_activo() -> str:
    return normalize_plan(os.getenv("NEXAR_PLAN", "DEMO"))


def get_modulos_plan(plan: str | None = None) -> set[str]:
    plan_key = normalize_plan(plan or get_plan_activo())
    return set(PLANES.get(plan_key, PLANES["DEMO"]))


def get_modulos_extra() -> set[str]:
    raw_modules = os.getenv("NEXAR_MODULES", "")
    return {module.strip().lower() for module in raw_modules.split(",") if module.strip()}


def get_modulos_activos() -> set[str]:
    return get_modulos_plan() | get_modulos_extra()
