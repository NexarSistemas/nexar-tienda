"""
Tests para integración de licencias modulares en Nexar Tienda.

Verifica que los tiers se mapeen correctamente a módulos:
- DEMO -> {core}
- BASICA -> {core, clientes, proveedores, pos, stock, caja}
- PRO -> {BASICA + compras, gastos, historial, reportes, export, multiusuario}
- MENSUAL_FULL/FULL -> {PRO + temporadas, multinegocio, ia}
"""

import os
import sys
import tempfile
from pathlib import Path

# Agregar raíz del proyecto al path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


from licensing.planes import PLANES, normalize_plan


PRO_MODULES = {
    'core',
    'clientes',
    'proveedores',
    'pos',
    'stock',
    'caja',
    'compras',
    'gastos',
    'historial',
    'reportes',
    'export',
    'multiusuario',
}

FULL_MODULES = {
    *PRO_MODULES,
    'temporadas',
    'ia',
    'multinegocio',
}
REMOTE_MODULES = ['clientes', 'core']


def _reset_license_env():
    for key in ('NEXAR_LICENSE_MODE', 'NEXAR_PLAN', 'NEXAR_MODULES'):
        os.environ.pop(key, None)


def _init_temp_database(database, temp_dir):
    database.DB_PATH = str(Path(temp_dir.name) / 'test_tienda.db')
    database._db_initialized = False
    database.init_db()


def test_tier_modules_mapping():
    """Verifica que el mapeo de tiers a módulos sea consistente."""
    from database import TIER_LIMITS

    # Verificar que existan los tiers esperados
    expected_tiers = {'DEMO', 'BASICA', 'PRO', 'MENSUAL_FULL'}
    assert set(PLANES.keys()) == expected_tiers, \
        f"Tiers esperados: {expected_tiers}, obtenido: {set(PLANES.keys())}"

    # Verificar que BASICA esté en TIER_LIMITS
    assert 'BASICA' in TIER_LIMITS, "BASICA debe estar en TIER_LIMITS"
    assert 'DEMO' in TIER_LIMITS, "DEMO debe estar en TIER_LIMITS"
    assert 'MENSUAL_FULL' in TIER_LIMITS, "MENSUAL_FULL debe estar en TIER_LIMITS"

    print("✓ Mapeo de tiers a módulos es consistente")


def test_normalize_tier():
    """Verifica que los aliases de tier se normalicen correctamente."""
    test_cases = {
        'BASIC': 'BASICA',
        'BASICO': 'BASICA',
        'TDA_BASICA': 'BASICA',
        'PRO': 'PRO',
        'FULL': 'MENSUAL_FULL',
        'MENSUAL': 'MENSUAL_FULL',
        'TDA_PRO': 'MENSUAL_FULL',
        'DEMO': 'DEMO',
        'BASICA': 'BASICA',
    }

    for input_tier, expected in test_cases.items():
        result = normalize_plan(input_tier)
        assert result == expected, \
            f"Normalizar '{input_tier}': esperado '{expected}', obtenido '{result}'"

    print("✓ Normalización de aliases de tier funciona correctamente")


def test_get_modulos_from_tier():
    """Verifica que se obtienen los módulos correctos para cada tier."""
    test_cases = {
        'DEMO': {'core'},
        'BASICA': {'core', 'clientes', 'proveedores', 'pos', 'stock', 'caja'},
        'PRO': PRO_MODULES,
        'MENSUAL_FULL': FULL_MODULES,
        'FULL': FULL_MODULES,
        'TDA_PRO': FULL_MODULES,
    }

    for tier, expected_modules in test_cases.items():
        from licensing.permisos import _get_modulos_from_tier

        result = _get_modulos_from_tier(tier)
        assert result == expected_modules, \
            f"Tier '{tier}': esperados {expected_modules}, obtenido {result}"

    print("✓ Obtención de módulos por tier funciona correctamente")


def test_database_tier_functions():
    """Verifica que PROD mode resuelva módulos desde DB."""
    import database
    from licensing.permisos import get_modulos_activos

    _reset_license_env()
    os.environ['NEXAR_LICENSE_MODE'] = 'prod'

    original_db_path = database.DB_PATH
    temp_dir = tempfile.TemporaryDirectory()
    try:
        _init_temp_database(database, temp_dir)
        database.q(
            "UPDATE config SET valor=? WHERE clave='license_tier'",
            ('PRO',),
            commit=True,
        )

        tier = database.get_license_tier_from_db()
        modules = database.get_modulos_from_tier(tier)
        active_modules = get_modulos_activos()

        assert tier == 'PRO', f"Tier esperado PRO, obtenido: {tier}"
        assert modules == PRO_MODULES, f"Módulos desde DB incorrectos: {modules}"
        assert active_modules == PRO_MODULES, f"Modo prod no tomó módulos desde DB: {active_modules}"

        print("✓ PROD mode usa correctamente license_tier desde DB")
    finally:
        database.DB_PATH = original_db_path
        temp_dir.cleanup()
        _reset_license_env()


def test_sync_license_modules_from_remote():
    """Verifica que sync_license_from_remote persista módulos remotos."""
    import database

    original_db_path = database.DB_PATH
    temp_dir = tempfile.TemporaryDirectory()
    try:
        _init_temp_database(database, temp_dir)
        database.sync_license_from_remote({
            'license_key': 'TEST-001',
            'plan': 'PRO',
            'modules': ['clientes', 'core'],
        })

        cfg = database.get_config()
        info = database.get_license_info()

        assert cfg['license_tier'] == 'PRO', f"Tier incorrecto: {cfg['license_tier']}"
        assert cfg['license_plan'] == 'PRO', f"Plan incorrecto: {cfg['license_plan']}"
        assert cfg['license_modules'] == '["clientes", "core"]', f"license_modules incorrecto: {cfg['license_modules']}"
        assert info['modules'] == REMOTE_MODULES, f"Módulos en get_license_info incorrectos: {info['modules']}"

        print("✓ sync_license_from_remote guarda módulos remotos")
    finally:
        database.DB_PATH = original_db_path
        temp_dir.cleanup()


def test_prod_prioritizes_persisted_modules():
    """Verifica que PROD use license_modules antes que el tier local."""
    import database
    from licensing.permisos import get_modulos_activos

    _reset_license_env()
    os.environ['NEXAR_LICENSE_MODE'] = 'prod'

    original_db_path = database.DB_PATH
    temp_dir = tempfile.TemporaryDirectory()
    try:
        _init_temp_database(database, temp_dir)
        database.q("UPDATE config SET valor=? WHERE clave='license_tier'", ('DEMO',), commit=True)
        database.q("UPDATE config SET valor=? WHERE clave='license_modules'", ('[\"core\", \"clientes\"]',), commit=True)

        active_modules = get_modulos_activos()
        assert active_modules == {'core', 'clientes'}, f"Debe priorizar módulos persistidos, obtuvo: {active_modules}"

        print("✓ PROD prioriza license_modules persistido")
    finally:
        database.DB_PATH = original_db_path
        temp_dir.cleanup()
        _reset_license_env()


def test_sync_accepts_features_alias():
    """Verifica compatibilidad con alias remoto 'features'."""
    import database

    original_db_path = database.DB_PATH
    temp_dir = tempfile.TemporaryDirectory()
    try:
        _init_temp_database(database, temp_dir)
        database.sync_license_from_remote({
            'license_key': 'TEST-002',
            'plan': 'BASICA',
            'features': ['core', 'clientes'],
        })

        cfg = database.get_config()
        assert cfg['license_modules'] == '["clientes", "core"]', f"Alias features no persistido correctamente: {cfg['license_modules']}"

        print("✓ sync_license_from_remote acepta alias features")
    finally:
        database.DB_PATH = original_db_path
        temp_dir.cleanup()


def test_sync_accepts_modulos_alias():
    """Verifica compatibilidad con alias remoto 'modulos'."""
    import database

    original_db_path = database.DB_PATH
    temp_dir = tempfile.TemporaryDirectory()
    try:
        _init_temp_database(database, temp_dir)
        database.sync_license_from_remote({
            'license_key': 'TEST-003',
            'plan': 'BASICA',
            'modulos': ['core', 'clientes'],
        })

        cfg = database.get_config()
        assert cfg['license_modules'] == '["clientes", "core"]', f"Alias modulos no persistido correctamente: {cfg['license_modules']}"

        print("✓ sync_license_from_remote acepta alias modulos")
    finally:
        database.DB_PATH = original_db_path
        temp_dir.cleanup()


def test_permisos_dev_mode():
    """Verifica que en DEV mode se use .env vars."""
    _reset_license_env()
    os.environ['NEXAR_LICENSE_MODE'] = 'dev'
    os.environ['NEXAR_PLAN'] = 'BASICA'
    os.environ['NEXAR_MODULES'] = 'reportes, export'

    from licensing.permisos import get_modulos_activos

    modules = get_modulos_activos()
    assert 'core' in modules, "DEV mode con NEXAR_PLAN=BASICA debe incluir 'core'"
    assert 'clientes' in modules, "DEV mode con NEXAR_PLAN=BASICA debe incluir 'clientes'"
    assert 'reportes' in modules, "DEV mode debe sumar módulos extra desde NEXAR_MODULES"
    assert 'export' in modules, "DEV mode debe sumar módulos extra desde NEXAR_MODULES"

    print("✓ DEV mode usa correctamente NEXAR_PLAN desde .env")
    _reset_license_env()


def test_tier_core_module():
    """Verifica que todos los tiers incluyan el módulo 'core'."""
    for tier, modules in PLANES.items():
        assert 'core' in modules, \
            f"Tier '{tier}' debe incluir el módulo 'core', tiene: {modules}"

    print("✓ Todos los tiers incluyen el módulo 'core'")


def test_basica_includes_clientes():
    """Verifica que BASICA incluya los módulos esperados."""
    basica_modules = PLANES['BASICA']
    assert 'clientes' in basica_modules, "BASICA debe incluir 'clientes'"
    expected = {'core', 'clientes', 'proveedores', 'pos', 'stock', 'caja'}
    assert basica_modules == expected, f"BASICA debe tener {expected}, tiene: {basica_modules}"

    print("✓ BASICA tiene mapeo correcto")


def test_pro_modules():
    """Verifica que PRO incluya los módulos esperados."""
    pro_modules = PLANES['PRO']
    assert pro_modules == PRO_MODULES, \
        f"PRO: esperados {PRO_MODULES}, obtenido {pro_modules}"

    print("✓ PRO tiene mapeo correcto")


def test_full_includes_all():
    """Verifica que MENSUAL_FULL incluya todos los módulos esperados."""
    full_modules = PLANES['MENSUAL_FULL']
    assert full_modules == FULL_MODULES, \
        f"MENSUAL_FULL: esperados {FULL_MODULES}, obtenido {full_modules}"

    print("✓ MENSUAL_FULL tiene mapeo completo")


def run_all_tests():
    """Ejecuta todos los tests."""
    tests = [
        test_tier_modules_mapping,
        test_normalize_tier,
        test_get_modulos_from_tier,
        test_tier_core_module,
        test_basica_includes_clientes,
        test_pro_modules,
        test_full_includes_all,
        test_database_tier_functions,
        test_sync_license_modules_from_remote,
        test_prod_prioritizes_persisted_modules,
        test_sync_accepts_features_alias,
        test_sync_accepts_modulos_alias,
        test_permisos_dev_mode,
    ]

    print("\n" + "="*70)
    print("TESTS DE INTEGRACIÓN DE LICENCIAS MODULARES - NEXAR TIENDA")
    print("="*70 + "\n")

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"✗ {test.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"✗ {test.__name__}: Error inesperado: {e}")
            failed += 1

    print("\n" + "="*70)
    print(f"Resultados: {passed} pasaron, {failed} fallaron")
    print("="*70 + "\n")

    return failed == 0


if __name__ == '__main__':
    success = run_all_tests()
    sys.exit(0 if success else 1)
