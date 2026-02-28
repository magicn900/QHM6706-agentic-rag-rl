"""Freebase 图适配器

实现 GraphAdapterProtocol，将 search + sparql + filter + mapper 串成统一接口。
输出 CandidateEdge（display 字段无 MID），异常情况下返回空候选不崩溃。
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

from agentic_rag_rl.contracts.graph_adapter import GraphAdapterProtocol
from agentic_rag_rl.contracts.types import CandidateEdge

from ..clients.entity_search_client import EntitySearchClient
from ..clients.sparql_client import SPARQLClient
from ..utils.mid_mapper import MidMapper
from ..utils.noise_filter import NoiseFilter

logger = logging.getLogger(__name__)


class FreebaseAdapter(GraphAdapterProtocol):
    """Freebase 图适配器
    
    整合实体搜索、SPARQL查询、噪音过滤和MID映射，
    实现统一的图查询接口。
    """

    def __init__(
        self,
        *,
        entity_search_url: str = "http://localhost:8000",
        sparql_url: str = "http://localhost:8890",
        search_timeout: float = 30.0,
        sparql_timeout: float = 30.0,
        max_retries: int = 3,
        max_edges_per_entity: int = 10,
    ):
        """初始化 Freebase 适配器
        
        Args:
            entity_search_url: 实体搜索服务地址
            sparql_url: SPARQL 端点地址
            search_timeout: 搜索超时时间
            sparql_timeout: SPARQL 超时时间
            max_retries: 最大重试次数
            max_edges_per_entity: 每个实体最大边数
        """
        self._entity_client = EntitySearchClient(
            base_url=entity_search_url,
            timeout=search_timeout,
            max_retries=max_retries,
        )
        self._sparql_client = SPARQLClient(
            base_url=sparql_url,
            timeout=sparql_timeout,
            max_retries=max_retries,
        )
        self._mid_mapper = MidMapper()
        self._noise_filter = NoiseFilter()
        self._max_edges_per_entity = max_edges_per_entity
        self._initialized = False

    async def initialize(self) -> None:
        """初始化适配器"""
        logger.info("Initializing FreebaseAdapter")
        self._initialized = True
        logger.info("FreebaseAdapter initialized successfully")

    async def finalize(self) -> None:
        """清理资源"""
        logger.info("Finalizing FreebaseAdapter")
        # 清理映射器
        self._mid_mapper.clear()
        self._initialized = False
        logger.info("FreebaseAdapter finalized")

    async def search_entities(
        self,
        query: str,
        *,
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        """实体向量召回
        
        Args:
            query: 搜索查询词
            top_k: 返回结果数量
            
        Returns:
            实体列表，每项包含 name/freebase_ids 等字段
        """
        if not self._initialized:
            await self.initialize()

        try:
            results = await self._entity_client.search(query, top_k=top_k)
            
            # 转换为 dict 格式并收集 MID 映射
            entities = []
            for result in results:
                entities.append({
                    "name": result.name,
                    "freebase_ids": result.freebase_ids,
                })
                # 添加 MID 映射
                for mid in result.freebase_ids:
                    self._mid_mapper.add_mapping(mid, result.name)
            
            return entities
            
        except Exception as e:
            logger.error(f"Entity search failed for '{query}': {e}")
            return []

    async def expand_edges(
        self,
        entity_ref: str,
        *,
        direction: str = "forward",
        max_edges: int = 10,
    ) -> list[CandidateEdge]:
        """图扩展 - 根据实体获取关联边
        
        Args:
            entity_ref: 实体引用（内部ID或可读名称）
            direction: 扩展方向 "forward" | "backward" | "both"
            max_edges: 最大边数
            
        Returns:
            候选边列表
        """
        if not self._initialized:
            await self.initialize()

        if not entity_ref:
            return []

        # 确定使用的 MID
        mid = self._resolve_mid(entity_ref)
        if not mid:
            logger.warning(f"Could not resolve MID for entity_ref: {entity_ref}")
            return []

        try:
            # 执行 SPARQL 查询获取边
            raw_edges = await self._sparql_client.expand_edges(
                mid=mid,
                direction=direction,
                max_edges=max_edges,
            )
            
            # 过滤噪音关系
            filtered_edges = self._noise_filter.filter_edges(raw_edges)
            
            # 转换为 CandidateEdge
            candidate_edges = self._convert_to_candidate_edges(
                filtered_edges,
                entity_ref,
                mid,
                direction,
            )
            
            logger.debug(
                f"Expanded {len(candidate_edges)} edges for {entity_ref} "
                f"(direction={direction})"
            )
            return candidate_edges
            
        except Exception as e:
            logger.error(f"Edge expansion failed for '{entity_ref}': {e}")
            return []

    async def answer_question(
        self,
        question: str,
        *,
        mode: str = "hybrid",
    ) -> str:
        """基于图知识回答问题
        
        Args:
            question: 用户问题
            mode: 检索模式（当前 Freebase 忽略此参数）
            
        Returns:
            答案文本
        """
        if not self._initialized:
            await self.initialize()

        # Freebase 不直接支持问答，需要先检索实体和关系
        # 这里返回空串，由 Env/Policy 决定如何处理
        logger.debug(f"Answer question not fully implemented for Freebase: {question}")
        return ""

    def _resolve_mid(self, entity_ref: str) -> str | None:
        """解析实体引用为 MID
        
        Args:
            entity_ref: 实体引用（可能是 MID 或名称）
            
        Returns:
            MID 或 None
        """
        # 如果已经是 MID 格式
        if entity_ref.startswith("m."):
            return entity_ref
        
        # 尝试从映射器获取
        mids = self._mid_mapper.get_mids(entity_ref)
        if mids:
            return mids[0]
        
        return None

    def _convert_to_candidate_edges(
        self,
        raw_edges: list[dict[str, Any]],
        entity_ref: str,
        mid: str,
        direction: str,
    ) -> list[CandidateEdge]:
        """将原始边转换为 CandidateEdge
        
        Args:
            raw_edges: 原始边列表
            entity_ref: 当前实体引用
            mid: 当前实体 MID
            direction: 扩展方向
            
        Returns:
            CandidateEdge 列表
        """
        candidate_edges: list[CandidateEdge] = []
        entity_name = self._mid_mapper.get_name(mid) or entity_ref

        for edge in raw_edges:
            relation = edge.get("relation", "")
            if not relation:
                continue

            if direction == "forward":
                target_uri = edge.get("target", "")
                target_name = edge.get("target_name", "")
                
                # 提取目标 MID
                target_mid = self._extract_mid(target_uri)
                if target_mid:
                    self._mid_mapper.add_mapping(target_mid, target_name or target_mid)

                edge_id = str(uuid.uuid4())[:8]
                candidate_edges.append(CandidateEdge(
                    edge_id=edge_id,
                    src_name=entity_name,
                    relation=relation,
                    tgt_name=target_name or target_mid or "",
                    direction="forward",
                    internal_src_ref=mid,
                    internal_tgt_ref=target_mid,
                ))

            elif direction == "backward":
                source_uri = edge.get("source", "")
                source_name = edge.get("source_name", "")
                
                # 提取源 MID
                source_mid = self._extract_mid(source_uri)
                if source_mid:
                    self._mid_mapper.add_mapping(source_mid, source_name or source_mid)

                edge_id = str(uuid.uuid4())[:8]
                candidate_edges.append(CandidateEdge(
                    edge_id=edge_id,
                    src_name=source_name or source_mid or "",
                    relation=relation,
                    tgt_name=entity_name,
                    direction="backward",
                    internal_src_ref=source_mid,
                    internal_tgt_ref=mid,
                ))

        return candidate_edges

    def _extract_mid(self, uri: str) -> str | None:
        """从 URI 提取 MID
        
        Args:
            uri: 实体 URI
            
        Returns:
            MID 或 None
        """
        if not uri:
            return None
        
        # Freebase MID 格式: http://rdf.freebase.com/ns/m.06n7_
        if "/ns/m." in uri:
            mid = uri.split("/ns/")[-1]
            return mid.rstrip(".")
        
        return None


# ========== 便捷函数 ==========

async def create_freebase_adapter(
    entity_search_url: str = "http://localhost:8000",
    sparql_url: str = "http://localhost:8890",
) -> FreebaseAdapter:
    """创建并初始化 Freebase 适配器
    
    Args:
        entity_search_url: 实体搜索服务地址
        sparql_url: SPARQL 端点地址
        
    Returns:
        初始化后的 FreebaseAdapter 实例
    """
    adapter = FreebaseAdapter(
        entity_search_url=entity_search_url,
        sparql_url=sparql_url,
    )
    await adapter.initialize()
    return adapter


# ========== 单元测试 ==========

if __name__ == "__main__":
    import asyncio

    async def test_adapter():
        """测试 Freebase Adapter"""
        print("=== Freebase Adapter Test ===")
        
        # 创建适配器（使用测试服务地址）
        adapter = FreebaseAdapter(
            entity_search_url="http://localhost:8000",
            sparql_url="http://localhost:8890",
        )
        await adapter.initialize()
        
        # 测试实体搜索（无服务时会返回空）
        print("\n1. Testing entity search...")
        entities = await adapter.search_entities("Barack Obama", top_k=3)
        print(f"   Found {len(entities)} entities")
        for e in entities:
            print(f"   - {e}")
        
        # 测试边扩展
        print("\n2. Testing edge expansion...")
        if entities and entities[0].get("freebase_ids"):
            mid = entities[0]["freebase_ids"][0]
            edges = await adapter.expand_edges(mid, direction="forward", max_edges=5)
            print(f"   Expanded {len(edges)} edges")
            for e in edges[:3]:
                print(f"   - {e.to_display_text()}")
        
        await adapter.finalize()
        print("\nTest completed!")

    # 运行测试
    asyncio.run(test_adapter())