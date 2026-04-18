from flask import Blueprint, current_app, flash, redirect, render_template, request, session
from services.license_storage import guardar_licencia, cargar_licencia
from services.supabase_license_api import (
    PRODUCTO_DEFAULT,
    activate_license,
    generate_activation_id,
    is_configured as supabase_configured,
)

main_bp = Blueprint("main", __name__)


def _render(nombre_template: str, **context):
    try:
        return render_template(nombre_template, **context)
    except Exception:
        titulo = nombre_template.replace(".html", "").replace("_", " ").title()
        return render_template(
            "placeholder.html",
            pagina=titulo,
            detalle="Esta pantalla aún no está conectada al backend en esta rama.",
        )


@main_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        if not username or not password:
            flash("⚠️ Usuario y contraseña son obligatorios.")
            return render_template("login.html")
        session["user"] = {
            "nombre_completo": username.title(),
            "username": username,
            "rol": "admin",
        }
        return redirect("/")
    return render_template("login.html")


@main_bp.route("/recuperar-password")
def recuperar_password():
    return _render("recuperar_password.html")


@main_bp.route("/apagar-rapido", methods=["POST"])
def apagar_rapido():
    session.clear()
    return _render("apagado.html")


@main_bp.route("/shutdown", methods=["POST"])
def shutdown():
    fn = request.environ.get("werkzeug.server.shutdown")
    if fn:
        fn()
        return ("", 204)
    current_app.logger.info("Shutdown solicitado, pero no disponible en este servidor.")
    return ("", 202)


@main_bp.route("/en-construccion/<path:endpoint>")
def endpoint_en_construccion(endpoint: str):
    return render_template(
        "placeholder.html",
        pagina=endpoint,
        detalle="Este enlace existe en la UI pero aún no tiene ruta funcional en esta rama.",
    )


@main_bp.route("/")
def dashboard():
    stats = {
        "temporada": "Ninguna",
        "ventas_hoy": 0,
        "monto_hoy": 0,
        "alertas": {"critico": 0, "sin_stock": 0, "bajo": 0},
        "ultimas_ventas": [],
    }
    return render_template("dashboard.html", stats=stats)


@main_bp.route("/productos")
def productos():
    return _render("productos.html")


@main_bp.route("/stock")
def stock():
    return _render("stock.html")


@main_bp.route("/temporadas")
def temporadas():
    return _render("temporadas.html")


@main_bp.route("/punto-venta")
def punto_venta():
    return _render("punto_venta.html")


@main_bp.route("/historial")
def historial():
    return _render("historial.html")


@main_bp.route("/compras")
def compras():
    return _render("compras.html")


@main_bp.route("/caja")
def caja():
    return _render("caja.html")


@main_bp.route("/gastos")
def gastos():
    return _render("gastos.html")


@main_bp.route("/clientes")
def clientes():
    return _render("clientes.html")


@main_bp.route("/proveedores")
def proveedores():
    return _render("proveedores.html")


@main_bp.route("/reportes")
def reportes():
    return _render("reportes.html")


@main_bp.route("/estadisticas")
def estadisticas():
    return _render("estadisticas.html")


@main_bp.route("/analisis")
def analisis():
    return _render("analisis.html")


@main_bp.route("/perfil")
def perfil():
    return _render("perfil.html")


@main_bp.route("/config")
def config():
    return _render("config.html")


@main_bp.route("/licencia")
def licencia():
    machine_id, machine_details = generate_activation_id(session.get("user", {}).get("username", ""))
    local_lic = cargar_licencia() or {}
    license_key_local = local_lic.get("license_key", "")

    return _render(
        "licencia.html",
        supabase_ok=supabase_configured(),
        machine_id=machine_id,
        machine_details=machine_details,
        producto=PRODUCTO_DEFAULT,
        license_key_local=license_key_local,
    )


@main_bp.route("/licencia/activar", methods=["POST"])
def licencia_activar():
    machine_id = request.form.get("machine_id", "").strip()
    license_key = request.form.get("license_key", "").strip()
    ok, msg, row = activate_license(license_key=license_key, machine_id=machine_id)
    if ok:
        guardar_licencia(license_key)
        titular = (row or {}).get("usuario", "—")
        flash(f"✅ {msg} Titular: {titular}.")
    else:
        flash(f"❌ {msg}")
    return redirect("/licencia")


@main_bp.route("/usuarios")
def usuarios():
    return _render("usuarios.html")


@main_bp.route("/respaldo")
def respaldo():
    return _render("respaldo.html")


@main_bp.route("/ayuda")
def ayuda():
    return _render("ayuda.html")


@main_bp.route("/changelog")
def changelog():
    return _render("changelog.html")


@main_bp.route("/acerca")
def acerca():
    return _render("acerca.html")


@main_bp.route("/logout")
def logout():
    session.clear()
    return redirect("/")


@main_bp.route("/apagar", methods=["POST"])
def apagar_sistema():
    session.clear()
    return _render("apagado.html")
