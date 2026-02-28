"""Freebase Integration 模块

提供与 Freebase 知识图谱的集成适配。
支持实体搜索、SPARQL查询、噪音过滤和MID映射。

使用方式:
    from third_party_integration.freebase_integration import FreebaseAdapter
    
    adapter = FreebaseAdapter(
        entity_search_url="http://localhost:8000/search",
        sparql_url="http://localhost:8890/sparql"
    )
    await adapter.initialize()
"""

from .adapters.freebase_adapter import FreebaseAdapter, create_freebase_adapter
from .clients.entity_search_client import EntitySearchClient
from .clients.sparql_client import SPARQLClient
from .utils.mid_mapper import MidMapper
from .utils.noise_filter import NoiseFilter

__all__ = [
    "FreebaseAdapter",
    "create_freebase_adapter",
    "EntitySearchClient",
    "SPARQLClient",
    "MidMapper",
    "NoiseFilter",
]