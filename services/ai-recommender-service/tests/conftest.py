"""Test bootstrap: provide lightweight stubs for optional heavy dependencies.

The characterization suite must never download Hugging Face models, touch a GPU,
or require a running ChromaDB.  `chroma_reviews_engine` imports `chromadb` at
module scope, so when it is unavailable we register a minimal, import-only stub.
The production code never calls these stubs in the tests that need them.
"""

from __future__ import annotations

import sys
import types


def _install_chromadb_stub() -> None:
    try:
        import chromadb  # noqa: F401
        return
    except Exception:
        pass

    class EmbeddingFunction:
        def __class_getitem__(cls, item):  # pragma: no cover - generic shim
            return cls

    Documents = list
    Embeddings = list

    root = types.ModuleType("chromadb")
    api = types.ModuleType("chromadb.api")
    api_types = types.ModuleType("chromadb.api.types")
    api_types.Documents = Documents
    api_types.Embeddings = Embeddings
    api_types.EmbeddingFunction = EmbeddingFunction
    api.types = api_types
    root.api = api

    sys.modules.setdefault("chromadb", root)
    sys.modules.setdefault("chromadb.api", api)
    sys.modules.setdefault("chromadb.api.types", api_types)


_install_chromadb_stub()
