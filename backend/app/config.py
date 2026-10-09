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
    ollama_model: str = "llama3.2"

    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_model: str = ""

    gemini_api_key: str = ""
    gemini_model: str = "gemini-flash-lite-latest"

    default_llm_backend: str = "gemini"  # ollama | openrouter | gemini

    # Tutor Agent / RAG
    chroma_persist_dir: str = "./chroma_db"
    ollama_embed_model: str = "nomic-embed-text"  # `ollama pull nomic-embed-text` first
    rag_chunk_size: int = 512
    rag_chunk_overlap: int = 64
    rag_top_k: int = 4
    # Hybrid-mode: if the best retrieved chunk's distance is above this,
    # the course material is considered "not relevant enough" and hybrid
    # mode falls back to the LLM's general knowledge (clearly labeled).
    # Approximate for cosine-like embeddings; tune by testing real queries.
    rag_hybrid_distance_threshold: float = 1.0


settings = Settings()
