from __future__ import annotations

from collections import defaultdict
import re

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
        search_queries = self._build_search_queries(question)

        # 多查询合并，降低长问句直接检索带来的歧义
        merged_entities: list[dict[str, object]] = []
        seen_primary_refs: set[str] = set()

        each_query_top_k = max(1, min(top_k, 6))
        for query in search_queries:
            query_entities = await self._adapter.search_entities(query, top_k=each_query_top_k)
            for entity in query_entities:
                entity_refs = entity.get("freebase_ids") or []
                primary_ref = str(entity_refs[0]).strip() if entity_refs else ""
                if not primary_ref or primary_ref in seen_primary_refs:
                    continue
                seen_primary_refs.add(primary_ref)
                merged_entities.append(entity)
                if len(merged_entities) >= top_k:
                    break
            if len(merged_entities) >= top_k:
                break

        entities = merged_entities

        for entity in entities:
            entity_name = str(entity.get("name", "")).strip()
            if not entity_name:
                continue

            entity_refs = entity.get("freebase_ids") or []
            if not entity_refs:
                continue

            # 同名实体可能对应多个 MID，扩展前若干个可降低首MID误命中风险
            for ref in entity_refs[:2]:
                primary_ref = str(ref).strip()
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
            # 过滤掉看起来像关系名的关键词（包含 '.' 但不是有效的 Freebase MID）
            # 关系名格式如 "book.book.editions"，不能用于实体扩展
            valid_keywords = [
                k.strip()
                for k in ll_keywords
                if k.strip()
                and not ("." in k and not k.startswith("m."))
                and not k.strip().isdigit()
            ]
            for keyword in valid_keywords:
                for edge in await self._adapter.expand_edges(keyword, direction="forward", max_edges=8):
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
                "search_queries": search_queries,
            },
            raw_data={
                "entities": entities,
            },
        )

    def _build_search_queries(self, question: str) -> list[str]:
        """从问题构建多条实体检索查询。

        目标：
        1. 保留原始问题检索；
        2. 额外抽取主体实体短语，缓解长问句检索歧义；
        3. 对常见问句模板做轻量短语拆分。
        """
        normalized = (question or "").strip()
        if not normalized:
            return []

        queries: list[str] = [normalized]
        lowered = normalized.lower().strip(" ?")

        template_patterns = [
            re.compile(r"who did (.+?) play in (.+)$", flags=re.IGNORECASE),
            re.compile(r"who influenced (.+)$", flags=re.IGNORECASE),
            re.compile(r"who was (.+?) mom$", flags=re.IGNORECASE),
            re.compile(r"who is (.+?) mom$", flags=re.IGNORECASE),
        ]

        for pattern in template_patterns:
            matched = pattern.match(lowered)
            if not matched:
                continue
            for group in matched.groups():
                candidate = group.strip(" ?")
                if candidate and candidate not in queries:
                    queries.append(candidate)

        # 通用短语抽取：挑选长度较长的连续词片段
        tokens = [token for token in re.findall(r"[a-zA-Z0-9']+", lowered) if token]
        stopwords = {
            "who", "what", "when", "where", "why", "how",
            "did", "does", "is", "was", "were", "the", "a", "an",
            "in", "on", "of", "to", "for", "and", "or", "with",
        }
        content_tokens = [token for token in tokens if token not in stopwords]
        if len(content_tokens) >= 2:
            chunk = " ".join(content_tokens[:4]).strip()
            if chunk and chunk not in queries:
                queries.append(chunk)

        return queries[:4]

    async def answer(self, question: str, *, mode: str = "hybrid") -> str:
        """调用 Freebase 适配器问答兜底接口。"""
        return await self._adapter.answer_question(question, mode=mode)

    async def resolve_mid_names(self, mids: list[str]) -> dict[str, str]:
        """解析 MID 到可读名称。"""
        return await self._adapter.resolve_mid_names(mids)


def create_freebase_graph_provider_from_env(
    *,
    search_timeout: float = 60.0,
    sparql_timeout: float = 120.0,
) -> FreebaseGraphProvider:
    """从环境配置创建 Freebase Provider。

    Args:
        search_timeout: 实体搜索超时时间（秒），默认 60 秒
        sparql_timeout: SPARQL 查询超时时间（秒），默认 120 秒

    Returns:
        FreebaseGraphProvider 实例。
    """
    api = CoreAPIConfig.from_env()
    adapter = FreebaseAdapter(
        entity_search_url=api.freebase_entity_api_url,
        sparql_url=api.freebase_sparql_api_url,
        search_timeout=search_timeout,
        sparql_timeout=sparql_timeout,
    )
    return FreebaseGraphProvider(adapter=adapter)
