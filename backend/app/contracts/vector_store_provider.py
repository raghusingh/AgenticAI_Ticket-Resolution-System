from abc import ABC, abstractmethod
from typing import Any, Dict, List


class VectorStoreProvider(ABC):
    @abstractmethod
    def upsert(self, documents: List[Dict[str, Any]]) -> None:
        raise NotImplementedError

    @abstractmethod
    def similarity_search(self, query: str, k: int = 5) -> List[Dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def delete_by_source(self, source: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def health(self) -> Dict[str, Any]:
        raise NotImplementedError
