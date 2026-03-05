from typing import Any, Dict, Tuple

import httpx


class TelegramClient:
    def __init__(self, bot_token: str) -> None:
        self._api_base = f"https://api.telegram.org/bot{bot_token}"
        self._file_base = f"https://api.telegram.org/file/bot{bot_token}"

    async def api(self, method: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(f"{self._api_base}/{method}", json=payload)
            response.raise_for_status()
            return response.json()

    async def send_chat_action(self, chat_id: int, action: str = "typing") -> None:
        try:
            await self.api("sendChatAction", {"chat_id": chat_id, "action": action})
        except Exception:
            return

    async def download_file(self, file_id: str) -> Tuple[bytes, str]:
        file_info = await self.api("getFile", {"file_id": file_id})
        file_path = file_info.get("result", {}).get("file_path")
        if not file_path:
            raise ValueError("Telegram file path not found")

        async with httpx.AsyncClient(timeout=60) as client:
            file_response = await client.get(f"{self._file_base}/{file_path}")
            file_response.raise_for_status()
            return file_response.content, file_path
