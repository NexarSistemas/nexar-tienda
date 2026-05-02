import os
from dotenv import load_dotenv

from licensing.planes import PLANES, TIER_ALIASES

# Cargar .env automáticamente
load_dotenv()

class Settings:
    """Configuración base para Nexar apps"""

    # =========================
    # APP
    # =========================
    APP_NAME = os.getenv("APP_NAME", "Nexar App")
    ENV = os.getenv("ENV", "development")  # development / production

    # =========================
    # SEGURIDAD
    # =========================
    SECRET_KEY = os.getenv("SECRET_KEY")

    # =========================
    # SUPABASE
    # =========================
    SUPABASE_URL = os.getenv("SUPABASE_URL")
    SUPABASE_KEY = os.getenv("SUPABASE_KEY")

    # =========================
    # LICENCIAS
    # =========================
    LICENSE_PRODUCT = os.getenv("LICENSE_PRODUCT", "nexar-tienda")

    # =========================
    # CACHE
    # =========================
    CACHE_FILE = os.getenv("CACHE_FILE", "license_cache.json")
    CACHE_DAYS = int(os.getenv("CACHE_DAYS", "3"))

    # =========================
    # DEBUG
    # =========================
    DEBUG = ENV == "development"

    # =========================
    # LICENCIAS - INTEGRACIÓN MODULAR
    # =========================
    LICENSE_MODE = os.getenv("NEXAR_LICENSE_MODE", "dev")  # "dev" o "prod"
    LICENSE_PLAN = os.getenv("NEXAR_PLAN", "DEMO")  # DEMO, BASICA, MENSUAL_FULL (dev mode)
    LICENSE_MODULES = os.getenv("NEXAR_MODULES", "")  # módulos extra (dev mode)

    TIER_ALIASES = TIER_ALIASES
    TIER_TO_MODULES = {tier: sorted(modules) for tier, modules in PLANES.items()}

    # =========================
    # VALIDACIÓN
    # =========================
    def validate(self):
        """Valida configuración crítica"""
        if not self.SECRET_KEY:
            raise RuntimeError("SECRET_KEY no definida")

        if not self.SUPABASE_URL:
            raise RuntimeError("SUPABASE_URL no definida")

        if not self.SUPABASE_KEY:
            raise RuntimeError("SUPABASE_KEY no definida")


# instancia global
settings = Settings()
settings.validate()
