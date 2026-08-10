import unittest
from pathlib import Path


class BuildReleaseAssetTests(unittest.TestCase):
    def test_public_installer_names_are_stable_without_changing_internal_versions(self):
        iss = Path("build/nexar_tienda.iss").read_text(encoding="utf-8")
        deb_builder = Path("build_deb.sh").read_text(encoding="utf-8")

        self.assertIn("OutputBaseFilename=Nexar_Comercio_Windows_Setup", iss)
        self.assertIn("AppVersion={#AppVersion}", iss)
        self.assertIn("AppVerName={#AppName} v{#AppVersion}", iss)
        self.assertIn('PACKAGE="nexar-tienda"', deb_builder)
        self.assertIn("Version: ${VERSION}", deb_builder)
        self.assertIn("Nexar_Comercio_Linux_${ARCH}.deb", deb_builder)

    def test_release_workflow_accepts_only_expected_final_assets_and_tags(self):
        workflow = Path(".github/workflows/build.yml").read_text(encoding="utf-8")

        self.assertIn("pull_request:", workflow)
        self.assertIn("branches: [main]", workflow)
        self.assertIn("tags: ['v*.*.*']", workflow)
        self.assertIn("github.event_name == 'push' && startsWith(github.ref, 'refs/tags/v')", workflow)
        self.assertIn("Nexar_Comercio_Windows_Setup.exe", workflow)
        self.assertIn("Nexar_Comercio_Linux_amd64.deb", workflow)
        self.assertIn("Cantidad inesperada de instaladores públicos", workflow)
        self.assertIn("SHA256SUMS contiene nombres públicos legacy", workflow)
        self.assertIn("Verificar SHA256 final", workflow)
        self.assertIn("Verificar firmas finales", workflow)

        checksum_step = workflow.split("      - name: Generar SHA256 único", 1)[1].split(
            "\n\n      - name:", 1
        )[0]
        self.assertIn("working-directory: final", checksum_step)
        self.assertIn("Nexar_Comercio_Linux_amd64.deb > SHA256SUMS.txt", checksum_step)
        self.assertNotIn("> final/SHA256SUMS.txt", checksum_step)

        package_job = workflow.split("  package:", 1)[1].split("\n  release:", 1)[0]
        tag_only = "github.event_name == 'push' && startsWith(github.ref, 'refs/tags/v')"
        self.assertNotIn("    env:\n      GPG_PRIVATE_KEY", package_job)
        self.assertNotIn("    env:\n      GPG_PASSPHRASE", package_job)
        self.assertIn(
            f"- name: Importar clave GPG\n        if: {tag_only}\n        env:\n"
            "          GPG_PRIVATE_KEY: ${{ secrets.GPG_PRIVATE_KEY }}",
            package_job,
        )
        self.assertIn(
            f"- name: Firmar archivos\n        if: {tag_only}\n        env:\n"
            "          GPG_PASSPHRASE: ${{ secrets.GPG_PASSPHRASE }}",
            package_job,
        )
        self.assertIn(f"- name: Verificar firmas finales\n        if: {tag_only}", package_job)
        self.assertNotIn("test -f \"final/$asset.sig\"", package_job.split("- name: Verificar SHA256 final", 1)[1].split("- name: Verificar firmas finales", 1)[0])


if __name__ == "__main__":
    unittest.main()
