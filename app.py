import os
from pathlib import Path
from typing import Any

from flask import Flask, redirect, request, session

from services.runtime_config import load_runtime_env

load_runtime_env()

import database as db
from routes.licencia import licencia_bp
from routes.main import main_bp
from services.license_storage import cargar_licencia
from services.license_sdk import validate_saved_license


def create_app() -> Flask:
    app = Flask(__name__)
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

    @app.context_processor
    def inject_global_vars() -> dict[str, Any]:
        def get_config_valor(key: str, default: Any = None) -> Any:
            config = db.get_config()
            return config.get(key, default)

        def get_licencia_status() -> dict[str, Any]:
            info = db.get_license_info()
            demo = db.get_demo_status()
            has_license = bool(cargar_licencia()) and info.get("tier") != "DEMO"
            license_expired = info.get("tier") == "DEMO" or (
                info.get("tier") == "MENSUAL_FULL" and bool(info.get("full_vencido"))
            )
            return {
                "es_demo": not has_license,
                "vencido": demo.get("vencido", False) if not has_license else license_expired,
                "tier": info.get("tier", "DEMO") if has_license else "DEMO",
                "dias_restantes": 0 if has_license else demo.get("dias_restantes", 0),
                "support": info.get("support", False),
                "updates": info.get("updates", False),
                "full_days": info.get("full_days"),
                "full_expires_soon": bool(info.get("pro_expires_soon")),
                "full_expires_tomorrow": bool(info.get("pro_expires_tomorrow")),
            }

        return {
            "get_config_valor": get_config_valor,
            "get_licencia_status": get_licencia_status,
            "app_version": app_version,
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

    @app.before_request
    def global_middleware():
        public_paths = (
            "/login",
            "/registro-inicial",
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

        # Permitir rutas libres de chequeo de licencia.
        if request.path.startswith(("/activar", "/licencia", "/static")):
            return None

        licencia = cargar_licencia()
        if not licencia:
            demo_status = db.get_demo_status()
            if not demo_status.get("vencido"):
                return None
            return redirect("/licencia")

        ok, _ = validate_saved_license(debug=True)
        if not ok:
            if db.get_license_info().get("tier") == "BASICA":
                return None
            return redirect("/licencia")

        return None

    app.register_blueprint(main_bp)
    app.register_blueprint(licencia_bp)

    def _legacy_url_build_error(error, endpoint, values):
        return f"/en-construccion/{endpoint}"

    app.url_build_error_handlers.append(_legacy_url_build_error)

    # Compatibilidad con templates legados que usan endpoints sin prefijo de blueprint.
    legacy_endpoints = [
        "registro_inicial",
        "login",
        "recuperar_password",
        "configurar_recuperacion",
        "dashboard",
        "productos",
        "producto_nuevo",
        "producto_editar",
        "producto_eliminar",
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
        "compras",
        "compra_nueva",
        "compra_detalle",
        "compra_eliminar",
        "caja",
        "caja_abrir",
        "caja_movimiento",
        "caja_cerrar",
        "gastos",
        "gasto_nuevo",
        "gasto_eliminar",
        "clientes",
        "cliente_nuevo",
        "cliente_editar",
        "cliente_detalle",
        "cliente_agregar_movimiento",
        "cliente_eliminar",
        "proveedores",
        "proveedor_nuevo",
        "proveedor_editar",
        "proveedor_detalle",
        "proveedor_agregar_movimiento",
        "proveedor_eliminar",
        "reportes",
        "estadisticas",
        "analisis",
        "perfil",
        "config",
        "config_categoria",
        "config_categoria_eliminar",
        "config_gasto_categoria",
        "config_gasto_categoria_eliminar",
        "config_gasto_categoria_editar",
        "licencia",
        "licencia_activar",
        "licencia_generar_desarrollador",
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
        "ayuda",
        "changelog",
        "acerca",
        "logout",
        "apagar_sistema",
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

    return app


# Compatibilidad con ejecuciones directas (`python app.py`).
app = create_app()
