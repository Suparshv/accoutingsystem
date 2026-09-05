"""Application settings, loaded from backend/.env (SPEC.md §5)."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/ — the directory that holds .env, requirements.txt and seed.py.
BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Every environment variable the backend reads.

    Field names are lower case; pydantic-settings matches the upper-case keys
    in .env case-insensitively, so `DATABASE_URL` populates `database_url`.
    """

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    database_url: str
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 480
    # Kept as a raw string: a bare comma-separated value is not valid JSON, and
    # pydantic-settings would try to JSON-decode a list-typed field.
    cors_origins: str = "http://localhost:5173"
    upload_dir: str = "./uploads"

    @property
    def cors_origins_list(self) -> list[str]:
        """CORS_ORIGINS split into the list FastAPI's middleware expects."""
        return [
            origin.strip() for origin in self.cors_origins.split(",") if origin.strip()
        ]


settings = Settings()
