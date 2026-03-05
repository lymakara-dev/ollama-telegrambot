from collections import defaultdict, deque
from typing import Any, Deque, Dict, List, Union


class ChatMemory:
    def __init__(self, max_turns: int) -> None:
        self._max_messages = max_turns * 2 if max_turns > 0 else 0
        self._memory: Dict[int, Union[Deque[Dict[str, Any]], List[Dict[str, Any]]]] = defaultdict(
            self._make_store
        )

    def _make_store(self) -> Union[Deque[Dict[str, Any]], List[Dict[str, Any]]]:
        if self._max_messages == 0:
            return []
        return deque(maxlen=self._max_messages)

    def history(self, chat_id: int) -> list[Dict[str, Any]]:
        return list(self._memory[chat_id])

    def append_message(self, chat_id: int, role: str, content: str) -> None:
        self._memory[chat_id].append({"role": role, "content": content})

    def append_user_assistant(self, chat_id: int, user_prompt: str, assistant_text: str) -> None:
        self.append_message(chat_id, "user", user_prompt)
        self.append_message(chat_id, "assistant", assistant_text)
