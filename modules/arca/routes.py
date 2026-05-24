from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, url_for

from licensing.permisos import modulo_activo
from modules.arca.services.arca_client import (
    obtener_estado_conexion,
    obtener_estado_wsfe,
    probar_conexion,
    probar_wsfe_conexion,
)
from modules.arca.services.certificados_service import (
    activar_certificado,
    listar_certificados,
    registrar_certificado,
)
from modules.arca.services.comprobantes_service import obtener_comprobante_por_id, listar_comprobantes
from modules.arca.services.facturacion_desde_venta_service import facturar_venta_desde_existente
from services.arca_config_service import (
    CONDICIONES_FISCALES_VALIDAS,
    get_config,
    obtener_estado_modulo,
    save_config,
)
from routes.main import admin_required


arca_bp = Blueprint("arca", __name__, url_prefix="/arca")


def _redirect_inactivo():
    flash("El módulo ARCA no está activo para esta instalación.", "warning")
    return redirect(url_for("dashboard"))


def _config_form_data() -> dict[str, object]:
    return {
        "cuit": request.form.get("cuit", ""),
        "razon_social": request.form.get("razon_social", ""),
        "condicion_fiscal": request.form.get("condicion_fiscal", ""),
        "punto_venta": request.form.get("punto_venta", ""),
        "ambiente": request.form.get("ambiente", "homologacion"),
        "certificado_path": request.form.get("certificado_path", ""),
        "key_path": request.form.get("key_path", ""),
        "certificado_vencimiento": request.form.get("certificado_vencimiento", ""),
        "activo": request.form.get("activo", ""),
    }


def _certificado_form_data() -> dict[str, object]:
    return {
        "nombre": request.form.get("nombre", ""),
        "ambiente": request.form.get("ambiente", "homologacion"),
        "cuit": request.form.get("cuit", ""),
        "certificado_path": request.form.get("certificado_path", ""),
        "key_path": request.form.get("key_path", ""),
        "vencimiento": request.form.get("vencimiento", ""),
        "observaciones": request.form.get("observaciones", ""),
    }


@arca_bp.before_request
def _validar_modulo_activo():
    if not modulo_activo("arca_facturacion"):
        return _redirect_inactivo()
    return None


@arca_bp.route("/")
@admin_required
def estado():
    estado_modulo = obtener_estado_modulo()
    conexion = obtener_estado_conexion()
    wsfe = obtener_estado_wsfe()
    return render_template(
        "arca/estado.html",
        estado_modulo=estado_modulo,
        config=estado_modulo["configuracion"],
        conexion=conexion,
        wsfe=wsfe,
    )


@arca_bp.route("/config", methods=["GET", "POST"])
@admin_required
def config():
    if request.method == "POST":
        form_data = _config_form_data()
        try:
            config_actualizada = save_config(form_data)
        except ValueError as exc:
            flash(str(exc), "warning")
            return render_template(
                "arca/config.html",
                config={**get_config(), **form_data},
                condiciones_fiscales=CONDICIONES_FISCALES_VALIDAS,
            )
        flash("Configuración ARCA guardada correctamente.", "success")
        return render_template(
            "arca/config.html",
            config=config_actualizada,
            condiciones_fiscales=CONDICIONES_FISCALES_VALIDAS,
        )

    return render_template(
        "arca/config.html",
        config=get_config(),
        condiciones_fiscales=CONDICIONES_FISCALES_VALIDAS,
    )


@arca_bp.route("/certificados", methods=["GET", "POST"])
@admin_required
def certificados():
    form_data = None
    if request.method == "POST":
        form_data = _certificado_form_data()
        try:
            registrar_certificado(form_data)
        except ValueError as exc:
            flash(str(exc), "warning")
        else:
            flash("Certificado ARCA registrado correctamente.", "success")
            return redirect(url_for("arca.certificados"))

    return render_template(
        "arca/certificados.html",
        certificados=listar_certificados(),
        form_data=form_data or {
            "nombre": "",
            "ambiente": "homologacion",
            "cuit": "",
            "certificado_path": "",
            "key_path": "",
            "vencimiento": "",
            "observaciones": "",
        },
    )


@arca_bp.route("/certificados/<int:certificado_id>/activar", methods=["POST"])
@admin_required
def certificados_activar(certificado_id: int):
    try:
        certificado = activar_certificado(certificado_id)
    except ValueError as exc:
        flash(str(exc), "warning")
    else:
        flash(
            f"Certificado '{certificado['nombre']}' activado para {certificado['ambiente']}.",
            "success",
        )
    return redirect(url_for("arca.certificados"))


@arca_bp.route("/probar-conexion", methods=["POST"])
@admin_required
def probar_conexion_route():
    resultado = probar_conexion()
    flash(resultado["mensaje"], "success" if resultado.get("ok") else "warning")
    return redirect(url_for("arca.estado"))


@arca_bp.route("/probar-wsfe", methods=["POST"])
@admin_required
def probar_wsfe_route():
    resultado = probar_wsfe_conexion()
    flash(resultado["mensaje"], "success" if resultado.get("ok") else "warning")
    return redirect(url_for("arca.estado"))


@arca_bp.route("/facturar-venta/<int:venta_id>", methods=["POST"])
@arca_bp.route("/ventas/<int:venta_id>/emitir", methods=["POST"])
@admin_required
def emitir_comprobante_venta_route(venta_id: int):
    resultado = facturar_venta_desde_existente(venta_id)
    category = "success" if resultado.get("ok") else "warning"
    flash(resultado["mensaje"], category)
    destino = request.form.get("next") or request.referrer or url_for("ticket", vid=venta_id)
    return redirect(destino)


@arca_bp.route("/comprobantes")
@admin_required
def comprobantes():
    return render_template(
        "arca/comprobantes.html",
        comprobantes=listar_comprobantes(),
    )


@arca_bp.route("/comprobantes/<int:comprobante_id>")
@admin_required
def comprobante_detalle(comprobante_id: int):
    comprobante = obtener_comprobante_por_id(comprobante_id)
    if not comprobante:
        flash("El comprobante ARCA indicado no existe.", "warning")
        return redirect(url_for("arca.comprobantes"))
    return render_template(
        "arca/comprobante_detalle.html",
        comprobante=comprobante,
    )
