import re
from pathlib import Path
from typing import List, Tuple

WORD_RE = re.compile(r"[a-zA-Z0-9_]+")


class RagStore:
    def __init__(self, kb_path: str, chunk_size: int, top_k: int) -> None:
        self._kb_path = Path(kb_path)
        self._chunk_size = chunk_size
        self._top_k = top_k
        self._chunks: List[str] = []
        self.reload()

    def reload(self) -> None:
        if not self._kb_path.exists():
            self._chunks = []
            return

        text = self._kb_path.read_text(encoding="utf-8")
        cleaned = re.sub(r"\s+", " ", text).strip()
        if not cleaned:
            self._chunks = []
            return

        self._chunks = [
            cleaned[index : index + self._chunk_size]
            for index in range(0, len(cleaned), self._chunk_size)
        ]

    def retrieve(self, query: str) -> List[str]:
        if not self._chunks:
            return []

        query_terms = set(self._normalize(query))
        if not query_terms:
            return []

        scored: List[Tuple[int, str]] = []
        for chunk in self._chunks:
            terms = set(self._normalize(chunk))
            score = len(query_terms.intersection(terms))
            if score > 0:
                scored.append((score, chunk))

        scored.sort(key=lambda item: item[0], reverse=True)
        return [chunk for _, chunk in scored[: self._top_k]]

    @staticmethod
    def _normalize(text: str) -> List[str]:
        return [token.lower() for token in WORD_RE.findall(text)]
