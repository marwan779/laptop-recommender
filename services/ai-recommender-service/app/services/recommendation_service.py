"""Application service orchestrating recommendations, dual-vector search, and live reloads.

Delegates pure TOPSIS math & workload estimation to `app.domain.recommendation`
and vector/snapshot persistence to `app.infrastructure`.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
import time
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from app.domain.recommendation.topsis import (
    CRITERIA_SEMANTIC_ANCHORS,
    DEFAULT_COMMUNITY_NLP_SCORE,
    PERSONA_CONFIGS,
    _LEGACY_WEIGHT_EXPANSION,
    _resolve_persona_key,
    build_budget_too_low_fallback,
    compute_semantic_weight_boosts,
    parse_user_text_prompt,
    rank_laptops_topsis,
    score_dual_review_vectors_detailed,
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
        self._cached_collection_count: int = -1
        self._pro_doc_count: int = 0
        self._con_doc_count: int = 0
        self._cached_dual_query = lru_cache(maxsize=256)(
            self._compute_dual_review_scores_uncached
        )

        self._init_resources()
        self._initialized = True

    def _get_polarity_counts(self) -> Tuple[int, int]:
        """Return exact indexed pro/con counts, refreshing if collection size changed."""
        if self.collection is None:
            return 0, 0
        total = self.collection.count()
        if total <= 0:
            self._cached_collection_count = 0
            self._pro_doc_count = 0
            self._con_doc_count = 0
            return 0, 0
        if total != self._cached_collection_count:
            pro_ids = self.collection.get(where={"polarity": "pro"}, include=[]).get("ids", [])
            con_ids = self.collection.get(where={"polarity": "con"}, include=[]).get("ids", [])
            pro_n = len(pro_ids)
            con_n = len(con_ids)
            if pro_n == 0 and con_n == 0:
                fallback_n = max(1, total // 2)
                pro_n = fallback_n
                con_n = fallback_n
            self._pro_doc_count = pro_n
            self._con_doc_count = con_n
            self._cached_collection_count = total
        return self._pro_doc_count, self._con_doc_count

    def _load_reviews_lookup(self, reviews_path: Optional[str] = None) -> None:
        rpath = reviews_path or self.reviews_fallback_path
        self._reviews_by_cid = load_fallback_reviews_lookup(rpath)

    def refresh_reviews_state(
        self,
        chroma_dir: Optional[str] = None,
        reviews_payload: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Refresh in-memory review lookups, ChromaDB collection handle, and query cache."""
        if isinstance(reviews_payload, dict):
            self._reviews_by_cid.update(extract_review_profiles_from_payload(reviews_payload))

        target_dir = chroma_dir or self.chroma_dir
        self._cached_collection_count = -1
        if self.query_emb_fn is not None and target_dir and Path(target_dir).exists():
            try:
                import chromadb

                client = chromadb.PersistentClient(path=target_dir)
                self.collection = client.get_collection(
                    name=COLLECTION_NAME,
                    embedding_function=self.query_emb_fn,
                )
                self._get_polarity_counts()
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
                self._get_polarity_counts()
                anchor_texts = [CRITERIA_SEMANTIC_ANCHORS[k] for k in self.anchor_keys]
                self.anchor_matrix = np.array(self.query_emb_fn(anchor_texts), dtype=float)
            except Exception as exc:
                print(f"[Warning] ChromaDB/Jina init skipped or fallback mode active: {exc}")

    def _compute_dual_review_scores_uncached(
        self, user_query: str
    ) -> Dict[str, Any]:
        """Encode query once and execute pure Dual-Vector ChromaDB search with signal spread."""
        if not self.collection or not self.query_emb_fn:
            return {
                "adjusted_nlp_scores": {},
                "nlp_dynamic_weight": 0.10,
                "signal_spread": 0.0,
                "query_embedding": None,
            }

        pro_n, con_n = self._get_polarity_counts()
        q_vec_list = self.query_emb_fn([user_query])
        dual_res = ChromaDualVectorQuery(self.collection).query(
            q_vec_list,
            pro_n_results=pro_n,
            con_n_results=con_n,
        )
        scored = score_dual_review_vectors_detailed(dual_res["pro"], dual_res["con"])
        return {
            "adjusted_nlp_scores": scored["adjusted_nlp_scores"],
            "nlp_dynamic_weight": scored["nlp_dynamic_weight"],
            "signal_spread": scored["signal_spread"],
            "query_embedding": tuple(float(x) for x in q_vec_list[0]),
        }

    def _compute_dual_review_and_semantic_boosts(
        self, user_query: str
    ) -> Dict[str, Any]:
        """Share the LRU Dual-Vector cache and add semantic anchor weight boosts."""
        dual_out = self._cached_dual_query(user_query)
        semantic_boosts: Dict[str, float] = {}
        q_emb = dual_out.get("query_embedding")
        if q_emb is not None and self.anchor_matrix is not None:
            q_vec = np.array(q_emb, dtype=float)
            semantic_boosts = compute_semantic_weight_boosts(
                self.anchor_keys, self.anchor_matrix, q_vec
            )

        return {
            "adjusted_nlp_scores": dual_out["adjusted_nlp_scores"],
            "semantic_weight_boosts": semantic_boosts,
            "nlp_dynamic_weight": dual_out["nlp_dynamic_weight"],
        }

    def score_prompt(self, user_text_prompt: Optional[str]) -> Dict[str, Any]:
        """Pure prompt scoring for `POST /score-prompt` without candidate_laptops."""
        t_start = time.perf_counter()
        cleaned = str(user_text_prompt).strip() if user_text_prompt else ""
        if not cleaned:
            return {
                "adjusted_nlp_scores": {},
                "nlp_dynamic_weight": 0.10,
                "parsed_constraints": {},
                "execution_time_ms": round((time.perf_counter() - t_start) * 1000.0, 2),
            }

        dual_out = self._cached_dual_query(cleaned)
        parsed_constraints = dict(parse_user_text_prompt(cleaned)["extracted_filters"])
        return {
            "adjusted_nlp_scores": dict(dual_out["adjusted_nlp_scores"]),
            "nlp_dynamic_weight": float(dual_out["nlp_dynamic_weight"]),
            "parsed_constraints": parsed_constraints,
            "execution_time_ms": round((time.perf_counter() - t_start) * 1000.0, 2),
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
        """Orchestrate semantic Chroma search, 14-column TOPSIS ranking, and workload profiles."""
        t_start = time.perf_counter()
        source_laptops = laptops if laptops is not None else (self._cached_catalog or [])
        working_laptops = []
        for lap in source_laptops:
            dm = lap.get("derived_metrics", {})
            ti = dict(dm.get("topsis_inputs", {}))
            cid = lap.get("canonical_id")
            if ti.get("community_nlp_score") is None:
                if cid in self._reviews_by_cid:
                    ti["community_nlp_score"] = self._reviews_by_cid[cid].get(
                        "community_nlp_score", DEFAULT_COMMUNITY_NLP_SCORE
                    )
                else:
                    ti["community_nlp_score"] = DEFAULT_COMMUNITY_NLP_SCORE
            working_laptops.append({
                **lap,
                "derived_metrics": {
                    **dm,
                    "topsis_inputs": ti,
                },
            })

        p_key = _resolve_persona_key(persona)
        merged_custom_weights = dict(custom_weights) if custom_weights else {}

        chroma_meta: Dict[str, Any] = {"adjusted_count": 0, "semantic_weight_boosts": {}}
        adj_map: Optional[Dict[str, float]] = None
        dyn_nlp_w: Optional[float] = None
        if user_text_prompt and str(user_text_prompt).strip():
            dual_out = self._compute_dual_review_and_semantic_boosts(str(user_text_prompt).strip())
            adj_map = dual_out["adjusted_nlp_scores"]
            sem_boosts = dual_out["semantic_weight_boosts"]
            dyn_nlp_w = dual_out.get("nlp_dynamic_weight")
            chroma_meta["adjusted_count"] = len(adj_map)
            chroma_meta["semantic_weight_boosts"] = sem_boosts
            chroma_meta["nlp_dynamic_weight"] = dyn_nlp_w

            for lap in working_laptops:
                cid = lap.get("canonical_id")
                if cid in adj_map:
                    lap["derived_metrics"]["topsis_inputs"]["community_nlp_score"] = adj_map[cid]

            base_w = PERSONA_CONFIGS[p_key]["weights"]
            for k, b_val in sem_boosts.items():
                if k in base_w:
                    merged_custom_weights[k] = merged_custom_weights.get(k, base_w[k]) + b_val
                elif k in _LEGACY_WEIGHT_EXPANSION:
                    for sub_k, share in _LEGACY_WEIGHT_EXPANSION[k]:
                        if sub_k in base_w:
                            merged_custom_weights[sub_k] = merged_custom_weights.get(sub_k, base_w[sub_k]) + (b_val * share)

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
            nlp_dynamic_weight=(
                dyn_nlp_w
                if (dyn_nlp_w is not None and "community_nlp_score" not in (custom_weights or {}))
                else None
            ),
            adjusted_nlp_scores=adj_map,
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

    def score_prompt(self, user_text_prompt: Optional[str] = "") -> Dict[str, Any]:
        return self.recommender.score_prompt(user_text_prompt=user_text_prompt)

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
