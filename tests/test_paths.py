import importlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock


def _write_sqlite_header(path: Path, payload: bytes = b"legacy-data") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"SQLite format 3\x00" + payload)


class PathLayoutTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.base = Path(self.temp_dir.name)
        self.local_app_data = self.base / "LocalAppData"
        self.roaming_app_data = self.base / "RoamingAppData"
        self.local_app_data.mkdir(parents=True, exist_ok=True)
        self.roaming_app_data.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        import services.paths as paths

        reloaded = importlib.reload(paths)
        reloaded.reset_path_layout_cache()

    def _load_module(self, **extra_env):
        env = {
            "LOCALAPPDATA": str(self.local_app_data),
            "APPDATA": str(self.roaming_app_data),
            "NEXAR_USE_USER_DATA": "1",
        }
        env.update(extra_env)
        patcher = mock.patch.dict(os.environ, env, clear=False)
        patcher.start()
        self.addCleanup(patcher.stop)

        import services.paths as paths

        module = importlib.reload(paths)
        module.project_dir = lambda: self.base / "RepoProject"
        module.bundle_dir = lambda: self.base / "RepoProject"
        module.reset_path_layout_cache()
        return module

    def test_layout_nuevo_sin_datos_previos(self):
        paths = self._load_module()

        layout = paths.get_path_layout()

        self.assertEqual(layout.active_root, self.local_app_data / "NexarComercio")
        self.assertEqual(layout.active_database_path, layout.data_dir / "nexar_comercio.db")
        self.assertFalse(layout.migration_performed)
        self.assertFalse(layout.using_fallback)
        self.assertTrue(layout.logs_dir.exists())
        self.assertTrue(layout.backups_dir.exists())
        self.assertTrue(layout.cache_dir.exists())
        self.assertFalse(layout.active_database_path.exists())

    def test_migra_desde_carpeta_legacy_sin_borrar_origen(self):
        legacy_root = self.local_app_data / "NexarTienda"
        legacy_db = legacy_root / "tienda.db"
        _write_sqlite_header(legacy_db, b"-ventas")
        (legacy_root / "license.json").write_text('{"license_key":"abc"}', encoding="utf-8")

        paths = self._load_module()
        layout = paths.get_path_layout()

        self.assertTrue(layout.migration_performed)
        self.assertEqual(layout.migration_source, legacy_root)
        self.assertFalse(layout.using_fallback)
        self.assertTrue(layout.database_path.exists())
        self.assertEqual(layout.active_database_path, layout.database_path)
        self.assertEqual(layout.database_path.read_bytes(), legacy_db.read_bytes())
        self.assertTrue((layout.licenses_dir / "license.json").exists())
        self.assertTrue(legacy_db.exists())

    def test_prioriza_ruta_nueva_si_ya_existe(self):
        new_db = self.local_app_data / "NexarComercio" / "data" / "nexar_comercio.db"
        legacy_db = self.local_app_data / "NexarTienda" / "tienda.db"
        _write_sqlite_header(new_db, b"-nuevo")
        _write_sqlite_header(legacy_db, b"-legacy")

        paths = self._load_module()
        layout = paths.get_path_layout()

        self.assertFalse(layout.migration_performed)
        self.assertFalse(layout.using_fallback)
        self.assertEqual(layout.active_database_path, new_db)
        self.assertEqual(new_db.read_bytes(), b"SQLite format 3\x00-nuevo")

    def test_si_falla_migracion_usa_fallback_legacy(self):
        legacy_root = self.local_app_data / "Nexar Tienda"
        legacy_db = legacy_root / "tienda.db"
        _write_sqlite_header(legacy_db, b"-fallback")

        paths = self._load_module()
        with mock.patch.object(paths, "_migrate_from_legacy", side_effect=RuntimeError("boom")):
            paths.reset_path_layout_cache()
            layout = paths.get_path_layout()

        self.assertTrue(layout.using_fallback)
        self.assertEqual(layout.active_root, legacy_root)
        self.assertEqual(layout.active_database_path, legacy_db)
        self.assertEqual(layout.migration_error, "RuntimeError: boom")
        self.assertTrue(layout.migration_log_path.exists())


if __name__ == "__main__":
    unittest.main()
