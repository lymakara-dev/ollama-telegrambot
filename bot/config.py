import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str
    ollama_base_url: str
    ollama_model: str
    ollama_vision_model: str
    telegram_webhook_secret: str
    chat_memory_turns: int
    max_text_extract_chars: int
    stream_chunk_chars: int
    knowledge_base_path: str
    rag_top_k: int
    rag_chunk_size: int



def load_settings() -> Settings:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is required")

    model = os.getenv("OLLAMA_MODEL", "llama3.1")
    return Settings(
        telegram_bot_token=token,
        ollama_base_url=os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434"),
        ollama_model=model,
        ollama_vision_model=os.getenv("OLLAMA_VISION_MODEL", model),
        telegram_webhook_secret=os.getenv("TELEGRAM_WEBHOOK_SECRET", ""),
        chat_memory_turns=int(os.getenv("CHAT_MEMORY_TURNS", "12")),
        max_text_extract_chars=int(os.getenv("MAX_TEXT_EXTRACT_CHARS", "4000")),
        stream_chunk_chars=int(os.getenv("STREAM_CHUNK_CHARS", "320")),
        knowledge_base_path=os.getenv("KNOWLEDGE_BASE_PATH", "knowledge_base.md"),
        rag_top_k=int(os.getenv("RAG_TOP_K", "3")),
        rag_chunk_size=int(os.getenv("RAG_CHUNK_SIZE", "700")),
    )
