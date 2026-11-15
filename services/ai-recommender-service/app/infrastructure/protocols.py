"""Dependency-inversion protocols for all external boundaries.

The application/domain layers depend on these structural interfaces, never on
concrete HTTP clients, model loaders, vector databases or file-system helpers.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol, Sequence, Tuple, runtime_checkable


@runtime_checkable
class IEmbeddingEncoder(Protocol):
    """Encodes documents into normalized float vectors."""

    def __call__(self, input: Sequence[str]) -> List[List[float]]:
        ...


@runtime_checkable
class ILLMClient(Protocol):
    """OpenAI-compatible chat-completions client returning parsed JSON + telemetry."""

    def __call__(
        self,
        model: str,
        messages: List[Dict[str, str]],
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout_sec: float = 90.0,
    ) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
        ...


@runtime_checkable
class IDeltaCacheRepository(Protocol):
    """Loads and atomically persists the enrichment delta cache."""

    def load(self, path: Optional[str]) -> Dict[str, Any]:
        ...

    def save(self, path: str, data: Dict[str, Any]) -> None:
        ...


@runtime_checkable
class IReviewsVectorStore(Protocol):
    """Persistent review vector store with dual pro/con semantic querying."""

    def build(
        self,
        data: Dict[str, Any],
        chroma_dir: str,
        model_name: str,
    ) -> Dict[str, Any]:
        ...

    def upsert_reviews(
        self,
        data: Dict[str, Any],
        chroma_dir: str,
        model_name: str,
    ) -> Dict[str, Any]:
        ...

    def query_dual(
        self,
        query_embeddings: List[List[float]],
        n_results: int = 189,
    ) -> Dict[str, Any]:
        ...


@runtime_checkable
class ICatalogSpecsProvider(Protocol):
    """Provides a canonical-id -> catalog laptop mapping."""

    def load_map(self, catalog_path: Optional[str]) -> Dict[str, Any]:
        ...
