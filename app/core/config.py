
import os
from pathlib import Path
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env file."""

    mongodb_uri: str = "mongodb+srv://nextstop_admin:nextstop_2006saloni@cluster0.t7jdntk.mongodb.net/nextstop?retryWrites=true&w=majority"
    database_name: str = "nextstop"

    jwt_secret_key: str = "default_secret_key_change_in_production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30

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
