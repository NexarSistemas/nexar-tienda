import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

from flask import Flask
from werkzeug.exceptions import NotFound

import routes.main as routes_main
from services import update_checker


def _release_response(tag_name="v9.9.9", assets=None):
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {
        "tag_name": tag_name,
        "html_url": "https://github.com/NexarSistemas/nexar-tienda/releases/tag/v9.9.9",
        "assets": assets or [],
    }
    return response


def _asset(name):
    return {
        "name": name,
        "browser_download_url": f"https://example.test/download/{name}",
    }


class UpdateCheckerTests(unittest.TestCase):
    def _check_release(self, platform_name, assets, tag_name="v9.9.9"):
        with (
            patch.object(update_checker.sys, "platform", platform_name),
            patch.object(update_checker.requests, "get", return_value=_release_response(tag_name, assets)),
        ):
            return update_checker.check_latest_release("1.0.0")

    def test_windows_selects_stable_asset_before_legacy_and_rejects_foreign_executables(self):
        info = self._check_release(
            "win32",
            [
                _asset("NexarComercio_9.9.9_Setup.exe"),
                _asset("otro_instalador.exe"),
                _asset(update_checker.WINDOWS_INSTALLER),
                _asset(update_checker.LINUX_INSTALLER),
                _asset(f"{update_checker.WINDOWS_INSTALLER}.sig"),
            ],
        )

        self.assertTrue(info["available"])
        self.assertEqual(info["latest"], "9.9.9")
        self.assertEqual(info["asset_name"], update_checker.WINDOWS_INSTALLER)
        self.assertEqual(info["asset_kind"], "windows")
        self.assertFalse(update_checker._asset_matches_platform("otro_instalador.exe"))
        self.assertFalse(update_checker._asset_matches_platform(update_checker.LINUX_INSTALLER))
        self.assertFalse(update_checker._asset_matches_platform(f"{update_checker.WINDOWS_INSTALLER}.sig"))

    def test_windows_keeps_versioned_legacy_compatibility(self):
        info = self._check_release("win32", [_asset("NexarTienda_9.9.9_Setup.exe")])

        self.assertEqual(info["asset_name"], "NexarTienda_9.9.9_Setup.exe")

    def test_linux_selects_stable_asset_before_legacy_and_rejects_foreign_packages(self):
        info = self._check_release(
            "linux",
            [
                _asset("nexar-tienda_9.9.9_amd64.deb"),
                _asset("otro_instalador.deb"),
                _asset(update_checker.WINDOWS_INSTALLER),
                _asset(update_checker.LINUX_INSTALLER),
                _asset(f"{update_checker.LINUX_INSTALLER}.sig"),
            ],
        )

        self.assertEqual(info["asset_name"], update_checker.LINUX_INSTALLER)
        self.assertEqual(info["asset_kind"], "linux")
        with patch.object(update_checker.sys, "platform", "linux"):
            self.assertFalse(update_checker._asset_matches_platform("otro_instalador.deb"))
            self.assertFalse(update_checker._asset_matches_platform(update_checker.WINDOWS_INSTALLER))
            self.assertFalse(update_checker._asset_matches_platform(f"{update_checker.LINUX_INSTALLER}.sig"))

    def test_linux_keeps_versioned_legacy_compatibility(self):
        info = self._check_release("linux", [_asset("nexar-tienda_9.9.9_amd64.deb")])

        self.assertEqual(info["asset_name"], "nexar-tienda_9.9.9_amd64.deb")

    def test_release_version_is_taken_only_from_a_valid_tag(self):
        self.assertEqual(update_checker.normalize_release_version("v09.009.0009"), "9.9.9")
        self.assertEqual(update_checker.normalize_release_version("9.9"), "")
        self.assertEqual(update_checker.normalize_release_version("v9.9.9-beta"), "")
        self.assertEqual(
            self._check_release("win32", [_asset(update_checker.WINDOWS_INSTALLER)], "v9.9.9-beta"),
            {"available": False},
        )

    def test_stable_filename_does_not_affect_version_comparison(self):
        with (
            patch.object(update_checker.sys, "platform", "win32"),
            patch.object(
                update_checker.requests,
                "get",
                return_value=_release_response("v1.0.0", [_asset(update_checker.WINDOWS_INSTALLER)]),
            ),
        ):
            info = update_checker.check_latest_release("9.9.9")

        self.assertFalse(info["available"])
        self.assertEqual(info["latest"], "1.0.0")
        self.assertEqual(info["asset_name"], update_checker.WINDOWS_INSTALLER)

    def test_download_persists_tag_version_for_a_stable_filename_inside_destination(self):
        response = MagicMock()
        response.__enter__.return_value = response
        response.iter_content.return_value = [b"installer"]

        with (
            tempfile.TemporaryDirectory() as tmp,
            patch.object(update_checker.sys, "platform", "win32"),
            patch.object(update_checker.requests, "get", return_value=response),
        ):
            destination = Path(tmp) / "updates"
            target = update_checker.download_release_asset(
                f"https://example.test/download/{update_checker.WINDOWS_INSTALLER}",
                destination,
                version="v9.9.9",
            )

            self.assertEqual(target, destination / update_checker.WINDOWS_INSTALLER)
            self.assertEqual(target.read_bytes(), b"installer")
            self.assertEqual(
                (destination / f"{update_checker.WINDOWS_INSTALLER}.version").read_text(encoding="utf-8"),
                "9.9.9",
            )
            self.assertEqual(target.parent.resolve(), destination.resolve())

    def test_download_rejects_traversal_separators_and_unlisted_filenames(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(update_checker.sys, "platform", "win32"):
            destination = Path(tmp) / "updates"
            rejected_urls = (
                f"https://example.test/../{update_checker.WINDOWS_INSTALLER}",
                f"https://example.test/%2E%2E/{update_checker.WINDOWS_INSTALLER}",
                f"https://example.test/{update_checker.WINDOWS_INSTALLER}%5C..",
                "https://example.test/otro_instalador.exe",
                f"http://example.test/{update_checker.WINDOWS_INSTALLER}",
            )

            for asset_url in rejected_urls:
                with self.subTest(asset_url=asset_url), self.assertRaises(ValueError):
                    update_checker.download_release_asset(asset_url, destination)

            self.assertFalse(destination.exists())


class UpdateRouteInstallerTests(unittest.TestCase):
    LEGACY_INSTALLERS = (
        ("NexarTienda_1.37_Setup.exe", "1.37"),
        ("NexarComercio_1.37_Setup.exe", "1.37"),
        ("NexarComercio_1.37.2_Setup.exe", "1.37.2"),
        ("nexar-tienda_1.37_amd64.deb", "1.37"),
        ("nexar-tienda_1.37.2_amd64.deb", "1.37.2"),
    )

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.app = Flask(__name__)
        self.app.config["APP_VERSION"] = "1.36.9"
        self.update_dir = Path(self.temp_dir.name)
        self.update_dir_patch = patch.object(routes_main, "UPDATE_DIR", self.update_dir)
        self.update_dir_patch.start()
        self.addCleanup(self.update_dir_patch.stop)

    def test_legacy_installers_are_accepted_parsed_and_listed(self):
        for filename, expected_version in self.LEGACY_INSTALLERS:
            with self.subTest(filename=filename):
                installer = self.update_dir / filename
                installer.write_bytes(b"installer")

                platform_name = "win32" if filename.endswith(".exe") else "linux"
                with patch.object(update_checker.sys, "platform", platform_name):
                    self.assertTrue(update_checker._asset_matches_platform(filename))
                self.assertTrue(routes_main._is_valid_update_installer_name(filename))
                self.assertEqual(routes_main._installer_version(filename), expected_version)
                self.assertGreater(
                    routes_main._version_tuple(expected_version),
                    routes_main._version_tuple(self.app.config["APP_VERSION"]),
                )
                with self.app.app_context():
                    updates = routes_main._update_list()
                self.assertIn(filename, [update["nombre"] for update in updates])
                with self.app.test_request_context():
                    self.assertEqual(routes_main._update_file(filename), installer.resolve())
                installer.unlink()

    def test_stable_installers_require_a_strict_sidecar_version(self):
        installer = self.update_dir / update_checker.WINDOWS_INSTALLER
        installer.write_bytes(b"installer")

        self.assertTrue(routes_main._is_valid_update_installer_name(installer.name))
        self.assertEqual(routes_main._installer_version(installer.name, "1.37"), "")
        with self.app.app_context():
            self.assertEqual(routes_main._update_list(), [])
        with self.app.test_request_context(), self.assertRaises(NotFound):
            routes_main._update_file(installer.name)

        (self.update_dir / f"{installer.name}.version").write_text("1.37.2", encoding="utf-8")
        with self.app.app_context():
            self.assertEqual(routes_main._update_list()[0]["version"], "1.37.2")
        with self.app.test_request_context():
            self.assertEqual(routes_main._update_file(installer.name), installer.resolve())


if __name__ == "__main__":
    unittest.main()
