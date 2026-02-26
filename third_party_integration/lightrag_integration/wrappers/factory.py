from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from .contracts import LightRAGIntegrationAdapter
from .lightrag_adapter import LightRAGAdapter
from .lightrag_adapter_mock import LightRAGMockAdapter


def _env_to_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


@dataclass(slots=True)
class LightRAGAdapterConfig:
    working_dir: str
    use_mock: bool = False
    llm_model: str = "gpt-4o-mini"
    embedding_model: str = "text-embedding-3-small"
    embedding_dim: int = 1536
    llm_base_url: str | None = None
    llm_api_key: str | None = None
    embedding_base_url: str | None = None
    embedding_api_key: str | None = None
    rerank_provider: str | None = None
    llm_model_kwargs: dict[str, Any] | None = None

    @classmethod
    def from_env(
        cls,
        *,
        working_dir: str,
        use_mock: bool | None = None,
    ) -> "LightRAGAdapterConfig":
        return cls(
            working_dir=working_dir,
            use_mock=_env_to_bool("LIGHTRAG_USE_MOCK", False) if use_mock is None else use_mock,
            llm_model=os.getenv("LIGHTRAG_LLM_MODEL", "gpt-4o-mini"),
            embedding_model=os.getenv("LIGHTRAG_EMBED_MODEL", "text-embedding-3-small"),
            embedding_dim=int(os.getenv("LIGHTRAG_EMBED_DIM", "1536")),
            llm_base_url=os.getenv("LIGHTRAG_LLM_BASE_URL"),
            llm_api_key=os.getenv("LIGHTRAG_LLM_API_KEY"),
            embedding_base_url=os.getenv("LIGHTRAG_EMBED_BASE_URL"),
            embedding_api_key=os.getenv("LIGHTRAG_EMBED_API_KEY"),
            rerank_provider=os.getenv("LIGHTRAG_RERANK_PROVIDER"),
        )


def create_lightrag_adapter(config: LightRAGAdapterConfig) -> LightRAGIntegrationAdapter:
    if config.use_mock:
        return LightRAGMockAdapter(working_dir=config.working_dir)

    return LightRAGAdapter(
        working_dir=config.working_dir,
        llm_model=config.llm_model,
        embedding_model=config.embedding_model,
        embedding_dim=config.embedding_dim,
        llm_base_url=config.llm_base_url,
        llm_api_key=config.llm_api_key,
        embedding_base_url=config.embedding_base_url,
        embedding_api_key=config.embedding_api_key,
        rerank_provider=config.rerank_provider,
        llm_model_kwargs=config.llm_model_kwargs,
    )


def create_lightrag_adapter_from_env(
    *,
    working_dir: str,
    use_mock: bool | None = None,
) -> LightRAGIntegrationAdapter:
    return create_lightrag_adapter(
        LightRAGAdapterConfig.from_env(
            working_dir=working_dir,
            use_mock=use_mock,
        )
    )
