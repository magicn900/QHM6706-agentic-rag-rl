"""Freebase SPARQL 查询客户端

封装对 Freebase SPARQL 端点的 HTTP 调用。
服务地址: GET /sparql?query=...&format=...
"""
from __future__ import annotations

import logging
from typing import Any

import aiohttp

logger = logging.getLogger(__name__)


class SPARQLClient:
    """Freebase SPARQL 查询客户端
    
    用于执行 SPARQL 查询获取图谱中的实体和关系信息。
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8890",
        timeout: float = 30.0,
        max_retries: int = 3,
    ):
        """初始化 SPARQL 客户端
        
        Args:
            base_url: 服务基础地址
            timeout: 请求超时时间（秒）
            max_retries: 最大重试次数
        """
        self._base_url = base_url.rstrip("/")
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._max_retries = max_retries

    async def query(self, sparql: str) -> dict[str, Any]:
        """执行 SPARQL 查询
        
        Args:
            sparql: SPARQL 查询字符串
            
        Returns:
            解析后的 JSON 响应结果
        """
        if not sparql or not sparql.strip():
            logger.warning("Empty SPARQL query received")
            return {"results": {"bindings": []}}

        url = f"{self._base_url}/sparql"
        params = {
            "query": sparql.strip(),
            "format": "application/sparql-results+json",
        }

        last_error: Exception | None = None
        for attempt in range(self._max_retries):
            try:
                async with aiohttp.ClientSession(timeout=self._timeout) as session:
                    async with session.get(url, params=params) as response:
                        if response.status != 200:
                            logger.warning(
                                f"SPARQL request failed with status {response.status}, "
                                f"attempt {attempt + 1}/{self._max_retries}"
                            )
                            last_error = ValueError(f"HTTP {response.status}")
                            continue

                        data = await response.json()
                        logger.debug(f"SPARQL query executed successfully")
                        return data

            except aiohttp.ClientError as e:
                logger.warning(
                    f"Network error during SPARQL query (attempt {attempt + 1}/{self._max_retries}): {e}"
                )
                last_error = e
            except Exception as e:
                logger.error(f"Unexpected error during SPARQL query: {e}")
                last_error = e
                break

        # 所有重试都失败
        logger.error(
            f"SPARQL query failed after {self._max_retries} attempts: {last_error}"
        )
        return {"results": {"bindings": []}}

    async def expand_edges(
        self,
        mid: str,
        direction: str = "forward",
        max_edges: int = 10,
    ) -> list[dict[str, Any]]:
        """扩展实体边
        
        根据实体 MID 获取关联的边（关系）信息。
        
        Args:
            mid: Freebase 实体 MID
            direction: 扩展方向 "forward" | "backward" | "both"
            max_edges: 最大边数
            
        Returns:
            边信息列表
        """
        if not mid:
            return []

        # 构建 SPARQL 查询
        if direction == "forward":
            # 查询从该实体出发的边
            sparql = f"""
            PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
            PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
            SELECT DISTINCT ?relation ?target ?targetName
            WHERE {{
                <{mid}> ?relation ?target .
                OPTIONAL {{ ?target rdfs:label ?targetName }}
            }}
            LIMIT {max_edges}
            """
        elif direction == "backward":
            # 查询指向该实体的边
            sparql = f"""
            PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
            PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
            SELECT DISTINCT ?relation ?source ?sourceName
            WHERE {{
                ?source ?relation <{mid}> .
                OPTIONAL {{ ?source rdfs:label ?sourceName }}
            }}
            LIMIT {max_edges}
            """
        else:  # both
            # 查询双向边
            sparql = f"""
            PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
            PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
            SELECT DISTINCT ?relation ?target ?targetName ?source ?sourceName ?dir
            WHERE {{
                {{
                    <{mid}> ?relation ?target .
                    OPTIONAL {{ ?target rdfs:label ?targetName }}
                    BIND("forward" AS ?dir)
                }}
                UNION
                {{
                    ?source ?relation <{mid}> .
                    OPTIONAL {{ ?source rdfs:label ?sourceName }}
                    BIND("backward" AS ?dir)
                }}
            }}
            LIMIT {max_edges * 2}
            """

        result = await self.query(sparql)
        return self._parse_edges(result, direction)

    def _parse_edges(
        self,
        result: dict[str, Any],
        direction: str,
    ) -> list[dict[str, Any]]:
        """解析 SPARQL 结果为边列表
        
        Args:
            result: SPARQL 查询结果
            direction: 扩展方向
            
        Returns:
            边信息列表
        """
        edges: list[dict[str, Any]] = []
        
        try:
            bindings = result.get("results", {}).get("bindings", [])
        except Exception:
            logger.warning("Failed to parse SPARQL results")
            return edges

        for binding in bindings:
            try:
                # 提取关系
                relation_uri = binding.get("relation", {}).get("value", "")
                relation = self._extract_relation_name(relation_uri)
                if not relation:
                    continue

                if direction == "forward":
                    target_uri = binding.get("target", {}).get("value", "")
                    target_name = binding.get("targetName", {}).get("value", "")
                    # 如果没有 label，使用 MID
                    if not target_name:
                        target_name = self._extract_mid(target_uri)
                    
                    if target_uri:
                        edges.append({
                            "relation": relation,
                            "target": target_uri,
                            "target_name": target_name,
                        })
                        
                elif direction == "backward":
                    source_uri = binding.get("source", {}).get("value", "")
                    source_name = binding.get("sourceName", {}).get("value", "")
                    if not source_name:
                        source_name = self._extract_mid(source_uri)
                    
                    if source_uri:
                        edges.append({
                            "relation": relation,
                            "source": source_uri,
                            "source_name": source_name,
                        })
                else:  # both
                    direction_val = binding.get("dir", {}).get("value", "forward")
                    if direction_val == "forward":
                        target_uri = binding.get("target", {}).get("value", "")
                        target_name = binding.get("targetName", {}).get("value", "")
                        if not target_name:
                            target_name = self._extract_mid(target_uri)
                        if target_uri:
                            edges.append({
                                "relation": relation,
                                "target": target_uri,
                                "target_name": target_name,
                            })
                    else:
                        source_uri = binding.get("source", {}).get("value", "")
                        source_name = binding.get("sourceName", {}).get("value", "")
                        if not source_name:
                            source_name = self._extract_mid(source_uri)
                        if source_uri:
                            edges.append({
                                "relation": relation,
                                "source": source_uri,
                                "source_name": source_name,
                            })

            except Exception as e:
                logger.debug(f"Failed to parse edge binding: {e}")
                continue

        return edges

    def _extract_relation_name(self, uri: str) -> str:
        """从 URI 提取关系名
        
        Args:
            uri: 关系 URI
            
        Returns:
            关系名（不含前缀）
        """
        if not uri:
            return ""
        
        # Freebase 关系格式: http://rdf.freebase.com/ns/type.object.type
        # 或: http://www.w3.org/1999/02/22-rdf-syntax-ns#type
        if "#" in uri:
            return uri.split("#")[-1]
        
        if "/ns/" in uri:
            return uri.split("/ns/")[-1]
        
        return uri

    def _extract_mid(self, uri: str) -> str:
        """从 URI 提取 MID
        
        Args:
            uri: 实体 URI
            
        Returns:
            Freebase MID (如 m.xxx)
        """
        if not uri:
            return ""
        
        # Freebase MID 格式: http://rdf.freebase.com/ns/m.06n7_
        if "/ns/m." in uri:
            mid = uri.split("/ns/")[-1]
            # 移除最后的点号
            return mid.rstrip(".")
        
        return uri