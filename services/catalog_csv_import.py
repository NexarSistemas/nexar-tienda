"""Neutral catalog-import application service.

Provider specific column names live only in the Tiendanube adapter below.  The
planner and writer consume the neutral dictionaries produced by that adapter.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import secrets
import unicodedata
from datetime import datetime, timedelta, timezone
from io import StringIO

import database as db
from services import inventory, product_variants

MAX_BYTES = 5 * 1024 * 1024
MAX_ROWS = 2_000
MAX_PRODUCTS = 500
MAX_VARIANTS = 2_000
MAX_VARIANTS_PER_PRODUCT = 100
MAX_FIELD_LENGTH = 2_000
PLAN_TTL_MINUTES = 15
MAX_STORED_PLANS_PER_USER = 3


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


def _visible(value, *, present: bool):
    if not present or not str(value or "").strip():
        return None
    normalized = _key(value)
    if normalized in {"si", "true", "1", "yes"}:
        return True
    if normalized in {"no", "false", "0"}:
        return False
    raise ValueError("Mostrar en tienda: debe ser SI o NO")


def _combination_identity(attributes: list[dict]) -> tuple[tuple[str, str], ...]:
    return tuple(sorted((_key(item["name"]), _key(item["value"])) for item in attributes))


def _now() -> datetime:
    return datetime.now(timezone.utc)


def store_plan(plan: dict, owner_user_id: int) -> tuple[str, str]:
    """Persist a one-use preview; the cookie keeps only its opaque identifier."""
    plan_id, token = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    now, expires = _now(), _now() + timedelta(minutes=PLAN_TTL_MINUTES)
    conn = db.get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM catalog_import_plans WHERE expires_at <= ? OR consumed_at IS NOT NULL", (now.isoformat(),))
        cursor.execute("DELETE FROM catalog_import_plans WHERE owner_user_id=? AND consumed_at IS NULL", (int(owner_user_id),))
        cursor.execute("INSERT INTO catalog_import_plans (id, owner_user_id, token_hash, payload, created_at, expires_at) VALUES (?,?,?,?,?,?)", (plan_id, int(owner_user_id), hashlib.sha256(token.encode()).hexdigest(), json.dumps(plan, separators=(",", ":")), now.isoformat(), expires.isoformat()))
        conn.commit()
        return plan_id, token
    finally:
        conn.close()


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
                         "visible": _visible(get("visible"), present="visible" in columns)})
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
            if has_variants:
                combinations = {}
                for row in group_rows:
                    combinations.setdefault(_combination_identity(row["attributes"]), []).append(row["row"])
                repeated = [numbers for numbers in combinations.values() if len(numbers) > 1]
                if repeated:
                    errors.append({"rows": [number for numbers in repeated for number in numbers], "field": "combinacion", "cause": "combinacion de atributos duplicada"}); continue
            if not has_variants and not canonical["barcode"]:
                errors.append({"rows": [r["row"] for r in group_rows], "field": "codigo de barras", "cause": "un producto simple requiere codigo de barras para importar de forma idempotente"}); continue
            matches = set()
            for row in group_rows:
                if row["sku"]:
                    found = conn.execute("SELECT producto_id FROM producto_variantes WHERE lower(sku)=lower(?)", (row["sku"],)).fetchall()
                    matches.update(int(x[0]) for x in found)
                if row["barcode"]:
                    found = conn.execute("SELECT producto_id FROM producto_variantes WHERE codigo_barras=?", (row["barcode"],)).fetchall()
                    matches.update(int(x[0]) for x in found)
                    legacy = conn.execute("SELECT id FROM productos WHERE codigo_barras=?", (row["barcode"],)).fetchall()
                    if has_variants and legacy: errors.append({"rows": [row["row"]], "field": "codigo de barras", "cause": "coincide con un producto legacy; requiere tratamiento manual"})
                    if not has_variants: matches.update(int(x[0]) for x in legacy)
            if len(matches) > 1:
                errors.append({"rows": [r["row"] for r in group_rows], "field": "identificacion", "cause": "coincidencia ambigua"}); continue
            if matches:
                mode = conn.execute("SELECT COALESCE(stock_modo, 'legacy') FROM productos WHERE id=?", (next(iter(matches)),)).fetchone()
                if not mode or (has_variants and str(mode[0]).lower() != "variantes") or (not has_variants and str(mode[0]).lower() == "variantes"):
                    errors.append({"rows": [r["row"] for r in group_rows], "field": "stock_modo", "cause": "el producto existente no opera por variantes"}); continue
            if has_variants and matches:
                product_id = next(iter(matches))
                for row in group_rows:
                    pairs = product_variants._resolve_attribute_pairs(conn.cursor(), [{"attribute_name": x["name"], "value_name": x["value"]} for x in row["attributes"]])
                    key = product_variants._build_combination_key(pairs)
                    variant = conn.execute("SELECT id FROM producto_variantes WHERE producto_id=? AND combination_key=?", (product_id, key)).fetchone()
                    row["variant_action"] = "update" if variant else "create"
                    row["variant_id"] = int(variant[0]) if variant else None
                    row["expected_combination_key"] = key
            planned.append({"action": "update" if matches else "create", "product_id": next(iter(matches), None), "rows": group_rows, "has_variants": has_variants})
    finally: conn.close()
    payload = {"products": planned, "errors": errors, "warnings": warnings}
    payload["token"] = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()
    return payload


def _adjust_stock_if_changed(cursor, product_id: int, target: float, *, variant_id=None, allow_inactive_variant=False):
    table, where, key = ("stock_variantes", "variante_id", variant_id) if variant_id is not None else ("stock", "producto_id", product_id)
    current = cursor.execute(f"SELECT stock_actual, stock_minimo, stock_maximo FROM {table} WHERE {where}=?", (key,)).fetchone()
    current_value = float(current[0] or 0) if current else 0.0
    if round(current_value, 6) != round(float(target), 6):
        inventory.adjust_inventory_item_in_cursor(cursor, product_id, variant_id=variant_id, stock_actual=target, stock_minimo=float(current[1] or 0) if current else 0, stock_maximo=float(current[2] or 0) if current else 0, motivo="Importacion CSV de catalogo", allow_inactive_variant=allow_inactive_variant)


def _project_active_product_count_in_cursor(cursor, plan: dict) -> int:
    current = int(cursor.execute("SELECT COUNT(*) FROM productos WHERE activo=1").fetchone()[0] or 0)
    delta = 0
    for item in plan["products"]:
        first = item["rows"][0]
        if item["action"] == "create":
            delta += int(first["visible"] is not False)
        elif not item["has_variants"] and first["visible"] is not None:
            active = cursor.execute("SELECT activo FROM productos WHERE id=?", (item["product_id"],)).fetchone()
            if active:
                delta += int(bool(first["visible"])) - int(bool(active[0]))
    return current + delta


def _check_product_limit_in_cursor(cursor, plan: dict) -> None:
    current = int(cursor.execute("SELECT COUNT(*) FROM productos WHERE activo=1").fetchone()[0] or 0)
    projected = _project_active_product_count_in_cursor(cursor, plan)
    if projected <= current:
        return
    check = db.check_license_limits("productos", projected)
    if not check["ok"]:
        raise ValueError(check["message"])


def _prepare_variant_commercial_updates_in_cursor(cursor, plan: dict) -> dict[int, dict]:
    updates = {}
    for item in plan["products"]:
        if item["action"] != "update" or not item["has_variants"]:
            continue
        for row in item["rows"]:
            pairs = product_variants._resolve_attribute_pairs(cursor, [{"attribute_name": x["name"], "value_name": x["value"]} for x in row["attributes"]])
            key = product_variants._build_combination_key(pairs)
            action = row.get("variant_action")
            if action not in {"create", "update"}:
                raise ValueError("El plan de importacion requiere una nueva vista previa.")
            if action == "create":
                if cursor.execute("SELECT id FROM producto_variantes WHERE producto_id=? AND combination_key=?", (item["product_id"], key)).fetchone():
                    raise ValueError("La combinacion planificada para crear ya existe. Genera una nueva vista previa.")
                continue
            if row.get("expected_combination_key") != key:
                raise ValueError("La variante planificada para actualizar ya no existe. Genera una nueva vista previa.")
            variant = cursor.execute("SELECT id, sku, codigo_barras, costo, precio FROM producto_variantes WHERE id=? AND producto_id=? AND combination_key=?", (row.get("variant_id"), item["product_id"], row.get("expected_combination_key"))).fetchone()
            if not variant:
                raise ValueError("La variante planificada para actualizar ya no existe. Genera una nueva vista previa.")
            variant_id = int(variant["id"])
            updates[variant_id] = {
                "product_id": int(item["product_id"]),
                "sku": product_variants._clean_text(row["sku"]) or variant["sku"],
                "codigo_barras": db.normalize_codigo_barras(row["barcode"]) if product_variants._clean_text(row["barcode"]) else variant["codigo_barras"],
                "costo": row["cost"] if row["cost"] is not None else variant["costo"],
                "precio": row["price"] if row["price"] is not None else variant["precio"],
            }
    if not updates:
        return updates
    ids = tuple(updates)
    external_skus = product_variants._normalized_variant_skus_excluding_in_cursor(cursor, exclude_variant_ids=ids)
    for field, label in (("sku", "SKU"), ("codigo_barras", "codigo de barras")):
        values = [str(update[field] or "") for update in updates.values() if update[field]]
        normalized_values = [product_variants._normalize_variant_sku_for_matching(value) for value in values] if field == "sku" else values
        if len(normalized_values) != len(set(normalized_values)):
            raise ValueError(f"El lote termina con {label}s duplicados.")
        for value, normalized_value in zip(values, normalized_values):
            marks = ",".join("?" for _ in ids)
            if field == "sku" and normalized_value in external_skus:
                raise ValueError("El SKU de la variante ya existe.")
            row = cursor.execute(f"SELECT id FROM producto_variantes WHERE {field}=? AND id NOT IN ({marks}) LIMIT 1", (value, *ids)).fetchone()
            if row:
                raise ValueError("El SKU de la variante ya existe." if field == "sku" else "Ya existe otra variante con ese codigo de barras.")
        if field == "codigo_barras":
            for value in values:
                if cursor.execute("SELECT id FROM productos WHERE TRIM(COALESCE(codigo_barras, ''))=? LIMIT 1", (value,)).fetchone():
                    raise ValueError("Ya existe un producto legacy con ese codigo de barras.")
    marks = ",".join("?" for _ in ids)
    cursor.execute(f"UPDATE producto_variantes SET sku=NULL, codigo_barras=NULL WHERE id IN ({marks})", ids)
    return updates


def _apply_plan_in_cursor(cursor, plan: dict) -> dict:
    _check_product_limit_in_cursor(cursor, plan)
    prepared_variant_updates = _prepare_variant_commercial_updates_in_cursor(cursor, plan)
    created = updated = 0
    for item in plan["products"]:
            rows, first = item["rows"], item["rows"][0]
            if item["action"] == "update":
                product_id = item["product_id"]; updated += 1
            else:
                cursor.execute("INSERT INTO productos (codigo_interno,descripcion,marca,categoria,costo,precio_venta,activo,stock_modo) VALUES (?,?,?,?,?,?,?,'legacy')",
                    (db._next_codigo_in_cursor(cursor), first["name"], first["brand"], first["category"].split(",")[0].strip(), first["cost"] or 0, first["price"] or 0, int(first["visible"] if first["visible"] is not None else True)))
                product_id = int(cursor.lastrowid); cursor.execute("INSERT INTO stock (producto_id,stock_actual,stock_minimo,stock_maximo,proveedor_habitual) VALUES (?,?,?,?,?)", (product_id, 0, 0, 0, "")); created += 1
            if item["has_variants"]:
                allocations = []
                enable_variants = []
                disable_variants = []
                for row in rows:
                    pairs = product_variants._resolve_attribute_pairs(cursor, [{"attribute_name": x["name"], "value_name": x["value"]} for x in row["attributes"]])
                    key = product_variants._build_combination_key(pairs)
                    if row.get("variant_action") == "update":
                        existing = cursor.execute("SELECT id FROM producto_variantes WHERE id=? AND producto_id=? AND combination_key=?", (row.get("variant_id"), product_id, row.get("expected_combination_key"))).fetchone()
                        if not existing:
                            raise ValueError("La variante planificada para actualizar ya no existe. Genera una nueva vista previa.")
                    else:
                        existing = cursor.execute("SELECT id FROM producto_variantes WHERE producto_id=? AND combination_key=?", (product_id, key)).fetchone()
                        if row.get("variant_action") == "create" and existing:
                            raise ValueError("La combinacion planificada para crear ya existe. Genera una nueva vista previa.")
                    if existing:
                        variant_id = int(existing[0])
                        prepared = prepared_variant_updates.get(variant_id)
                        if prepared:
                            product_variants._apply_prevalidated_variant_commercial_fields_in_cursor(cursor, product_id, variant_id, **{key: prepared[key] for key in ("sku", "codigo_barras", "costo", "precio")})
                        else:
                            product_variants._update_variant_commercial_fields_in_cursor(cursor, product_id, variant_id, sku=row["sku"], codigo_barras=row["barcode"], costo=row["cost"], precio=row["price"])
                        if row["visible"] is not None:
                            (enable_variants if row["visible"] else disable_variants).append(variant_id)
                    else:
                        variant_id = product_variants._insert_variant_row(cursor, {"product_id": product_id, "combination_key": key, "variant_name": product_variants._build_variant_name(pairs), "sku": product_variants._validate_variant_sku(cursor, row["sku"]), "codigo_barras": product_variants._validate_variant_barcode(cursor, row["barcode"]), "costo": row["cost"], "precio": row["price"], "precio_promocional": None, "activo": int(row["visible"] if row["visible"] is not None else True), "external_id": ""})
                        product_variants._insert_variant_attribute_values(cursor, variant_id, pairs)
                        # New variants without source stock still need their safe
                        # zero-valued inventory configuration.
                        product_variants._insert_variant_stock(cursor, variant_id, stock_actual=0, stock_minimo=0, stock_maximo=0)
                    allocations.append({"variant_id": variant_id, "stock_actual": row["stock"], "stock_minimo": 0, "stock_maximo": 0})
                cursor.execute("UPDATE productos SET stock_modo='variantes' WHERE id=?", (product_id,))
                for variant_id in enable_variants:
                    cursor.execute("UPDATE producto_variantes SET activo=1, updated_at=CURRENT_TIMESTAMP WHERE id=?", (variant_id,))
                for allocation in allocations:
                    if allocation["stock_actual"] is not None:
                        _adjust_stock_if_changed(cursor, product_id, allocation["stock_actual"], variant_id=allocation["variant_id"], allow_inactive_variant=True)
                for variant_id in disable_variants:
                    cursor.execute("UPDATE producto_variantes SET activo=0, updated_at=CURRENT_TIMESTAMP WHERE id=?", (variant_id,))
            else:
                row = first
                fields, params = ["codigo_barras=?"], [row["barcode"]]
                if row["visible"] is not None:
                    fields.append("activo=?"); params.append(int(row["visible"]))
                for column, source in (("descripcion", "name"), ("marca", "brand"), ("categoria", "category")):
                    if row[source]:
                        fields.append(f"{column}=?"); params.append(row[source].split(",")[0].strip() if column == "categoria" else row[source])
                for column, source in (("costo", "cost"), ("precio_venta", "price")):
                    if row[source] is not None:
                        fields.append(f"{column}=?"); params.append(row[source])
                params.append(product_id)
                cursor.execute(f"UPDATE productos SET {', '.join(fields)} WHERE id=?", tuple(params))
                if row["stock"] is not None:
                    _adjust_stock_if_changed(cursor, product_id, row["stock"])
    return {"created": created, "updated": updated}


def apply_stored_plan(plan_id: str, token: str, owner_user_id: int) -> dict:
    # Consume first in its own committed transaction: a later catalog rollback
    # must never make this preview confirmable again.
    conn = db.get_conn()
    try:
        cursor = conn.cursor(); cursor.execute("BEGIN IMMEDIATE")
        row = cursor.execute("SELECT payload, token_hash FROM catalog_import_plans WHERE id=? AND owner_user_id=? AND consumed_at IS NULL AND expires_at > ?", (plan_id, int(owner_user_id), _now().isoformat())).fetchone()
        if not row or not secrets.compare_digest(str(row["token_hash"]), hashlib.sha256(str(token).encode()).hexdigest()):
            raise ValueError("El plan de importacion no existe, vencio o ya fue utilizado")
        plan = json.loads(row["payload"])
        if plan.get("errors"):
            raise ValueError("El plan de importacion contiene conflictos")
        cursor.execute("UPDATE catalog_import_plans SET consumed_at=? WHERE id=? AND consumed_at IS NULL", (_now().isoformat(), plan_id))
        if cursor.rowcount != 1:
            raise ValueError("El plan de importacion ya fue utilizado")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    conn = db.get_conn()
    try:
        cursor = conn.cursor(); cursor.execute("BEGIN IMMEDIATE")
        result = _apply_plan_in_cursor(cursor, plan)
        conn.commit()
        return result
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
