"""
Configuración central del Módulo de Tiempos SIRH.
Carga exclusivamente desde variables de entorno o archivo .env.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Cargar .env si existe en la raíz del proyecto
_root = Path(__file__).resolve().parent.parent.parent
_env_path = _root / ".env"
if _env_path.exists():
    load_dotenv(dotenv_path=_env_path)


def _get_bool(key: str, default: bool = False) -> bool:
    val = os.getenv(key)
    if val is None:
        return default
    return val.strip().lower() in ("true", "1", "yes", "si", "s")


class Settings:
    # Base de Datos (SQLite por defecto para desarrollo ágil, PostgreSQL para producción on-premise)
    DATABASE_URL: str = os.getenv("DATABASE_URL", f"sqlite:///{_root / 'sirh_tiempos.db'}")

    # BioTime API
    BIOTIME_BASE_URL: str = os.getenv("BIOTIME_BASE_URL", "").rstrip("/")
    BIOTIME_USER: str = os.getenv("BIOTIME_USER", "")
    BIOTIME_PASS: str = os.getenv("BIOTIME_PASS", "")
    BIOTIME_TIMEOUT: int = int(os.getenv("BIOTIME_TIMEOUT", "60"))
    BIOTIME_PAGE_SIZE: int = int(os.getenv("BIOTIME_PAGE_SIZE", "500"))
    BIOTIME_VERIFY_SSL: bool = _get_bool("BIOTIME_VERIFY_SSL", False)

    # Entorno
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    SECRET_KEY: str = os.getenv("SECRET_KEY", "sirh-plastitec-insecure-secret-key-change-in-prod")


settings = Settings()
