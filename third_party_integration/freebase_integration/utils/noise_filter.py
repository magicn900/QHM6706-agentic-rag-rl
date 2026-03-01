"""Freebase 噪音关系过滤器

过滤 Freebase 中的系统级噪音关系，如 type.object.*, kg.*, common.* 等。
这些关系对推理无实际价值，应从候选边中移除。
"""
from __future__ import annotations

import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)

# 默认黑名单前缀 - 只过滤真正的系统级噪音，保留业务关系
# 注意：不要过滤 book. location. 等业务前缀，否则会丢失关键关系
DEFAULT_BLACKLIST_PREFIXES = (
    "type.object",    # 系统元数据关系，必须过滤
    "type.content",   # 内容存储元数据（blob/length/media_type），对推理无价值
    "type.type.",     # 类型元关系
    "common.image.",  # 图片尺寸/画廊等多媒体元数据
    "common.resource.",  # 资源标注等非语义主干关系
    "common.topic.",  # 通用topic元关系（notable_types/article/description等）
    "kg.",            # 图谱系统关系
    "freebase.",      # Freebase 内部表示关系
    "base.kwebbase.", # WebBase 爬虫数据，质量差
    "user.",          # 用户自定义关系，质量参差不齐
)

# 默认黑名单关系名（精确匹配）
DEFAULT_BLACKLIST_RELATIONS = (
    "type",
    "id",
    "timestamp",
    "creator",
    "contributor",
    "description",
    "alias",
    "link",
    "key",
)


class NoiseFilter:
    """Freebase 噪音关系过滤器
    
    根据预设规则过滤无意义的系统关系。
    """

    def __init__(
        self,
        blacklist_prefixes: tuple[str, ...] | None = None,
        blacklist_relations: tuple[str, ...] | None = None,
        custom_filter_func: Callable[[str], bool] | None = None,
    ):
        """初始化噪音过滤器
        
        Args:
            blacklist_prefixes: 需过滤的关系前缀元组
            blacklist_relations: 需精确过滤的关系名元组
            custom_filter_func: 自定义过滤函数，输入关系名，返回是否过滤
        """
        self._blacklist_prefixes = blacklist_prefixes or DEFAULT_BLACKLIST_PREFIXES
        self._blacklist_relations = blacklist_relations or DEFAULT_BLACKLIST_RELATIONS
        self._custom_filter = custom_filter_func

    def is_noisy(self, relation: str) -> bool:
        """判断关系是否为噪音
        
        Args:
            relation: 关系名
            
        Returns:
            True 表示应过滤，False 表示保留
        """
        if not relation:
            return True

        # 检查前缀黑名单
        for prefix in self._blacklist_prefixes:
            if relation.startswith(prefix):
                logger.debug(f"Filtered relation by prefix: {relation}")
                return True

        # 检查精确匹配黑名单
        if relation in self._blacklist_relations:
            logger.debug(f"Filtered relation by exact match: {relation}")
            return True

        # 检查自定义过滤函数
        if self._custom_filter and self._custom_filter(relation):
            logger.debug(f"Filtered relation by custom filter: {relation}")
            return True

        return False

    def filter_relations(self, relations: list[str]) -> list[str]:
        """过滤关系列表
        
        Args:
            relations: 关系名列表
            
        Returns:
            过滤后的关系列表
        """
        return [r for r in relations if not self.is_noisy(r)]

    def filter_edges(self, edges: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """过滤边列表中的噪音关系
        
        Args:
            edges: 边列表，每项应包含 "relation" 字段
            
        Returns:
            过滤后的边列表
        """
        filtered = []
        for edge in edges:
            relation = edge.get("relation", "")
            if not self.is_noisy(relation):
                filtered.append(edge)
            else:
                logger.debug(f"Filtered edge: {relation}")
        return filtered

    def filter_candidate_edges(
        self,
        candidate_edges: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """过滤候选边（适配 Agentic RAG 格式）
        
        Args:
            candidate_edges: 候选边列表
            
        Returns:
            过滤后的候选边列表
        """
        return self.filter_edges(candidate_edges)


# ========== 便捷函数 ==========

def create_default_filter() -> NoiseFilter:
    """创建默认噪音过滤器
    
    Returns:
        使用默认规则配置的过滤器
    """
    return NoiseFilter()


def filter_noisy_relations(relations: list[str]) -> list[str]:
    """过滤噪音关系（便捷函数）
    
    Args:
        relations: 关系名列表
        
    Returns:
        过滤后的关系列表
    """
    return create_default_filter().filter_relations(relations)


# ========== 单元测试 ==========

if __name__ == "__main__":
    # 简单自测
    test_relations = [
        "type.object.type",
        "kg.index",
        "common.topic",
        "film.film",
        "people.person",
        "location.location",
        "known_for",  # 有意义的关系，应保留
        "creator",  # 噪音，应过滤
    ]
    
    filter_obj = create_default_filter()
    
    print("=== Noise Filter Test ===")
    for rel in test_relations:
        result = "FILTER" if filter_obj.is_noisy(rel) else "KEEP"
        print(f"  {rel}: {result}")
    
    filtered = filter_obj.filter_relations(test_relations)
    print(f"\nFiltered result: {filtered}")
    
    # 测试边过滤
    test_edges = [
        {"relation": "type.object.type", "target": "A"},
        {"relation": "known_for", "target": "B"},
        {"relation": "creator", "target": "C"},
    ]
    filtered_edges = filter_obj.filter_edges(test_edges)
    print(f"\nFiltered edges: {len(filtered_edges)}/{len(test_edges)}")
    for e in filtered_edges:
        print(f"  - {e}")