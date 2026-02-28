"""Freebase 实体搜索客户端

封装对 Freebase 实体向量召回服务的 HTTP 调用。
服务地址: POST /search
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import aiohttp

logger = logging.getLogger(__name__)


@dataclass
class EntitySearchResult:
    """实体搜索结果"""
    name: str
    freebase_ids: list[str]


class EntitySearchClient:
    """Freebase 实体搜索客户端
    
    用于通过向量相似度搜索 Freebase 实体。
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        timeout: float = 30.0,
        max_retries: int = 3,
    ):
        """初始化搜索客户端
        
        Args:
            base_url: 服务基础地址
            timeout: 请求超时时间（秒）
            max_retries: 最大重试次数
        """
        self._base_url = base_url.rstrip("/")
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._max_retries = max_retries

    async def search(
        self,
        query: str,
        top_k: int = 5,
    ) -> list[EntitySearchResult]:
        """搜索实体
        
        Args:
            query: 搜索查询词
            top_k: 返回结果数量
            
        Returns:
            实体搜索结果列表
        """
        if not query or not query.strip():
            logger.warning("Empty query received, returning empty results")
            return []

        url = f"{self._base_url}/search"
        payload = {
            "query": query.strip(),
            "top_k": top_k,
        }

        last_error: Exception | None = None
        for attempt in range(self._max_retries):
            try:
                async with aiohttp.ClientSession(timeout=self._timeout) as session:
                    async with session.post(url, json=payload) as response:
                        if response.status != 200:
                            logger.warning(
                                f"Search request failed with status {response.status}, "
                                f"attempt {attempt + 1}/{self._max_retries}"
                            )
                            last_error = ValueError(f"HTTP {response.status}")
                            continue

                        data = await response.json()
                        results = self._parse_response(data)
                        logger.debug(
                            f"Search '{query}' returned {len(results)} results"
                        )
                        return results

            except aiohttp.ClientError as e:
                logger.warning(
                    f"Network error during search (attempt {attempt + 1}/{self._max_retries}): {e}"
                )
                last_error = e
            except Exception as e:
                logger.error(f"Unexpected error during search: {e}")
                last_error = e
                break

        # 所有重试都失败
        logger.error(
            f"Search failed after {self._max_retries} attempts for query '{query}': {last_error}"
        )
        return []

    def _parse_response(self, data: dict[str, Any]) -> list[EntitySearchResult]:
        """解析响应数据
        
        Args:
            data: 原始响应数据
            
        Returns:
            实体结果列表
        """
        results: list[EntitySearchResult] = []
        
        raw_results = data.get("results", [])
        if not isinstance(raw_results, list):
            logger.warning(f"Unexpected results format: {type(raw_results)}")
            return results

        for item in raw_results:
            if not isinstance(item, dict):
                continue
                
            name = item.get("name", "")
            freebase_ids = item.get("freebase_ids", [])
            
            if not name:
                continue
                
            if isinstance(freebase_ids, str):
                freebase_ids = [freebase_ids]
            elif not isinstance(freebase_ids, list):
                freebase_ids = []

            results.append(EntitySearchResult(
                name=name,
                freebase_ids=freebase_ids,
            ))

        return results