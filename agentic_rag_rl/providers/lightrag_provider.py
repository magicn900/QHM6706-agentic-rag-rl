from __future__ import annotations

from collections import defaultdict

from third_party_integration.lightrag_integration import (
    LightRAGAdapterConfig,
    LightRAGIntegrationAdapter,
    create_lightrag_adapter,
)

from ..config import CoreAPIConfig
from ..contracts import CandidateEdge, SeedSnapshot
from .base import GraphProvider


class LightRAGGraphProvider(GraphProvider):
    def __init__(self, adapter: LightRAGIntegrationAdapter, *, default_mode: str = "hybrid") -> None:
        self._adapter = adapter
        self._default_mode = default_mode

    async def initialize(self) -> None:
        await self._adapter.initialize()

    async def finalize(self) -> None:
        await self._adapter.finalize()

    async def insert_texts(self, texts: list[str]) -> None:
        for text in texts:
            normalized = text.strip()
            if normalized:
                await self._adapter.insert(normalized)

    async def get_snapshot(
        self,
        question: str,
        *,
        top_k: int,
        hl_keywords: list[str] | None = None,
        ll_keywords: list[str] | None = None,
    ) -> SeedSnapshot:
        response = await self._adapter.query_graph_seed(
            question,
            mode=self._default_mode,
            top_k=top_k,
            hl_keywords=hl_keywords,
            ll_keywords=ll_keywords,
        )
        data = response.get("data", {}) if isinstance(response, dict) else {}

        entity_edges: dict[str, list[CandidateEdge]] = defaultdict(list)
        for entity_candidate in data.get("entity_relation_candidates", []):
            entity_name = str(entity_candidate.get("entity_name", "")).strip()
            if not entity_name:
                continue
            for edge in entity_candidate.get("candidate_edges", []):
                relation = self._extract_relation_name(edge)
                # 确定边的方向和端点
                direction = str(edge.get("direction", "unknown"))
                if direction == "forward":
                    src_name = entity_name
                    tgt_name = edge.get("next_entity", entity_name)
                else:
                    src_name = edge.get("next_entity", entity_name)
                    tgt_name = entity_name

                entity_edges[entity_name].append(
                    CandidateEdge(
                        edge_id=str(edge.get("edge_id", "")),
                        src_name=src_name,
                        relation=relation,
                        tgt_name=tgt_name,
                        direction=direction,
                        description=str(edge.get("description", "")),
                        keywords=str(edge.get("keywords", "")),
                        weight=float(edge.get("weight", 1.0)),
                        # 内部引用（LightRAG 可选填）
                        internal_src_ref=edge.get("src_id"),
                        internal_tgt_ref=edge.get("tgt_id"),
                    )
                )

        return SeedSnapshot(
            question=question,
            keywords=data.get("keywords", {"high_level": [], "low_level": []}),
            entity_edges=dict(entity_edges),
            processing_info=data.get("processing_info", {}),
            raw_data=data,
        )

    async def answer(self, question: str, *, mode: str = "hybrid") -> str:
        return await self._adapter.query(question, mode=mode)

    @staticmethod
    def _extract_relation_name(edge: dict) -> str:
        raw_keywords = str(edge.get("keywords", "")).strip()
        if raw_keywords:
            parts = [part.strip() for part in raw_keywords.replace(";", ",").split(",") if part.strip()]
            if parts:
                return parts[0]

        edge_id = str(edge.get("edge_id", "")).strip()
        if edge_id:
            return edge_id

        src_id = str(edge.get("src_id", "")).strip()
        tgt_id = str(edge.get("tgt_id", "")).strip()
        fallback = f"{src_id}->{tgt_id}".strip("->")
        return fallback or "unknown_relation"


def create_lightrag_graph_provider_from_env(
    *,
    working_dir: str,
    use_mock: bool | None = None,
    default_mode: str = "hybrid",
) -> LightRAGGraphProvider:
    api = CoreAPIConfig.from_env()
    config = LightRAGAdapterConfig(
        working_dir=working_dir,
        use_mock=False if use_mock is None else use_mock,
        llm_model=api.llm_model,
        embedding_model=api.embed_model,
        embedding_dim=api.embed_dim,
        llm_base_url=api.llm_base_url,
        llm_api_key=api.llm_api_key,
        embedding_base_url=api.embed_base_url,
        embedding_api_key=api.embed_api_key,
    )
    adapter = create_lightrag_adapter(config)
    return LightRAGGraphProvider(adapter=adapter, default_mode=default_mode)
