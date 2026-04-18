from __future__ import annotations

import importlib
import os
import sys
from typing import Any

from flask import Flask, redirect, request, session

from routes.licencia import licencia_bp
from routes.main import main_bp
from services.license_storage import cargar_licencia


def _import_validar_licencia():
    """Importa el SDK de licencias de forma tolerante a errores."""
    sdk_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "nexar_licencias"))
    if sdk_path not in sys.path:
        sys.path.append(sdk_path)

    try:
        module = importlib.import_module("nexar_licencias")
    except Exception:
        return None

    return getattr(module, "validar_licencia", None)


def create_app() -> Flask:
    app = Flask(__name__)
    app.secret_key = os.getenv("FLASK_SECRET_KEY", "super-secret-key")

    @app.context_processor
    def inject_global_vars() -> dict[str, Any]:
        def get_config_valor(key: str, default: Any = None) -> Any:
            config = {"nombre_negocio": "Nexar Tienda"}
            return config.get(key, default)

        def get_licencia_status() -> dict[str, Any]:
            # Estado mínimo para no romper templates mientras se integra licenciamiento online.
            return {
                "es_demo": False,
                "vencido": False,
                "tier": "PRO",
                "dias_restantes": 30,
            }

        return {
            "get_config_valor": get_config_valor,
            "get_licencia_status": get_licencia_status,
            "app_version": "1.0.0",
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
            "/activar",
            "/static",
            "/recuperar-password",
            "/apagar-rapido",
            "/en-construccion",
        )
        if request.path.startswith(public_paths):
            return None

        if "user" not in session:
            return redirect("/login")

        # Permitir rutas libres de chequeo de licencia.
        if request.path.startswith(("/activar", "/static")):
            return None

        licencia = cargar_licencia()
        if not licencia:
            return redirect("/activar")

        validar_licencia = _import_validar_licencia()
        if validar_licencia is None:
            # Si el SDK no está instalado no bloqueamos el uso local.
            return None

        try:
            ok = validar_licencia(licencia, None, "nexar-tienda", debug=True)
        except Exception:
            return redirect("/activar")

        if not ok:
            return redirect("/activar")

        return None

    app.register_blueprint(main_bp)
    app.register_blueprint(licencia_bp)

    def _legacy_url_build_error(error, endpoint, values):
        return f"/en-construccion/{endpoint}"

    app.url_build_error_handlers.append(_legacy_url_build_error)

    # Compatibilidad con templates legados que usan endpoints sin prefijo de blueprint.
    legacy_endpoints = [
        "dashboard",
        "productos",
        "stock",
        "temporadas",
        "punto_venta",
        "historial",
        "compras",
        "caja",
        "gastos",
        "clientes",
        "proveedores",
        "reportes",
        "estadisticas",
        "analisis",
        "perfil",
        "config",
        "licencia",
        "usuarios",
        "respaldo",
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
