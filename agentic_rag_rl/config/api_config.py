from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _load_dotenv_file(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        normalized_key = key.strip()
        normalized_value = value.strip().strip('"').strip("'")
        if normalized_key and normalized_key not in os.environ:
            os.environ[normalized_key] = normalized_value


def _load_project_envs() -> str:
    repo_root = Path(__file__).resolve().parents[2]
    candidates = [
        repo_root / "agentic_rag_rl" / ".env",
        repo_root / ".env",
    ]

    for candidate in candidates:
        if candidate.exists():
            _load_dotenv_file(candidate)
            return str(candidate)

    return ""


@dataclass(slots=True)
class CoreAPIConfig:
    # LLM配置
    llm_model: str = "gpt-4o-mini"
    llm_base_url: str | None = None
    llm_api_key: str | None = None
    # Embedding配置
    embed_model: str = "text-embedding-3-small"
    embed_dim: int = 1536
    embed_base_url: str | None = None
    embed_api_key: str | None = None
    # Action Model配置
    action_model: str = "gpt-4o-mini"
    action_base_url: str | None = None
    action_api_key: str | None = None
    # 图适配器配置
    graph_adapter_type: str = "lightrag"  # "lightrag" | "freebase"
    # Freebase配置
    freebase_entity_api_url: str = "http://localhost:8000"
    freebase_sparql_api_url: str = "http://localhost:8890"
    freebase_entity_api_key: str | None = None
    freebase_sparql_api_key: str | None = None
    # 环境源
    env_source: str = ""

    @classmethod
    def from_env(cls) -> "CoreAPIConfig":
        env_source = _load_project_envs()

        llm_base_url = (
            os.getenv("AGENTIC_RAG_LLM_BASE_URL")
            or os.getenv("LIGHTRAG_LLM_BASE_URL")
            or os.getenv("LIGHTRAG_BASE_URL")
        )
        llm_api_key = (
            os.getenv("AGENTIC_RAG_LLM_API_KEY")
            or os.getenv("LIGHTRAG_LLM_API_KEY")
            or os.getenv("LIGHTRAG_API_KEY")
        )

        embed_base_url = (
            os.getenv("AGENTIC_RAG_EMBED_BASE_URL")
            or os.getenv("LIGHTRAG_EMBED_BASE_URL")
            or os.getenv("LIGHTRAG_BASE_URL")
            or llm_base_url
        )
        embed_api_key = (
            os.getenv("AGENTIC_RAG_EMBED_API_KEY")
            or os.getenv("LIGHTRAG_EMBED_API_KEY")
            or os.getenv("LIGHTRAG_API_KEY")
            or llm_api_key
        )

        action_base_url = (
            os.getenv("AGENTIC_RAG_ACTION_BASE_URL")
            or os.getenv("ACTION_LLM_BASE_URL")
            or llm_base_url
        )
        action_api_key = (
            os.getenv("AGENTIC_RAG_ACTION_API_KEY")
            or os.getenv("ACTION_LLM_API_KEY")
            or llm_api_key
        )

        # 图适配器类型
        graph_adapter_type = (
            os.getenv("AGENTIC_RAG_GRAPH_ADAPTER")
            or os.getenv("GRAPH_ADAPTER_TYPE")
            or "lightrag"
        )

        # Freebase配置
        freebase_entity_api_url = (
            os.getenv("FREEBASE_ENTITY_API_URL")
            or "http://localhost:8000"
        )
        freebase_sparql_api_url = (
            os.getenv("FREEBASE_SPARQL_API_URL")
            or "http://localhost:8890"
        )
        freebase_entity_api_key = os.getenv("FREEBASE_ENTITY_API_KEY")
        freebase_sparql_api_key = os.getenv("FREEBASE_SPARQL_API_KEY")

        return cls(
            llm_model=os.getenv("AGENTIC_RAG_LLM_MODEL") or os.getenv("LIGHTRAG_LLM_MODEL", "gpt-4o-mini"),
            llm_base_url=llm_base_url,
            llm_api_key=llm_api_key,
            embed_model=os.getenv("AGENTIC_RAG_EMBED_MODEL") or os.getenv("LIGHTRAG_EMBED_MODEL", "text-embedding-3-small"),
            embed_dim=int(os.getenv("AGENTIC_RAG_EMBED_DIM") or os.getenv("LIGHTRAG_EMBED_DIM", "1536")),
            embed_base_url=embed_base_url,
            embed_api_key=embed_api_key,
            action_model=os.getenv("AGENTIC_RAG_ACTION_MODEL") or os.getenv("ACTION_LLM_MODEL") or os.getenv("LIGHTRAG_LLM_MODEL", "gpt-4o-mini"),
            action_base_url=action_base_url,
            action_api_key=action_api_key,
            graph_adapter_type=graph_adapter_type,
            freebase_entity_api_url=freebase_entity_api_url,
            freebase_sparql_api_url=freebase_sparql_api_url,
            freebase_entity_api_key=freebase_entity_api_key,
            freebase_sparql_api_key=freebase_sparql_api_key,
            env_source=env_source,
        )

    def validate(self) -> list[str]:
        """验证配置合法性，返回错误信息列表"""
        errors = []
        if not self.has_provider_credentials:
            errors.append("缺少LLM API配置 (llm_api_key)")
        if self.graph_adapter_type not in ("lightrag", "freebase"):
            errors.append(f"无效的graph_adapter_type: {self.graph_adapter_type}")
        return errors

    @property
    def has_provider_credentials(self) -> bool:
        return bool(self.llm_api_key)

    @property
    def has_action_credentials(self) -> bool:
        return bool(self.action_api_key)
