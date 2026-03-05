from collections import defaultdict, deque
from typing import Any, Deque, Dict


class ChatMemory:
    def __init__(self, max_turns: int) -> None:
        self._memory: Dict[int, Deque[Dict[str, Any]]] = defaultdict(
            lambda: deque(maxlen=max_turns)
        )

    def history(self, chat_id: int) -> list[Dict[str, Any]]:
        return list(self._memory[chat_id])

    def append_user_assistant(self, chat_id: int, user_prompt: str, assistant_text: str) -> None:
        self._memory[chat_id].append({"role": "user", "content": user_prompt})
        self._memory[chat_id].append({"role": "assistant", "content": assistant_text})
