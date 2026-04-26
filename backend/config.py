from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        env_ignore_empty=True,  # treat empty shell env vars as unset so .env wins
    )

    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"

    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-6"

    hf_token: str = ""

    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "INFO"

    allowed_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    use_mock_diarization: bool = True
    use_mock_sign_lookup: bool = True

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
