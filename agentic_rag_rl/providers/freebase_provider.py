from __future__ import annotations

from collections import defaultdict

from third_party_integration.freebase_integration import FreebaseAdapter

from ..config import CoreAPIConfig
from ..contracts import CandidateEdge, SeedSnapshot
from .base import GraphProvider


class FreebaseGraphProvider(GraphProvider):
    """Freebase 图数据 Provider。

    负责将 Freebase Integration 适配器输出转换为统一 SeedSnapshot，
    并向 Env 暴露一致的 get_snapshot/answer 接口。
    """

    def __init__(self, adapter: FreebaseAdapter) -> None:
        """初始化 Freebase Provider。

        Args:
            adapter: Freebase 集成适配器实例。
        """
        self._adapter = adapter

    async def initialize(self) -> None:
        """初始化底层适配器资源。"""
        await self._adapter.initialize()

    async def finalize(self) -> None:
        """释放底层适配器资源。"""
        await self._adapter.finalize()

    async def insert_texts(self, texts: list[str]) -> None:
        """Freebase 外部图源不支持写入文本，保留空实现以兼容统一接口。"""
        _ = texts

    async def get_snapshot(
        self,
        question: str,
        *,
        top_k: int,
        hl_keywords: list[str] | None = None,
        ll_keywords: list[str] | None = None,
    ) -> SeedSnapshot:
        """基于问题与关键词构建统一图快照。

        Args:
            question: 用户问题。
            top_k: 实体召回数。
            hl_keywords: 预留高层关键词（当前不直接使用）。
            ll_keywords: 低层关键词，用于驱动后续实体扩展。

        Returns:
            标准化 SeedSnapshot。
        """
        entity_edges: dict[str, list[CandidateEdge]] = defaultdict(list)
        entities = await self._adapter.search_entities(question, top_k=top_k)

        for entity in entities:
            entity_name = str(entity.get("name", "")).strip()
            if not entity_name:
                continue

            entity_refs = entity.get("freebase_ids") or []
            if not entity_refs:
                continue

            primary_ref = str(entity_refs[0]).strip()
            if not primary_ref:
                continue

            expanded = await self._adapter.expand_edges(
                primary_ref,
                direction="forward",
                max_edges=min(top_k, 20),
            )
            if expanded:
                entity_edges[entity_name].extend(expanded)

        if ll_keywords:
            for keyword in ll_keywords:
                normalized = str(keyword).strip()
                if not normalized:
                    continue
                for edge in await self._adapter.expand_edges(normalized, direction="forward", max_edges=8):
                    if edge.src_name:
                        entity_edges[edge.src_name].append(edge)

        return SeedSnapshot(
            question=question,
            keywords={
                "high_level": hl_keywords or [],
                "low_level": ll_keywords or [],
            },
            entity_edges=dict(entity_edges),
            processing_info={
                "source": "freebase",
                "entities_count": len(entities),
            },
            raw_data={
                "entities": entities,
            },
        )

    async def answer(self, question: str, *, mode: str = "hybrid") -> str:
        """调用 Freebase 适配器问答兜底接口。"""
        return await self._adapter.answer_question(question, mode=mode)


def create_freebase_graph_provider_from_env() -> FreebaseGraphProvider:
    """从环境配置创建 Freebase Provider。

    Returns:
        FreebaseGraphProvider 实例。
    """
    api = CoreAPIConfig.from_env()
    adapter = FreebaseAdapter(
        entity_search_url=api.freebase_entity_api_url,
        sparql_url=api.freebase_sparql_api_url,
    )
    return FreebaseGraphProvider(adapter=adapter)
