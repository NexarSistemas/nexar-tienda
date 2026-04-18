"""
license_verifier.py — Nexar Tienda
====================================
Verifica la licencia online contra Supabase usando el SDK nexar_licencias.
"""

from services.license_sdk import get_license_product, import_validar_licencia, load_public_key

# ── Configuracion ─────────────────────────────────────────────────────────────
DIAS_GRACIA = 7
# ── Logica principal ──────────────────────────────────────────────────────────

def verificar_licencia_online(db_module) -> dict:
    """
    Verifica la licencia contra Drive.

    Retorna dict con:
      ok         : bool  — True si la licencia es valida
      modo       : 'online_ok' | 'gracia' | 'revocada' | 'demo'
      dias_gracia: int   — dias restantes de gracia (si aplica)
    """
    cfg = db_module.get_config()

    if cfg.get('demo_mode', '1') == '1':
        return {'ok': True, 'modo': 'demo', 'dias_gracia': 0,
                'mensaje': 'Modo demo activo'}

    import json
    lic_json = cfg.get('license_data_full', '{}')
    try:
        licencia = json.loads(lic_json)
    except:
        licencia = {"license_key": cfg.get('license_key', ''), "public_signature": cfg.get('license_signature', '')}

    validar_licencia = import_validar_licencia()
    if validar_licencia is None:
        _revocar(db_module)
        return {'ok': False, 'modo': 'revocada', 'mensaje': 'No se pudo cargar el SDK de licencias.'}

    ok = validar_licencia(licencia, load_public_key(), get_license_product(), debug=True)

    if not ok:
        _revocar(db_module)
        return {'ok': False, 'modo': 'revocada', 'mensaje': 'Licencia inválida o revocada.'}

    return {'ok': True, 'modo': 'online_ok', 'mensaje': 'Verificación exitosa.'}


def _revocar(db_module):
    """Vuelve a modo basica (si estaba activada) o demo sin borrar datos."""
    cfg = db_module.get_config()
    # Si la licencia basica fue activada previamente, volvemos a BASICA en lugar de DEMO
    if cfg.get('basica_activada', '0') == '1':
        db_module.set_config({
            'demo_mode':            '0',
            'license_tier':         'BASICA',
            'license_plan':         'BASICA',
            'license_last_check':   '',
        })
    else:
        db_module.set_config({
            'demo_mode':            '1',
            'license_tier':         'DEMO',
            'license_plan':         'DEMO',
            'license_last_check':   '',
        })
