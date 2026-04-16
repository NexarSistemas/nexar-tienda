"""
license_verifier.py — Nexar Tienda
====================================
Verifica la licencia online contra Supabase usando el SDK nexar_licencias.
"""

from datetime import date, datetime
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'nexar_licencias')))
from nexar_licencias import validar_licencia

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

    # Usar variable de entorno para la clave pública
    public_key = os.getenv("PUBLIC_KEY", "")
    ok = validar_licencia(licencia, public_key, "tienda", debug=True)

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
