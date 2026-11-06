
from pathlib import Path
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env file."""

    # MongoDB settings
    mongodb_uri: str
    database_name: str = "nextstop"

    # Supabase settings
    supabase_url: str
    supabase_secret_key: str
    supabase_bucket: str = "nextstop-media"

    # JWT settings
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 43200
    refresh_token_expire_days: int = 90

    # CORS settings
    allowed_origins: str = "*"

    model_config = SettingsConfigDict(
        env_file=str(
            Path(__file__).resolve().parent.parent.parent / ".env"
        ),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    @property
    def cors_origins(self) -> List[str]:
        """Return parsed CORS origins."""

        if self.allowed_origins.strip() == "*":
            return ["*"]

        return [
            origin.strip()
            for origin in self.allowed_origins.split(",")
            if origin.strip()
        ]


settings = Settings()
