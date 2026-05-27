"""Configuracion central leida de variables de entorno (.env).

Una sola fuente de verdad para rutas, credenciales y parametros.
Importar `settings` desde aqui en el resto del codigo.
"""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Raiz del repo (este fichero esta en api/config.py -> raiz = parent.parent)
ROOT_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Parametros de la app. Prefijo CLARITY_ para los propios; el resto literal."""

    model_config = SettingsConfigDict(
        env_file=ROOT_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Base de datos
    clarity_db_path: str = "data/clarity.db"

    # API
    clarity_api_host: str = "127.0.0.1"
    clarity_api_port: int = 8000
    clarity_api_url: str = "http://127.0.0.1:8000"

    # Azure OpenAI (vacio -> insights por plantilla, sin LLM)
    azure_openai_endpoint: str = ""
    azure_openai_api_key: str = ""
    azure_openai_deployment: str = "gpt-4o-mini"
    azure_openai_api_version: str = "2024-06-01"
    azure_openai_region: str = "swedencentral"

    # Anonimizacion
    presidio_spacy_model: str = "es_core_news_md"

    @property
    def db_path(self) -> Path:
        """Ruta absoluta al fichero SQLite (crea el directorio padre si falta)."""
        p = Path(self.clarity_db_path)
        if not p.is_absolute():
            p = ROOT_DIR / p
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def llm_enabled(self) -> bool:
        """True si hay credenciales Azure para usar el LLM real."""
        return bool(self.azure_openai_endpoint and self.azure_openai_api_key)


settings = Settings()
