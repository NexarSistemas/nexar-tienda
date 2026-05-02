import os


TIER_ALIASES = {
    "BASIC": "BASICA",
    "BASICO": "BASICA",
    "TDA_BASICA": "BASICA",
    "FULL": "MENSUAL_FULL",
    "MENSUAL": "MENSUAL_FULL",
    "PRO": "MENSUAL_FULL",
    "TDA_PRO": "MENSUAL_FULL",
}


PLANES = {
    "DEMO": {"core"},
    "BASICA": {"core", "clientes"},
    "MENSUAL_FULL": {
        "core",
        "clientes",
        "reportes",
        "export",
        "temporadas",
        "ia",
        "multinegocio",
        "multiusuario",
    },
}


def normalize_plan(plan: str | None = None, default: str = "DEMO") -> str:
    raw = (plan or default).strip().upper().replace("-", "_").replace(" ", "_")
    normalized = TIER_ALIASES.get(raw, raw)
    return normalized if normalized in PLANES else default


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
