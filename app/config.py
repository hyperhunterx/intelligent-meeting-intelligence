"""Central configuration.

All runtime settings come from environment variables (loaded from a `.env`
file in development). Nothing secret is ever hard-coded. `pydantic-settings`
reads the env, validates types, and gives us one typed `settings` object the
rest of the app imports.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Reads from .env, ignores unknown keys, case-insensitive.
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    OPENROUTER_API_KEY: str = ""
    MODEL: str = "google/gemini-2.0-flash-001"
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
    DB_PATH: str = "imies.db"


# Single shared instance imported everywhere: `from app.config import settings`.
settings = Settings()
