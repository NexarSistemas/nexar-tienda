from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, url_for

from licensing.permisos import modulo_activo
from modules.arca.services.arca_client import probar_conexion
from modules.arca.services.comprobantes_service import listar_comprobantes
from modules.arca.services.config_service import (
    obtener_configuracion,
    obtener_estado_modulo,
    guardar_configuracion,
)
from routes.main import admin_required


arca_bp = Blueprint("arca", __name__, url_prefix="/arca")


def _redirect_inactivo():
    flash("El módulo ARCA no está activo para esta instalación.", "warning")
    return redirect(url_for("dashboard"))


@arca_bp.before_request
def _validar_modulo_activo():
    if not modulo_activo("arca_facturacion"):
        return _redirect_inactivo()
    return None


@arca_bp.route("/")
@admin_required
def estado():
    estado_modulo = obtener_estado_modulo()
    return render_template(
        "arca/estado.html",
        estado_modulo=estado_modulo,
        config=estado_modulo["configuracion"],
        conexion=probar_conexion(),
    )


@arca_bp.route("/config", methods=["GET", "POST"])
@admin_required
def config():
    if request.method == "POST":
        form_data = {
            "cuit": request.form.get("cuit", ""),
            "razon_social": request.form.get("razon_social", ""),
            "condicion_fiscal": request.form.get("condicion_fiscal", ""),
            "punto_venta": request.form.get("punto_venta", ""),
            "ambiente": request.form.get("ambiente", "homologacion"),
            "activo": request.form.get("activo", ""),
        }
        try:
            guardar_configuracion(form_data)
        except ValueError as exc:
            flash(str(exc), "warning")
            return render_template("arca/config.html", config={**obtener_configuracion(), **form_data})
        flash("Configuración ARCA guardada correctamente.", "success")
        return redirect(url_for("arca.config"))

    return render_template("arca/config.html", config=obtener_configuracion())


@arca_bp.route("/comprobantes")
@admin_required
def comprobantes():
    return render_template(
        "arca/comprobantes.html",
        comprobantes=listar_comprobantes(),
    )
