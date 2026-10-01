"""Pydantic Settings — loads from environment / .env file."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    env: str = "development"

    # Database
    database_url: str = "postgresql+asyncpg://user:password@localhost:5432/agentic_lms"

    # Moodle
    moodle_base_url: str = "http://localhost:8080"
    moodle_ws_token: str = ""

    # LLM backends
    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "llama3.1"

    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_model: str = ""

    gemini_api_key: str = ""
    gemini_model: str = "gemini-1.5-flash"

    default_llm_backend: str = "gemini"  # ollama | openrouter | gemini


settings = Settings()
