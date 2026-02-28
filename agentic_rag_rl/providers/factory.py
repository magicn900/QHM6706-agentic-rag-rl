"""Provider 工厂模块

根据配置选择并创建对应的 GraphProvider 实现。

支持的 provider 类型：
- lightrag: LightRAG 图数据库
- freebase: Freebase 外部 HTTP 服务（待实现）

职责：
- 读取配置中的 graph_adapter_type
- 工厂方法不涉及具体 HTTP 调用细节
"""
from __future__ import annotations

from pathlib import Path

from ..config import CoreAPIConfig
from .base import GraphProvider
from .freebase_provider import FreebaseGraphProvider, create_freebase_graph_provider_from_env
from .lightrag_provider import LightRAGGraphProvider, create_lightrag_graph_provider_from_env


class ProviderFactoryError(Exception):
    """Provider 工厂异常"""
    pass


class UnsupportedProviderError(ProviderFactoryError):
    """不支持的 provider 类型"""
    pass


class ProviderInitError(ProviderFactoryError):
    """Provider 初始化异常"""
    pass


def create_graph_provider_from_env(
    *,
    working_dir: str | Path | None = None,
    use_mock: bool = False,
    default_mode: str = "hybrid",
) -> GraphProvider:
    """根据环境变量创建对应的 GraphProvider
    
    读取配置中的 graph_adapter_type（默认 lightrag），
    并实例化对应的 provider。
    
    Args:
        working_dir: 工作目录路径（部分 provider 需要）
        use_mock: 是否使用 mock 模式（用于测试）
        default_mode: 默认查询模式
    
    Returns:
        GraphProvider 实例
    
    Raises:
        UnsupportedProviderError: 不支持的 provider 类型
        ProviderInitError: Provider 初始化失败
    """
    config = CoreAPIConfig.from_env()
    provider_type = config.graph_adapter_type.lower()
    
    # 默认使用 lightrag
    if provider_type == "lightrag" or not provider_type:
        working_dir = working_dir or "./lightrag_working_dir"
        try:
            return create_lightrag_graph_provider_from_env(
                working_dir=str(working_dir),
                use_mock=use_mock,
                default_mode=default_mode,
            )
        except Exception as e:
            raise ProviderInitError(
                f"Failed to initialize LightRAG provider: {e}"
            ) from e
    
    elif provider_type == "freebase":
        try:
            return create_freebase_graph_provider_from_env()
        except Exception as e:
            raise ProviderInitError(
                f"Failed to initialize Freebase provider: {e}"
            ) from e
    
    else:
        raise UnsupportedProviderError(
            f"Unsupported graph_adapter_type: '{provider_type}'. "
            f"Supported: 'lightrag', 'freebase'"
        )


__all__ = [
    "GraphProvider",
    "create_graph_provider_from_env",
    "ProviderFactoryError",
    "UnsupportedProviderError",
    "ProviderInitError",
]