import os
from dotenv import load_dotenv

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