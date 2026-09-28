"""Application configuration via environment variables (never hardcode business values)."""
import os
from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "Karyana Manager"
    version: str = "1.0.0"
    data_dir: str = "data"
    database_url: str = ""          # empty -> sqlite file under data_dir
    secret_key: str = "change-me-in-production"
    token_ttl_hours: int = 12
    device_id: str = "POS-01"       # this machine's device identity
    cloud_url: str = ""             # remote server base URL for sync/backup
    cloud_api_key: str = ""
    whatsapp_api_url: str = ""      # official WhatsApp Business Platform endpoint
    whatsapp_api_token: str = ""
    whatsapp_phone_number_id: str = ""

    class Config:
        env_file = ".env"
        env_prefix = "KARYANA_"

    @property
    def db_url(self) -> str:
        if self.database_url:
            return self.database_url
        os.makedirs(self.data_dir, exist_ok=True)
        return f"sqlite:///{os.path.join(self.data_dir, 'karyana.db')}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
