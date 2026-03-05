import os
from dataclasses import dataclass


def _parse_admin_chat_ids(raw: str) -> list[int]:
    if not raw.strip():
        return []
    values: list[int] = []
    for chunk in raw.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            values.append(int(chunk))
        except ValueError:
            continue
    return values


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str
    ollama_base_url: str
    ollama_model: str
    ollama_vision_model: str
    ollama_fast_model: str
    ollama_reasoning_model: str
    long_prompt_threshold: int
    telegram_webhook_secret: str
    chat_memory_turns: int
    max_text_extract_chars: int
    max_prompt_chars: int
    stream_chunk_chars: int
    knowledge_base_path: str
    rag_top_k: int
    rag_chunk_size: int
    blocked_terms: list[str]
    rate_limit_count: int
    rate_limit_window_seconds: int
    admin_chat_ids: list[int]
    admin_api_token: str


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
        ollama_fast_model=os.getenv("OLLAMA_FAST_MODEL", model),
        ollama_reasoning_model=os.getenv("OLLAMA_REASONING_MODEL", model),
        long_prompt_threshold=int(os.getenv("LONG_PROMPT_THRESHOLD", "800")),
        telegram_webhook_secret=os.getenv("TELEGRAM_WEBHOOK_SECRET", ""),
        chat_memory_turns=int(os.getenv("CHAT_MEMORY_TURNS", "12")),
        max_text_extract_chars=int(os.getenv("MAX_TEXT_EXTRACT_CHARS", "4000")),
        max_prompt_chars=int(os.getenv("MAX_PROMPT_CHARS", "6000")),
        stream_chunk_chars=int(os.getenv("STREAM_CHUNK_CHARS", "320")),
        knowledge_base_path=os.getenv("KNOWLEDGE_BASE_PATH", "knowledge_base.md"),
        rag_top_k=int(os.getenv("RAG_TOP_K", "3")),
        rag_chunk_size=int(os.getenv("RAG_CHUNK_SIZE", "700")),
        blocked_terms=[item.strip().lower() for item in os.getenv("BLOCKED_TERMS", "").split(",") if item.strip()],
        rate_limit_count=int(os.getenv("RATE_LIMIT_COUNT", "12")),
        rate_limit_window_seconds=int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60")),
        admin_chat_ids=_parse_admin_chat_ids(os.getenv("ADMIN_CHAT_IDS", "")),
        admin_api_token=os.getenv("ADMIN_API_TOKEN", ""),
    )
