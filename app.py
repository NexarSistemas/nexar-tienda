from flask import Flask, request, redirect, render_template, session
from nexar_licencias import validar_licencia

app = Flask(__name__)
app.secret_key = "super-secret-key"

print("🔥 APP CARGADA")

@app.context_processor
def inject_global_vars():
    def get_config_valor(key, default=None):
        # MVP → después lo conectás a DB
        config = {
            "nombre_negocio": "Nexar Tienda"
        }
        return config.get(key, default)

    def get_licencia_status():
        # MVP → mock simple para que no rompa
        return {
            "es_demo": False,
            "vencido": False,
            "tier": "PRO",
            "dias_restantes": 30
        }

    return dict(
        get_config_valor=get_config_valor,
        get_licencia_status=get_licencia_status,
        app_version="1.0.0"
    )

def inject_global_vars():
    print("🔥 CONTEXT PROCESSOR ACTIVO")

@app.before_request
def global_middleware():
    # 🔹 Fake login (temporal)
    session['user'] = {
        "nombre_completo": "Rolo",
        "username": "rolo",
        "rol": "admin"
    }

@app.route("/")
def index():
    return render_template("index.html")

    # 🔹 Permitir rutas libres
    if request.path.startswith("/activar") or request.path.startswith("/static"):
        return

    from services.license_storage import cargar_licencia

    licencia = cargar_licencia()

    if not licencia:
        return redirect("/activar")

    try:
        validar_licencia(
            licencia,
            None,
            "nexar-tienda",
            debug=True
        )
    except Exception:
        return redirect("/activar")