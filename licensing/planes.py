import os


PLANES = {
    "DEMO": {"core"},
    "BASICA": {"core", "clientes"},
    "PRO": {"core", "clientes", "reportes", "export", "temporadas"},
    "FULL": {
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


def get_plan_activo() -> str:
    plan = os.getenv("NEXAR_PLAN", "DEMO").strip().upper()
    return plan if plan in PLANES else "DEMO"


def get_modulos_plan(plan: str | None = None) -> set[str]:
    plan_key = (plan or get_plan_activo()).strip().upper()
    return set(PLANES.get(plan_key, PLANES["DEMO"]))


def get_modulos_extra() -> set[str]:
    raw_modules = os.getenv("NEXAR_MODULES", "")
    return {module.strip().lower() for module in raw_modules.split(",") if module.strip()}


def get_modulos_activos() -> set[str]:
    return get_modulos_plan() | get_modulos_extra()
