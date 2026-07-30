from __future__ import annotations

import database as db
from services.rubros import normalizar_rubro


def _clean_text(value) -> str:
    return db._clean_attribute_profile_text(value)


def _name_key(value) -> str:
    return db._attribute_profile_key(value)


def _validate_attribute_names(attribute_names):
    names = []
    seen = set()
    for raw_name in attribute_names or []:
        name = _clean_text(raw_name)
        if not name:
            continue
        key = _name_key(name)
        if key in seen:
            raise ValueError("El perfil no puede asociar el mismo atributo mas de una vez.")
        seen.add(key)
        names.append(name)
    return names


def _row_to_dict(row):
    return dict(row) if row else None


def _attributes_for_profile_ids(profile_ids):
    if not profile_ids:
        return {}
    placeholders = ",".join("?" for _ in profile_ids)
    rows = db.q(
        f"""
        SELECT pa.perfil_id, a.id, a.nombre, a.nombre_normalizado, a.activo, pa.orden
        FROM atributo_perfil_atributos pa
        JOIN producto_atributos a ON a.id = pa.atributo_id
        WHERE pa.perfil_id IN ({placeholders})
        ORDER BY pa.perfil_id, pa.orden, a.nombre
        """,
        tuple(profile_ids),
    )
    grouped = {int(profile_id): [] for profile_id in profile_ids}
    for row in rows:
        grouped.setdefault(int(row["perfil_id"]), []).append(
            {
                "id": int(row["id"]),
                "nombre": row["nombre"],
                "nombre_normalizado": row["nombre_normalizado"],
                "activo": bool(row["activo"]),
                "orden": int(row["orden"] or 0),
            }
        )
    return grouped


def list_profiles():
    rows = db.q(
        """
        SELECT id, nombre, nombre_normalizado, descripcion, activo, orden, created_at, updated_at
        FROM atributo_perfiles
        ORDER BY orden, nombre
        """
    )
    profiles = [_row_to_dict(row) for row in rows]
    attrs_by_profile = _attributes_for_profile_ids([int(profile["id"]) for profile in profiles])
    for profile in profiles:
        profile["activo"] = bool(profile["activo"])
        profile["atributos"] = attrs_by_profile.get(int(profile["id"]), [])
        profile["atributos_texto"] = ", ".join(attr["nombre"] for attr in profile["atributos"])
    return profiles


def get_profile(profile_id):
    row = db.q(
        """
        SELECT id, nombre, nombre_normalizado, descripcion, activo, orden, created_at, updated_at
        FROM atributo_perfiles
        WHERE id=?
        """,
        (profile_id,),
        fetchone=True,
    )
    profile = _row_to_dict(row)
    if not profile:
        return None
    profile["activo"] = bool(profile["activo"])
    profile["atributos"] = _attributes_for_profile_ids([int(profile["id"])]).get(int(profile["id"]), [])
    profile["atributos_texto"] = ", ".join(attr["nombre"] for attr in profile["atributos"])
    return profile


def _ensure_unique_profile_name(cursor, name, *, exclude_id=None):
    key = _name_key(name)
    if not key:
        raise ValueError("Ingresa un nombre de perfil.")
    params = [key]
    sql = "SELECT id FROM atributo_perfiles WHERE nombre_normalizado=?"
    if exclude_id is not None:
        sql += " AND id<>?"
        params.append(int(exclude_id))
    row = cursor.execute(sql, tuple(params)).fetchone()
    if row:
        raise ValueError("Ya existe un perfil con ese nombre.")
    return key


def _replace_profile_attributes(cursor, profile_id, attribute_names):
    names = _validate_attribute_names(attribute_names)
    cursor.execute("DELETE FROM atributo_perfil_atributos WHERE perfil_id=?", (profile_id,))
    for idx, name in enumerate(names, start=1):
        attribute_id = db._ensure_profile_attribute_in_cursor(cursor, name)
        cursor.execute(
            """
            INSERT OR IGNORE INTO atributo_perfil_atributos (perfil_id, atributo_id, orden)
            VALUES (?, ?, ?)
            """,
            (profile_id, attribute_id, idx),
        )


def create_profile(nombre, descripcion="", activo=True, orden=0, attribute_names=None):
    name = _clean_text(nombre)
    conn = db.get_conn()
    try:
        cursor = conn.cursor()
        key = _ensure_unique_profile_name(cursor, name)
        cursor.execute(
            """
            INSERT INTO atributo_perfiles (nombre, nombre_normalizado, descripcion, activo, orden, updated_at)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (name, key, _clean_text(descripcion), int(bool(activo)), int(orden or 0)),
        )
        profile_id = int(cursor.lastrowid)
        _replace_profile_attributes(cursor, profile_id, attribute_names or [])
        conn.commit()
        return profile_id
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def update_profile(profile_id, nombre, descripcion="", activo=True, orden=0, attribute_names=None):
    profile = get_profile(profile_id)
    if not profile:
        raise ValueError("No se encontro el perfil.")
    name = _clean_text(nombre)
    conn = db.get_conn()
    try:
        cursor = conn.cursor()
        key = _ensure_unique_profile_name(cursor, name, exclude_id=profile_id)
        cursor.execute(
            """
            UPDATE atributo_perfiles
            SET nombre=?, nombre_normalizado=?, descripcion=?, activo=?, orden=?, updated_at=CURRENT_TIMESTAMP
            WHERE id=?
            """,
            (name, key, _clean_text(descripcion), int(bool(activo)), int(orden or 0), int(profile_id)),
        )
        _replace_profile_attributes(cursor, int(profile_id), attribute_names or [])
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def set_profile_active(profile_id, active):
    if not get_profile(profile_id):
        raise ValueError("No se encontro el perfil.")
    db.q(
        "UPDATE atributo_perfiles SET activo=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
        (int(bool(active)), int(profile_id)),
        commit=True,
    )


def set_rubro_profile(rubro, profile_id):
    rubro_key = normalizar_rubro(rubro)
    if profile_id in (None, "", "0", 0):
        db.q(
            "DELETE FROM rubro_atributo_perfiles WHERE rubro=?",
            (rubro_key,),
            commit=True,
        )
        return
    profile = get_profile(profile_id)
    if not profile:
        raise ValueError("No se encontro el perfil.")
    if not profile["activo"]:
        raise ValueError("No se puede activar un perfil inactivo.")
    db.q(
        """
        INSERT INTO rubro_atributo_perfiles (rubro, perfil_id, updated_at)
        VALUES (?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(rubro) DO UPDATE SET perfil_id=excluded.perfil_id, updated_at=CURRENT_TIMESTAMP
        """,
        (rubro_key, int(profile_id)),
        commit=True,
    )


def get_rubro_profile(rubro):
    rubro_key = normalizar_rubro(rubro)
    row = db.q(
        """
        SELECT perfil_id
        FROM rubro_atributo_perfiles
        WHERE rubro=?
        """,
        (rubro_key,),
        fetchone=True,
    )
    if not row or not row["perfil_id"]:
        return None
    return get_profile(row["perfil_id"])


def get_effective_suggested_attributes(rubro):
    profile = get_rubro_profile(rubro)
    if not profile or not profile["activo"]:
        return []
    return [attr for attr in profile["atributos"] if attr["activo"]]


def get_config_context(rubro):
    selected_profile = get_rubro_profile(rubro)
    active_profile = selected_profile if selected_profile and selected_profile["activo"] else None
    return {
        "profiles": list_profiles(),
        "active_profile": active_profile,
        "active_profile_id": int(active_profile["id"]) if active_profile else 0,
    }
