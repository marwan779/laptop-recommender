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

    from pydantic import BaseModel, ConfigDict
    from pydantic_core import PydanticUndefined

    def SettingsConfigDict(**kwargs):  # noqa: N802 - mirrors pydantic-settings API
        # Only the config keys that affect the lightweight fallback are retained.
        return ConfigDict(extra=kwargs.get("extra", "ignore"))

    class BaseSettings(BaseModel):
        """Import-only pydantic-backed stand-in supporting defaults, env and kwargs."""

        model_config = ConfigDict(extra="ignore")

        def __init__(self, **kwargs):
            values: dict = {}
            for field_name, field_info in type(self).model_fields.items():
                if field_info.default is not PydanticUndefined:
                    values[field_name] = field_info.default
                elif field_info.default_factory is not None:
                    values[field_name] = field_info.default_factory()

                env_value = os.environ.get(field_name.upper())
                if env_value is None:
                    env_value = os.environ.get(field_name)
                if env_value is not None:
                    values[field_name] = env_value

            values.update(kwargs)
            super().__init__(**values)

    module = types.ModuleType("pydantic_settings")
    module.BaseSettings = BaseSettings
    module.SettingsConfigDict = SettingsConfigDict
    sys.modules.setdefault("pydantic_settings", module)


def _install_redis_stub() -> None:
    """Minimal redis.asyncio fallback used only when redis-py is unavailable."""
    try:
        import redis  # noqa: F401
        import redis.asyncio  # noqa: F401
        import redis.exceptions  # noqa: F401

        return
    except Exception:
        pass

    exceptions = types.ModuleType("redis.exceptions")

    class RedisError(Exception):
        pass

    exceptions.RedisError = RedisError

    asyncio_module = types.ModuleType("redis.asyncio")

    class Redis:
        def __init__(self, url: str | None = None, **kwargs):
            self.url = url
            self.kwargs = kwargs

        @classmethod
        def from_url(cls, url: str, **kwargs):
            return cls(url=url, **kwargs)

        async def ping(self) -> bool:  # pragma: no cover - only without injection
            return True

        async def aclose(self) -> None:  # pragma: no cover - only without injection
            return None

    asyncio_module.Redis = Redis

    redis_module = types.ModuleType("redis")
    redis_module.asyncio = asyncio_module
    redis_module.exceptions = exceptions

    sys.modules.setdefault("redis", redis_module)
    sys.modules.setdefault("redis.asyncio", asyncio_module)
    sys.modules.setdefault("redis.exceptions", exceptions)


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


def _install_aio_pika_stub() -> None:
    """Minimal aio_pika fallback used only when aio-pika is unavailable."""
    try:
        import aio_pika  # noqa: F401
        import aio_pika.abc  # noqa: F401

        return
    except Exception:
        pass

    class ExchangeType:
        TOPIC = "topic"

    class DeliveryMode:
        PERSISTENT = 2

    class Message:
        def __init__(self, body: bytes = b"", **kwargs):
            self.body = body
            self.__dict__.update(kwargs)

    async def connect_robust(*args, **kwargs):  # pragma: no cover - only without injection
        raise RuntimeError("aio-pika is not installed in this test environment; mock connect_robust.")

    abc_module = types.ModuleType("aio_pika.abc")
    abc_module.AbstractChannel = object
    abc_module.AbstractConnection = object
    abc_module.AbstractExchange = object
    abc_module.AbstractIncomingMessage = object

    module = types.ModuleType("aio_pika")
    module.ExchangeType = ExchangeType
    module.DeliveryMode = DeliveryMode
    module.Message = Message
    module.connect_robust = connect_robust
    module.abc = abc_module

    sys.modules.setdefault("aio_pika", module)
    sys.modules.setdefault("aio_pika.abc", abc_module)


_install_chromadb_stub()
_install_pydantic_settings_stub()
_install_boto_stubs()
_install_redis_stub()
_install_aio_pika_stub()
