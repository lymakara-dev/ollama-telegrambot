import asyncio
import ast
import base64
import json
import os
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Any, Deque, Dict, List, Optional, Tuple

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Request

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1")
OLLAMA_VISION_MODEL = os.getenv("OLLAMA_VISION_MODEL", OLLAMA_MODEL)
TELEGRAM_WEBHOOK_SECRET = os.getenv("TELEGRAM_WEBHOOK_SECRET", "")
CHAT_MEMORY_TURNS = int(os.getenv("CHAT_MEMORY_TURNS", "12"))
MAX_TEXT_EXTRACT_CHARS = int(os.getenv("MAX_TEXT_EXTRACT_CHARS", "4000"))
STREAM_CHUNK_CHARS = int(os.getenv("STREAM_CHUNK_CHARS", "320"))

if not TELEGRAM_BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN is required")

TELEGRAM_API_BASE = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
TELEGRAM_FILE_BASE = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}"
app = FastAPI(title="Ollama Telegram Bridge")
CHAT_MEMORY: Dict[int, Deque[Dict[str, Any]]] = defaultdict(
    lambda: deque(maxlen=CHAT_MEMORY_TURNS)
)


async def _telegram_api(method: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(f"{TELEGRAM_API_BASE}/{method}", json=payload)
        response.raise_for_status()
        return response.json()


async def _send_chat_action(chat_id: int, action: str = "typing") -> None:
    try:
        await _telegram_api("sendChatAction", {"chat_id": chat_id, "action": action})
    except Exception:
        return


async def _download_telegram_file(file_id: str) -> Tuple[bytes, str]:
    file_info = await _telegram_api("getFile", {"file_id": file_id})
    file_path = file_info.get("result", {}).get("file_path")
    if not file_path:
        raise ValueError("Telegram file path not found")

    async with httpx.AsyncClient(timeout=60) as client:
        file_response = await client.get(f"{TELEGRAM_FILE_BASE}/{file_path}")
        file_response.raise_for_status()
        return file_response.content, file_path


def _extract_text_from_document(content: bytes, mime_type: Optional[str], filename: Optional[str]) -> str:
    lower_name = (filename or "").lower()
    text_like = {"text/plain", "text/markdown", "application/json", "text/csv"}
    if mime_type in text_like or lower_name.endswith((".txt", ".md", ".json", ".csv", ".log")):
        decoded = content.decode("utf-8", errors="replace").strip()
        if not decoded:
            return ""
        return decoded[:MAX_TEXT_EXTRACT_CHARS]
    return ""


async def _build_user_prompt_and_images(message: Dict[str, Any]) -> Tuple[str, List[str], str]:
    prompt_parts: List[str] = []
    images_b64: List[str] = []
    model = OLLAMA_MODEL

    if text := message.get("text"):
        prompt_parts.append(f"User text: {text}")
    if caption := message.get("caption"):
        prompt_parts.append(f"Caption: {caption}")

    if voice := message.get("voice"):
        prompt_parts.append(
            f"Voice message metadata: duration={voice.get('duration')} mime={voice.get('mime_type')}"
        )

    if audio := message.get("audio"):
        prompt_parts.append(
            f"Audio uploaded: {audio.get('file_name')} duration={audio.get('duration')}"
        )

    if video := message.get("video"):
        prompt_parts.append(f"Video uploaded: duration={video.get('duration')}")

    if photos := message.get("photo"):
        prompt_parts.append("Image uploaded. Analyze the image content in your answer.")
        try:
            image_bytes, _ = await _download_telegram_file(photos[-1]["file_id"])
            images_b64.append(base64.b64encode(image_bytes).decode("utf-8"))
            model = OLLAMA_VISION_MODEL
        except Exception:
            prompt_parts.append("Note: failed to download image, falling back to metadata-only handling.")

    if document := message.get("document"):
        file_name = document.get("file_name")
        mime_type = document.get("mime_type")
        prompt_parts.append(f"Document uploaded: {file_name} ({mime_type})")
        try:
            document_bytes, _ = await _download_telegram_file(document["file_id"])
            extracted_text = _extract_text_from_document(document_bytes, mime_type, file_name)
            if extracted_text:
                prompt_parts.append(f"Extracted document text:\n{extracted_text}")
            else:
                prompt_parts.append(
                    "Document content extraction not supported for this file type; respond based on metadata/caption."
                )
        except Exception:
            prompt_parts.append("Document download/extraction failed; respond based on metadata/caption.")

    if not prompt_parts:
        prompt_parts.append("User sent an unsupported message type. Respond helpfully.")

    return "\n".join(prompt_parts), images_b64, model


def _build_tool_definitions() -> List[Dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": "calculator",
                "description": "Evaluate a basic arithmetic expression (+, -, *, /, parentheses).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "expression": {
                            "type": "string",
                            "description": "Arithmetic expression, e.g. (12+8)/2",
                        }
                    },
                    "required": ["expression"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "utc_time",
                "description": "Get the current UTC timestamp in ISO format.",
                "parameters": {"type": "object", "properties": {}},
            },
        },
    ]


def _safe_eval_math(expression: str) -> float:
    allowed_nodes = (
        ast.Expression,
        ast.BinOp,
        ast.UnaryOp,
        ast.Add,
        ast.Sub,
        ast.Mult,
        ast.Div,
        ast.USub,
        ast.UAdd,
        ast.Constant,
    )

    def _eval(node: ast.AST) -> float:
        if not isinstance(node, allowed_nodes):
            raise ValueError("Unsupported operation")
        if isinstance(node, ast.Expression):
            return _eval(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return float(node.value)
        if isinstance(node, ast.UnaryOp):
            value = _eval(node.operand)
            if isinstance(node.op, ast.USub):
                return -value
            if isinstance(node.op, ast.UAdd):
                return value
        if isinstance(node, ast.BinOp):
            left = _eval(node.left)
            right = _eval(node.right)
            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
            if isinstance(node.op, ast.Mult):
                return left * right
            if isinstance(node.op, ast.Div):
                if right == 0:
                    raise ValueError("Division by zero")
                return left / right
        raise ValueError("Invalid expression")

    parsed = ast.parse(expression, mode="eval")
    return _eval(parsed)


async def _execute_tool(tool_name: str, arguments: Dict[str, Any]) -> str:
    if tool_name == "calculator":
        expression = str(arguments.get("expression", "")).strip()
        if not expression:
            return "calculator error: missing expression"
        try:
            value = _safe_eval_math(expression)
            return f"calculator result: {value}"
        except Exception as exc:
            return f"calculator error: {exc}"

    if tool_name == "utc_time":
        return f"current utc time: {datetime.now(timezone.utc).isoformat()}"

    return f"unsupported tool: {tool_name}"


def _extract_tool_call(assistant_message: Dict[str, Any]) -> Optional[Tuple[str, Dict[str, Any]]]:
    tool_calls = assistant_message.get("tool_calls")
    if not tool_calls:
        return None

    first_call = tool_calls[0]
    function_call = first_call.get("function", {})
    name = function_call.get("name")
    raw_arguments = function_call.get("arguments", "{}")
    if not name:
        return None
    try:
        arguments = json.loads(raw_arguments) if isinstance(raw_arguments, str) else raw_arguments
    except json.JSONDecodeError:
        arguments = {}
    if not isinstance(arguments, dict):
        arguments = {}
    return name, arguments


def _build_ollama_messages(chat_id: int, prompt: str, images_b64: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    history = list(CHAT_MEMORY[chat_id])
    current_user_message: Dict[str, Any] = {"role": "user", "content": prompt}
    if images_b64:
        current_user_message["images"] = images_b64

    return [
        {
            "role": "system",
            "content": (
                "You are a Telegram bot assistant. Keep responses concise and helpful. "
                "Use conversation history for continuity. If image/document text is provided, use it directly. "
                "Use tools when needed for time/calculation."
            ),
        },
        *history,
        current_user_message,
    ]


async def _call_ollama(chat_id: int, prompt: str, images_b64: Optional[List[str]], model: str) -> str:
    messages = _build_ollama_messages(chat_id, prompt, images_b64)
    payload = {
        "model": model,
        "messages": messages,
        "tools": _build_tool_definitions(),
        "stream": False,
    }

    async with httpx.AsyncClient(timeout=90) as client:
        first_response = await client.post(f"{OLLAMA_BASE_URL}/api/chat", json=payload)
        first_response.raise_for_status()
        first_data = first_response.json()

    assistant_message = first_data.get("message", {})
    tool_call = _extract_tool_call(assistant_message)
    if tool_call:
        tool_name, arguments = tool_call
        tool_result = await _execute_tool(tool_name, arguments)
        messages.append(assistant_message)
        messages.append({"role": "tool", "content": tool_result})

        final_payload = {
            "model": model,
            "messages": messages,
            "stream": False,
        }
        async with httpx.AsyncClient(timeout=90) as client:
            second_response = await client.post(f"{OLLAMA_BASE_URL}/api/chat", json=final_payload)
            second_response.raise_for_status()
            second_data = second_response.json()
        llm_response = second_data.get("message", {}).get("content", "I could not generate a response.")
    else:
        llm_response = assistant_message.get("content", "I could not generate a response.")

    CHAT_MEMORY[chat_id].append({"role": "user", "content": prompt})
    CHAT_MEMORY[chat_id].append({"role": "assistant", "content": llm_response})
    return llm_response


async def _stream_text_reply(chat_id: int, text: str) -> None:
    if not text:
        await _telegram_api("sendMessage", {"chat_id": chat_id, "text": "..."})
        return

    first_chunk = text[:STREAM_CHUNK_CHARS]
    sent = await _telegram_api("sendMessage", {"chat_id": chat_id, "text": first_chunk})
    message_id = sent.get("result", {}).get("message_id")
    if not message_id:
        return

    while len(first_chunk) < len(text):
        await _send_chat_action(chat_id, "typing")
        next_end = min(len(first_chunk) + STREAM_CHUNK_CHARS, len(text))
        first_chunk = text[:next_end]
        await _telegram_api(
            "editMessageText",
            {"chat_id": chat_id, "message_id": message_id, "text": first_chunk},
        )
        await asyncio.sleep(0.2)


async def _reply_all_formats(chat_id: int, message: Dict[str, Any], llm_response: str) -> None:
    await _stream_text_reply(chat_id, llm_response)

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
    await _send_chat_action(chat_id, "typing")
    prompt, images_b64, model = await _build_user_prompt_and_images(message)
    llm_response = await _call_ollama(chat_id, prompt, images_b64, model)
    await _reply_all_formats(chat_id, message, llm_response)
    return {"ok": True}
