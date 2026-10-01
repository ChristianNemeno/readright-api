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
    WHISPERX_MODEL: str = "base.en"
    WHISPERX_DEVICE: str = "cpu"
    WHISPERX_COMPUTE_TYPE: str = "int8"  # lightest CPU footprint; use float16 on cuda

    MAX_CONCURRENCY: int = 1
    # Frontend caps a recording at 5 min with no explicit MediaRecorder bitrate, so
    # the browser default (~2.5-3Mbps combined) can produce a ~95-115MB file at the
    # cap. 150 covers that with margin — too low here rejects legitimate long reads
    # from exactly the slow/struggling readers this assessment is meant to catch.
    MAX_UPLOAD_MB: int = 150

    SUPABASE_URL: str = ""
    SUPABASE_SERVICE_KEY: str = ""

    ALLOWED_ORIGINS: list[str] = ["http://localhost:5173"]


@lru_cache
def get_settings() -> Settings:
    """Returns cached Settings singleton — .env read once."""
    return Settings()  # type: ignore[call-arg]
