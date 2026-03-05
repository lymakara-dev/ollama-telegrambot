import time
from collections import defaultdict, deque
from typing import Deque, Dict, List, Tuple


class SafetyManager:
    def __init__(
        self,
        blocked_terms: List[str],
        max_prompt_chars: int,
        rate_limit_count: int,
        rate_limit_window_seconds: int,
    ) -> None:
        self._blocked_terms = blocked_terms
        self._max_prompt_chars = max_prompt_chars
        self._rate_limit_count = rate_limit_count
        self._rate_limit_window_seconds = rate_limit_window_seconds
        self._rate_log: Dict[int, Deque[float]] = defaultdict(deque)

    def check_rate_limit(self, chat_id: int) -> Tuple[bool, int]:
        now = time.time()
        timestamps = self._rate_log[chat_id]
        while timestamps and now - timestamps[0] > self._rate_limit_window_seconds:
            timestamps.popleft()
        if len(timestamps) >= self._rate_limit_count:
            retry_after = int(self._rate_limit_window_seconds - (now - timestamps[0]))
            return False, max(retry_after, 1)
        timestamps.append(now)
        return True, 0

    def moderate_prompt(self, prompt: str) -> Tuple[bool, str]:
        trimmed = prompt[: self._max_prompt_chars]
        lowered = trimmed.lower()
        for term in self._blocked_terms:
            if term and term in lowered:
                return False, "Message blocked by safety policy."
        return True, trimmed

    def sanitize_output(self, text: str) -> str:
        sanitized = text
        for term in self._blocked_terms:
            if not term:
                continue
            sanitized = sanitized.replace(term, "[redacted]")
            sanitized = sanitized.replace(term.capitalize(), "[redacted]")
            sanitized = sanitized.replace(term.upper(), "[redacted]")
        return sanitized
