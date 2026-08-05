"""Tiendanube CSV adapter for the neutral Nexar catalog export service."""
from __future__ import annotations

import csv
from collections.abc import Iterator
from decimal import Decimal
from io import StringIO
from tempfile import SpooledTemporaryFile

from services.catalog_csv_export import CatalogExportValidationError, decimal_text, iter_catalog_products, safe_text


# Fixture version: Tiendanube Argentina help centre, updated 2026-07-17.
# Unsupported columns are deliberately emitted blank to preserve the provider's
# current template contract without introducing them into the Nexar domain.
CSV_COLUMNS = (
    "Identificador de URL", "Nombre", "Categorías",
    "Nombre de propiedad 1", "Valor de propiedad 1",
    "Nombre de propiedad 2", "Valor de propiedad 2",
    "Nombre de propiedad 3", "Valor de propiedad 3",
    "Precio", "Precio promocional", "Peso", "Alto", "Ancho", "Profundidad",
    "Stock", "SKU", "Código de barras", "Mostrar en tienda", "Envío sin cargo",
    "Descripción", "Tags", "Título para SEO", "Descripción para SEO", "Marca",
    "Producto físico", "MPN", "Sexo", "Rango de edad", "Costo",
)


def _url_identifier(product: dict) -> str:
    """Stable external identity: product names are editable in Nexar."""
    return f"nexar-{product['id']}"


def _category_text(value) -> str:
    """Escape Tiendanube's category separators without altering Unicode text."""
    return str(value or "").replace("\\", "\\\\").replace(",", "\\,").replace(">", "\\>")


def _label(product: dict, variant: dict | None = None) -> str:
    return f"Producto {product['id']}" + (f", variante {variant.get('id')}" if variant else "")


def _variant_values(product: dict, variant: dict) -> list[tuple[str, str]]:
    attributes = variant.get("atributos") or []
    if not attributes:
        raise CatalogExportValidationError(f"{_label(product, variant)}: una variante exportable requiere atributos.")
    if len(attributes) > 3:
        raise CatalogExportValidationError(f"{_label(product, variant)}: Tiendanube admite hasta 3 atributos por variante.")
    values = [(safe_text(item.get("attribute_name")), safe_text(item.get("value_name"))) for item in attributes]
    if any(not name or not value for name, value in values):
        raise CatalogExportValidationError(f"{_label(product, variant)}: atributo y valor son obligatorios.")
    if len({name.casefold() for name, _ in values}) != len(values):
        raise CatalogExportValidationError(f"{_label(product, variant)}: contiene atributos repetidos.")
    return values


def _commercial_values(product: dict, variant: dict | None) -> tuple[str, str, str, str, str]:
    source = variant or product
    label = _label(product, variant)
    price = decimal_text(source.get("precio", product.get("price")), "precio", label)
    cost = decimal_text(source.get("costo", product.get("cost")), "costo", label)
    stock = decimal_text(source.get("stock_actual", product.get("stock")), "stock", label)
    promotional = source.get("precio_promocional")
    promo = "" if promotional in (None, "") else decimal_text(promotional, "precio promocional", label)
    if promo and Decimal(promo) >= Decimal(price):
        raise CatalogExportValidationError(f"{label}: el precio promocional debe ser menor que el precio.")
    return price, promo, cost, stock, safe_text(source.get("sku"))


def _validate_product(product: dict) -> None:
    if not product["name"]:
        raise CatalogExportValidationError(f"Producto {product['id']}: el nombre es obligatorio.")
    variants = product["variants"]
    if product["has_variants"] and not variants:
        raise CatalogExportValidationError(f"Producto {product['id']}: todas sus variantes están inactivas; no puede exportarse como producto simple.")
    if variants:
        seen = set()
        for variant in variants:
            attributes = tuple(_variant_values(product, variant))
            if attributes in seen:
                raise CatalogExportValidationError(f"{_label(product, variant)}: combinación de atributos duplicada.")
            seen.add(attributes)
            _commercial_values(product, variant)
    else:
        _commercial_values(product, None)


def validate_catalog(**filters) -> None:
    """Validate every selected record before starting the download stream."""
    errors = []
    for product in iter_catalog_products(**filters):
        try:
            _validate_product(product)
        except CatalogExportValidationError as exc:
            errors.append(str(exc))
            if len(errors) == 10:
                break
    if errors:
        suffix = " Se muestran los primeros 10 errores." if len(errors) == 10 else ""
        raise CatalogExportValidationError("No se generó el CSV: " + " ".join(errors) + suffix)


def _row(product: dict, variant: dict | None, *, first_for_product: bool) -> list[str]:
    attributes = _variant_values(product, variant) if variant else []
    price, promo, cost, stock, sku = _commercial_values(product, variant)
    values = {
        "Identificador de URL": _url_identifier(product),
        "Nombre": product["name"] if first_for_product else "",
        "Categorías": _category_text(product["category"]) if first_for_product else "",
        "Precio": price,
        "Precio promocional": promo,
        "Stock": stock,
        "SKU": sku,
        "Código de barras": safe_text((variant or product).get("codigo_barras") or (variant or product).get("barcode")),
        "Mostrar en tienda": "SI" if first_for_product else "",
        "Marca": product["brand"] if first_for_product else "",
        "Producto físico": "",
        "Costo": cost,
    }
    for index, (name, value) in enumerate(attributes, start=1):
        values[f"Nombre de propiedad {index}"] = name
        values[f"Valor de propiedad {index}"] = value
    return [values.get(column, "") for column in CSV_COLUMNS]


def iter_rows(**filters) -> Iterator[list[str]]:
    for product in iter_catalog_products(**filters):
        variants = product["variants"]
        if variants:
            for index, variant in enumerate(variants):
                yield _row(product, variant, first_for_product=index == 0)
        else:
            yield _row(product, None, first_for_product=True)


def _serialize_row(row: list[str]) -> str:
    output = StringIO(newline="")
    csv.writer(output, lineterminator="\r\n").writerow(row)
    return output.getvalue()


def iter_csv(**filters) -> Iterator[str]:
    """Yield an UTF-8-with-BOM, comma-delimited provider file incrementally."""
    yield "\ufeff"
    yield _serialize_row(list(CSV_COLUMNS))
    yield from (_serialize_row(row) for row in iter_rows(**filters))


def build_csv_file(**filters):
    """Create the whole validated download before HTTP begins streaming it.

    The spooled file keeps small exports in memory and transparently spills
    larger catalogs to disk, while the catalog iterator holds one read snapshot.
    """
    output = SpooledTemporaryFile(max_size=1024 * 1024, mode="w+t", encoding="utf-8", newline="")
    try:
        output.write("\ufeff")
        output.write(_serialize_row(list(CSV_COLUMNS)))
        for product in iter_catalog_products(**filters):
            _validate_product(product)
            variants = product["variants"]
            if variants:
                for index, variant in enumerate(variants):
                    output.write(_serialize_row(_row(product, variant, first_for_product=index == 0)))
            else:
                output.write(_serialize_row(_row(product, None, first_for_product=True)))
        output.seek(0)
        return output
    except Exception:
        output.close()
        raise


def download_name(today) -> str:
    return f"catalogo_tiendanube_{today:%Y%m%d}.csv"
