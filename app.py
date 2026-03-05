import os
from collections import defaultdict, deque
from typing import Any, Deque, Dict, List, Optional

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Request

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1")
TELEGRAM_WEBHOOK_SECRET = os.getenv("TELEGRAM_WEBHOOK_SECRET", "")
CHAT_MEMORY_TURNS = int(os.getenv("CHAT_MEMORY_TURNS", "12"))

if not TELEGRAM_BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN is required")

TELEGRAM_API_BASE = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
app = FastAPI(title="Ollama Telegram Bridge")
CHAT_MEMORY: Dict[int, Deque[Dict[str, str]]] = defaultdict(
    lambda: deque(maxlen=CHAT_MEMORY_TURNS)
)


def _extract_prompt(message: Dict[str, Any]) -> str:
    prompt_parts = []
    if text := message.get("text"):
        prompt_parts.append(f"User text: {text}")
    if caption := message.get("caption"):
        prompt_parts.append(f"Caption: {caption}")
    if voice := message.get("voice"):
        prompt_parts.append(
            f"Voice message metadata: duration={voice.get('duration')} mime={voice.get('mime_type')}"
        )
    if photos := message.get("photo"):
        prompt_parts.append(f"Image uploaded ({len(photos)} resolutions).")
    if document := message.get("document"):
        prompt_parts.append(
            f"Document uploaded: {document.get('file_name')} ({document.get('mime_type')})"
        )
    if audio := message.get("audio"):
        prompt_parts.append(
            f"Audio uploaded: {audio.get('file_name')} duration={audio.get('duration')}"
        )
    if video := message.get("video"):
        prompt_parts.append(f"Video uploaded: duration={video.get('duration')}")

    if not prompt_parts:
        prompt_parts.append("User sent an unsupported message type. Respond helpfully.")

    return "\n".join(prompt_parts)


def _build_ollama_messages(chat_id: int, prompt: str) -> List[Dict[str, str]]:
    history = list(CHAT_MEMORY[chat_id])
    return [
        {
            "role": "system",
            "content": (
                "You are a Telegram bot assistant. Keep responses concise and helpful. "
                "Use the conversation history for continuity when relevant."
            ),
        },
        *history,
        {"role": "user", "content": prompt},
    ]


async def _call_ollama(chat_id: int, prompt: str) -> str:
    payload = {
        "model": OLLAMA_MODEL,
        "messages": _build_ollama_messages(chat_id, prompt),
        "stream": False,
    }

    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(f"{OLLAMA_BASE_URL}/api/chat", json=payload)
        response.raise_for_status()
        data = response.json()

    llm_response = data.get("message", {}).get("content", "I could not generate a response.")
    CHAT_MEMORY[chat_id].append({"role": "user", "content": prompt})
    CHAT_MEMORY[chat_id].append({"role": "assistant", "content": llm_response})
    return llm_response


async def _telegram_api(method: str, payload: Dict[str, Any]) -> None:
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(f"{TELEGRAM_API_BASE}/{method}", json=payload)
        response.raise_for_status()


async def _reply_all_formats(chat_id: int, message: Dict[str, Any], llm_response: str) -> None:
    await _telegram_api("sendMessage", {"chat_id": chat_id, "text": llm_response})

    if photos := message.get("photo"):
        await _telegram_api(
            "sendPhoto",
            {
                "chat_id": chat_id,
                "photo": photos[-1]["file_id"],
                "caption": "Image received ✅",
            },
        )

    if voice := message.get("voice"):
        await _telegram_api(
            "sendVoice",
            {
                "chat_id": chat_id,
                "voice": voice["file_id"],
                "caption": "Voice received ✅",
            },
        )

    if document := message.get("document"):
        await _telegram_api(
            "sendDocument",
            {
                "chat_id": chat_id,
                "document": document["file_id"],
                "caption": "File received ✅",
            },
        )

    if audio := message.get("audio"):
        await _telegram_api(
            "sendAudio",
            {
                "chat_id": chat_id,
                "audio": audio["file_id"],
                "caption": "Audio received ✅",
            },
        )


@app.get("/health")
async def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.post("/telegram/webhook")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: Optional[str] = Header(default=None),
) -> Dict[str, bool]:
    if TELEGRAM_WEBHOOK_SECRET and x_telegram_bot_api_secret_token != TELEGRAM_WEBHOOK_SECRET:
        raise HTTPException(status_code=403, detail="Invalid webhook secret")

    update = await request.json()
    message = update.get("message") or update.get("edited_message")
    if not message:
        return {"ok": True}

    chat_id = message["chat"]["id"]
    prompt = _extract_prompt(message)
    llm_response = await _call_ollama(chat_id, prompt)
    await _reply_all_formats(chat_id, message, llm_response)
    return {"ok": True}
