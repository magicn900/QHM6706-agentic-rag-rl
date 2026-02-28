"""图适配器协议定义

定义 Provider 与 Integration 层之间的统一接口契约。
该协议屏蔽底层图源差异（如LightRAG vs Freebase），实现多图源可插拔。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from .types import CandidateEdge, SeedSnapshot


class GraphAdapterProtocol(ABC):
    """图适配器协议 - Integration层实现该协议以对接不同图源"""

    @abstractmethod
    async def initialize(self) -> None:
        """初始化图适配器（如建立连接、加载配置等）"""
        raise NotImplementedError

    @abstractmethod
    async def finalize(self) -> None:
        """清理资源（如关闭连接等）"""
        raise NotImplementedError

    @abstractmethod
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
        raise NotImplementedError

    @abstractmethod
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
        raise NotImplementedError

    @abstractmethod
    async def answer_question(
        self,
        question: str,
        *,
        mode: str = "hybrid",
    ) -> str:
        """基于图知识回答问题

        Args:
            question: 用户问题
            mode: 检索模式 "local" | "global" | "hybrid"

        Returns:
            答案文本
        """
        raise NotImplementedError


# ========== 辅助类型 ==========

class AdapterMetadata:
    """适配器元信息"""
    name: str
    adapter_type: str  # "lightrag" | "freebase"
    version: str
    capabilities: list[str]

    def __init__(
        self,
        name: str,
        adapter_type: str,
        version: str = "1.0.0",
        capabilities: list[str] | None = None,
    ):
        self.name = name
        self.adapter_type = adapter_type
        self.version = version
        self.capabilities = capabilities or []