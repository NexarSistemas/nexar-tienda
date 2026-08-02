import os
import hmac
import logging
import secrets
import sys
from pathlib import Path
from typing import Any

from flask import Flask, abort, redirect, render_template, request, session

from services.paths import get_path_layout
from services.runtime_config import load_runtime_env

load_runtime_env()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

import database as db
from licensing.planes import get_license_status_context, get_plan_display_name, get_update_access_context
from routes.licencia import licencia_bp
from routes.main import ensure_license_auto_refresh_thread, main_bp
from licensing.permisos import modulo_activo
from services.license_storage import cargar_licencia
from services.license_sdk import validate_saved_license
from services.rubros import get_rubro_actual
from services.update_checker import get_cached_update_info

APP_DISPLAY_NAME = "Nexar Comercio"
APP_INTERNAL_PRODUCT = "nexar-tienda"


def _is_test_process() -> bool:
    if os.getenv("PYTEST_CURRENT_TEST"):
        return True
    if "pytest" in sys.modules:
        return True

    argv = " ".join(str(arg).lower() for arg in sys.argv)
    return "unittest" in argv or "pytest" in argv


def create_app() -> Flask:
    path_layout = get_path_layout()
    logging.info("Ruta de datos activa: %s", path_layout.active_root)
    logging.info("Ruta de base SQLite activa: %s", path_layout.active_database_path)
    if path_layout.migration_performed:
        logging.info("Migracion automatica completada desde: %s", path_layout.migration_source)
    if path_layout.using_fallback:
        logging.warning("Se esta usando fallback temporal de datos: %s", path_layout.active_root)
    if path_layout.migration_error:
        logging.error("Error de migracion de datos: %s", path_layout.migration_error)
    app = Flask(__name__)
    if _is_test_process():
        app.config["TESTING"] = True
    db.init_db()
    secret_key = os.getenv("SECRET_KEY", "").strip()
    if not secret_key:
        raise RuntimeError("SECRET_KEY no definida. Configurar variable de entorno.")
    app.secret_key = secret_key
    version_file = Path(__file__).resolve().parent / "VERSION"
    app_version = "0.0.0"
    try:
        app_version = version_file.read_text(encoding="utf-8").strip() or app_version
    except Exception:
        pass
    app.config["APP_VERSION"] = app_version

    def csrf_token() -> str:
        token = session.get("_csrf_token")
        if not token:
            token = secrets.token_urlsafe(32)
            session["_csrf_token"] = token
            session.modified = True
        return token

    def validate_csrf_token() -> bool:
        expected = session.get("_csrf_token", "")
        provided = request.form.get("csrf_token", "") or request.headers.get("X-CSRFToken", "")
        return bool(expected and provided and hmac.compare_digest(expected, provided))

    @app.context_processor
    def inject_global_vars() -> dict[str, Any]:
        def get_config_valor(key: str, default: Any = None) -> Any:
            return db.get_config_valor(key, default)

        def get_licencia_status() -> dict[str, Any]:
            info = db.get_license_info()
            demo = db.get_demo_status()
            has_license = bool(cargar_licencia()) and info.get("tier") != "DEMO"
            status = get_license_status_context(info, demo_status=demo)
            license_expired = not bool(status.get("licencia_utilizable"))
            return {
                "es_demo": not has_license,
                "vencido": demo.get("vencido", False) if not has_license else license_expired,
                "tier": info.get("tier", "DEMO") if has_license else "DEMO",
                "tier_label": status.get("plan_efectivo_display", get_plan_display_name(info.get("tier", "DEMO"))) if has_license else "PRUEBA",
                "dias_restantes": 0 if has_license else demo.get("dias_restantes", 0),
                "support": info.get("support", False),
                "updates": info.get("updates", False),
                "full_days": info.get("full_days"),
                "full_expires_soon": bool(info.get("pro_expires_soon")),
                "full_expires_tomorrow": bool(info.get("pro_expires_tomorrow")),
                "estado_comercial": status.get("estado_comercial"),
                "mensaje_estado": status.get("mensaje_estado"),
            }

        lic_status = get_licencia_status() if "user" in session else None
        config = db.get_config()
        rubro_actual = get_rubro_actual(config)
        caja_abierta_actual = db.get_caja_abierta() if "user" in session else None

        return {
            "get_config_valor": get_config_valor,
            "get_licencia_status": get_licencia_status,
            "get_license_info": db.get_license_info,
            "get_plan_display_name": get_plan_display_name,
            "app_version": app_version,
            "app_display_name": APP_DISPLAY_NAME,
            "app_internal_product": APP_INTERNAL_PRODUCT,
            "rubro_actual_app": rubro_actual,
            "modulo_activo": modulo_activo,
            "update_info": (
                get_cached_update_info(app, app_version)
                if lic_status and get_update_access_context(lic_status).get("puede_actualizar")
                else {"available": False}
            ),
            "caja_abierta_actual": caja_abierta_actual,
            "csrf_token": csrf_token,
        }



    @app.template_filter("fmt_ars")
    def fmt_ars(value: Any) -> str:
        try:
            number = float(value or 0)
        except (TypeError, ValueError):
            number = 0.0
        entero, dec = f"{number:,.2f}".split(".")
        entero = entero.replace(",", ".")
        return f"$ {entero},{dec}"



    @app.template_filter("date")
    def format_date(value: Any) -> str:
        if value in (None, ""):
            return "-"
        text = str(value)
        for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
            try:
                from datetime import datetime

                return datetime.strptime(text[:19], fmt).strftime("%d/%m/%Y")
            except ValueError:
                continue
        return text

    @app.errorhandler(403)
    def forbidden(error):
        return render_template("403.html"), 403

    @app.before_request
    def global_middleware():
        if request.method in {"POST", "PUT", "PATCH", "DELETE"} and not validate_csrf_token():
            abort(400)

        public_paths = (
            "/login",
            "/registro-inicial",
            "/acuerdo-licencia",
            "/activar",
            "/static",
            "/recuperar-password",
            "/apagar-rapido",
            "/shutdown",
            "/en-construccion",
        )
        if request.path.startswith(public_paths):
            return None

        if db.count_usuarios() == 0:
            return redirect("/registro-inicial")

        if "user" not in session:
            return redirect("/login")

        recovery_allowed_paths = (
            "/configurar-recuperacion",
            "/logout",
            "/static",
            "/licencia",
            "/api/licencia/estado",
            "/mi-plan",
            "/api/desktop/close-warning",
            "/apagar-rapido",
            "/shutdown",
        )
        if not request.path.startswith(recovery_allowed_paths):
            user = db.q("SELECT security_question, security_answer_hash FROM usuarios WHERE id=?", (session["user"]["id"],), fetchone=True)
            if not user:
                session.clear()
                return redirect("/login")
            if user and (not user["security_question"] or not user["security_answer_hash"]):
                return redirect("/configurar-recuperacion")

        rubro_allowed_paths = (
            "/configuracion/rubro-inicial",
            "/logout",
            "/static",
            "/licencia",
            "/api/licencia/estado",
            "/mi-plan",
            "/api/desktop/close-warning",
            "/apagar-rapido",
            "/shutdown",
            "/ayuda",
            "/acerca",
            "/changelog",
        )
        if not request.path.startswith(rubro_allowed_paths) and db.necesita_configuracion_inicial_rubro():
            return redirect("/configuracion/rubro-inicial")

        license_info = db.get_license_info()
        if (
            license_info.get("tier") in {"BASICA", "PRO", "FULL"}
            and db.get_config_valor("activation_initial_completed", "1") == "0"
        ):
            db.set_config({"activation_initial_completed": "1"})

        activation_allowed_paths = (
            "/activacion-inicial",
            "/mi-plan",
            "/licencia",
            "/api/licencia/estado",
            "/configurar-recuperacion",
            "/configuracion/rubro-inicial",
            "/logout",
            "/static",
            "/api/desktop/close-warning",
            "/apagar",
            "/apagar-rapido",
            "/shutdown",
            "/acuerdo-licencia",
        )
        if (
            db.get_config_valor("activation_initial_completed", "1") == "0"
            and license_info.get("tier") not in {"BASICA", "PRO", "FULL"}
            and not request.path.startswith(activation_allowed_paths)
        ):
            return redirect("/activacion-inicial")

        if (
            db.get_config_valor("activation_initial_completed", "1") == "1"
            and license_info.get("tier") not in {"BASICA", "PRO", "FULL"}
        ):
            try:
                from routes.main import _retry_pending_demo_request_if_needed

                _retry_pending_demo_request_if_needed()
            except Exception:
                logger.exception("No se pudo reintentar el registro DEMO pendiente")

        # Permitir rutas libres de chequeo de licencia.
        license_allowed_paths = (
            "/activar",
            "/licencia",
            "/api/licencia/estado",
            "/configurar-recuperacion",
            "/mi-plan",
            "/api/desktop/close-warning",
            "/configuracion/rubro-inicial",
            "/logout",
            "/apagar",
            "/apagar-rapido",
            "/shutdown",
            "/static",
            "/ayuda",
            "/acerca",
            "/changelog",
        )
        if request.path.startswith(license_allowed_paths):
            return None

        demo_status = db.get_demo_status()
        if (
            license_info.get("tier") in {"DEMO", "SIN_PLAN"}
            and demo_status.get("demo")
            and not demo_status.get("vencido")
        ):
            return None

        license_status = get_license_status_context(license_info, demo_status=demo_status)
        if not bool(license_status.get("licencia_utilizable")):
            return redirect("/mi-plan")

        licencia = cargar_licencia()
        if not licencia:
            if not demo_status.get("vencido"):
                return None
            return redirect("/licencia")

        local_info = license_info
        if local_info.get("tier") in {"BASICA", "PRO", "FULL"}:
            return None

        ok, _ = validate_saved_license(debug=False)
        if not ok:
            cfg = db.get_config()
            current_info = db.get_license_info()
            current_status = get_license_status_context(current_info, demo_status=demo_status)
            if (
                cfg.get("basica_activada", "0") == "1"
                and current_info.get("plan_base_permanente")
                and current_status.get("plan_efectivo") == "BASICA"
                and bool(current_status.get("licencia_utilizable"))
            ):
                db.set_config({
                    "demo_mode": "0",
                    "license_tier": "BASICA",
                    "license_plan": "BASICA",
                    "license_expires_at": "",
                    "license_support": "0",
                    "license_updates": "0",
                })
                return None
            if current_info.get("tier") == "BASICA":
                return None
            if not demo_status.get("vencido") and local_info.get("tier") in {"DEMO", "SIN_PLAN"}:
                return None
            return redirect("/licencia")

        return None

    app.register_blueprint(main_bp)
    app.register_blueprint(licencia_bp)
    if modulo_activo("arca_facturacion"):
        from modules.arca import arca_bp

        app.register_blueprint(arca_bp)

    def _legacy_url_build_error(error, endpoint, values):
        return f"/en-construccion/{endpoint}"

    app.url_build_error_handlers.append(_legacy_url_build_error)

    # Compatibilidad con templates legados que usan endpoints sin prefijo de blueprint.
    legacy_endpoints = [
        "registro_inicial",
        "login",
        "recuperar_password",
        "configurar_recuperacion",
        "activacion_inicial",
        "dashboard",
        "productos",
        "productos_importar",
        "productos_importar_plantilla",
        "productos_importar_generar_plantilla",
        "productos_importar_abrir_carpeta",
        "productos_lote",
        "producto_nuevo",
        "producto_editar",
        "producto_eliminar",
        "producto_variantes_gestion",
        "producto_variantes_generar_previsualizar",
        "producto_variantes_generar_confirmar",
        "producto_variantes_activar_stock",
        "producto_variante_editar",
        "producto_variante_estado",
        "producto_variante_eliminar",
        "exportar_excel",
        "exportar_pdf",
        "stock",
        "stock_ajustar",
        "temporadas",
        "temporada_nueva",
        "temporada_editar",
        "temporada_eliminar",
        "punto_venta",
        "venta_finalizar",
        "ticket",
        "historial",
        "historial_detalle",
        "historial_eliminar",
        "compras",
        "compra_nueva",
        "compra_detalle",
        "compra_eliminar",
        "caja",
        "caja_detalle",
        "caja_abrir",
        "caja_movimiento",
        "caja_movimiento_anular",
        "caja_cerrar",
        "gastos",
        "gasto_nuevo",
        "gasto_editar",
        "gasto_eliminar",
        "clientes",
        "cliente_nuevo",
        "cliente_editar",
        "cliente_detalle",
        "cliente_agregar_movimiento",
        "cliente_anular_movimiento",
        "cliente_eliminar",
        "proveedores",
        "proveedor_nuevo",
        "proveedor_editar",
        "proveedor_detalle",
        "proveedor_facturas",
        "proveedor_factura_nueva",
        "proveedor_factura_editar",
        "proveedor_factura_pagar",
        "proveedor_factura_eliminar",
        "proveedor_agregar_movimiento",
        "proveedor_eliminar",
        "precios_proveedor",
        "precios_proveedor_previsualizar",
        "precios_proveedor_aplicar",
        "reportes",
        "estadisticas",
        "analisis",
        "rentabilidad_detallada",
        "auditoria",
        "perfil",
        "config",
        "configuracion_rubro_inicial",
        "mi_plan",
        "config_categoria",
        "config_categoria_editar",
        "config_categoria_toggle",
        "config_categoria_eliminar",
        "config_atributo_perfil_crear",
        "config_atributo_perfil_editar",
        "config_atributo_perfil_estado",
        "config_atributo_perfil_rubro",
        "config_gasto_categoria",
        "config_gasto_categoria_eliminar",
        "config_gasto_categoria_editar",
        "licencia",
        "licencia_activar",
        "licencia_solicitar",
        "usuarios",
        "usuario_nuevo",
        "usuario_editar",
        "usuario_toggle_activo",
        "usuario_eliminar",
        "respaldo",
        "respaldo_ahora",
        "respaldo_config",
        "respaldo_descargar",
        "respaldo_restaurar",
        "actualizacion_descargar",
        "actualizacion_abrir_carpeta",
        "actualizacion_instalar",
        "actualizacion_estado",
        "actualizacion_reiniciar",
        "actualizacion_limpiar_estado",
        "ayuda",
        "changelog",
        "acuerdo_licencia",
        "acerca",
        "logout",
        "desktop_close_warning",
        "salida_protegida_cerrar_app",
        "apagar_rapido",
        "apagar_sistema",
        "shutdown",
    ]
    for endpoint in legacy_endpoints:
        prefixed = f"main.{endpoint}"
        if prefixed in app.view_functions and endpoint not in app.view_functions:
            rules = [r for r in app.url_map.iter_rules() if r.endpoint == prefixed]
            if not rules:
                continue
            rule = rules[0]
            methods = sorted(m for m in rule.methods if m not in {"HEAD", "OPTIONS"})
            app.add_url_rule(
                rule.rule,
                endpoint=endpoint,
                view_func=app.view_functions[prefixed],
                methods=methods,
            )

    ensure_license_auto_refresh_thread(app)
    return app


# Compatibilidad con ejecuciones directas (`python app.py`).
app = create_app()


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.getenv("PORT", "5000")), debug=False)
