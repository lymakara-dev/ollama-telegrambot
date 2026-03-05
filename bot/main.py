from typing import Dict, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Request

from .config import load_settings
from .memory import ChatMemory
from .ollama_client import OllamaClient
from .rag import RagStore
from .service import BotService
from .telegram_client import TelegramClient

load_dotenv()
settings = load_settings()
telegram_client = TelegramClient(settings.telegram_bot_token)
ollama_client = OllamaClient(settings.ollama_base_url)
memory = ChatMemory(settings.chat_memory_turns)
rag_store = RagStore(settings.knowledge_base_path, settings.rag_chunk_size, settings.rag_top_k)
service = BotService(settings, telegram_client, ollama_client, memory, rag_store)

app = FastAPI(title="Ollama Telegram Bridge")


@app.get("/health")
async def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.post("/rag/reload")
async def rag_reload() -> Dict[str, bool]:
    rag_store.reload()
    return {"ok": True}


@app.post("/telegram/webhook")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: Optional[str] = Header(default=None),
) -> Dict[str, bool]:
    if (
        settings.telegram_webhook_secret
        and x_telegram_bot_api_secret_token != settings.telegram_webhook_secret
    ):
        raise HTTPException(status_code=403, detail="Invalid webhook secret")

    update = await request.json()
    message = update.get("message") or update.get("edited_message")
    if not message:
        return {"ok": True}

    chat_id = message["chat"]["id"]
    await telegram_client.send_chat_action(chat_id, "typing")

    prompt, images_b64, model = await service.build_user_prompt_and_images(message)
    llm_response = await service.call_ollama(chat_id, prompt, images_b64, model)
    await service.reply_all_formats(chat_id, message, llm_response)
    return {"ok": True}
