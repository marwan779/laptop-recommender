#!/usr/bin/env python3
"""
Unified Turnkey Recommendation Pipeline (recommendation_pipeline.py)
--------------------------------------------------------------------
Connects:
  1. Singleton `jinaai/jina-embeddings-v3` + Persistent `ChromaDB` Dual-Vector Search
  2. Bilingual Semantic & Keyword Intent Weight Boosting
  3. Budget-Scoped Vector TOPSIS (`topsis_engine.py`)
  4. Zero-Candidate Graceful Fallback (`BUDGET_TOO_LOW_FOR_CATEGORY`)
Supports both direct Python import for FastAPI AND CLI execution for testing.
"""
import argparse
import copy
import json
import time
from functools import lru_cache
from pathlib import Path
from typing import Dict, Any, List, Optional

import numpy as np
import chromadb

from chroma_reviews_engine import (
    JinaV3EmbeddingFunction,
    MODEL_NAME,
    CHROMA_DEFAULT_DIR,
    COLLECTION_NAME,
)
from topsis_engine import (
    rank_laptops_topsis,
    PERSONA_CONFIGS,
    parse_user_text_prompt,
)
from workload_engine import evaluate_workloads

# Reference bilingual anchor descriptions for Semantic Weight Boosting
CRITERIA_SEMANTIC_ANCHORS: Dict[str, str] = {
    "cpu_score": "معالج قوي بروسيسور سريع للبرمجة والملتي تاسكينج والمحاكاة والداتا fast CPU processor heavy coding multitasking virtualization",
    "gpu_score": "كارت شاشة قوي للألعاب الثقيلة وفريمات عالية وريندر وجرافيك 3D powerful gaming GPU high FPS RTX rendering",
    "power_therm_score": "تبريد ممتاز ميسخنش في الصيف مراوح قوية باور عالي بدون اختناق حراري excellent cooling thermals runs cool no thermal throttling full TGP",
    "display_score": "شاشة اوليد ألوان دقيقة مونتاج وتصميم سطوع عالي 100% sRGB OLED display screen accurate colors brightness",
    "mobility_score": "بطارية تقعد وقت طويل وزن خفيف للتنقل والسفر والجامعة والمحاضرات long battery life lightweight portable thin travel",
    "longevity_score": "قابل للتطوير وزيادة الرامات والهارد ومفصلات وشاسيه متين يعيش للمستقبل upgradeable RAM SSD slots durable metal chassis sturdy hinges",
    "ergonomics_score": "كيبورد مريحة في الكتابة كاميرا نقية للاجتماعات وصوت عالي وبصمة comfortable backlit keyboard good webcam microphone speakers fingerprint",
    "connectivity_score": "منافذ كتير تايب سي ثندربولت وكابل نت وشاشات خارجية thunderbolt USB-C PD HDMI ethernet LAN ports",
}


class LaptopRecommenderService:
    """
    Singleton Service for Backend integration.
    Loads `jina-embeddings-v3` and `ChromaDB` once in RAM at server startup.
    """
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(LaptopRecommenderService, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(
        self,
        chroma_dir: str = CHROMA_DEFAULT_DIR,
        catalog_fallback_path: str = "unified_catalog_topsis_ready_v6.json",
        reviews_fallback_path: str = "reviews_deduplicated_v6.json",
        model_name: str = MODEL_NAME,
    ):
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
        rpath = Path(reviews_path or self.reviews_fallback_path)
        if not rpath.exists():
            return
        with open(rpath, "r", encoding="utf-8") as f:
            rev_json = json.load(f)
        lookup: Dict[str, Dict[str, Any]] = {}
        for entry in rev_json.get("chassis_reviews", []):
            clean_lists = entry.get("clean_profile_lists", {})
            chunks = entry.get("deduplicated_chunks", [])
            ed_pros = [c["text"] for c in chunks if c.get("source_type") == "scraped_editorial" and c.get("polarity") == "pro"]
            ed_cons = [c["text"] for c in chunks if c.get("source_type") == "scraped_editorial" and c.get("polarity") == "con"]
            fallback_profile = {
                "community_nlp_score": float(entry.get("community_nlp_score", 75.0)),
                "aspect_scores": dict(entry.get("aspect_scores", {})),
                "pros_ar": list(clean_lists.get("pros_ar", [])),
                "cons_ar": list(clean_lists.get("cons_ar", [])),
                "pros_en": list(dict.fromkeys(list(clean_lists.get("pros_en", [])) + ed_pros)),
                "cons_en": list(dict.fromkeys(list(clean_lists.get("cons_en", [])) + ed_cons)),
            }
            for cid in entry.get("matched_canonical_ids", []):
                if cid:
                    lookup[cid] = fallback_profile
        self._reviews_by_cid = lookup

    def _init_resources(self) -> None:
        if Path(self.catalog_fallback_path).exists():
            with open(self.catalog_fallback_path, "r", encoding="utf-8") as f:
                self._cached_catalog = json.load(f).get("laptops", [])

        self._load_reviews_lookup()

        if Path(self.chroma_dir).exists():
            try:
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
        """LRU-cached wrapper (maxsize=256) around ChromaDB + Semantic anchor inference."""
        return self._cached_dual_query(user_query)

    def _compute_dual_review_and_semantic_boosts_uncached(
        self, user_query: str
    ) -> Dict[str, Any]:
        """
        Encodes `user_query` ONCE and computes:
          1. Dual-Vector Net Review Similarity (`Cosine(Q, Pros) - 0.75 * Cosine(Q, Cons)`)
          2. Semantic Criteria Weight Boosts against the 8 hardware anchors.
        """
        if not self.collection or not self.query_emb_fn:
            return {"adjusted_nlp_scores": {}, "semantic_weight_boosts": {}}

        q_vec_list = self.query_emb_fn([user_query])
        q_vec = np.array(q_vec_list[0], dtype=float)

        # 1. Query ChromaDB Pros & Cons using pre-computed query embedding
        pro_res = self.collection.query(
            query_embeddings=q_vec_list,
            n_results=189,
            where={"polarity": "pro"},
        )
        con_res = self.collection.query(
            query_embeddings=q_vec_list,
            n_results=189,
            where={"polarity": "con"},
        )

        pro_sim, base_scores, cids_map = {}, {}, {}
        if pro_res and pro_res.get("metadatas") and pro_res.get("distances"):
            for meta, dist in zip(pro_res["metadatas"][0], pro_res["distances"][0]):
                ckey = meta["chassis_key"]
                pro_sim[ckey] = max(0.0, 1.0 - float(dist))
                base_scores[ckey] = float(meta.get("community_nlp_score", 75.0))
                cids_map[ckey] = [c for c in meta.get("matched_canonical_ids", "").split(",") if c]

        con_sim = {}
        if con_res and con_res.get("metadatas") and con_res.get("distances"):
            for meta, dist in zip(con_res["metadatas"][0], con_res["distances"][0]):
                ckey = meta["chassis_key"]
                con_sim[ckey] = max(0.0, 1.0 - float(dist))

        adjusted_nlp_scores: Dict[str, float] = {}
        for ckey, base_s in base_scores.items():
            net_sim = pro_sim.get(ckey, 0.0) - 0.75 * con_sim.get(ckey, 0.0)
            adj = max(35.0, min(98.0, round(base_s + net_sim * 32.0, 2)))
            for cid in cids_map.get(ckey, []):
                adjusted_nlp_scores[cid] = adj

        # 2. Semantic Weight Boosts via dot product with normalized anchor matrix
        semantic_boosts: Dict[str, float] = {}
        if self.anchor_matrix is not None:
            sims = np.dot(self.anchor_matrix, q_vec)
            for idx, sim_val in enumerate(sims):
                if sim_val >= 0.48:
                    key = self.anchor_keys[idx]
                    semantic_boosts[key] = round(float((sim_val - 0.45) * 0.35), 3)

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
        """
        Single entry-point function for Backend `POST /api/recommend`.
        """
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
            # Boost `community_nlp_score` inside the 10-column TOPSIS matrix when text prompt is active
            if "community_nlp_score" not in (custom_weights or {}):
                merged_custom_weights["community_nlp_score"] = 0.22

        # Run 10-column TOPSIS (`community_nlp_score` integrated directly inside the matrix)
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

        # Attach rich community_reviews (Pros/Cons/5 Aspects) with fallback to deduplicated reviews map
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

        # Handle Zero-Candidate Edge Case (`BUDGET_TOO_LOW_FOR_CATEGORY`)
        if not ranked["results"]:
            active_all = [
                l for l in working_laptops
                if l.get("derived_metrics", {}).get("topsis_inputs", {}).get("in_stock_active")
            ]
            active_all.sort(
                key=lambda x: x["derived_metrics"]["topsis_inputs"].get("effective_price_egp") or 999999
            )
            closest_alts = [
                {
                    "canonical_id": l["canonical_id"],
                    "title": l.get("title"),
                    "effective_price_egp": l["derived_metrics"]["topsis_inputs"].get("effective_price_egp"),
                    "cheapest_store": l.get("cheapest_store"),
                }
                for l in active_all[:3]
            ]
            ranked["status"] = "BUDGET_TOO_LOW_FOR_CATEGORY"
            ranked["message_ar"] = "الميزانية المحددة أقل من أسعار الأجهزة المتاحة في هذه الفئة حالياً؛ إليك أقرب 3 بدائل اقتصادية متاحة."
            ranked["closest_alternatives"] = closest_alts
        else:
            ranked["status"] = "OK"
            ranked["message_ar"] = "تم ترتيب أفضل اللابتوبات المطابقة لاحتياجاتك بنجاح."
            ranked["closest_alternatives"] = []

        ranked["chroma_nlp_metadata"] = chroma_meta
        ranked["execution_time_ms"] = round((time.perf_counter() - t_start) * 1000.0, 2)
        return ranked


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Turnkey Laptop Recommendation Pipeline (CLI)")
    parser.add_argument("--budget", type=float, default=65000.0, help="Max budget in EGP")
    parser.add_argument("--persona", type=str, default="gaming", help="User persona key")
    parser.add_argument("--query", type=str, default="", help="Optional Arabic/English user text box prompt")
    parser.add_argument("--top-k", type=int, default=5, help="Number of results to return")
    args = parser.parse_args()

    service = LaptopRecommenderService()
    out = service.recommend(
        max_budget_egp=args.budget,
        persona=args.persona,
        user_text_prompt=args.query,
        top_k=args.top_k,
    )
    print(f"\nStatus: {out['status']} | Execution Time: {out['execution_time_ms']} ms")
    print(f"Budget Window: {out['applied_budget_window_egp']} | Candidates Scored: {out['total_candidates_after_gates_and_floor']}")
    for item in out["results"]:
        print(
            f"  #{item['rank']} [{item['topsis_match_score']}% | NLP={item['topsis_inputs']['community_nlp_score']}] "
            f"{item['canonical_id']} | {item['effective_price_egp']:,.0f} EGP ({item['cheapest_store']})"
        )