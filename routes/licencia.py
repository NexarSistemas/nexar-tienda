from flask import Blueprint, render_template, request, redirect
from nexar_licencias import validar_licencia
from services.license_storage import guardar_licencia

licencia_bp = Blueprint("licencia", __name__)


@licencia_bp.route("/activar", methods=["GET"])
def activar_form():
    return render_template("activar.html")


@licencia_bp.route("/activar", methods=["POST"])
def activar():
    license_key = request.form.get("license_key")

    licencia = {
        "license_key": license_key
    }

    ok = validar_licencia(
        licencia,
        None,
        "nexar-tienda",
        debug=True
    )

    if ok:
        guardar_licencia(license_key)
        return redirect("/")
    else:
        return render_template("activar.html", error="Licencia inválida")