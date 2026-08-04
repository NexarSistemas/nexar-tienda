"""Neutral catalog-export application service.

This module only resolves the Nexar catalog into exportable product and variant
records. Provider column names and file rules intentionally live in adapters.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
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
        number = Decimal(str(value if value not in (None, "") else 0))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise CatalogExportValidationError(f"{label}: {field} debe ser numérico.") from exc
    if not number.is_finite() or number < 0:
        raise CatalogExportValidationError(f"{label}: {field} debe ser un número finito no negativo.")
    text = format(number, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def iter_catalog_products(*, search="", category="", provider="", rubro="") -> Iterator[dict]:
    """Yield active, neutral catalog records in bounded batches.

    The product-list filters remain the single source for search, category,
    supplier and compatible-rubro visibility. Variants are loaded only for the
    product currently being serialized, not for the whole catalog.
    """
    conn = db.get_conn()
    try:
        conn.execute("BEGIN")
        for rows in db.iter_productos(search=str(search or "").strip(), categoria=str(category or "").strip(), proveedor=str(provider or "").strip(), rubro=str(rubro or "").strip(), conn=conn):
            products = {int(row["id"]): dict(row) for row in rows}
            modern_products = {product_id: product for product_id, product in products.items() if str(product.get("stock_modo") or "legacy").strip().lower() == "variantes"}
            variants_by_product = product_variants.list_product_variants_for_products(modern_products, conn)
            for row in rows:
                product = dict(row)
                stock_mode = str(product.get("stock_modo") or "legacy").strip().lower()
                if stock_mode not in {"legacy", "variantes"}:
                    raise CatalogExportValidationError(f"Producto {product['id']}: stock_modo desconocido ({stock_mode}).")
                all_variants = variants_by_product.get(int(product["id"]), []) if stock_mode == "variantes" else []
                yield {
                    "id": int(product["id"]),
                    "name": _clean_text(product.get("descripcion")),
                    "category": _clean_text(product.get("categoria")),
                    "brand": _clean_text(product.get("marca")),
                    "barcode": _clean_text(product.get("codigo_barras")),
                    "price": product.get("precio_venta"),
                    "cost": product.get("costo"),
                    "stock": product.get("stock_actual"),
                    "stock_modo": stock_mode,
                    "has_variants": stock_mode == "variantes",
                    "variants": [item for item in all_variants if int(item.get("activo") or 0) == 1],
                }
    finally:
        conn.close()


def safe_text(value) -> str:
    """Normalize an adapter value with the same safe spreadsheet policy."""
    return _clean_text(value)
