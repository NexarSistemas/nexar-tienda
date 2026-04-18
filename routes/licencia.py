from flask import Blueprint, flash, redirect, request

from services.license_storage import guardar_licencia
from services.license_sdk import validate_license_key

licencia_bp = Blueprint("licencia", __name__)


@licencia_bp.route("/activar", methods=["GET"])
def activar_form():
    return redirect("/licencia")


@licencia_bp.route("/activar", methods=["POST"])
def activar():
    license_key = request.form.get("license_key", "").strip()
    ok, msg = validate_license_key(license_key, debug=True)

    if ok:
        guardar_licencia(license_key)
        flash("✅ Licencia activada correctamente.")
        return redirect("/")

    flash(f"❌ {msg}")
    return redirect("/licencia")
