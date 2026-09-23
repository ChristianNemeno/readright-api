from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Reads app config from .env — API key, WhisperX, Supabase, CORS origins."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    API_KEY: str
    WHISPERX_MODEL: str = "large-v3"
    WHISPERX_DEVICE: str = "cpu"
    WHISPERX_COMPUTE_TYPE: str = "int8"

    MAX_CONCURRENCY: int = 1
    MAX_UPLOAD_MB: int = 40

    SUPABASE_URL: str = ""
    SUPABASE_SERVICE_KEY: str = ""

    ALLOWED_ORIGINS: list[str] = ["http://localhost:5173"]


@lru_cache
def get_settings() -> Settings:
    """Returns cached Settings singleton — .env read once."""
    return Settings()  # type: ignore[call-arg]
