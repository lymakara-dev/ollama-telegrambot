import logging
from typing import Any, Dict, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Request

from .config import load_settings
from .jobs import JobRunner
from .memory import ChatMemory
from .metrics import BotMetrics
from .ollama_client import OllamaClient
from .rag import RagStore
from .router import ModelRouter
from .safety import SafetyManager
from .service import BotService
from .telegram_client import TelegramClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)

load_dotenv()
settings = load_settings()
telegram_client = TelegramClient(settings.telegram_bot_token)
ollama_client = OllamaClient(settings.ollama_base_url)
memory = ChatMemory(settings.chat_memory_turns)
rag_store = RagStore(settings.knowledge_base_path, settings.rag_chunk_size, settings.rag_top_k)
metrics = BotMetrics()
safety = SafetyManager(
    blocked_terms=settings.blocked_terms,
    max_prompt_chars=settings.max_prompt_chars,
    rate_limit_count=settings.rate_limit_count,
    rate_limit_window_seconds=settings.rate_limit_window_seconds,
)
router = ModelRouter(settings)
service = BotService(
    settings,
    telegram_client,
    ollama_client,
    memory,
    rag_store,
    safety,
    metrics,
    router,
)
job_runner = JobRunner(service.process_update)

app = FastAPI(title="Ollama Telegram Bridge")


@app.on_event("startup")
async def startup() -> None:
    await job_runner.start()
    logger.info("Background job runner started")


@app.on_event("shutdown")
async def shutdown() -> None:
    await job_runner.stop()
    logger.info("Background job runner stopped")


@app.get("/health")
async def health() -> Dict[str, Any]:
    return {
        "status": "ok",
        "queue_size": job_runner.queue_size(),
    }


@app.get("/admin/stats")
async def admin_stats(x_admin_token: Optional[str] = Header(default=None)) -> Dict[str, Any]:
    if not settings.admin_api_token or x_admin_token != settings.admin_api_token:
        raise HTTPException(status_code=403, detail="Invalid admin token")
    return {
        "metrics": metrics.snapshot(),
        "queue_size": job_runner.queue_size(),
    }


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
    accepted = await job_runner.enqueue(update)
    if not accepted:
        metrics.inc("dropped_updates")
        raise HTTPException(status_code=503, detail="Queue is full")

    metrics.inc("queued_updates")
    return {"ok": True}
