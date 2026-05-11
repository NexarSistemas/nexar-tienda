from __future__ import annotations

from datetime import date, datetime
from typing import Iterable, Mapping


def _to_float(value) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _get_value(item: Mapping, key: str, default=None):
    try:
        return item[key]
    except Exception:
        return default


def _coerce_date(value) -> date | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw).date()
    except ValueError:
        return None


def calcular_saldo_cliente_desde_movimientos(movimientos: Iterable[Mapping]) -> float:
    """
    Fuente de verdad de clientes: cc_clientes_mov.

    La reconciliacion con ventas sigue dependiendo de venta_id en el modelo actual.
    """
    saldo = 0.0
    for movimiento in movimientos:
        saldo += _to_float(_get_value(movimiento, "debe")) - _to_float(_get_value(movimiento, "haber"))
    return saldo


def calcular_saldo_factura(factura: Mapping) -> float:
    return _to_float(_get_value(factura, "importe")) - _to_float(_get_value(factura, "pagado"))


def calcular_estado_factura(factura: Mapping, hoy=None) -> str:
    saldo = calcular_saldo_factura(factura)
    if saldo <= 0:
        return "PAGADA"

    fecha_vencimiento = _coerce_date(_get_value(factura, "fecha_vencimiento"))
    if fecha_vencimiento is None:
        return "VIGENTE"

    if hoy is None:
        hoy_date = date.today()
    elif isinstance(hoy, datetime):
        hoy_date = hoy.date()
    elif isinstance(hoy, date):
        hoy_date = hoy
    else:
        hoy_date = _coerce_date(hoy) or date.today()

    if fecha_vencimiento < hoy_date:
        return "VENCIDA"
    if (fecha_vencimiento - hoy_date).days <= 7:
        return "POR VENCER"
    return "VIGENTE"


def calcular_deuda_proveedor_desde_facturas(facturas: Iterable[Mapping]) -> float:
    """
    Fuente de verdad futura de proveedores: facturas_proveedores.

    cc_proveedores_mov queda como legado/libro auxiliar y no debe usarse como
    fuente principal de deuda comercial.
    """
    deuda = 0.0
    for factura in facturas:
        saldo = calcular_saldo_factura(factura)
        if saldo > 0:
            deuda += saldo
    return deuda
