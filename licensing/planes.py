import os


TECHNICAL_FULL_PLAN = "MENSUAL_FULL"
COMMERCIAL_FULL_LABEL = "FULL"
SIN_PLAN = "SIN_PLAN"
COMMERCIAL_PLAN_ORDER = ("BASICA", "PRO", TECHNICAL_FULL_PLAN)

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


def get_commercial_plan_options() -> list[dict[str, str]]:
    return [
        {
            "plan": plan,
            "plan_display": get_plan_display_name(plan),
        }
        for plan in COMMERCIAL_PLAN_ORDER
    ]


def get_plan_actions(
    plan_actual: str | None,
    *,
    basica_activada: bool = False,
    licencia_vencida: bool = False,
    tiene_checkout: bool = True,
) -> dict[str, object]:
    raw_plan = str(plan_actual or "DEMO").strip().upper().replace("-", "_").replace(" ", "_")
    normalized_plan = SIN_PLAN if raw_plan == SIN_PLAN else normalize_plan(raw_plan, default="DEMO")

    effective_plan = normalized_plan
    if licencia_vencida:
        effective_plan = "BASICA" if basica_activada else SIN_PLAN

    if effective_plan == "BASICA":
        purchasable_plans = ["PRO", TECHNICAL_FULL_PLAN]
        title = "Plan BASICA activo"
        message = (
            "Tu licencia permanente BASICA sigue activa."
            if licencia_vencida and basica_activada
            else "Podés actualizar esta instalación a PRO o FULL."
        )
        alert_class = "info"
    elif effective_plan == "PRO":
        purchasable_plans = [TECHNICAL_FULL_PLAN]
        title = "Plan PRO activo"
        message = "Podés actualizar a FULL desde esta pantalla."
        alert_class = "primary"
    elif effective_plan == TECHNICAL_FULL_PLAN:
        purchasable_plans = []
        title = "Plan completo activo"
        message = "Esta instalación ya tiene el plan comercial más completo."
        alert_class = "success"
    elif effective_plan == SIN_PLAN:
        purchasable_plans = list(COMMERCIAL_PLAN_ORDER)
        title = "App limitada por licencia vencida"
        message = "La suscripción venció y no hay BASICA permanente para aplicar fallback."
        alert_class = "danger"
    else:
        purchasable_plans = list(COMMERCIAL_PLAN_ORDER)
        title = "Período de prueba activo"
        message = "Podés adquirir BASICA, PRO o FULL."
        alert_class = "warning"
        effective_plan = "DEMO"

    actions: list[dict[str, object]] = []
    for index, plan in enumerate(purchasable_plans):
        plan_display = get_plan_display_name(plan)
        verb = "Actualizar a" if effective_plan in {"BASICA", "PRO"} else "Adquirir"
        actions.append(
            {
                "plan": plan,
                "plan_display": plan_display,
                "button_label": f"{verb} {plan_display}",
                "is_primary": index == 0,
            }
        )

    manual_actions = [
        {
            "plan": action["plan"],
            "plan_display": action["plan_display"],
            "button_label": f"Solicitar {action['plan_display']}, manual",
        }
        for action in actions
    ]

    checkout_message = ""
    if actions and tiene_checkout:
        if effective_plan in {"DEMO", SIN_PLAN}:
            checkout_message = (
                "El checkout usa el backend existente de Nexar Pagos y abre Mercado Pago al continuar."
            )
        else:
            checkout_message = (
                "El checkout se abre en Mercado Pago y la licencia se refresca al volver a la app."
            )
    elif actions:
        checkout_message = (
            "Si todavía no ves checkout directo para esta instalación, podés continuar desde Licencia."
        )

    return {
        "plan_actual": effective_plan,
        "plan_display": "SIN PLAN" if effective_plan == SIN_PLAN else get_plan_display_name(effective_plan),
        "planes_comprables": purchasable_plans,
        "upgrades": purchasable_plans,
        "acciones": actions,
        "acciones_manuales": manual_actions,
        "mostrar_checkout": bool(actions) and bool(tiene_checkout),
        "mostrar_solicitud_manual": bool(actions),
        "mensaje_estado": message,
        "titulo_estado": title,
        "estado_clase": alert_class,
        "mensaje_checkout": checkout_message,
        "es_plan_completo": effective_plan == TECHNICAL_FULL_PLAN,
    }
