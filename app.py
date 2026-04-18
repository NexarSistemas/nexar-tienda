from __future__ import annotations

import importlib
import os
import sys
from typing import Any

from flask import Flask, redirect, render_template, request, session

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

    @app.before_request
    def global_middleware():
        session.setdefault(
            "user",
            {
                "nombre_completo": "Rolo",
                "username": "rolo",
                "rol": "admin",
            },
        )

        # Permitir rutas libres.
        if request.path.startswith("/activar") or request.path.startswith("/static"):
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

    @app.route("/")
    def index():
        return render_template("index.html")

    app.register_blueprint(main_bp)
    app.register_blueprint(licencia_bp)

    return app


# Compatibilidad con ejecuciones directas (`python app.py`).
app = create_app()
