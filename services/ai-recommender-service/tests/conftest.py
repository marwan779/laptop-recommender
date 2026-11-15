"""Test bootstrap: provide lightweight stubs for optional heavy dependencies.

The characterization suite must never download Hugging Face models, touch a GPU,
or require a running ChromaDB.  `chroma_reviews_engine` imports `chromadb` at
module scope, so when it is unavailable we register a minimal, import-only stub.
The storage suite likewise uses import-only fallbacks for pydantic-settings and
boto3/botocore when those packages are not installed globally.  Real packages are
never replaced.
"""

from __future__ import annotations

import os
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


def _install_pydantic_settings_stub() -> None:
    """Minimal BaseSettings fallback used only when pydantic-settings is unavailable."""
    try:
        import pydantic_settings  # noqa: F401
        return
    except Exception:
        pass

    def SettingsConfigDict(**kwargs):  # noqa: N802 - mirrors pydantic-settings API
        return dict(kwargs)

    class BaseSettings:
        """Import-only stand-in supporting field defaults, env lookup and kwargs."""

        model_config: dict = {}

        def __init__(self, **kwargs):
            annotations = {}
            for klass in reversed(type(self).__mro__):
                annotations.update(getattr(klass, "__annotations__", {}))

            for field_name in annotations:
                if field_name == "model_config":
                    continue
                env_value = os.environ.get(field_name.upper())
                if env_value is None:
                    env_value = os.environ.get(field_name)
                if env_value is not None:
                    setattr(self, field_name, env_value)
                elif hasattr(type(self), field_name):
                    setattr(self, field_name, getattr(type(self), field_name))

            for key, value in kwargs.items():
                setattr(self, key, value)

    module = types.ModuleType("pydantic_settings")
    module.BaseSettings = BaseSettings
    module.SettingsConfigDict = SettingsConfigDict
    sys.modules.setdefault("pydantic_settings", module)


def _install_boto_stubs() -> None:
    """Minimal botocore/boto3 fallback used only when the SDKs are unavailable."""
    try:
        import boto3  # noqa: F401
        import botocore.config  # noqa: F401
        import botocore.exceptions  # noqa: F401

        return
    except Exception:
        pass

    botocore = types.ModuleType("botocore")

    class ClientError(Exception):
        def __init__(self, error_response, operation_name="Unknown"):
            self.response = error_response
            self.operation_name = operation_name
            super().__init__(f"{operation_name}: {error_response}")

    class EndpointConnectionError(Exception):
        def __init__(self, *args, **kwargs):
            self.kwargs = kwargs
            message = args[0] if args else kwargs.get("endpoint_url", "endpoint connection error")
            super().__init__(message)

    class ConnectTimeoutError(Exception):
        def __init__(self, *args, **kwargs):
            self.kwargs = kwargs
            message = args[0] if args else kwargs.get("endpoint_url", "connection timeout")
            super().__init__(message)

    exceptions = types.ModuleType("botocore.exceptions")
    exceptions.ClientError = ClientError
    exceptions.EndpointConnectionError = EndpointConnectionError
    exceptions.ConnectTimeoutError = ConnectTimeoutError

    class Config:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    config = types.ModuleType("botocore.config")
    config.Config = Config

    botocore.exceptions = exceptions
    botocore.config = config

    class Session:
        def client(self, service_name, **kwargs):  # pragma: no cover - only without injection
            raise RuntimeError(
                "boto3 is not installed in this test environment; inject a fake boto3_client."
            )

    boto3 = types.ModuleType("boto3")
    boto3_session = types.ModuleType("boto3.session")
    boto3_session.Session = Session
    boto3.session = boto3_session

    sys.modules.setdefault("botocore", botocore)
    sys.modules.setdefault("botocore.exceptions", exceptions)
    sys.modules.setdefault("botocore.config", config)
    sys.modules.setdefault("boto3", boto3)
    sys.modules.setdefault("boto3.session", boto3_session)


_install_chromadb_stub()
_install_pydantic_settings_stub()
_install_boto_stubs()
