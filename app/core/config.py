import re
from pathlib import Path
from typing import List, Union

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Project directory paths for reliable .env discovery across local and cloud environments
BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
PROJECT_ROOT_DIR = BACKEND_DIR.parent


class Settings(BaseSettings):
    """Production-grade application configuration loaded from environment variables and .env file.

    Features:
    - Validates MongoDB Atlas, Supabase Storage, and JWT authentication settings.
    - Cloud deployment ready (Render, Docker, local development).
    - Preserves 100% compatibility with existing backend and frontend consumers.
    - Masks and redacts sensitive credentials from logs, prints, and error reports.
    """

    # --------------------------------------------------------------------------
    # Application & Environment Settings
    # --------------------------------------------------------------------------
    app_name: str = Field(
        default="Next Stop API",
        validation_alias=AliasChoices("app_name", "APP_NAME"),
        description="Public API application title",
    )
    environment: str = Field(
        default="production",
        validation_alias=AliasChoices("environment", "ENVIRONMENT", "env", "ENV"),
        description="Deployment environment (development, staging, production)",
    )
    debug: bool = Field(
        default=False,
        validation_alias=AliasChoices("debug", "DEBUG"),
        description="Debug mode toggle (False in production)",
    )
    port: int = Field(
        default=8000,
        validation_alias=AliasChoices("port", "PORT"),
        description="Server binding port (Render injects PORT automatically)",
    )

    # --------------------------------------------------------------------------
    # MongoDB Settings (Primary Document & Relational Storage)
    # --------------------------------------------------------------------------
    mongodb_uri: str = Field(
        validation_alias=AliasChoices(
            "mongodb_uri",
            "MONGODB_URI",
            "mongo_uri",
            "MONGO_URI",
            "mongodb_url",
            "MONGODB_URL",
        ),
        description="MongoDB Atlas connection URI with credentials and options",
    )
    database_name: str = Field(
        default="nextstop",
        validation_alias=AliasChoices(
            "database_name",
            "DATABASE_NAME",
            "mongo_database",
            "MONGO_DATABASE",
            "mongodb_database",
            "MONGODB_DATABASE",
        ),
        description="Target MongoDB database name",
    )

    # --------------------------------------------------------------------------
    # Supabase Settings (Media & Object Storage)
    # --------------------------------------------------------------------------
    supabase_url: str = Field(
        validation_alias=AliasChoices(
            "supabase_url",
            "SUPABASE_URL",
            "next_public_supabase_url",
            "NEXT_PUBLIC_SUPABASE_URL",
        ),
        description="Supabase project URL (e.g. 'https://<project-ref>.supabase.co')",
    )
    supabase_secret_key: str = Field(
        validation_alias=AliasChoices(
            "supabase_secret_key",
            "SUPABASE_SECRET_KEY",
            "supabase_service_role_key",
            "SUPABASE_SERVICE_ROLE_KEY",
            "supabase_key",
            "SUPABASE_KEY",
        ),
        description="Supabase Service Role secret or API key for secure media storage operations",
    )
    supabase_bucket: str = Field(
        default="nextstop-media",
        validation_alias=AliasChoices(
            "supabase_bucket",
            "SUPABASE_BUCKET",
            "supabase_storage_bucket",
            "SUPABASE_STORAGE_BUCKET",
        ),
        description="Supabase Storage bucket name for photos, videos, and avatars",
    )

    # --------------------------------------------------------------------------
    # JWT Authentication Settings
    # --------------------------------------------------------------------------
    jwt_secret_key: str = Field(
        validation_alias=AliasChoices(
            "jwt_secret_key",
            "JWT_SECRET_KEY",
            "secret_key",
            "SECRET_KEY",
        ),
        description="Cryptographic secret key used to sign and verify HMAC JWT tokens",
    )
    jwt_algorithm: str = Field(
        default="HS256",
        validation_alias=AliasChoices("jwt_algorithm", "JWT_ALGORITHM"),
        description="HMAC algorithm for JWT signing (HS256, HS384, or HS512)",
    )
    access_token_expire_minutes: int = Field(
        default=43200,
        ge=1,
        validation_alias=AliasChoices(
            "access_token_expire_minutes",
            "ACCESS_TOKEN_EXPIRE_MINUTES",
        ),
        description="Access token lifespan in minutes (default: 43200 = 30 days)",
    )
    refresh_token_expire_days: int = Field(
        default=90,
        ge=1,
        validation_alias=AliasChoices(
            "refresh_token_expire_days",
            "REFRESH_TOKEN_EXPIRE_DAYS",
        ),
        description="Refresh token lifespan in days (default: 90 days)",
    )

    # --------------------------------------------------------------------------
    # CORS Settings (Cross-Origin Support for Flutter Android, iOS, Web & Desktop)
    # --------------------------------------------------------------------------
    allowed_origins: Union[str, List[str]] = Field(
        default="*",
        validation_alias=AliasChoices(
            "allowed_origins",
            "ALLOWED_ORIGINS",
            "cors_origins",
            "CORS_ORIGINS",
        ),
        description="Comma-separated string or list of allowed CORS origins (* for wildcard)",
    )

    # --------------------------------------------------------------------------
    # Pydantic Settings Configuration
    # --------------------------------------------------------------------------
    model_config = SettingsConfigDict(
        env_file=(
            str(BACKEND_DIR / ".env"),
            str(PROJECT_ROOT_DIR / ".env"),
            ".env",
        ),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --------------------------------------------------------------------------
    # Field Validators
    # --------------------------------------------------------------------------
    @field_validator("mongodb_uri")
    @classmethod
    def validate_mongodb_uri(cls, v: str) -> str:
        clean = v.strip()
        if not clean:
            raise ValueError(
                "MONGODB_URI is required and cannot be empty. "
                "Provide a valid connection string (e.g., 'mongodb+srv://user:nextstoptop_2018@cluster.mongodb.net/nextstop')."
            )
        if not clean.startswith(("mongodb://", "mongodb+srv://")):
            raise ValueError(
                f"Invalid MONGODB_URI scheme in '{clean[:15]}...'. "
                "The URI must begin with 'mongodb://' or 'mongodb+srv://'."
            )
        for placeholder in ("<username>", "<password>", "YOUR_PASSWORD", "YOUR_USERNAME"):
            if placeholder in clean:
                raise ValueError(
                    f"MONGODB_URI contains unconfigured placeholder '{placeholder}'. "
                    "Please configure real database credentials."
                )
        return clean

    @field_validator("database_name")
    @classmethod
    def validate_database_name(cls, v: str) -> str:
        clean = v.strip()
        if not clean:
            return "nextstop"
        invalid_chars = set('/\\."$*<>:|?')
        if any(c in invalid_chars for c in clean):
            raise ValueError(
                f"DATABASE_NAME '{clean}' contains invalid characters. "
                "MongoDB database names cannot contain spaces, slashes, or special characters."
            )
        return clean

    @field_validator("supabase_url")
    @classmethod
    def validate_supabase_url(cls, v: str) -> str:
        clean = v.strip().rstrip("/")
        if not clean:
            raise ValueError(
                "SUPABASE_URL is required for media storage. "
                "Provide a valid project URL (e.g., 'https://<project-ref>.supabase.co')."
            )
        if not clean.startswith(("https://", "http://")):
            raise ValueError(
                f"Invalid SUPABASE_URL '{clean}'. It must begin with 'https://' or 'http://'."
            )
        return clean

    @field_validator("supabase_secret_key")
    @classmethod
    def validate_supabase_secret_key(cls, v: str) -> str:
        clean = v.strip()
        if not clean:
            raise ValueError(
                "SUPABASE_SECRET_KEY is required for Supabase Storage operations. "
                "Provide your Supabase service role secret or API key."
            )
        for placeholder in ("YOUR_SUPABASE_KEY", "YOUR_SUPABASE_SECRET", "changeme"):
            if clean == placeholder:
                raise ValueError(
                    f"SUPABASE_SECRET_KEY is set to placeholder '{placeholder}'. "
                    "Please configure a valid Supabase key."
                )
        return clean

    @field_validator("jwt_secret_key")
    @classmethod
    def validate_jwt_secret_key(cls, v: str) -> str:
        clean = v.strip()
        if not clean:
            raise ValueError(
                "JWT_SECRET_KEY is required and cannot be empty. "
                "A secure cryptographic secret key is required to sign authentication tokens."
            )
        for placeholder in ("YOUR_SECURE_SECRET_KEY_HERE", "changeme", "secret", "default_secret"):
            if clean == placeholder:
                raise ValueError(
                    f"JWT_SECRET_KEY is set to insecure placeholder '{placeholder}'. "
                    "Please generate a secure random secret."
                )
        if len(clean) < 32:
            raise ValueError(
                f"JWT_SECRET_KEY is too short ({len(clean)} characters). "
                "It must be at least 32 characters long to ensure cryptographic security."
            )
        return clean

    @field_validator("jwt_algorithm")
    @classmethod
    def validate_jwt_algorithm(cls, v: str) -> str:
        clean = v.strip().upper()
        allowed = {"HS256", "HS384", "HS512"}
        if clean not in allowed:
            raise ValueError(
                f"Unsupported JWT_ALGORITHM '{v}'. Allowed algorithms: {', '.join(sorted(allowed))}."
            )
        return clean

    # --------------------------------------------------------------------------
    # Backward-Compatible Properties & SDK Helpers
    # --------------------------------------------------------------------------
    @property
    def cors_origins(self) -> List[str]:
        """Return parsed list of CORS origins for FastAPI CORSMiddleware."""
        if isinstance(self.allowed_origins, list):
            return [o.strip() for o in self.allowed_origins if o.strip()]

        raw = self.allowed_origins.strip()
        if raw == "*":
            return ["*"]

        # Support "development" preset alias for common local development origins
        if raw.lower() in ("development", "dev", "local"):
            return [
                "http://localhost",
                "http://localhost:3000",
                "http://localhost:8000",
                "http://127.0.0.1",
                "http://127.0.0.1:3000",
                "http://127.0.0.1:8000",
                "http://10.0.2.2:8000",
            ]

        return [origin.strip() for origin in raw.split(",") if origin.strip()]

    @property
    def supabase_key(self) -> str:
        """Alias for supabase_secret_key matching Supabase Python SDK parameter naming."""
        return self.supabase_secret_key

    # --------------------------------------------------------------------------
    # Secret Redaction (Prevents Leaking Credentials in Logs/Repr)
    # --------------------------------------------------------------------------
    def _mask_credential(self, value: str, prefix_len: int = 4, suffix_len: int = 4) -> str:
        if not value:
            return ""
        if len(value) <= prefix_len + suffix_len:
            return "***"
        return f"{value[:prefix_len]}...{value[-suffix_len:]} (masked)"

    @property
    def masked_mongodb_uri(self) -> str:
        """Return MongoDB connection URI with user password redacted."""
        return re.sub(r"(://[^:]+:)([^@]+)(@)", r"\g<1>***\g<3>", self.mongodb_uri)

    @property
    def masked_jwt_secret_key(self) -> str:
        """Return masked JWT secret key."""
        return self._mask_credential(self.jwt_secret_key, prefix_len=4, suffix_len=4)

    @property
    def masked_supabase_secret_key(self) -> str:
        """Return masked Supabase secret key."""
        return self._mask_credential(self.supabase_secret_key, prefix_len=6, suffix_len=4)

    def __repr__(self) -> str:
        """Redact sensitive secrets when printing or logging Settings instances."""
        return (
            f"Settings("
            f"app_name='{self.app_name}', "
            f"environment='{self.environment}', "
            f"database_name='{self.database_name}', "
            f"mongodb_uri='{self.masked_mongodb_uri}', "
            f"supabase_url='{self.supabase_url}', "
            f"supabase_bucket='{self.supabase_bucket}', "
            f"supabase_secret_key='{self.masked_supabase_secret_key}', "
            f"jwt_secret_key='{self.masked_jwt_secret_key}', "
            f"jwt_algorithm='{self.jwt_algorithm}', "
            f"access_token_expire_minutes={self.access_token_expire_minutes}, "
            f"refresh_token_expire_days={self.refresh_token_expire_days}, "
            f"cors_origins={self.cors_origins})"
        )

    def __str__(self) -> str:
        return self.__repr__()


settings = Settings()
