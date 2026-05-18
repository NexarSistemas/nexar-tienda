import os
from datetime import date


TECHNICAL_FULL_PLAN = "FULL"
LEGACY_FULL_PLAN = "MENSUAL_FULL"
COMMERCIAL_FULL_LABEL = "FULL"
SIN_PLAN = "SIN_PLAN"
COMMERCIAL_PLAN_ORDER = ("BASICA", "PRO", TECHNICAL_FULL_PLAN)
PLANES_CON_ACTUALIZACIONES = ("PRO", TECHNICAL_FULL_PLAN)

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
    "DEMO": {"core", "reportes"},
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


def get_update_access_context(license_info: dict[str, object] | None) -> dict[str, object]:
    info = license_info or {}
    plan_value = (
        info.get("plan_efectivo")
        or info.get("effective_plan")
        or info.get("tier")
        or info.get("plan")
        or "DEMO"
    )
    normalized_plan = _normalize_status_plan(str(plan_value), default="DEMO")
    plan_display = "SIN PLAN" if normalized_plan == SIN_PLAN else get_plan_display_name(normalized_plan)
    updates_enabled = bool(info.get("updates"))
    puede_actualizar = normalized_plan in PLANES_CON_ACTUALIZACIONES and updates_enabled

    if puede_actualizar:
        mensaje = "Tu plan incluye actualizaciones normales de la aplicacion."
    elif normalized_plan == "BASICA":
        mensaje = "Las actualizaciones normales estan disponibles para PRO y FULL. BASICA mantiene fixes criticos y mantenimiento basico."
    else:
        mensaje = "Las actualizaciones normales estan disponibles para PRO y FULL."

    return {
        "plan": normalized_plan,
        "plan_display": plan_display,
        "puede_actualizar": puede_actualizar,
        "mensaje": mensaje,
    }


def get_plan_actions(
    plan_actual: str | None,
    *,
    basica_activada: bool = False,
    licencia_vencida: bool = False,
    tiene_checkout: bool = True,
    plan_original: str | None = None,
    dias_para_vencer: int | None = None,
) -> dict[str, object]:
    raw_plan = str(plan_actual or "DEMO").strip().upper().replace("-", "_").replace(" ", "_")
    normalized_plan = SIN_PLAN if raw_plan == SIN_PLAN else normalize_plan(raw_plan, default="DEMO")
    normalized_original = _normalize_status_plan(plan_original, default=normalized_plan)

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

    renewal_plan = normalized_original if normalized_original in {"PRO", TECHNICAL_FULL_PLAN} else ""
    renewal_display = get_plan_display_name(renewal_plan) if renewal_plan else ""
    renewal_available = bool(renewal_plan)
    renewal_highlighted = False
    renewal_cta = ""
    renewal_text = ""

    if renewal_available:
        renewal_text = "La renovacion actual es manual. Al pagar nuevamente se extendera tu licencia."
        if licencia_vencida:
            renewal_cta = "Reactivar/Renovar plan"
            renewal_highlighted = True
        elif dias_para_vencer is not None and dias_para_vencer <= 7:
            renewal_cta = "Renovar ahora"
            renewal_highlighted = True
        else:
            renewal_cta = f"Renovar {renewal_display}"

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
        "puede_renovar": renewal_available,
        "plan_renovable": renewal_plan,
        "plan_renovable_display": renewal_display,
        "texto_renovacion": renewal_text,
        "cta_renovacion": renewal_cta,
        "renovacion_destacada": renewal_highlighted,
        "auto_renovacion": False,
        "puede_cancelar_auto_renovacion": False,
        "puede_activar_auto_renovacion": False,
        "texto_auto_renovacion": "Renovacion automatica: proximamente.",
    }


def _normalize_status_plan(plan: str | None, default: str = "DEMO") -> str:
    raw = str(plan or default).strip().upper().replace("-", "_").replace(" ", "_")
    if raw == SIN_PLAN:
        return SIN_PLAN
    return normalize_plan(raw, default=default)


def _get_remaining_days(expires_at: str | None) -> int | None:
    raw_value = str(expires_at or "").strip()
    if not raw_value:
        return None
    try:
        return (date.fromisoformat(raw_value) - date.today()).days
    except Exception:
        return None


def get_license_status_context(
    license_info: dict[str, object] | None,
    *,
    demo_status: dict[str, object] | None = None,
) -> dict[str, object]:
    info = license_info or {}
    plan_original = _normalize_status_plan(
        info.get("plan_original") or info.get("plan") or info.get("tier"),
        default="DEMO",
    )
    plan_efectivo = _normalize_status_plan(
        info.get("plan_efectivo") or info.get("effective_plan") or info.get("tier") or plan_original,
        default=plan_original,
    )
    licencia_vencida = bool(info.get("expirada"))
    basica_activada = bool(info.get("plan_base_permanente"))
    expires_at = str(info.get("expires_at") or "").strip()
    dias_para_vencer = _get_remaining_days(expires_at) if plan_original in {"PRO", "FULL"} else None
    plan_original_display = "SIN PLAN" if plan_original == SIN_PLAN else get_plan_display_name(plan_original)
    plan_efectivo_display = "SIN PLAN" if plan_efectivo == SIN_PLAN else get_plan_display_name(plan_efectivo)

    estado_comercial = "plan_activo"
    titulo_estado = f"Plan {plan_efectivo_display} activo"
    mensaje_estado = "La licencia actual esta activa."
    alert_class = "info"
    mostrar_aviso_preventivo = False
    mostrar_aviso_vencimiento = False
    recomendar_basica = False

    if plan_original == "BASICA":
        estado_comercial = "basica_permanente"
        titulo_estado = "Licencia BASICA permanente"
        mensaje_estado = "Tu licencia BASICA es permanente y no vence."
        alert_class = "info"
        dias_para_vencer = None
    elif plan_original in {"PRO", "FULL"} and licencia_vencida and basica_activada:
        estado_comercial = "mensual_vencido_con_basica"
        titulo_estado = f"Plan {plan_original_display} vencido"
        mensaje_estado = "Tu plan mensual vencio. Seguis usando BASICA porque tenes licencia permanente."
        alert_class = "warning"
        mostrar_aviso_vencimiento = True
    elif plan_original in {"PRO", "FULL"} and licencia_vencida:
        estado_comercial = "mensual_vencido_sin_plan"
        titulo_estado = f"Plan {plan_original_display} vencido"
        mensaje_estado = (
            "Tu plan mensual vencio y la app quedo limitada. "
            "Te recomendamos BASICA para no quedar bloqueado."
        )
        alert_class = "danger"
        mostrar_aviso_vencimiento = True
        recomendar_basica = True
    elif plan_original in {"PRO", "FULL"} and dias_para_vencer is not None and dias_para_vencer <= 7:
        estado_comercial = "mensual_por_vencer"
        titulo_estado = f"Plan {plan_original_display} por vencer"
        if dias_para_vencer <= 0:
            mensaje_estado = (
                f"Tu plan {plan_original_display} vence hoy. Podes renovar o actualizar tu licencia."
            )
        elif dias_para_vencer == 1:
            mensaje_estado = (
                f"Tu plan {plan_original_display} vence en 1 dia. Podes renovar o actualizar tu licencia."
            )
        else:
            mensaje_estado = (
                f"Tu plan {plan_original_display} vence en {dias_para_vencer} dias. "
                "Podes renovar o actualizar tu licencia."
            )
        alert_class = "warning"
        mostrar_aviso_preventivo = True
    elif plan_original in {"PRO", "FULL"}:
        estado_comercial = "mensual_activo"
        titulo_estado = f"Plan {plan_original_display} activo"
        mensaje_estado = "Tu plan mensual esta activo."
        alert_class = "success"
    elif plan_original == "DEMO":
        demo = demo_status or {}
        if bool(demo.get("vencido")):
            estado_comercial = "demo_vencido"
            titulo_estado = "Periodo demo vencido"
            mensaje_estado = "El demo vencio y no se convierte en BASICA automaticamente."
            alert_class = "warning"
        else:
            estado_comercial = "demo_activo"
            titulo_estado = "Periodo demo activo"
            mensaje_estado = "Estas usando el periodo de prueba."
            alert_class = "warning"
    elif plan_efectivo == SIN_PLAN:
        estado_comercial = "sin_plan"
        titulo_estado = "App limitada"
        mensaje_estado = "Esta instalacion no tiene un plan activo en este momento."
        alert_class = "danger"

    return {
        "plan_original": plan_original,
        "plan_original_display": plan_original_display,
        "plan_efectivo": plan_efectivo,
        "plan_efectivo_display": plan_efectivo_display,
        "licencia_vencida": licencia_vencida,
        "dias_para_vencer": dias_para_vencer,
        "basica_activada": basica_activada,
        "estado_comercial": estado_comercial,
        "titulo_estado": titulo_estado,
        "mensaje_estado": mensaje_estado,
        "alert_class": alert_class,
        "mostrar_revalidar": plan_original in {"PRO", "FULL"} and licencia_vencida,
        "mostrar_aviso_preventivo": mostrar_aviso_preventivo,
        "mostrar_aviso_vencimiento": mostrar_aviso_vencimiento,
        "recomendar_basica": recomendar_basica,
        "expires_at": expires_at,
    }
