import importlib
import os
import tempfile
import unittest
from pathlib import Path


HEADER = "Identificador de URL,Nombre,Categorías,Nombre de propiedad 1,Valor de propiedad 1,Precio,Costo,Stock,SKU,Código de barras,Mostrar en tienda\n"


class CatalogImportMixedIdentifierTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        os.environ["SECRET_KEY"] = "test-secret"

        import database
        from services import catalog_csv_import

        self.db = importlib.reload(database)
        self.db.DB_PATH = str(Path(self.temp_dir.name) / "catalog.db")
        self.db._db_initialized = False
        self.db.init_db()
        self.service = importlib.reload(catalog_csv_import)
        self.db.add_usuario(
            "importador",
            "1234",
            "Administrador",
            "Importador",
            security_question="color",
            security_answer="azul",
        )
        self.owner = int(self.db.get_usuario_by_username("importador")["id"])

    def _import(self, content: str):
        plan = self.service.build_plan(self.service.parse_tiendanube_csv(content.encode()))
        self.assertFalse(plan["errors"])
        plan_id, token = self.service.store_plan(plan, self.owner)
        return self.service.apply_stored_plan(plan_id, token, self.owner)

    def test_mixed_create_and_retained_update_reject_canonical_sku_collision(self):
        self._import(
            HEADER
            + "remera,Remera,Ropa,Color,Negro,100,40,5,ABC,7790000010501,SI\n"
        )
        before = self.db.q(
            "SELECT id, sku, codigo_barras, costo, precio FROM producto_variantes ORDER BY id"
        )
        stock_before = self.db.q(
            "SELECT variante_id, stock_actual FROM stock_variantes ORDER BY variante_id"
        )
        movements_before = self.db.q(
            "SELECT COUNT(*) AS total FROM stock_movimientos", fetchone=True
        )["total"]

        mixed = (
            HEADER
            + "remera,Remera,Ropa,Color,Blanco,110,45,2,abc,,SI\n"
            + "remera,,,Color,Negro,100,40,7,,7790000010501,SI\n"
        )
        plan = self.service.build_plan(self.service.parse_tiendanube_csv(mixed.encode()))
        self.assertFalse(plan["errors"])
        self.assertEqual(
            [row["variant_action"] for row in plan["products"][0]["rows"]],
            ["create", "update"],
        )
        plan_id, token = self.service.store_plan(plan, self.owner)

        with self.assertRaisesRegex(ValueError, "SKUs duplicados"):
            self.service.apply_stored_plan(plan_id, token, self.owner)

        after = self.db.q(
            "SELECT id, sku, codigo_barras, costo, precio FROM producto_variantes ORDER BY id"
        )
        stock_after = self.db.q(
            "SELECT variante_id, stock_actual FROM stock_variantes ORDER BY variante_id"
        )
        self.assertEqual([tuple(row) for row in after], [tuple(row) for row in before])
        self.assertEqual([tuple(row) for row in stock_after], [tuple(row) for row in stock_before])
        self.assertEqual(
            self.db.q("SELECT COUNT(*) AS total FROM stock_movimientos", fetchone=True)["total"],
            movements_before,
        )


if __name__ == "__main__":
    unittest.main()
