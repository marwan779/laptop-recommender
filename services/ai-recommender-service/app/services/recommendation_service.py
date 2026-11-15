"""Application service orchestrating recommendations, dual-vector search, and live reloads.

Delegates pure TOPSIS math & workload estimation to `app.domain.recommendation`
and vector/snapshot persistence to `app.infrastructure`.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
import time
from typing import Any, Dict, List, Optional

import numpy as np

from app.domain.recommendation.topsis import (
    CRITERIA_SEMANTIC_ANCHORS,
    PERSONA_CONFIGS,
    build_budget_too_low_fallback,
    compute_semantic_weight_boosts,
    rank_laptops_topsis,
    score_dual_review_vectors,
)
from app.domain.recommendation.workloads import evaluate_workloads
from app.infrastructure.chroma_repository import (
    CHROMA_DEFAULT_DIR,
    COLLECTION_NAME,
    ChromaDualVectorQuery,
)
from app.infrastructure.fallback_catalog_repository import (
    extract_review_profiles_from_payload,
    load_fallback_catalog,
    load_fallback_reviews_lookup,
)
from app.infrastructure.jina_embedder import (
    JinaV3EmbeddingFunction,
    MODEL_NAME,
)


class LaptopRecommenderService:
    """Singleton pipeline loading Jina-v3 & ChromaDB once in RAM and running TOPSIS + workloads."""

    _instance = None

    def __new__(cls, *args: Any, **kwargs: Any):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(
        self,
        chroma_dir: str = CHROMA_DEFAULT_DIR,
        catalog_fallback_path: str = "unified_catalog_topsis_ready_v6.json",
        reviews_fallback_path: str = "reviews_deduplicated_v6.json",
        model_name: str = MODEL_NAME,
    ) -> None:
        if self._initialized:
            return
        self.chroma_dir = chroma_dir
        self.catalog_fallback_path = catalog_fallback_path
        self.reviews_fallback_path = reviews_fallback_path
        self.model_name = model_name
        self.query_emb_fn = None
        self.collection = None
        self.anchor_keys: List[str] = list(CRITERIA_SEMANTIC_ANCHORS.keys())
        self.anchor_matrix: Optional[np.ndarray] = None
        self._cached_catalog: Optional[List[Dict[str, Any]]] = None
        self._reviews_by_cid: Dict[str, Dict[str, Any]] = {}
        self._cached_dual_query = lru_cache(maxsize=256)(
            self._compute_dual_review_and_semantic_boosts_uncached
        )

        self._init_resources()
        self._initialized = True

    def _load_reviews_lookup(self, reviews_path: Optional[str] = None) -> None:
        self._reviews_by_cid = load_fallback_reviews_lookup(
            reviews_path or self.reviews_fallback_path
        )

    def refresh_reviews_state(
        self,
        chroma_dir: Optional[str] = None,
        reviews_payload: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Refresh in-memory review lookups, ChromaDB collection handle, and query cache."""
        if isinstance(reviews_payload, dict):
            self._reviews_by_cid.update(extract_review_profiles_from_payload(reviews_payload))

        target_dir = chroma_dir or self.chroma_dir
        if self.query_emb_fn is not None and target_dir and Path(target_dir).exists():
            try:
                import chromadb

                client = chromadb.PersistentClient(path=target_dir)
                self.collection = client.get_collection(
                    name=COLLECTION_NAME,
                    embedding_function=self.query_emb_fn,
                )
            except Exception as exc:
                print(f"[Warning] Could not refresh ChromaDB collection handle: {exc}")

        self._cached_dual_query.cache_clear()

    def _init_resources(self) -> None:
        fallback_catalog = load_fallback_catalog(self.catalog_fallback_path)
        if fallback_catalog:
            self._cached_catalog = fallback_catalog

        self._load_reviews_lookup()

        if Path(self.chroma_dir).exists():
            try:
                import chromadb

                self.query_emb_fn = JinaV3EmbeddingFunction(
                    model_name=self.model_name,
                    task="retrieval.query",
                )
                client = chromadb.PersistentClient(path=self.chroma_dir)
                self.collection = client.get_collection(
                    name=COLLECTION_NAME,
                    embedding_function=self.query_emb_fn,
                )
                anchor_texts = [CRITERIA_SEMANTIC_ANCHORS[k] for k in self.anchor_keys]
                self.anchor_matrix = np.array(self.query_emb_fn(anchor_texts), dtype=float)
            except Exception as exc:
                print(f"[Warning] ChromaDB/Jina init skipped or fallback mode active: {exc}")

    def _compute_dual_review_and_semantic_boosts(
        self, user_query: str
    ) -> Dict[str, Any]:
        """LRU-cached wrapper (maxsize=256) around ChromaDB + semantic anchor inference."""
        return self._cached_dual_query(user_query)

    def _compute_dual_review_and_semantic_boosts_uncached(
        self, user_query: str
    ) -> Dict[str, Any]:
        """Encode query once and compute Dual-Vector review adjustments & semantic weight boosts."""
        if not self.collection or not self.query_emb_fn:
            return {"adjusted_nlp_scores": {}, "semantic_weight_boosts": {}}

        q_vec_list = self.query_emb_fn([user_query])
        q_vec = np.array(q_vec_list[0], dtype=float)

        dual_res = ChromaDualVectorQuery(self.collection).query(q_vec_list, n_results=189)
        adjusted_nlp_scores = score_dual_review_vectors(dual_res["pro"], dual_res["con"])
        semantic_boosts = compute_semantic_weight_boosts(
            self.anchor_keys, self.anchor_matrix, q_vec
        )

        return {
            "adjusted_nlp_scores": adjusted_nlp_scores,
            "semantic_weight_boosts": semantic_boosts,
        }

    def recommend(
        self,
        laptops: Optional[List[Dict[str, Any]]] = None,
        max_budget_egp: float = 300000.0,
        min_budget_egp: Optional[float] = None,
        persona: str = "balanced",
        user_text_prompt: Optional[str] = None,
        min_ram_gb: Optional[int] = None,
        min_storage_gb: Optional[int] = None,
        require_dgpu: Optional[bool] = None,
        brand_filter: Optional[List[str]] = None,
        custom_weights: Optional[Dict[str, float]] = None,
        top_k: int = 10,
        include_workloads: bool = True,
    ) -> Dict[str, Any]:
        """Orchestrate semantic Chroma search, 10-column TOPSIS ranking, and workload profiles."""
        t_start = time.perf_counter()
        source_laptops = laptops if laptops is not None else (self._cached_catalog or [])
        working_laptops = []
        for lap in source_laptops:
            dm = lap.get("derived_metrics", {})
            ti = dict(dm.get("topsis_inputs", {}))
            cid = lap.get("canonical_id")
            if ti.get("community_nlp_score") is None and cid in self._reviews_by_cid:
                ti["community_nlp_score"] = self._reviews_by_cid[cid].get("community_nlp_score", 75.0)
            working_laptops.append({
                **lap,
                "derived_metrics": {
                    **dm,
                    "topsis_inputs": ti,
                },
            })

        p_key = persona if persona in PERSONA_CONFIGS else "balanced"
        merged_custom_weights = dict(custom_weights) if custom_weights else {}

        chroma_meta = {"adjusted_count": 0, "semantic_weight_boosts": {}}
        if user_text_prompt and str(user_text_prompt).strip():
            dual_out = self._compute_dual_review_and_semantic_boosts(str(user_text_prompt).strip())
            adj_map = dual_out["adjusted_nlp_scores"]
            sem_boosts = dual_out["semantic_weight_boosts"]
            chroma_meta["adjusted_count"] = len(adj_map)
            chroma_meta["semantic_weight_boosts"] = sem_boosts

            for lap in working_laptops:
                cid = lap.get("canonical_id")
                if cid in adj_map:
                    lap["derived_metrics"]["topsis_inputs"]["community_nlp_score"] = adj_map[cid]

            base_w = PERSONA_CONFIGS[p_key]["weights"]
            for k, b_val in sem_boosts.items():
                if k in base_w:
                    merged_custom_weights[k] = merged_custom_weights.get(k, base_w[k]) + b_val
            if "community_nlp_score" not in (custom_weights or {}):
                merged_custom_weights["community_nlp_score"] = 0.22

        ranked = rank_laptops_topsis(
            laptops=working_laptops,
            max_budget_egp=max_budget_egp,
            min_budget_egp=min_budget_egp,
            persona=p_key,
            user_text_prompt=user_text_prompt,
            min_ram_gb=min_ram_gb,
            min_storage_gb=min_storage_gb,
            require_dgpu=require_dgpu,
            brand_filter=brand_filter,
            custom_weights=merged_custom_weights if merged_custom_weights else None,
            top_k=top_k,
        )

        lap_lookup = {l["canonical_id"]: l for l in working_laptops}
        for r in ranked["results"]:
            cid = r["canonical_id"]
            orig = lap_lookup.get(cid, {})
            comm_rev = orig.get("derived_metrics", {}).get("community_reviews") or {}
            fb_rev = self._reviews_by_cid.get(cid, {})
            r["community_reviews"] = {
                "community_nlp_score": r["topsis_inputs"].get("community_nlp_score") or fb_rev.get("community_nlp_score"),
                "aspect_scores": comm_rev.get("aspect_scores") or fb_rev.get("aspect_scores", {}),
                "pros_ar": comm_rev.get("pros_ar") or fb_rev.get("pros_ar", []),
                "cons_ar": comm_rev.get("cons_ar") or fb_rev.get("cons_ar", []),
                "pros_en": comm_rev.get("pros_en") or fb_rev.get("pros_en", []),
                "cons_en": comm_rev.get("cons_en") or fb_rev.get("cons_en", []),
            }
            if include_workloads and orig:
                r["workloads"] = evaluate_workloads(orig)

        if not ranked["results"]:
            ranked["status"] = "BUDGET_TOO_LOW_FOR_CATEGORY"
            ranked["message_ar"] = "الميزانية المحددة أقل من أسعار الأجهزة المتاحة في هذه الفئة حالياً؛ إليك أقرب 3 بدائل اقتصادية متاحة."
            ranked["closest_alternatives"] = build_budget_too_low_fallback(working_laptops)
        else:
            ranked["status"] = "OK"
            ranked["message_ar"] = "تم ترتيب أفضل اللابتوبات المطابقة لاحتياجاتك بنجاح."
            ranked["closest_alternatives"] = []

        ranked["chroma_nlp_metadata"] = chroma_meta
        ranked["execution_time_ms"] = round((time.perf_counter() - t_start) * 1000.0, 2)
        return ranked


class RecommendationService:
    """Application-service facade over `LaptopRecommenderService`."""

    def __init__(self, recommender: Optional[LaptopRecommenderService] = None) -> None:
        self._recommender = recommender

    @property
    def recommender(self) -> LaptopRecommenderService:
        if self._recommender is None:
            self._recommender = LaptopRecommenderService()
        return self._recommender

    def warm_up(self) -> LaptopRecommenderService:
        return self.recommender

    def refresh_reviews_state(
        self,
        chroma_dir: Optional[str] = None,
        reviews_payload: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Refresh live Chroma collection and review lookup caches after batch ingestion."""
        if self._recommender is not None:
            self._recommender.refresh_reviews_state(
                chroma_dir=chroma_dir,
                reviews_payload=reviews_payload,
            )

    def recommend(
        self,
        laptops: Optional[List[Dict[str, Any]]] = None,
        max_budget_egp: float = 300000.0,
        min_budget_egp: Optional[float] = None,
        persona: str = "balanced",
        user_text_prompt: Optional[str] = None,
        min_ram_gb: Optional[int] = None,
        min_storage_gb: Optional[int] = None,
        require_dgpu: Optional[bool] = None,
        brand_filter: Optional[List[str]] = None,
        custom_weights: Optional[Dict[str, float]] = None,
        top_k: int = 10,
        include_workloads: bool = True,
    ) -> Dict[str, Any]:
        return self.recommender.recommend(
            laptops=laptops,
            max_budget_egp=max_budget_egp,
            min_budget_egp=min_budget_egp,
            persona=persona,
            user_text_prompt=user_text_prompt,
            min_ram_gb=min_ram_gb,
            min_storage_gb=min_storage_gb,
            require_dgpu=require_dgpu,
            brand_filter=brand_filter,
            custom_weights=custom_weights,
            top_k=top_k,
            include_workloads=include_workloads,
        )


_DEFAULT_SERVICE: Optional[RecommendationService] = None


def get_recommendation_service() -> RecommendationService:
    """FastAPI lifecycle singleton accessor."""
    global _DEFAULT_SERVICE
    if _DEFAULT_SERVICE is None:
        _DEFAULT_SERVICE = RecommendationService()
    return _DEFAULT_SERVICE
