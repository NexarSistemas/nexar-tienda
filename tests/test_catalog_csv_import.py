import unittest

from services.catalog_csv_import import build_plan, parse_tiendanube_csv


HEADER = "Identificador de URL,Nombre,Categorías,Nombre de propiedad 1,Valor de propiedad 1,Precio,Costo,Stock,SKU,Código de barras,Mostrar en tienda\n"


class TiendanubeCsvAdapterTests(unittest.TestCase):
    def test_utf8_bom_simple_product(self):
        rows = parse_tiendanube_csv(("\ufeff" + HEADER + "mate,Maté,Accesorios,,,1200,600,3,,,SI\n").encode())
        self.assertEqual(rows[0]["external_group"], "mate")
        self.assertEqual(rows[0]["stock"], 3)

    def test_groups_multiple_variants_with_neutral_attributes(self):
        content = HEADER + "remera,Remera,Ropa,Material,Algodón,100,40,2,R-ALG,,SI\nremera,,,Material,Lino,110,45,1,R-LIN,,SI\n"
        rows = parse_tiendanube_csv(content.encode())
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1]["attributes"], [{"name": "Material", "value": "Lino"}])

    def test_rejects_missing_headers_empty_and_non_finite_numbers(self):
        with self.assertRaisesRegex(ValueError, "incompatibles"):
            parse_tiendanube_csv(b"Nombre,Precio\nProducto,10\n")
        with self.assertRaisesRegex(ValueError, "vacio"):
            parse_tiendanube_csv(b"")
        with self.assertRaisesRegex(ValueError, "finito"):
            parse_tiendanube_csv((HEADER + "x,Producto,,,,NaN,2,1,,,SI\n").encode())

    def test_rejects_malformed_row_and_duplicate_sku_before_persistence(self):
        with self.assertRaisesRegex(ValueError, "cantidad incorrecta"):
            parse_tiendanube_csv((HEADER + "x,Producto\n").encode())
        rows = parse_tiendanube_csv((HEADER + "x,Producto,,,,1,1,1,DUP,,SI\ny,Otro,,,,1,1,1,DUP,,SI\n").encode())
        plan = build_plan(rows)
        self.assertTrue(any(error["field"] == "SKU" for error in plan["errors"]))


if __name__ == "__main__":
    unittest.main()
