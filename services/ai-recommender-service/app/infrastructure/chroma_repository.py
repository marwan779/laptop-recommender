"""ChromaDB persistent review-vector store adapter."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.infrastructure.jina_embedder import JinaV3EmbeddingFunction
from app.infrastructure.protocols import IReviewsVectorStore

CHROMA_DEFAULT_DIR = "./chroma_reviews_db"
COLLECTION_NAME = "laptop_chassis_reviews_jina_v3"


class ChromaDualVectorQuery:
    """Runs the paired pro/con semantic queries used for net review similarity."""

    def __init__(self, collection: Any) -> None:
        self.collection = collection

    def query(self, query_embeddings: List[List[float]], n_results: int = 189) -> Dict[str, Any]:
        pro_res = self.collection.query(
            query_embeddings=query_embeddings,
            n_results=n_results,
            where={"polarity": "pro"},
        )
        con_res = self.collection.query(
            query_embeddings=query_embeddings,
            n_results=n_results,
            where={"polarity": "con"},
        )
        return {"pro": pro_res, "con": con_res}


class ChromaReviewsRepository(IReviewsVectorStore):
    """Persistent ChromaDB collection builder / upsert + query adapter."""

    def __init__(self, collection: Any = None) -> None:
        self.collection = collection
        self.last_profiles_by_canonical_id: Dict[str, Any] = {}

    # -- construction -----------------------------------------------------
    @staticmethod
    def open_collection(chroma_dir: str, embedding_function: Any) -> Any:
        import chromadb

        client = chromadb.PersistentClient(path=chroma_dir)
        return client.get_collection(
            name=COLLECTION_NAME,
            embedding_function=embedding_function,
        )

    def _extract_records_and_profiles(
        self,
        data: Dict[str, Any],
    ) -> tuple[Dict[str, tuple], Dict[str, Dict[str, Any]]]:
        """Extract Chroma `(text, metadata)` documents and canonical-id NLP profiles."""
        merged_by_ckey: Dict[str, Dict[str, Any]] = {}
        db_update_payload: Dict[str, Dict[str, Any]] = {}

        if "chassis_reviews" in data:
            for item in data.get("chassis_reviews", []):
                ckey = item["chassis_key"]
                cids_list = self._resolve_canonical_ids(item)
                brand = item.get("identity", {}).get("brand", "") or ""
                comm_score = float(item.get("community_nlp_score", 75.0))
                clean_lists = item.get("clean_profile_lists", {})
                chunks = item.get("deduplicated_chunks", [])
                ed_pros = [
                    c["text"]
                    for c in chunks
                    if c.get("source_type") == "scraped_editorial" and c.get("polarity") == "pro"
                ]
                ed_cons = [
                    c["text"]
                    for c in chunks
                    if c.get("source_type") == "scraped_editorial" and c.get("polarity") == "con"
                ]

                pros_ar_list = list(clean_lists.get("pros_ar", []))
                cons_ar_list = list(clean_lists.get("cons_ar", []))
                pros_en_list = list(dict.fromkeys(list(clean_lists.get("pros_en", [])) + ed_pros))
                cons_en_list = list(dict.fromkeys(list(clean_lists.get("cons_en", [])) + ed_cons))

                prof_summary = {
                    "community_nlp_score": comm_score,
                    "aspect_scores": item.get("aspect_scores", {}),
                    "pros_ar": pros_ar_list,
                    "cons_ar": cons_ar_list,
                    "pros_en": pros_en_list,
                    "cons_en": cons_en_list,
                }
                for cid in cids_list:
                    db_update_payload[cid] = prof_summary

                merged_by_ckey[ckey] = {
                    "brand": brand,
                    "cids": list(cids_list),
                    "scores": [comm_score],
                    "pros_ar": pros_ar_list,
                    "pros_en": pros_en_list,
                    "cons_ar": cons_ar_list,
                    "cons_en": cons_en_list,
                }
        else:
            for item in data.get("laptops", []):
                ckey = item["chassis_key"]
                prof = item.get("nlp_review_profile", {})
                cids_list = self._resolve_canonical_ids(item)
                brand = item.get("identity", {}).get("brand", "") or ""
                comm_score = float(prof.get("community_nlp_score", 75.0))

                for cid in cids_list:
                    db_update_payload[cid] = prof

                if ckey not in merged_by_ckey:
                    merged_by_ckey[ckey] = {
                        "brand": brand,
                        "cids": list(cids_list),
                        "scores": [comm_score],
                        "pros_ar": list(prof.get("pros_ar", [])),
                        "pros_en": list(prof.get("pros_en", [])),
                        "cons_ar": list(prof.get("cons_ar", [])),
                        "cons_en": list(prof.get("cons_en", [])),
                    }
                else:
                    entry = merged_by_ckey[ckey]
                    entry["cids"].extend(cids_list)
                    entry["scores"].append(comm_score)
                    entry["pros_ar"].extend(prof.get("pros_ar", []))
                    entry["pros_en"].extend(prof.get("pros_en", []))
                    entry["cons_ar"].extend(prof.get("cons_ar", []))
                    entry["cons_en"].extend(prof.get("cons_en", []))

        records_by_id: Dict[str, tuple] = {}
        for ckey, entry in merged_by_ckey.items():
            cids_csv = ",".join(dict.fromkeys(c for c in entry["cids"] if c))
            avg_score = round(sum(entry["scores"]) / len(entry["scores"]), 2)

            # Preserve order while deduplicating sentences across merged duplicate chassis entries
            pros_ar_u = list(dict.fromkeys(s.strip() for s in entry["pros_ar"] if s and s.strip()))
            pros_en_u = list(dict.fromkeys(s.strip() for s in entry["pros_en"] if s and s.strip()))
            cons_ar_u = list(dict.fromkeys(s.strip() for s in entry["cons_ar"] if s and s.strip()))
            cons_en_u = list(dict.fromkeys(s.strip() for s in entry["cons_en"] if s and s.strip()))

            pros_text = " | ".join(pros_ar_u + pros_en_u)
            if pros_text:
                records_by_id[f"{ckey}__pro"] = (
                    pros_text,
                    {
                        "chassis_key": ckey,
                        "brand": entry["brand"],
                        "polarity": "pro",
                        "community_nlp_score": avg_score,
                        "matched_canonical_ids": cids_csv,
                    },
                )

            cons_text = " | ".join(cons_ar_u + cons_en_u)
            if cons_text:
                records_by_id[f"{ckey}__con"] = (
                    cons_text,
                    {
                        "chassis_key": ckey,
                        "brand": entry["brand"],
                        "polarity": "con",
                        "community_nlp_score": avg_score,
                        "matched_canonical_ids": cids_csv,
                    },
                )

        return records_by_id, db_update_payload

    @staticmethod
    def _resolve_canonical_ids(item: Dict[str, Any]) -> List[str]:
        cids = [str(c) for c in (item.get("matched_canonical_ids") or []) if c]
        for fallback_key in ("primary_canonical_id", "canonical_id"):
            cid = item.get(fallback_key)
            if cid and str(cid) not in cids:
                cids.append(str(cid))
        return cids

    def _sync_collection(
        self,
        data: Dict[str, Any],
        chroma_dir: str,
        model_name: str,
        *,
        recreate: bool,
    ) -> Dict[str, Any]:
        """Shared ChromaDB persistence helper for full rebuilds and incremental batch upserts."""
        import chromadb

        client = chromadb.PersistentClient(path=chroma_dir)
        passage_emb_fn = JinaV3EmbeddingFunction(model_name=model_name, task="retrieval.passage")

        if recreate:
            # Recreate collection cleanly so 512d vectors never clash with previous collections
            try:
                client.delete_collection(name=COLLECTION_NAME)
            except Exception:
                pass
            collection = client.create_collection(
                name=COLLECTION_NAME,
                embedding_function=passage_emb_fn,
                metadata={"hnsw:space": "cosine"},
            )
        else:
            collection = client.get_or_create_collection(
                name=COLLECTION_NAME,
                embedding_function=passage_emb_fn,
                metadata={"hnsw:space": "cosine"},
            )

        self.collection = collection
        records_by_id, db_update_payload = self._extract_records_and_profiles(data)

        existing_ids = set(collection.get(include=[]).get("ids") or []) if recreate else set()
        pending = [(did, txt, meta) for did, (txt, meta) in records_by_id.items() if did not in existing_ids]
        docs = [p[1] for p in pending]
        metadatas = [p[2] for p in pending]
        ids = [p[0] for p in pending]

        action = "rebuilt" if recreate else "upserted"
        print(
            f"[ChromaDB] ({action}) Batch docs: {len(records_by_id)}, "
            f"already indexed skipped: {len(existing_ids)}, pending: {len(ids)}"
        )

        batch_size = 16
        for i in range(0, len(docs), batch_size):
            collection.upsert(
                documents=docs[i:i + batch_size],
                metadatas=metadatas[i:i + batch_size],
                ids=ids[i:i + batch_size],
            )
            print(f"  [ChromaDB] Indexed {min(i + batch_size, len(docs))}/{len(docs)} documents...")

        print(f"[ChromaDB] Persisted {len(records_by_id)} unique documents into '{chroma_dir}' using {model_name}.")
        self.last_profiles_by_canonical_id = db_update_payload
        return {
            "indexed_documents_count": len(records_by_id),
            "updated_laptops_count": len(db_update_payload),
            "profiles_by_canonical_id": db_update_payload,
        }

    def build(self, data: Dict[str, Any], chroma_dir: str, model_name: str) -> Dict[str, Any]:
        """Destructively rebuild the persistent collection from scratch (CLI/batch rebuilds)."""
        return self._sync_collection(data, chroma_dir=chroma_dir, model_name=model_name, recreate=True)

    def upsert_reviews(self, data: Dict[str, Any], chroma_dir: str, model_name: str) -> Dict[str, Any]:
        """Incrementally add/update a review batch in ChromaDB without wiping existing laptops."""
        return self._sync_collection(data, chroma_dir=chroma_dir, model_name=model_name, recreate=False)

    # -- query ------------------------------------------------------------
    def query_dual(
        self,
        query_embeddings: List[List[float]],
        n_results: int = 189,
    ) -> Dict[str, Any]:
        if self.collection is None:
            return {"pro": {}, "con": {}}
        return ChromaDualVectorQuery(self.collection).query(query_embeddings, n_results=n_results)


def build_chroma_collection(data: Dict[str, Any], chroma_dir: str, model_name: str) -> Dict[str, Any]:
    """Compatibility helper around `ChromaReviewsRepository.build`."""
    return ChromaReviewsRepository().build(data, chroma_dir=chroma_dir, model_name=model_name)
