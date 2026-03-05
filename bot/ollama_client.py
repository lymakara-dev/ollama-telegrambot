from typing import Any, Dict

import httpx


class OllamaClient:
    def __init__(self, base_url: str) -> None:
        self._base_url = base_url

    async def chat(self, payload: Dict[str, Any], timeout_seconds: int = 90) -> Dict[str, Any]:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            response = await client.post(f"{self._base_url}/api/chat", json=payload)
            response.raise_for_status()
            return response.json()
