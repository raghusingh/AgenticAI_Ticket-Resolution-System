from abc import ABC, abstractmethod
from typing import Any, Dict, List


class LLMProvider(ABC):
    @abstractmethod
    def generate(self, prompt: str, context: List[Dict[str, Any]] | None = None) -> str:
        raise NotImplementedError

    @abstractmethod
    def model_name(self) -> str:
        raise NotImplementedError
