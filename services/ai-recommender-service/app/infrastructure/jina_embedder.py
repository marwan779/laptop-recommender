"""Jina-v3 embedding adapter + passage scorer.

This is the only place where the SentenceTransformer model is loaded.  All
cosine/vector math is delegated to the pure domain scorer.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from app.domain.enrichment.chunking import (
    _format_catalog_specs_summary,
    _gather_raw_candidate_chunks,
    _select_top_candidates_for_jina,
)
from app.domain.enrichment.models import (
    ASPECT_KEYS,
    _CON_ANCHORS,
    _NOISE_ANCHOR,
    _PRO_ANCHORS,
)
from app.domain.enrichment.scoring import _score_snippets_from_vectors
from app.infrastructure.protocols import IEmbeddingEncoder

try:  # ChromaDB is optional at import time (tests / lightweight CLI usage).
    from chromadb.api.types import Documents, EmbeddingFunction, Embeddings

    _EmbeddingFunctionBase = EmbeddingFunction[Documents]
except Exception:  # pragma: no cover - exercised only without chromadb installed
    Documents = list  # type: ignore[assignment,misc]
    Embeddings = list  # type: ignore[assignment,misc]
    _EmbeddingFunctionBase = object  # type: ignore[assignment,misc]

MODEL_NAME = "jinaai/jina-embeddings-v3"
EMBED_DIM = 512

_EMBED_FN_SINGLETON: Any = None
_ANCHOR_EMBS_CACHE: Optional[Dict[str, Any]] = None


class JinaV3EmbeddingFunction(_EmbeddingFunctionBase):  # type: ignore[misc,valid-type]
    """
    Singleton-friendly wrapper around SentenceTransformer for `jinaai/jina-embeddings-v3`.
    Supports `task="retrieval.passage"` during indexing and `task="retrieval.query"` at search time,
    using Matryoshka `truncate_dim=512` (selected via A/B benchmark: 90.7% Top-5 overlap, 0.9874 rank corr).
    """
    _model_instance = None

    def __init__(self, model_name: str = MODEL_NAME, task: str = "retrieval.passage", truncate_dim: int = EMBED_DIM):
        self.model_name = model_name
        self.task = task
        self.truncate_dim = truncate_dim
        if JinaV3EmbeddingFunction._model_instance is None:
            import torch
            from sentence_transformers import SentenceTransformer

            dtype = torch.float16 if torch.cuda.is_available() else torch.float32
            try:
                JinaV3EmbeddingFunction._model_instance = SentenceTransformer(
                    model_name,
                    trust_remote_code=True,
                    truncate_dim=truncate_dim,
                    model_kwargs={"torch_dtype": dtype},
                )
            except Exception:
                # Fallback if float16 or remote code fails on older CPU
                JinaV3EmbeddingFunction._model_instance = SentenceTransformer(
                    model_name,
                    trust_remote_code=True,
                    truncate_dim=truncate_dim,
                )
            JinaV3EmbeddingFunction._model_instance.max_seq_length = 256

    def __call__(self, input: Documents) -> Embeddings:
        model = JinaV3EmbeddingFunction._model_instance
        try:
            vecs = model.encode(
                list(input),
                task=self.task,
                prompt_name=self.task,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
        except TypeError:
            vecs = model.encode(
                list(input),
                normalize_embeddings=True,
                show_progress_bar=False,
            )
        return vecs.tolist()


class JinaPassageScorer:
    """Adapter around a Jina encoder that delegates all scoring math to the domain."""

    def __init__(self, encoder: Optional[IEmbeddingEncoder] = None) -> None:
        self._encoder = encoder
        self._anchor_cache: Optional[Dict[str, Any]] = None

    @property
    def encoder(self) -> IEmbeddingEncoder:
        if self._encoder is None:
            self._encoder = _get_jina_embed_fn()
        return self._encoder

    def anchor_embeddings(self) -> Dict[str, Any]:
        """Compute and cache normalized embeddings for the 10 aspect anchors + 1 noise anchor."""
        if self._anchor_cache is not None:
            return self._anchor_cache

        keys_and_texts: List[Tuple[str, str, str]] = []
        for k in ASPECT_KEYS:
            keys_and_texts.append(("pro", k, _PRO_ANCHORS[k]))
            keys_and_texts.append(("con", k, _CON_ANCHORS[k]))
        keys_and_texts.append(("noise", "noise", _NOISE_ANCHOR))

        vecs = np.asarray(self.encoder([t for _, _, t in keys_and_texts]), dtype=np.float32)
        norms = np.linalg.norm(vecs, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        vecs = vecs / norms

        pro_vecs = np.stack([vecs[i] for i, (kind, _, _) in enumerate(keys_and_texts) if kind == "pro"])
        con_vecs = np.stack([vecs[i] for i, (kind, _, _) in enumerate(keys_and_texts) if kind == "con"])
        noise_vec = vecs[-1]

        self._anchor_cache = {
            "pro": pro_vecs,
            "con": con_vecs,
            "noise": noise_vec,
        }
        return self._anchor_cache

    def score_item(
        self,
        chassis_key: str,
        unique_cands: List[Dict[str, Any]],
        doc_count: int,
        specs_summary: Dict[str, Any],
        vecs: np.ndarray,
        max_snippets: int = 20,
        dedup_cosine: float = 0.88,
    ) -> Dict[str, Any]:
        return _score_snippets_from_vectors(
            chassis_key=chassis_key,
            unique_cands=unique_cands,
            doc_count=doc_count,
            specs_summary=specs_summary,
            vecs=vecs,
            anchors=self.anchor_embeddings(),
            max_snippets=max_snippets,
            dedup_cosine=dedup_cosine,
        )

    def extract_hardware_sentences_jina(
        self,
        item: Dict[str, Any],
        cat_map: Optional[Dict[str, Any]] = None,
        max_snippets: int = 16,
        dedup_cosine: float = 0.88,
        max_candidates: int = 24,
    ) -> Dict[str, Any]:
        """
        Use local `Jina-v3` (512-dim) embeddings to filter out noisy/off-topic lines,
        deduplicate near-identical chunks, select the top `max_snippets` hardware-relevant
        sentences across aspects & sources, and compute Jina 10-anchor aspect signals.
        """
        return self.extract_hardware_sentences_jina_batch(
            items=[item],
            cat_map=cat_map,
            max_snippets=max_snippets,
            dedup_cosine=dedup_cosine,
            max_candidates=max_candidates,
        )[0]

    def extract_hardware_sentences_jina_batch(
        self,
        items: List[Dict[str, Any]],
        cat_map: Optional[Dict[str, Any]] = None,
        max_snippets: int = 16,
        dedup_cosine: float = 0.88,
        max_candidates: int = 24,
        encode_slice_size: int = 256,
    ) -> List[Dict[str, Any]]:
        """
        Batch-extract Jina-v3 hardware evidence across multiple chassis with global
        length sorting to minimize Transformer padding overhead on CPU.
        """
        prepared: List[Tuple[str, List[Dict[str, Any]], int, Dict[str, Any]]] = []
        flat_texts: List[Tuple[int, int, str]] = []

        for item_idx, item in enumerate(items):
            ckey = str(item.get("chassis_key") or "")
            candidates, doc_count = _gather_raw_candidate_chunks(item)
            specs_summary = _format_catalog_specs_summary(item, cat_map)
            unique_cands = _select_top_candidates_for_jina(candidates, max_candidates=max_candidates)
            prepared.append((ckey, unique_cands, doc_count, specs_summary))
            for cand_idx, c in enumerate(unique_cands):
                flat_texts.append((item_idx, cand_idx, c["text"]))

        if not flat_texts:
            return [
                self.score_item(
                    chassis_key=ckey,
                    unique_cands=[],
                    doc_count=doc_count,
                    specs_summary=specs_summary,
                    vecs=np.empty((0, 512), dtype=np.float32),
                    max_snippets=max_snippets,
                    dedup_cosine=dedup_cosine,
                )
                for ckey, _, doc_count, specs_summary in prepared
            ]

        emb_fn = self.encoder
        anchors = self.anchor_embeddings()

        # Global length sort minimizes attention padding per batch on CPU
        sorted_refs = sorted(flat_texts, key=lambda x: len(x[2]))
        total_texts = len(sorted_refs)
        sorted_vecs: List[np.ndarray] = []

        model_obj = getattr(emb_fn, "_model", None)
        prev_max_seq = getattr(model_obj, "max_seq_length", 256) if model_obj is not None else None
        try:
            if model_obj is not None:
                model_obj.max_seq_length = 96
            for start in range(0, total_texts, encode_slice_size):
                batch_strs = [row[2] for row in sorted_refs[start : start + encode_slice_size]]
                bvecs = np.asarray(emb_fn(batch_strs), dtype=np.float32)
                norms = np.linalg.norm(bvecs, axis=1, keepdims=True)
                norms[norms == 0] = 1.0
                bvecs = bvecs / norms
                sorted_vecs.append(bvecs)
                if total_texts > encode_slice_size:
                    done_n = min(start + encode_slice_size, total_texts)
                    print(f"  [Jina-v3 batch] Encoded {done_n}/{total_texts} candidate chunks...")
        finally:
            if model_obj is not None:
                model_obj.max_seq_length = prev_max_seq if prev_max_seq is not None else 256

        all_vecs = np.concatenate(sorted_vecs, axis=0)
        per_item_slots: List[List[Optional[np.ndarray]]] = [
            [None] * len(prep[1]) for prep in prepared
        ]
        for pos, (item_idx, cand_idx, _) in enumerate(sorted_refs):
            per_item_slots[item_idx][cand_idx] = all_vecs[pos]

        outputs: List[Dict[str, Any]] = []
        for item_idx, (ckey, unique_cands, doc_count, specs_summary) in enumerate(prepared):
            if unique_cands:
                item_vecs = np.stack([v for v in per_item_slots[item_idx] if v is not None])
            else:
                item_vecs = np.empty((0, 512), dtype=np.float32)
            outputs.append(
                self.score_item(
                    chassis_key=ckey,
                    unique_cands=unique_cands,
                    doc_count=doc_count,
                    specs_summary=specs_summary,
                    vecs=item_vecs,
                    max_snippets=max_snippets,
                    dedup_cosine=dedup_cosine,
                )
            )
        return outputs


_DEFAULT_SCORER: Optional[JinaPassageScorer] = None


def _get_default_scorer() -> JinaPassageScorer:
    global _DEFAULT_SCORER
    if _DEFAULT_SCORER is None:
        _DEFAULT_SCORER = JinaPassageScorer()
    return _DEFAULT_SCORER


def _get_jina_embed_fn():
    """Return a singleton JinaV3EmbeddingFunction (retrieval.passage, dim=512)."""
    global _EMBED_FN_SINGLETON
    if _EMBED_FN_SINGLETON is None:
        _EMBED_FN_SINGLETON = JinaV3EmbeddingFunction(
            model_name=MODEL_NAME,
            task="retrieval.passage",
            truncate_dim=EMBED_DIM,
        )
    return _EMBED_FN_SINGLETON


def _get_anchor_embeddings() -> Dict[str, Any]:
    """Compute and cache normalized embeddings for the 10 aspect anchors + 1 noise anchor."""
    global _ANCHOR_EMBS_CACHE
    if _ANCHOR_EMBS_CACHE is None:
        _ANCHOR_EMBS_CACHE = _get_default_scorer().anchor_embeddings()
    return _ANCHOR_EMBS_CACHE


def _score_and_select_evidence_for_item(
    chassis_key: str,
    unique_cands: List[Dict[str, Any]],
    doc_count: int,
    specs_summary: Dict[str, Any],
    vecs: np.ndarray,
    anchors: Dict[str, Any],
    max_snippets: int = 20,
    dedup_cosine: float = 0.88,
) -> Dict[str, Any]:
    """Run 10-anchor Jina cosine scoring, noise rejection, and cosine dedup for one chassis."""
    return _score_snippets_from_vectors(
        chassis_key=chassis_key,
        unique_cands=unique_cands,
        doc_count=doc_count,
        specs_summary=specs_summary,
        vecs=vecs,
        anchors=anchors,
        max_snippets=max_snippets,
        dedup_cosine=dedup_cosine,
    )


def extract_hardware_sentences_jina(
    item: Dict[str, Any],
    cat_map: Optional[Dict[str, Any]] = None,
    max_snippets: int = 16,
    dedup_cosine: float = 0.88,
    max_candidates: int = 24,
) -> Dict[str, Any]:
    return _get_default_scorer().extract_hardware_sentences_jina(
        item=item,
        cat_map=cat_map,
        max_snippets=max_snippets,
        dedup_cosine=dedup_cosine,
        max_candidates=max_candidates,
    )


def extract_hardware_sentences_jina_batch(
    items: List[Dict[str, Any]],
    cat_map: Optional[Dict[str, Any]] = None,
    max_snippets: int = 16,
    dedup_cosine: float = 0.88,
    max_candidates: int = 24,
    encode_slice_size: int = 256,
) -> List[Dict[str, Any]]:
    return _get_default_scorer().extract_hardware_sentences_jina_batch(
        items=items,
        cat_map=cat_map,
        max_snippets=max_snippets,
        dedup_cosine=dedup_cosine,
        max_candidates=max_candidates,
        encode_slice_size=encode_slice_size,
    )
