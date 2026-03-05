import asyncio
import base64
import logging
import re
import time
from typing import Any, Dict, List, Optional, Tuple

from .config import Settings
from .memory import ChatMemory
from .metrics import BotMetrics
from .ollama_client import OllamaClient
from .rag import RagStore
from .router import ModelRouter
from .safety import SafetyManager
from .telegram_client import TelegramClient
from .tools import build_tool_definitions, execute_tool, extract_tool_call


class BotService:
    TELEGRAM_MESSAGE_LIMIT = 4096
    TELEGRAM_SAFE_CHUNK_SIZE = 4000

    def __init__(
        self,
        settings: Settings,
        telegram: TelegramClient,
        ollama: OllamaClient,
        memory: ChatMemory,
        rag_store: RagStore,
        safety: SafetyManager,
        metrics: BotMetrics,
        router: ModelRouter,
    ) -> None:
        self.settings = settings
        self.telegram = telegram
        self.ollama = ollama
        self.memory = memory
        self.rag_store = rag_store
        self.safety = safety
        self.metrics = metrics
        self.router = router
        self.logger = logging.getLogger(__name__)

    async def process_update(self, update: Dict[str, Any]) -> None:
        message = update.get("message") or update.get("edited_message")
        if not message:
            return

        chat_id = message["chat"]["id"]
        text = (message.get("text") or "").strip()

        if text == "/stats" and chat_id in self.settings.admin_chat_ids:
            await self.telegram.api("sendMessage", {"chat_id": chat_id, "text": self._format_stats()})
            return

        allowed, retry_after = self.safety.check_rate_limit(chat_id)
        if not allowed:
            self.metrics.inc("rate_limited_updates")
            await self.telegram.api(
                "sendMessage",
                {
                    "chat_id": chat_id,
                    "text": f"Rate limit reached. Please retry in {retry_after}s.",
                },
            )
            return

        await self.telegram.send_chat_action(chat_id, "typing")

        prompt, images_b64, suggested_model = await self.build_user_prompt_and_images(message)
        is_allowed, moderated_prompt = self.safety.moderate_prompt(prompt)
        if not is_allowed:
            self.metrics.inc("blocked_prompts")
            await self.telegram.api(
                "sendMessage", {"chat_id": chat_id, "text": moderated_prompt}
            )
            return

        selected_model = self.router.route(
            prompt=moderated_prompt,
            has_image=bool(images_b64),
            requested_model=suggested_model if suggested_model != self.settings.ollama_model else None,
        )

        started = time.perf_counter()
        llm_response = await self.call_ollama(chat_id, moderated_prompt, images_b64, selected_model)
        elapsed_ms = int((time.perf_counter() - started) * 1000)

        self.metrics.inc("processed_updates")
        self.metrics.inc(f"model_used:{selected_model}")
        self.logger.info("Processed chat_id=%s model=%s elapsed_ms=%s", chat_id, selected_model, elapsed_ms)

        llm_response = self.safety.sanitize_output(llm_response)
        await self.reply_all_formats(chat_id, message, llm_response)

    def _format_stats(self) -> str:
        snapshot = self.metrics.snapshot()
        lines = ["Bot metrics:"]
        for key in sorted(snapshot.keys()):
            lines.append(f"- {key}: {snapshot[key]}")
        return "\n".join(lines)

    def _extract_text_from_document(
        self, content: bytes, mime_type: Optional[str], filename: Optional[str]
    ) -> str:
        lower_name = (filename or "").lower()
        text_like = {"text/plain", "text/markdown", "application/json", "text/csv"}
        if mime_type in text_like or lower_name.endswith((".txt", ".md", ".json", ".csv", ".log")):
            decoded = content.decode("utf-8", errors="replace").strip()
            if not decoded:
                return ""
            return decoded[: self.settings.max_text_extract_chars]
        return ""

    async def build_user_prompt_and_images(
        self, message: Dict[str, Any]
    ) -> Tuple[str, List[str], str]:
        prompt_parts: List[str] = []
        images_b64: List[str] = []
        model = self.settings.ollama_model

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
                image_bytes, _ = await self.telegram.download_file(photos[-1]["file_id"])
                images_b64.append(base64.b64encode(image_bytes).decode("utf-8"))
                model = self.settings.ollama_vision_model
            except Exception:
                prompt_parts.append(
                    "Note: failed to download image, falling back to metadata-only handling."
                )

        if document := message.get("document"):
            file_name = document.get("file_name")
            mime_type = document.get("mime_type")
            prompt_parts.append(f"Document uploaded: {file_name} ({mime_type})")
            try:
                document_bytes, _ = await self.telegram.download_file(document["file_id"])
                extracted_text = self._extract_text_from_document(
                    document_bytes, mime_type, file_name
                )
                if extracted_text:
                    prompt_parts.append(f"Extracted document text:\n{extracted_text}")
                else:
                    prompt_parts.append(
                        "Document content extraction not supported for this file type; respond based on metadata/caption."
                    )
            except Exception:
                prompt_parts.append(
                    "Document download/extraction failed; respond based on metadata/caption."
                )

        if not prompt_parts:
            prompt_parts.append("User sent an unsupported message type. Respond helpfully.")

        return "\n".join(prompt_parts), images_b64, model

    def _build_rag_context(self, prompt: str) -> str:
        matched_chunks = self.rag_store.retrieve(prompt)
        if not matched_chunks:
            return ""

        context_parts = [f"[{idx}] {chunk}" for idx, chunk in enumerate(matched_chunks, start=1)]
        self.metrics.inc("rag_hits")
        return "\n".join(context_parts)

    def build_ollama_messages(
        self, chat_id: int, prompt: str, images_b64: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        rag_context = self._build_rag_context(prompt)
        rag_instruction = (
            f"Knowledge base context (if relevant):\n{rag_context}"
            if rag_context
            else "Knowledge base context: none matched."
        )

        current_user_message: Dict[str, Any] = {
            "role": "user",
            "content": f"{prompt}\n\n{rag_instruction}",
        }
        if images_b64:
            current_user_message["images"] = images_b64

        return [
            {
                "role": "system",
                "content": (
                    "You are a Telegram bot assistant. Keep responses concise and helpful. "
                    "Use conversation history for continuity. Cite knowledge-base facts naturally "
                    "when context is provided and avoid fabricating unknown facts. "
                    "Use tools when needed for time/calculation."
                ),
            },
            *self.memory.history(chat_id),
            current_user_message,
        ]

    async def call_ollama(
        self, chat_id: int, prompt: str, images_b64: Optional[List[str]], model: str
    ) -> str:
        messages = self.build_ollama_messages(chat_id, prompt, images_b64)
        first_payload = {
            "model": model,
            "messages": messages,
            "tools": build_tool_definitions(),
            "stream": False,
        }

        first_data = await self.ollama.chat(first_payload)
        assistant_message = first_data.get("message", {})
        tool_call = extract_tool_call(assistant_message)

        if tool_call:
            self.metrics.inc("tool_calls")
            tool_name, arguments = tool_call
            tool_result = await execute_tool(tool_name, arguments)
            messages.append(assistant_message)
            messages.append({"role": "tool", "content": tool_result})

            second_data = await self.ollama.chat(
                {
                    "model": model,
                    "messages": messages,
                    "stream": False,
                }
            )
            llm_response = second_data.get("message", {}).get(
                "content", "I could not generate a response."
            )
        else:
            llm_response = assistant_message.get("content", "I could not generate a response.")

        self.memory.append_user_assistant(chat_id, prompt, llm_response)
        return llm_response

    async def stream_text_reply(self, chat_id: int, text: str) -> None:
        clean_text = self._format_telegram_text(text)
        if not clean_text:
            await self.telegram.api("sendMessage", {"chat_id": chat_id, "text": "…"})
            return

        chunks = self._split_telegram_chunks(clean_text)
        await self._stream_single_message(chat_id, chunks[0])

        for chunk in chunks[1:]:
            await self.telegram.send_chat_action(chat_id, "typing")
            await self.telegram.api("sendMessage", {"chat_id": chat_id, "text": chunk})

    def _format_telegram_text(self, text: str) -> str:
        normalized = text.replace("\r\n", "\n").replace("\r", "\n")
        trimmed_lines = [line.rstrip() for line in normalized.split("\n")]
        collapsed_newlines = re.sub(r"\n{3,}", "\n\n", "\n".join(trimmed_lines))
        return collapsed_newlines.strip()

    def _split_telegram_chunks(self, text: str) -> List[str]:
        if len(text) <= self.TELEGRAM_MESSAGE_LIMIT:
            return [text]

        chunks: List[str] = []
        remaining = text

        while remaining:
            if len(remaining) <= self.TELEGRAM_SAFE_CHUNK_SIZE:
                chunks.append(remaining)
                break

            candidate = remaining[: self.TELEGRAM_SAFE_CHUNK_SIZE]
            split_at = max(candidate.rfind("\n\n"), candidate.rfind("\n"), candidate.rfind(" "))

            if split_at <= 0:
                split_at = self.TELEGRAM_SAFE_CHUNK_SIZE

            chunk = remaining[:split_at].strip()
            if not chunk:
                chunk = remaining[: self.TELEGRAM_SAFE_CHUNK_SIZE]
                split_at = len(chunk)

            chunks.append(chunk)
            remaining = remaining[split_at:].lstrip()

        return chunks

    async def _stream_single_message(self, chat_id: int, text: str) -> None:
        if not text:
            return

        streamed_text = text[: self.settings.stream_chunk_chars]
        sent = await self.telegram.api("sendMessage", {"chat_id": chat_id, "text": streamed_text})
        message_id = sent.get("result", {}).get("message_id")
        if not message_id:
            return

        while len(streamed_text) < len(text):
            await self.telegram.send_chat_action(chat_id, "typing")
            next_end = min(
                len(streamed_text) + self.settings.stream_chunk_chars,
                len(text),
            )
            streamed_text = text[:next_end]
            await self.telegram.api(
                "editMessageText",
                {
                    "chat_id": chat_id,
                    "message_id": message_id,
                    "text": streamed_text,
                },
            )
            await asyncio.sleep(0.2)

    async def reply_all_formats(
        self, chat_id: int, message: Dict[str, Any], llm_response: str
    ) -> None:
        await self.stream_text_reply(chat_id, llm_response)
