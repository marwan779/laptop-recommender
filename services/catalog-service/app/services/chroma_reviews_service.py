"""Singleton ChromaDB-backed dual-vector review similarity service.

The service owns the process-wide ``chromadb.PersistentClient`` and
``SentenceTransformerEmbeddingFunction`` so the embedding model is loaded at
most once per process (instead of once per query). It indexes bilingual
pros/cons/community snippets from the enriched chassis reviews artifact and
computes a Dual-Vector Cosine Similarity adjustment for TOPSIS:

    NetReviewSim = Cosine(Query, Pros) - 0.75 * Cosine(Query, Cons)

Clean Architecture note: this is the only module allowed to import ChromaDB or
sentence-transformers. The pure domain layer consumes plain ``float`` scores.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import json
import logging
from pathlib import Path
import threading
from typing import Any, ClassVar

logger = logging.getLogger("catalog.services.chroma_reviews")

SERVICE_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_CHROMA_DIR = SERVICE_ROOT / "data" / "chroma_reviews_db"
DEFAULT_REVIEWS_JSON = SERVICE_ROOT / "data" / "cleaned_and_enriched_chassis_reviews_v6.json"
DEFAULT_EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
COLLECTION_NAME = "laptop_chassis_reviews"
DEFAULT_QUERY_RESULTS = 189
UPSERT_BATCH_SIZE = 100


class ChromaReviewsService:
    """Process-wide singleton around a persistent ChromaDB review collection."""

    _instance: ClassVar[ChromaReviewsService | None] = None
    _instance_lock: ClassVar[threading.Lock] = threading.Lock()

    def __new__(cls, *args: Any, **kwargs: Any) -> ChromaReviewsService:
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    instance = super().__new__(cls)
                    instance._configured = False
                    cls._instance = instance
        return cls._instance

    def __init__(
        self,
        chroma_dir: str | Path | None = None,
        reviews_json_path: str | Path | None = None,
        embedding_model_name: str | None = None,
    ) -> None:
        if getattr(self, "_configured", False):
            return

        self.chroma_dir = Path(chroma_dir) if chroma_dir else DEFAULT_CHROMA_DIR
        self.reviews_json_path = (
            Path(reviews_json_path) if reviews_json_path else DEFAULT_REVIEWS_JSON
        )
        self.embedding_model_name = embedding_model_name or DEFAULT_EMBEDDING_MODEL
        self.collection_name = COLLECTION_NAME

        self._client: Any = None
        self._embedding_fn: Any = None
        self._collection: Any = None
        self._init_lock = threading.RLock()
        self._configured = True

    # ─── Lifecycle ──────────────────────────────────────────────────────────

    @classmethod
    def reset_singleton(cls) -> None:
        """Drop the process-wide instance (used by isolated tests)."""
        with cls._instance_lock:
            cls._instance = None

    @property
    def is_ready(self) -> bool:
        return self._collection is not None

    @property
    def document_count(self) -> int:
        """Number of indexed review documents, or 0 when the collection is unavailable."""
        if self._collection is None:
            return 0
        try:
            return int(self._collection.count())
        except Exception:
            logger.exception("Could not read the Chroma review collection count")
            return 0

    def initialize(self, auto_build_if_empty: bool = True) -> bool:
        """Load the embedding model and collection once; optionally seed the index."""
        with self._init_lock:
            if self._collection is not None:
                return True

            try:
                import chromadb
                from chromadb.utils import embedding_functions
            except ImportError:
                logger.exception(
                    "ChromaDB / sentence-transformers are not installed; review similarity disabled"
                )
                return False

            try:
                self.chroma_dir.mkdir(parents=True, exist_ok=True)
                self._client = chromadb.PersistentClient(path=str(self.chroma_dir))
                self._embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
                    model_name=self.embedding_model_name
                )
                self._collection = self._client.get_or_create_collection(
                    name=self.collection_name,
                    embedding_function=self._embedding_fn,
                    metadata={"hnsw:space": "cosine"},
                )
                logger.info(
                    "Chroma review collection ready at %s (documents=%d)",
                    self.chroma_dir,
                    self._collection.count(),
                )
            except Exception:
                logger.exception("Failed to initialize the Chroma reviews service")
                self._client = None
                self._embedding_fn = None
                self._collection = None
                return False

            if (
                auto_build_if_empty
                and self._collection.count() == 0
                and self.reviews_json_path.exists()
            ):
                try:
                    indexed = self.build_from_json(self.reviews_json_path)
                    logger.info("Auto-built Chroma review index with %d documents", indexed)
                except Exception:
                    logger.exception(
                        "Failed to auto-build the Chroma review index; "
                        "review similarity will stay disabled until rebuilt"
                    )

            return True

    # ─── Indexing ───────────────────────────────────────────────────────────

    def build_from_json(self, reviews_json_path: str | Path | None = None) -> int:
        """Index the enriched chassis reviews JSON into the Chroma collection."""
        path = Path(reviews_json_path) if reviews_json_path else self.reviews_json_path
        if not path.exists():
            logger.warning("Reviews JSON not found at %s; nothing to index", path)
            return 0

        if self._collection is None and not self.initialize(auto_build_if_empty=False):
            return 0

        with path.open(encoding="utf-8") as handle:
            data = json.load(handle)

        return self.upsert_chassis_reviews(data.get("laptops", []))

    def upsert_chassis_reviews(self, laptops: Sequence[Mapping[str, Any]]) -> int:
        """Upsert pro/con/context documents for each chassis and return the count."""
        if self._collection is None and not self.initialize(auto_build_if_empty=False):
            return 0

        # Chroma requires globally unique document IDs. The source artifact can
        # contain repeated chassis keys (the same chassis aggregated by several
        # store identities), so we keep the last record for each deterministic ID.
        records: dict[str, tuple[str, dict[str, Any]]] = {}

        for item in laptops:
            chassis_key = item.get("chassis_key")
            if not chassis_key:
                continue

            profile = item.get("nlp_review_profile") or {}
            canonical_ids_csv = ",".join(item.get("matched_canonical_ids") or [])
            brand = (item.get("identity") or {}).get("brand", "")
            base_score = float(profile.get("community_nlp_score", 75.0))

            pros_text = " | ".join(profile.get("pros_ar", []) + profile.get("pros_en", []))
            if pros_text:
                records[f"{chassis_key}__pro"] = (
                    pros_text,
                    {
                        "chassis_key": chassis_key,
                        "brand": brand,
                        "polarity": "pro",
                        "community_nlp_score": base_score,
                        "matched_canonical_ids": canonical_ids_csv,
                    },
                )

            cons_text = " | ".join(profile.get("cons_ar", []) + profile.get("cons_en", []))
            if cons_text:
                records[f"{chassis_key}__con"] = (
                    cons_text,
                    {
                        "chassis_key": chassis_key,
                        "brand": brand,
                        "polarity": "con",
                        "community_nlp_score": base_score,
                        "matched_canonical_ids": canonical_ids_csv,
                    },
                )

            discussions = (item.get("communities") or {}).get("discussions", [])
            for index, discussion in enumerate(discussions[:3]):
                body = (discussion.get("post_body") or "").strip()
                if len(body) < 80:
                    continue
                snippet = f"{discussion.get('post_title', '')}: {body[:700]}"
                records[f"{chassis_key}__disc_{index}"] = (
                    snippet,
                    {
                        "chassis_key": chassis_key,
                        "brand": brand,
                        "polarity": "context",
                        "platform": discussion.get("platform", "community"),
                        "matched_canonical_ids": canonical_ids_csv,
                    },
                )

        ids = list(records.keys())
        documents = [records[record_id][0] for record_id in ids]
        metadatas = [records[record_id][1] for record_id in ids]

        for start in range(0, len(ids), UPSERT_BATCH_SIZE):
            self._collection.upsert(
                documents=documents[start : start + UPSERT_BATCH_SIZE],
                metadatas=metadatas[start : start + UPSERT_BATCH_SIZE],
                ids=ids[start : start + UPSERT_BATCH_SIZE],
            )

        return len(ids)

    # ─── Querying ───────────────────────────────────────────────────────────

    def query_dual_similarity(self, user_query: str) -> dict[str, float]:
        """Return ``canonical_id -> adjusted community NLP score`` for a prompt."""
        if not user_query or not str(user_query).strip():
            return {}

        if self._collection is None and not self.initialize(auto_build_if_empty=True):
            return {}

        collection_count = self._collection.count()
        if collection_count == 0:
            return {}

        n_results = min(DEFAULT_QUERY_RESULTS, collection_count)

        try:
            pro_results = self._collection.query(
                query_texts=[user_query],
                n_results=n_results,
                where={"polarity": "pro"},
            )
            con_results = self._collection.query(
                query_texts=[user_query],
                n_results=n_results,
                where={"polarity": "con"},
            )
        except Exception:
            logger.exception("Chroma dual-similarity query failed")
            return {}

        pro_sim_by_chassis: dict[str, float] = {}
        base_score_by_chassis: dict[str, float] = {}
        cids_by_chassis: dict[str, list[str]] = {}

        if pro_results and pro_results.get("metadatas") and pro_results.get("distances"):
            for metadata, distance in zip(
                pro_results["metadatas"][0], pro_results["distances"][0]
            ):
                chassis_key = metadata.get("chassis_key")
                if not chassis_key:
                    continue
                pro_sim_by_chassis[chassis_key] = max(0.0, 1.0 - float(distance))
                base_score_by_chassis[chassis_key] = float(
                    metadata.get("community_nlp_score", 75.0)
                )
                cids_by_chassis[chassis_key] = [
                    cid
                    for cid in str(metadata.get("matched_canonical_ids", "")).split(",")
                    if cid
                ]

        con_sim_by_chassis: dict[str, float] = {}
        if con_results and con_results.get("metadatas") and con_results.get("distances"):
            for metadata, distance in zip(
                con_results["metadatas"][0], con_results["distances"][0]
            ):
                chassis_key = metadata.get("chassis_key")
                if not chassis_key:
                    continue
                con_sim_by_chassis[chassis_key] = max(0.0, 1.0 - float(distance))

        adjusted_by_canonical_id: dict[str, float] = {}
        for chassis_key, base_score in base_score_by_chassis.items():
            pro_similarity = pro_sim_by_chassis.get(chassis_key, 0.0)
            con_similarity = con_sim_by_chassis.get(chassis_key, 0.0)
            net_similarity = pro_similarity - 0.75 * con_similarity
            adjusted_score = max(35.0, min(98.0, round(base_score + net_similarity * 25.0, 2)))
            for canonical_id in cids_by_chassis.get(chassis_key, []):
                adjusted_by_canonical_id[canonical_id] = adjusted_score

        return adjusted_by_canonical_id


def get_chroma_reviews_service() -> ChromaReviewsService:
    """Return the process-wide ChromaReviewsService singleton."""
    return ChromaReviewsService()


__all__ = [
    "COLLECTION_NAME",
    "DEFAULT_CHROMA_DIR",
    "DEFAULT_EMBEDDING_MODEL",
    "DEFAULT_REVIEWS_JSON",
    "ChromaReviewsService",
    "get_chroma_reviews_service",
]
