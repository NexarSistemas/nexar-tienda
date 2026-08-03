"""Neutral catalog-import application service.

Provider specific column names live only in the Tiendanube adapter below.  The
planner and writer consume the neutral dictionaries produced by that adapter.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import unicodedata
from io import StringIO

import database as db
from services import inventory, product_variants

MAX_BYTES = 5 * 1024 * 1024
MAX_ROWS = 2_000
MAX_PRODUCTS = 500
MAX_VARIANTS = 2_000
MAX_VARIANTS_PER_PRODUCT = 100
MAX_FIELD_LENGTH = 2_000


def _key(value: str) -> str:
    value = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(ch for ch in value if not unicodedata.combining(ch)).strip().casefold()


def _text(value, field: str, *, required=False) -> str:
    result = str(value or "").strip()
    if len(result) > MAX_FIELD_LENGTH:
        raise ValueError(f"{field}: supera {MAX_FIELD_LENGTH} caracteres")
    if result[:1] in ("=", "+", "-", "@"):
        raise ValueError(f"{field}: no admite valores que comienzan con formula")
    if required and not result:
        raise ValueError(f"{field}: es obligatorio")
    return result


def _number(value, field: str, *, required=False):
    raw = str(value or "").strip()
    if not raw:
        if required:
            raise ValueError(f"{field}: es obligatorio")
        return None
    try:
        result = float(raw.replace(",", "."))
    except ValueError as exc:
        raise ValueError(f"{field}: debe ser numerico") from exc
    if not math.isfinite(result) or result < 0:
        raise ValueError(f"{field}: debe ser un numero finito no negativo")
    return result


HEADER_ALIASES = {
    "url": {"identificador de url"}, "name": {"nombre"},
    "category": {"categorias", "categorías"}, "description": {"descripcion", "descripción"},
    "brand": {"marca"}, "price": {"precio"}, "cost": {"costo"}, "stock": {"stock"},
    "sku": {"sku"}, "barcode": {"codigo de barras", "código de barras"},
    "visible": {"mostrar en tienda"},
}
for index in range(1, 4):
    HEADER_ALIASES[f"attribute_{index}"] = {f"nombre de propiedad {index}", f"nombre propiedad {index}"}
    HEADER_ALIASES[f"value_{index}"] = {f"valor de propiedad {index}", f"valor propiedad {index}"}


def _column_map(headers):
    normalized = {_key(header): header for header in headers}
    mapped = {}
    for target, aliases in HEADER_ALIASES.items():
        matches = list({normalized[_key(alias)] for alias in aliases if _key(alias) in normalized})
        if len(matches) > 1:
            raise ValueError(f"Encabezado ambiguo para {target}")
        if matches:
            mapped[target] = matches[0]
    missing = [item for item in ("url", "name") if item not in mapped]
    if missing:
        raise ValueError("Encabezados incompatibles: faltan Identificador de URL o Nombre")
    return mapped


def parse_tiendanube_csv(content: bytes) -> list[dict]:
    if not content:
        raise ValueError("El archivo CSV esta vacio")
    if len(content) > MAX_BYTES:
        raise ValueError(f"El archivo supera el limite de {MAX_BYTES // (1024 * 1024)} MB")
    decoded = None
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            decoded = content.decode(encoding)
            break
        except UnicodeDecodeError:
            pass
    if decoded is None:
        raise ValueError("No se pudo leer el encoding del CSV")
    try:
        dialect = csv.Sniffer().sniff(decoded[:8192], delimiters=",;")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(StringIO(decoded), dialect=dialect)
    if not reader.fieldnames:
        raise ValueError("El archivo CSV esta vacio")
    columns = _column_map(reader.fieldnames)
    rows = []
    for number, raw in enumerate(reader, start=2):
        if number - 1 > MAX_ROWS:
            raise ValueError(f"El archivo supera el limite de {MAX_ROWS} filas")
        if None in raw or any(value is None for value in raw.values()):
            raise ValueError(f"Fila {number}: cantidad incorrecta de columnas")
        if not any(str(value or "").strip() for value in raw.values()):
            continue
        def get(name): return raw.get(columns.get(name, ""), "")
        try:
            attributes = []
            for index in range(1, 4):
                name, value = _text(get(f"attribute_{index}"), "atributo"), _text(get(f"value_{index}"), "valor")
                if bool(name) != bool(value):
                    raise ValueError("atributo y valor deben informarse juntos")
                if name: attributes.append({"name": name, "value": value})
            rows.append({"row": number, "external_group": _text(get("url"), "Identificador de URL", required=True),
                         "name": _text(get("name"), "Nombre"), "category": _text(get("category"), "Categorías"),
                         "description": _text(get("description"), "Descripción"), "brand": _text(get("brand"), "Marca"),
                         "price": _number(get("price"), "Precio"), "cost": _number(get("cost"), "Costo"),
                         "stock": _number(get("stock"), "Stock"), "sku": _text(get("sku"), "SKU"),
                         "barcode": _text(get("barcode"), "Código de barras"), "attributes": attributes,
                         "visible": _key(get("visible")) not in {"no", "false", "0"}})
        except ValueError as exc:
            raise ValueError(f"Fila {number}, {exc}") from exc
    if not rows: raise ValueError("El CSV no contiene filas importables")
    return rows


def build_plan(rows: list[dict]) -> dict:
    errors, warnings, products = [], [], {}
    sku_rows, barcode_rows = {}, {}
    for row in rows:
        for value, bucket, label in ((row["sku"], sku_rows, "SKU"), (row["barcode"], barcode_rows, "codigo de barras")):
            if value: bucket.setdefault(value.casefold(), []).append(row["row"])
        group = products.setdefault(row["external_group"], {"rows": [], "name": row["name"]})
        group["rows"].append(row)
    for label, values in (("SKU", sku_rows), ("codigo de barras", barcode_rows)):
        for value, numbers in values.items():
            if len(numbers) > 1: errors.append({"rows": numbers, "field": label, "cause": f"duplicado en el archivo: {value}"})
    if len(products) > MAX_PRODUCTS: errors.append({"rows": [], "field": "productos", "cause": f"supera {MAX_PRODUCTS} productos"})
    variants = sum(len(item["rows"]) for item in products.values() if item["rows"][0]["attributes"])
    if variants > MAX_VARIANTS: errors.append({"rows": [], "field": "variantes", "cause": f"supera {MAX_VARIANTS} variantes"})
    if errors:
        payload = {"products": [], "errors": errors, "warnings": warnings}
        payload["token"] = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()
        return payload
    planned = []
    conn = db.get_conn()
    try:
        for group, item in products.items():
            group_rows = item["rows"]
            canonical = next((row for row in group_rows if row["name"]), None)
            if not canonical:
                errors.append({"rows": [r["row"] for r in group_rows], "field": "Nombre", "cause": "es obligatorio para el producto"}); continue
            for row in group_rows:
                for field in ("name", "category", "description", "brand"):
                    if not row[field]: row[field] = canonical[field]
            has_variants = any(row["attributes"] for row in group_rows)
            if has_variants and (not all(row["attributes"] for row in group_rows) or len(group_rows) > MAX_VARIANTS_PER_PRODUCT):
                errors.append({"rows": [r["row"] for r in group_rows], "field": "variantes", "cause": "grupo de variantes incompleto o excesivo"}); continue
            matches = set()
            for row in group_rows:
                if row["sku"]:
                    found = conn.execute("SELECT producto_id FROM producto_variantes WHERE lower(sku)=lower(?)", (row["sku"],)).fetchall()
                    matches.update(int(x[0]) for x in found)
                if row["barcode"]:
                    found = conn.execute("SELECT producto_id FROM producto_variantes WHERE codigo_barras=?", (row["barcode"],)).fetchall()
                    matches.update(int(x[0]) for x in found)
                    legacy = conn.execute("SELECT id FROM productos WHERE codigo_barras=?", (row["barcode"],)).fetchall()
                    if legacy: errors.append({"rows": [row["row"]], "field": "codigo de barras", "cause": "coincide con un producto legacy; requiere tratamiento manual"})
            if len(matches) > 1:
                errors.append({"rows": [r["row"] for r in group_rows], "field": "identificacion", "cause": "coincidencia ambigua"}); continue
            if matches and not has_variants:
                errors.append({"rows": [r["row"] for r in group_rows], "field": "identificacion", "cause": "un producto simple no actualiza variantes automaticamente"}); continue
            if matches:
                mode = conn.execute("SELECT COALESCE(stock_modo, 'legacy') FROM productos WHERE id=?", (next(iter(matches)),)).fetchone()
                if not mode or str(mode[0]).lower() != "variantes":
                    errors.append({"rows": [r["row"] for r in group_rows], "field": "stock_modo", "cause": "el producto existente no opera por variantes"}); continue
            planned.append({"action": "update" if matches else "create", "product_id": next(iter(matches), None), "rows": group_rows, "has_variants": has_variants})
    finally: conn.close()
    payload = {"products": planned, "errors": errors, "warnings": warnings}
    payload["token"] = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()
    return payload


def apply_plan(plan: dict, token: str) -> dict:
    if token != plan.get("token") or plan.get("errors"):
        raise ValueError("El plan de importacion ya no es valido")
    conn = db.get_conn()
    try:
        cursor = conn.cursor(); cursor.execute("BEGIN IMMEDIATE")
        created = updated = 0
        for item in plan["products"]:
            rows, first = item["rows"], item["rows"][0]
            if item["action"] == "update":
                product_id = item["product_id"]; updated += 1
            else:
                cursor.execute("INSERT INTO productos (codigo_interno,descripcion,marca,categoria,costo,precio_venta,activo,stock_modo) VALUES (?,?,?,?,?,?,?,'legacy')",
                    (db.next_codigo(), first["name"], first["brand"], first["category"].split(",")[0].strip(), first["cost"] or 0, first["price"] or 0, int(first["visible"])))
                product_id = int(cursor.lastrowid); cursor.execute("INSERT INTO stock (producto_id,stock_actual,stock_minimo,stock_maximo,proveedor_habitual) VALUES (?,?,?,?,?)", (product_id, 0, 0, 0, "")); created += 1
            if item["has_variants"]:
                allocations = []
                for row in rows:
                    pairs = product_variants._resolve_attribute_pairs(cursor, [{"attribute_name": x["name"], "value_name": x["value"]} for x in row["attributes"]])
                    key = product_variants._build_combination_key(pairs)
                    existing = cursor.execute("SELECT id FROM producto_variantes WHERE producto_id=? AND combination_key=?", (product_id, key)).fetchone()
                    if existing: variant_id = int(existing[0])
                    else:
                        variant_id = product_variants._insert_variant_row(cursor, {"product_id": product_id, "combination_key": key, "variant_name": product_variants._build_variant_name(pairs), "sku": row["sku"] or None, "codigo_barras": row["barcode"], "costo": row["cost"], "precio": row["price"], "precio_promocional": None, "activo": int(row["visible"]), "external_id": ""})
                        product_variants._insert_variant_attribute_values(cursor, variant_id, pairs)
                    product_variants._persist_variant_stock_config(cursor, variant_id, stock_actual=0, stock_minimo=0, stock_maximo=0)
                    allocations.append({"variant_id": variant_id, "stock_actual": row["stock"] or 0, "stock_minimo": 0, "stock_maximo": 0})
                cursor.execute("UPDATE productos SET stock_modo='variantes' WHERE id=?", (product_id,))
                for allocation in allocations:
                    inventory.adjust_inventory_item_in_cursor(cursor, product_id, variant_id=allocation["variant_id"],
                        stock_actual=allocation["stock_actual"], stock_minimo=0, stock_maximo=0,
                        motivo="Importacion CSV de catalogo")
            else:
                row = first; cursor.execute("UPDATE productos SET codigo_barras=? WHERE id=?", (row["barcode"], product_id))
                inventory.adjust_inventory_item_in_cursor(cursor, product_id, stock_actual=row["stock"] or 0, stock_minimo=0, stock_maximo=0,
                    motivo="Importacion CSV de catalogo")
        conn.commit(); return {"created": created, "updated": updated}
    except Exception:
        conn.rollback(); raise
    finally: conn.close()
