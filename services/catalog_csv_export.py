"""Neutral catalog-export application service.

This module only resolves the Nexar catalog into exportable product and variant
records. Provider column names and file rules intentionally live in adapters.
"""
from __future__ import annotations

import math
import unicodedata
from collections.abc import Iterator

import database as db
from services import product_variants


class CatalogExportValidationError(ValueError):
    """Raised when an active catalog record cannot be represented safely."""


def _clean_text(value) -> str:
    """Copy user-controlled text without modifying the persisted source value."""
    result = unicodedata.normalize("NFC", str(value or "")).replace("\x00", "").strip()
    # Spreadsheet applications can execute a cell that starts with these values.
    return "'" + result if result[:1] in ("=", "+", "-", "@") else result


def decimal_text(value, field: str, label: str) -> str:
    try:
        number = float(value or 0)
    except (TypeError, ValueError) as exc:
        raise CatalogExportValidationError(f"{label}: {field} debe ser numérico.") from exc
    if not math.isfinite(number) or number < 0:
        raise CatalogExportValidationError(f"{label}: {field} debe ser un número finito no negativo.")
    return format(number, ".15g")


def _catalog_query(search: str, category: str, provider: str, rubro: str):
    rubro_sql, rubro_params = db._build_rubro_compatible_filter_sql("p", rubro)
    conditions, params = ["p.activo=1", rubro_sql], list(rubro_params)
    if search:
        conditions.append("(p.codigo_interno LIKE ? OR p.codigo_barras LIKE ? OR p.descripcion LIKE ? OR p.categoria LIKE ? OR COALESCE(s.proveedor_habitual, '') LIKE ?)")
        params.extend([f"%{search}%"] * 5)
    if category:
        conditions.append("LOWER(COALESCE(p.categoria, '')) = ?")
        params.append(category.lower())
    if provider:
        conditions.append("LOWER(COALESCE(s.proveedor_habitual, '')) = ?")
        params.append(provider.lower())
    return (
        "SELECT p.*, COALESCE(s.stock_actual, 0) AS stock_actual "
        "FROM productos p LEFT JOIN stock s ON s.producto_id=p.id "
        "WHERE " + " AND ".join(conditions) + " ORDER BY p.descripcion, p.id",
        params,
    )


def iter_catalog_products(*, search="", category="", provider="", rubro="") -> Iterator[dict]:
    """Yield active, neutral catalog records in bounded batches.

    The product-list filters remain the single source for search, category,
    supplier and compatible-rubro visibility. Variants are loaded only for the
    product currently being serialized, not for the whole catalog.
    """
    sql, params = _catalog_query(
        str(search or "").strip(),
        str(category or "").strip(),
        str(provider or "").strip(),
        str(rubro or "").strip(),
    )
    conn = db.get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute(sql, params)
        while rows := cursor.fetchmany(100):
            for row in rows:
                product = dict(row)
                all_variants = product_variants.list_product_variants(int(product["id"]))
                yield {
                    "id": int(product["id"]),
                    "name": _clean_text(product.get("descripcion")),
                    "category": _clean_text(product.get("categoria")),
                    "brand": _clean_text(product.get("marca")),
                    "barcode": _clean_text(product.get("codigo_barras")),
                    "price": product.get("precio_venta"),
                    "cost": product.get("costo"),
                    "stock": product.get("stock_actual"),
                    "has_variants": bool(all_variants),
                    "variants": [item for item in all_variants if int(item.get("activo") or 0) == 1],
                }
    finally:
        conn.close()


def safe_text(value) -> str:
    """Normalize an adapter value with the same safe spreadsheet policy."""
    return _clean_text(value)
