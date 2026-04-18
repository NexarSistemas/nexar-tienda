import importlib
import os
import sys

from flask import Blueprint, redirect, render_template, request

from services.license_storage import guardar_licencia

licencia_bp = Blueprint("licencia", __name__)


def _import_validar_licencia():
    sdk_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "nexar_licencias"))
    if sdk_path not in sys.path:
        sys.path.append(sdk_path)

    try:
        module = importlib.import_module("nexar_licencias")
    except Exception:
        return None

    return getattr(module, "validar_licencia", None)


@licencia_bp.route("/activar", methods=["GET"])
def activar_form():
    return render_template("activar.html")


@licencia_bp.route("/activar", methods=["POST"])
def activar():
    license_key = request.form.get("license_key", "").strip()

    if not license_key:
        return render_template("activar.html", error="Ingresá una licencia válida")

    licencia = {"license_key": license_key}
    validar_licencia = _import_validar_licencia()

    if validar_licencia is None:
        # Permite desarrollo local sin dependencia externa.
        guardar_licencia(license_key)
        return redirect("/")

    try:
        ok = validar_licencia(licencia, None, "nexar-tienda", debug=True)
    except Exception:
        ok = False

    if ok:
        guardar_licencia(license_key)
        return redirect("/")

    return render_template("activar.html", error="Licencia inválida")
