import importlib
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _reset_env():
    for key in ("FLASK_ENV", "NEXAR_LICENSE_MODE", "NEXAR_EXTRA_MODULES", "SECRET_KEY"):
        os.environ.pop(key, None)


class AttributeProfileTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        _reset_env()
        os.environ["SECRET_KEY"] = "test-secret"
        os.environ["FLASK_ENV"] = "development"
        os.environ["NEXAR_LICENSE_MODE"] = "prod"

        import app as app_module
        import database
        from routes import main as routes_main
        from services import attribute_profiles
        from services import product_variants

        self.database = importlib.reload(database)
        self.database.DB_PATH = str(Path(self.temp_dir.name) / "test_tienda.db")
        self.database._db_initialized = False
        self.database.init_db()

        self.attribute_profiles = importlib.reload(attribute_profiles)
        self.product_variants = importlib.reload(product_variants)
        self.routes_main = importlib.reload(routes_main)
        self.routes_main.db = self.database
        self.routes_main.attribute_profiles = self.attribute_profiles
        self.routes_main.product_variants = self.product_variants

        self.app_module = importlib.reload(app_module)
        self.app_module.db = self.database
        self.app = self.app_module.create_app()

        self.database.add_usuario(
            "admin",
            "1234",
            "Administrador",
            "Administrador Test",
            security_question="color",
            security_answer="azul",
        )
        self.database.set_rubro_configurado("tienda")

    def tearDown(self):
        _reset_env()

    def _login_admin(self, client):
        with client.session_transaction() as session:
            session["_csrf_token"] = "test-token"
        response = client.post(
            "/login",
            data={"username": "admin", "password": "1234", "csrf_token": "test-token"},
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)

    def _crear_producto_simple(self, descripcion="Producto simple"):
        return int(
            self.database.add_producto(
                {
                    "descripcion": descripcion,
                    "marca": "",
                    "categoria": "General",
                    "tipo_unidad": "unidad",
                    "unidad": "unidad",
                    "stock_actual": 3,
                    "stock_minimo": 1,
                    "stock_maximo": 8,
                    "costo": 10,
                    "precio_venta": 20,
                    "iva": "21%",
                }
            )
        )

    def _profile_by_name(self, name):
        key = self.database._attribute_profile_key(name)
        for profile in self.attribute_profiles.list_profiles():
            if profile["nombre_normalizado"] == key:
                return profile
        return None

    def _attribute_by_key(self, name):
        return self.database.q(
            "SELECT id, nombre, nombre_normalizado FROM producto_atributos WHERE nombre_normalizado=?",
            (self.database.normalize_attribute_name_key(name),),
            fetchone=True,
        )

    def test_perfiles_iniciales_configurables_e_idempotentes(self):
        perfiles = {profile["nombre"]: profile for profile in self.attribute_profiles.list_profiles()}

        self.assertEqual(perfiles["Indumentaria"]["seed_key"], "indumentaria")
        self.assertEqual(perfiles["Calzado"]["seed_key"], "calzado")
        self.assertEqual(perfiles["Ferreteria"]["seed_key"], "ferreteria")
        self.assertEqual(
            [attr["nombre"] for attr in perfiles["Indumentaria"]["atributos"]],
            ["Talle", "Color"],
        )
        self.assertEqual(
            [attr["nombre"] for attr in perfiles["Calzado"]["atributos"]],
            ["Número", "Color"],
        )
        self.assertEqual(
            [attr["nombre"] for attr in perfiles["Ferreteria"]["atributos"]],
            ["Medida", "Material"],
        )

        self.database._db_initialized = False
        self.database.init_db()

        self.assertEqual(
            self.database.q("SELECT COUNT(*) AS total FROM atributo_perfiles", fetchone=True)["total"],
            3,
        )
        self.assertEqual(
            self.database.q("SELECT COUNT(*) AS total FROM atributo_perfil_atributos", fetchone=True)["total"],
            6,
        )

    def test_seed_renombrada_conserva_identidad_y_no_se_duplica_en_init_db(self):
        profile = self._profile_by_name("Indumentaria")
        self.attribute_profiles.update_profile(
            profile["id"],
            "Ropa",
            descripcion="Nombre editado",
            activo=False,
            orden=99,
            attribute_names=["Talle"],
        )

        self.database._db_initialized = False
        self.database.init_db()

        row = self.database.q(
            "SELECT id, seed_key, nombre, descripcion, activo, orden FROM atributo_perfiles WHERE seed_key=?",
            ("indumentaria",),
            fetchone=True,
        )
        self.assertEqual(int(row["id"]), profile["id"])
        self.assertEqual(row["nombre"], "Ropa")
        self.assertEqual(row["descripcion"], "Nombre editado")
        self.assertEqual(int(row["activo"]), 0)
        self.assertEqual(int(row["orden"]), 99)
        self.assertIsNone(self._profile_by_name("Indumentaria"))
        self.assertEqual(
            self.database.q("SELECT COUNT(*) AS total FROM atributo_perfiles", fetchone=True)["total"],
            3,
        )

    def test_base_legacy_sin_seed_key_se_migra_idempotentemente(self):
        profile = self._profile_by_name("Indumentaria")
        self.database.q(
            "UPDATE atributo_perfiles SET seed_key=NULL WHERE id=?",
            (profile["id"],),
            commit=True,
        )

        self.database._db_initialized = False
        self.database.init_db()
        self.database._db_initialized = False
        self.database.init_db()

        row = self.database.q(
            "SELECT id, seed_key FROM atributo_perfiles WHERE nombre_normalizado=?",
            (self.database._attribute_profile_key("Indumentaria"),),
            fetchone=True,
        )
        self.assertEqual(int(row["id"]), profile["id"])
        self.assertEqual(row["seed_key"], "indumentaria")
        self.assertEqual(
            self.database.q("SELECT COUNT(*) AS total FROM atributo_perfiles WHERE seed_key='indumentaria'", fetchone=True)["total"],
            1,
        )

    def test_perfiles_personalizados_no_reciben_seed_key(self):
        profile_id = self.attribute_profiles.create_profile(
            "Mascotas",
            descripcion="Personalizado",
            activo=True,
            attribute_names=["Tamaño"],
        )

        profile = self.attribute_profiles.get_profile(profile_id)
        self.assertIsNone(profile["seed_key"])

    def test_calzado_numero_usa_normalizacion_de_variantes_sin_duplicar(self):
        calzado = self._profile_by_name("Calzado")
        numero_attr = next(attr for attr in calzado["atributos"] if attr["nombre"] == "Número")
        expected_key = self.database.normalize_attribute_name_key("Número")

        self.assertEqual(numero_attr["nombre_normalizado"], expected_key)
        self.assertEqual(expected_key, "número")
        self.assertEqual(int(self._attribute_by_key("Número")["id"]), numero_attr["id"])
        self.assertEqual(
            self.database.q(
                "SELECT COUNT(*) AS total FROM producto_atributos WHERE nombre=?",
                ("Número",),
                fetchone=True,
            )["total"],
            1,
        )

        self.database._db_initialized = False
        self.database.init_db()

        self.assertEqual(
            self.database.q(
                "SELECT COUNT(*) AS total FROM producto_atributos WHERE nombre_normalizado=?",
                (expected_key,),
                fetchone=True,
            )["total"],
            1,
        )

    def test_variante_con_numero_reutiliza_atributo_sugerido_por_calzado(self):
        calzado = self._profile_by_name("Calzado")
        self.attribute_profiles.set_rubro_profile("tienda", calzado["id"])
        suggested_attr = next(attr for attr in calzado["atributos"] if attr["nombre"] == "Número")
        producto_id = self._crear_producto_simple("Zapato con número")

        self.product_variants.create_variant(
            producto_id,
            attributes=[{"attribute_name": "Número", "value_name": "40"}],
            sku="ZAP-40",
            stock_actual=1,
            stock_minimo=0,
            stock_maximo=5,
        )

        variant_attr = self.database.q(
            """
            SELECT a.id
            FROM producto_variante_valores vv
            JOIN producto_atributo_valores v ON v.id = vv.valor_id
            JOIN producto_atributos a ON a.id = v.atributo_id
            WHERE vv.variante_id = (
                SELECT id FROM producto_variantes WHERE producto_id=? LIMIT 1
            )
            """,
            (producto_id,),
            fetchone=True,
        )
        self.assertEqual(int(variant_attr["id"]), suggested_attr["id"])
        self.assertEqual(
            self.database.q(
                "SELECT COUNT(*) AS total FROM producto_atributos WHERE nombre_normalizado=?",
                (self.database.normalize_attribute_name_key("Número"),),
                fetchone=True,
            )["total"],
            1,
        )

    def test_gestion_variantes_muestra_badge_sugerido_para_numero(self):
        calzado = self._profile_by_name("Calzado")
        self.attribute_profiles.set_rubro_profile("tienda", calzado["id"])
        producto_id = self._crear_producto_simple("Zapato UI")

        with self.app.test_client() as client:
            self._login_admin(client)
            response = client.get(f"/productos/{producto_id}/variantes")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('data-attribute-name="Número"', html)
        self.assertIn("Sugerido", html)

    def test_perfiles_con_nombres_acentuados_conservan_normalizacion_independiente(self):
        profile_id = self.attribute_profiles.create_profile(
            "Decoración",
            descripcion="Perfil con acento",
            attribute_names=["Número"],
        )

        profile = self.attribute_profiles.get_profile(profile_id)
        self.assertEqual(profile["nombre_normalizado"], "decoracion")
        self.assertEqual(profile["atributos"][0]["nombre_normalizado"], "número")

    def test_init_db_no_restaura_asociaciones_quitadas_de_perfil_existente(self):
        profile = self._profile_by_name("Indumentaria")
        attr = next(item for item in profile["atributos"] if item["nombre"] == "Color")
        self.database.q(
            "DELETE FROM atributo_perfil_atributos WHERE perfil_id=? AND atributo_id=?",
            (profile["id"], attr["id"]),
            commit=True,
        )

        self.database._db_initialized = False
        self.database.init_db()

        updated = self.attribute_profiles.get_profile(profile["id"])
        self.assertEqual([item["nombre"] for item in updated["atributos"]], ["Talle"])

    def test_creacion_edicion_y_asociacion_de_atributos(self):
        profile_id = self.attribute_profiles.create_profile(
            "Decoracion",
            descripcion="Perfil inicial",
            orden=5,
            attribute_names=["Material", "Textura"],
        )

        profile = self.attribute_profiles.get_profile(profile_id)
        self.assertEqual(profile["nombre"], "Decoracion")
        self.assertEqual([attr["nombre"] for attr in profile["atributos"]], ["Material", "Textura"])

        self.attribute_profiles.update_profile(
            profile_id,
            "Decoracion premium",
            descripcion="Perfil editado",
            activo=False,
            orden=7,
            attribute_names=["Color"],
        )

        edited = self.attribute_profiles.get_profile(profile_id)
        self.assertFalse(edited["activo"])
        self.assertEqual(edited["descripcion"], "Perfil editado")
        self.assertEqual([attr["nombre"] for attr in edited["atributos"]], ["Color"])
        self.assertIsNotNone(
            self.database.q(
                "SELECT id FROM producto_atributos WHERE nombre_normalizado=?",
                (self.database._attribute_profile_key("Material"),),
                fetchone=True,
            )
        )

    def test_activacion_desactivacion_y_repeticion_sin_duplicados(self):
        profile = self._profile_by_name("Indumentaria")
        self.attribute_profiles.set_rubro_profile("tienda", profile["id"])
        self.attribute_profiles.set_rubro_profile("tienda", profile["id"])

        self.assertEqual(self.attribute_profiles.get_rubro_profile("tienda")["id"], profile["id"])
        self.assertEqual(
            self.database.q("SELECT COUNT(*) AS total FROM rubro_atributo_perfiles WHERE rubro='tienda'", fetchone=True)["total"],
            1,
        )
        self.assertEqual(
            self.database.q(
                "SELECT COUNT(*) AS total FROM atributo_perfil_atributos WHERE perfil_id=?",
                (profile["id"],),
                fetchone=True,
            )["total"],
            2,
        )

        self.attribute_profiles.set_profile_active(profile["id"], False)
        self.assertFalse(self.attribute_profiles.get_profile(profile["id"])["activo"])
        with self.assertRaises(ValueError):
            self.attribute_profiles.set_rubro_profile("almacen", profile["id"])
        self.attribute_profiles.set_rubro_profile("tienda", "")
        self.assertIsNone(self.attribute_profiles.get_rubro_profile("tienda"))

    def test_perfil_activo_devuelve_atributos_sugeridos_en_orden(self):
        profile = self._profile_by_name("Indumentaria")
        self.attribute_profiles.set_rubro_profile("tienda", profile["id"])

        sugeridos = self.attribute_profiles.get_effective_suggested_attributes("tienda")

        self.assertEqual([attr["nombre"] for attr in sugeridos], ["Talle", "Color"])

    def test_perfil_inactivo_no_genera_sugerencias(self):
        profile = self._profile_by_name("Indumentaria")
        self.attribute_profiles.set_rubro_profile("tienda", profile["id"])
        self.attribute_profiles.set_profile_active(profile["id"], False)

        self.assertEqual(self.attribute_profiles.get_effective_suggested_attributes("tienda"), [])

    def test_rubro_sin_perfil_devuelve_sugerencias_vacias(self):
        self.assertEqual(self.attribute_profiles.get_effective_suggested_attributes("almacen"), [])

    def test_rubro_sin_perfil_y_producto_simple_siguen_neutros(self):
        self.assertIsNone(self.attribute_profiles.get_rubro_profile("almacen"))
        producto_id = self._crear_producto_simple()

        self.assertEqual(
            self.database.q("SELECT COUNT(*) AS total FROM producto_variantes", fetchone=True)["total"],
            0,
        )
        producto = self.database.get_producto(producto_id)
        self.assertEqual(producto["stock_modo"], "legacy")
        stock = self.database.q("SELECT stock_actual FROM stock WHERE producto_id=?", (producto_id,), fetchone=True)
        self.assertEqual(float(stock["stock_actual"]), 3.0)

    def test_desactivar_perfil_conserva_datos_de_productos(self):
        profile = self._profile_by_name("Indumentaria")
        producto_id = self._crear_producto_simple("Remera")
        variante_id = self.product_variants.create_variant(
            producto_id,
            attributes=[{"attribute_name": "Color", "value_name": "Rojo"}],
            sku="REM-ROJO",
            stock_actual=1.25,
            stock_minimo=0,
            stock_maximo=5,
        )

        self.attribute_profiles.set_profile_active(profile["id"], False)

        self.assertIsNotNone(
            self.database.q("SELECT id FROM producto_variantes WHERE id=?", (variante_id,), fetchone=True)
        )
        self.assertIsNotNone(
            self.database.q(
                """
                SELECT v.id
                FROM producto_atributo_valores v
                JOIN producto_atributos a ON a.id = v.atributo_id
                WHERE a.nombre_normalizado=? AND v.valor_normalizado=?
                """,
                (self.database._attribute_profile_key("Color"), self.database._attribute_profile_key("Rojo")),
                fetchone=True,
            )
        )

    def test_gestion_variantes_muestra_sugerencias_del_perfil_activo(self):
        profile = self._profile_by_name("Indumentaria")
        self.attribute_profiles.set_rubro_profile("tienda", profile["id"])
        producto_id = self._crear_producto_simple("Remera UI")

        with self.app.test_client() as client:
            self._login_admin(client)
            response = client.get(f"/productos/{producto_id}/variantes")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("Atributos sugeridos por el perfil activo", html)
        self.assertIn('data-attribute-name="Talle"', html)
        self.assertIn('data-attribute-name="Color"', html)
        self.assertIn("Sugerido", html)
        self.assertEqual(
            self.database.q("SELECT COUNT(*) AS total FROM producto_variantes", fetchone=True)["total"],
            0,
        )
        self.assertEqual(self.database.get_producto(producto_id)["stock_modo"], "legacy")

    def test_atributo_adicional_no_perteneciente_al_perfil_sigue_permitido(self):
        profile = self._profile_by_name("Indumentaria")
        self.attribute_profiles.set_rubro_profile("tienda", profile["id"])
        producto_id = self._crear_producto_simple("Producto atributo libre")

        variant_id = self.product_variants.create_variant(
            producto_id,
            attributes=[{"attribute_name": "Textura", "value_name": "Lisa"}],
            sku="LIBRE-1",
            stock_actual=1,
            stock_minimo=0,
            stock_maximo=5,
        )

        variante = self.product_variants.list_product_variants(producto_id)[0]
        self.assertEqual(variante["id"], variant_id)
        self.assertEqual(variante["resumen_atributos"], "Textura: Lisa")
        self.assertEqual(
            [attr["nombre"] for attr in self.attribute_profiles.get_effective_suggested_attributes("tienda")],
            ["Talle", "Color"],
        )

    def test_cambiar_perfil_actualiza_sugerencias_sin_modificar_variantes(self):
        indumentaria = self._profile_by_name("Indumentaria")
        calzado = self._profile_by_name("Calzado")
        producto_id = self._crear_producto_simple("Producto cambia perfil")
        variant_id = self.product_variants.create_variant(
            producto_id,
            attributes=[{"attribute_name": "Color", "value_name": "Negro"}],
            sku="CAMBIO-1",
            stock_actual=1,
            stock_minimo=0,
            stock_maximo=5,
        )

        self.attribute_profiles.set_rubro_profile("tienda", indumentaria["id"])
        self.assertEqual(
            [attr["nombre"] for attr in self.attribute_profiles.get_effective_suggested_attributes("tienda")],
            ["Talle", "Color"],
        )
        self.attribute_profiles.set_rubro_profile("tienda", calzado["id"])

        self.assertEqual(
            [attr["nombre"] for attr in self.attribute_profiles.get_effective_suggested_attributes("tienda")],
            ["Número", "Color"],
        )
        variante = self.product_variants.list_product_variants(producto_id)[0]
        self.assertEqual(variante["id"], variant_id)
        self.assertEqual(variante["resumen_atributos"], "Color: Negro")

    def test_desactivar_perfil_quita_sugerencia_no_datos(self):
        profile = self._profile_by_name("Indumentaria")
        self.attribute_profiles.set_rubro_profile("tienda", profile["id"])
        producto_id = self._crear_producto_simple("Producto sin sugerencia")
        variant_id = self.product_variants.create_variant(
            producto_id,
            attributes=[{"attribute_name": "Talle", "value_name": "M"}],
            sku="SUG-1",
            stock_actual=1,
            stock_minimo=0,
            stock_maximo=5,
        )

        self.attribute_profiles.set_profile_active(profile["id"], False)

        self.assertEqual(self.attribute_profiles.get_effective_suggested_attributes("tienda"), [])
        self.assertIsNotNone(
            self.database.q("SELECT id FROM producto_variantes WHERE id=?", (variant_id,), fetchone=True)
        )
        self.assertIsNotNone(
            self.database.q(
                "SELECT id FROM producto_atributos WHERE nombre_normalizado=?",
                (self.database._attribute_profile_key("Talle"),),
                fetchone=True,
            )
        )

    def test_almacen_conserva_fraccionamiento_y_capacidades(self):
        from services.rubros import convertir_cantidad_a_base, es_unidad_fraccionable, get_unidades_disponibles

        self.database.set_rubro_configurado("almacen")
        unidades = get_unidades_disponibles("almacen")
        self.assertIn("kg", unidades)
        self.assertIn("gramo", unidades)
        self.assertTrue(es_unidad_fraccionable("gramo"))
        self.assertEqual(convertir_cantidad_a_base(750, "gramo"), 0.75)

    def test_base_legacy_sin_tablas_de_perfiles_conserva_productos(self):
        producto_id = self._crear_producto_simple("Legacy")
        conn = self.database.get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("DROP TABLE IF EXISTS rubro_atributo_perfiles")
            cursor.execute("DROP TABLE IF EXISTS atributo_perfil_atributos")
            cursor.execute("DROP TABLE IF EXISTS atributo_perfiles")
            conn.commit()
        finally:
            conn.close()

        self.database._db_initialized = False
        self.database.init_db()

        self.assertEqual(self.database.get_producto(producto_id)["descripcion"], "Legacy")
        self.assertEqual(
            self.database.q("SELECT COUNT(*) AS total FROM atributo_perfiles", fetchone=True)["total"],
            3,
        )

    def test_ui_config_crear_perfil_sin_activo_guarda_inactivo(self):
        with self.app.test_client() as client:
            self._login_admin(client)
            response = client.post(
                "/config/atributo-perfil",
                data={
                    "csrf_token": "test-token",
                    "nombre": "Inactivo UI",
                    "descripcion": "Sin checkbox",
                    "atributos": "Color",
                    "orden": "51",
                },
                follow_redirects=False,
            )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(self._profile_by_name("Inactivo UI")["activo"])

    def test_ui_config_editar_perfil_sin_activo_guarda_inactivo(self):
        profile_id = self.attribute_profiles.create_profile("Editable UI", activo=True, attribute_names=["Color"])

        with self.app.test_client() as client:
            self._login_admin(client)
            response = client.post(
                f"/config/atributo-perfil/{profile_id}/editar",
                data={
                    "csrf_token": "test-token",
                    "nombre": "Editable UI",
                    "descripcion": "Sin checkbox",
                    "atributos": "Color",
                    "orden": "52",
                },
                follow_redirects=False,
            )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(self.attribute_profiles.get_profile(profile_id)["activo"])

    def test_ui_config_crear_y_editar_con_activo_guarda_activo(self):
        with self.app.test_client() as client:
            self._login_admin(client)
            response = client.post(
                "/config/atributo-perfil",
                data={
                    "csrf_token": "test-token",
                    "nombre": "Activo UI",
                    "descripcion": "Con checkbox",
                    "atributos": "Color",
                    "activo": "1",
                    "orden": "53",
                },
                follow_redirects=False,
            )
            self.assertEqual(response.status_code, 302)
            profile = self._profile_by_name("Activo UI")
            self.assertTrue(profile["activo"])

            response = client.post(
                f"/config/atributo-perfil/{profile['id']}/editar",
                data={
                    "csrf_token": "test-token",
                    "nombre": "Activo UI",
                    "descripcion": "Con checkbox editado",
                    "atributos": "Color",
                    "activo": "1",
                    "orden": "54",
                },
                follow_redirects=False,
            )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(self.attribute_profiles.get_profile(profile["id"])["activo"])

    def test_no_hay_condicionales_fijos_por_nombre_de_rubro(self):
        patrones = ("if rubro", "if normalizar_rubro", "elif rubro")
        nombres = ("indumentaria", "calzado", "ferreteria", "ferretería")
        for relative_path in ("database.py", "services/attribute_profiles.py", "routes/main.py"):
            text = (PROJECT_ROOT / relative_path).read_text(encoding="utf-8").lower()
            for pattern in patrones:
                if pattern in text:
                    for name in nombres:
                        self.assertNotIn(f"{pattern} == \"{name}\"", text)
                        self.assertNotIn(f"{pattern} == '{name}'", text)

    def test_rollback_ante_error_en_creacion_de_perfil(self):
        with mock.patch.object(
            self.attribute_profiles.db,
            "_ensure_profile_attribute_in_cursor",
            side_effect=RuntimeError("fallo simulado"),
        ):
            with self.assertRaises(RuntimeError):
                self.attribute_profiles.create_profile("Rollback", attribute_names=["Color"])

        self.assertIsNone(self._profile_by_name("Rollback"))

    def test_ui_config_permite_crear_editar_y_seleccionar_perfil(self):
        with self.app.test_client() as client:
            self._login_admin(client)
            response = client.get("/config")
            self.assertEqual(response.status_code, 200)
            html = response.get_data(as_text=True)
            self.assertIn("Perfiles de Atributos", html)
            self.assertIn("bloquea atributos adicionales", html)

            response = client.post(
                "/config/atributo-perfil",
                data={
                    "csrf_token": "test-token",
                    "nombre": "Mascotas",
                    "descripcion": "Accesorios por mascota",
                    "atributos": "Tamaño, Material",
                    "activo": "1",
                    "orden": "40",
                },
                follow_redirects=False,
            )
            self.assertEqual(response.status_code, 302)
            profile = self._profile_by_name("Mascotas")
            self.assertIsNotNone(profile)

            response = client.post(
                f"/config/atributo-perfil/{profile['id']}/editar",
                data={
                    "csrf_token": "test-token",
                    "nombre": "Mascotas",
                    "descripcion": "Editado",
                    "atributos": "Tamaño, Color",
                    "activo": "1",
                    "orden": "41",
                },
                follow_redirects=False,
            )
            self.assertEqual(response.status_code, 302)

            response = client.post(
                "/config/atributo-perfil/rubro",
                data={"csrf_token": "test-token", "perfil_id": str(profile["id"])},
                follow_redirects=False,
            )
            self.assertEqual(response.status_code, 302)
            self.assertEqual(self.attribute_profiles.get_rubro_profile("tienda")["id"], profile["id"])


if __name__ == "__main__":
    unittest.main()
