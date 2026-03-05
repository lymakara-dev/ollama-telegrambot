from typing import Optional

from .config import Settings


class ModelRouter:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def route(self, prompt: str, has_image: bool, requested_model: Optional[str] = None) -> str:
        if requested_model:
            return requested_model
        if has_image:
            return self.settings.ollama_vision_model
        if len(prompt) >= self.settings.long_prompt_threshold:
            return self.settings.ollama_reasoning_model
        return self.settings.ollama_fast_model
