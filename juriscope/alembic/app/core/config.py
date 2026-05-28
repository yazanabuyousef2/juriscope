import os
from functools import lru_cache

from dotenv import load_dotenv


load_dotenv()


class Settings:
    PROJECT_NAME: str = "Mizan"
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")

    DATABASE_URL: str = os.getenv("DATABASE_URL", "").strip()

    SECRET_KEY: str = os.getenv("SECRET_KEY", "change-this-secret-key")
    SESSION_COOKIE_NAME: str = "mizan_session"
    STAFF_SESSION_COOKIE_NAME: str = "mizan_staff_session"

    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    GEMINI_FALLBACK_MODEL: str = os.getenv("GEMINI_FALLBACK_MODEL", "gemini-2.0-flash")

    UPLOAD_DIR: str = os.getenv("UPLOAD_DIR", "data/uploads")
    LEGAL_UPLOAD_DIR: str = os.getenv("LEGAL_UPLOAD_DIR", "data/legal_uploads")

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT.lower() == "production"

    def normalized_database_url(self) -> str:
        if not self.DATABASE_URL:
            raise RuntimeError(
                "DATABASE_URL is missing. Add PostgreSQL DATABASE_URL to .env."
            )

        if self.DATABASE_URL.startswith("postgres://"):
            return self.DATABASE_URL.replace("postgres://", "postgresql://", 1)

        return self.DATABASE_URL


@lru_cache
def get_settings() -> Settings:
    return Settings()