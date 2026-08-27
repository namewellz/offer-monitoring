from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    app_env: str = "development"
    database_url: str = "postgresql+psycopg://flyer:flyer@localhost:5432/flyer"
    redis_url: str = "redis://localhost:6379/0"
    ollama_base_url: str = "http://host.docker.internal:11434"
    ollama_model: str = "qwen3-vl:8b"
    flyer_storage_path: Path = Path("/data")
    discovery_enabled: bool = True
    discovery_cron: str = "0 */6 * * *"
    catalog_collection_enabled: bool = True
    catalog_collection_cron: str = "0 6,14,22 * * *"
    davita_api_token: str | None = None
    davita_token_file: Path = Path("/run/secrets/davita_dotenv")
    assai_username: str | None = None
    assai_password: SecretStr | None = None
    assai_bundle_file: Path = Path("/run/secrets/meu_assai_bundle.js")
    scheduler_timezone: str = "America/Sao_Paulo"
    http_timeout_seconds: int = 30
    http_max_retries: int = 3
    extraction_max_retries: int = 2
    qwen_temperature: float = 0
    qwen_request_timeout_seconds: int = 300
    qwen_context_size: int = 16384
    qwen_num_predict: int = 8192
    extraction_mode: str = "tiles"
    tile_overlap_percent: int = 20
    max_asset_size_mb: int = 50
    job_lock_timeout_seconds: int = 1800
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
