"""Freebase SPARQL 查询客户端

封装对 Freebase SPARQL 端点的 HTTP 调用。
服务地址: GET /sparql?query=...&format=...
"""
from __future__ import annotations

import logging
import re
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

        # Freebase RDF 使用完整 URI 格式: http://rdf.freebase.com/ns/m.xxxx
        fb_ns = "http://rdf.freebase.com/ns/"
        mid_uri = f"{fb_ns}{mid}"

        # 构建 SPARQL 查询
        if direction == "forward":
            # 查询从该实体出发的边
            sparql = f"""
            PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
            PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
            PREFIX ns: <http://rdf.freebase.com/ns/>
            SELECT DISTINCT ?relation ?target ?targetName
            WHERE {{
                <{mid_uri}> ?relation ?target .
                OPTIONAL {{
                    ?target ns:type.object.name ?targetNameFb .
                    FILTER(lang(?targetNameFb) = '' || langMatches(lang(?targetNameFb), 'en'))
                }}
                OPTIONAL {{
                    ?target rdfs:label ?targetNameRdfs .
                    FILTER(lang(?targetNameRdfs) = '' || langMatches(lang(?targetNameRdfs), 'en'))
                }}
                BIND(COALESCE(?targetNameFb, ?targetNameRdfs) AS ?targetName)
            }}
            LIMIT {max_edges}
            """
        elif direction == "backward":
            # 查询指向该实体的边
            sparql = f"""
            PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
            PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
            PREFIX ns: <http://rdf.freebase.com/ns/>
            SELECT DISTINCT ?relation ?source ?sourceName
            WHERE {{
                ?source ?relation <{mid_uri}> .
                OPTIONAL {{
                    ?source ns:type.object.name ?sourceNameFb .
                    FILTER(lang(?sourceNameFb) = '' || langMatches(lang(?sourceNameFb), 'en'))
                }}
                OPTIONAL {{
                    ?source rdfs:label ?sourceNameRdfs .
                    FILTER(lang(?sourceNameRdfs) = '' || langMatches(lang(?sourceNameRdfs), 'en'))
                }}
                BIND(COALESCE(?sourceNameFb, ?sourceNameRdfs) AS ?sourceName)
            }}
            LIMIT {max_edges}
            """
        else:  # both
            # 查询双向边
            sparql = f"""
            PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
            PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
            PREFIX ns: <http://rdf.freebase.com/ns/>
            SELECT DISTINCT ?relation ?target ?targetName ?source ?sourceName ?dir
            WHERE {{
                {{
                    <{mid_uri}> ?relation ?target .
                    OPTIONAL {{
                        ?target ns:type.object.name ?targetNameFb .
                        FILTER(lang(?targetNameFb) = '' || langMatches(lang(?targetNameFb), 'en'))
                    }}
                    OPTIONAL {{
                        ?target rdfs:label ?targetNameRdfs .
                        FILTER(lang(?targetNameRdfs) = '' || langMatches(lang(?targetNameRdfs), 'en'))
                    }}
                    BIND(COALESCE(?targetNameFb, ?targetNameRdfs) AS ?targetName)
                    BIND("forward" AS ?dir)
                }}
                UNION
                {{
                    ?source ?relation <{mid_uri}> .
                    OPTIONAL {{
                        ?source ns:type.object.name ?sourceNameFb .
                        FILTER(lang(?sourceNameFb) = '' || langMatches(lang(?sourceNameFb), 'en'))
                    }}
                    OPTIONAL {{
                        ?source rdfs:label ?sourceNameRdfs .
                        FILTER(lang(?sourceNameRdfs) = '' || langMatches(lang(?sourceNameRdfs), 'en'))
                    }}
                    BIND(COALESCE(?sourceNameFb, ?sourceNameRdfs) AS ?sourceName)
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
                    if not target_name:
                        target_name = self._extract_literal(target_uri)
                    
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
                        source_name = self._extract_literal(source_uri)
                    
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
                            target_name = self._extract_literal(target_uri)
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
                            source_name = self._extract_literal(source_uri)
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
            Freebase MID (如 m.xxx)，如果不是实体 URI 则返回空字符串
        """
        if not uri:
            return ""
        
        # Freebase 实体 MID 格式: http://rdf.freebase.com/ns/m.06n7_
        # 关系 URI 格式: http://rdf.freebase.com/ns/book.written_work.author
        # 其他 URI 格式: http://rdf.freebase.com/ns/type.object.type
        if "/ns/m." in uri:
            mid = uri.split("/ns/")[-1]
            # 移除最后的点号
            return mid.rstrip(".")
        
        # 非实体 URI（关系、类型等），返回空字符串
        return ""

    def _extract_literal(self, value: str) -> str:
        """从对象值中提取可读字面量。

        - 如果是 MID URI：返回空（交给上层映射与占位逻辑处理）
        - 如果是其他 URI：返回空（通常非可读实体名）
        - 如果是普通字面量：直接返回
        """
        if not value:
            return ""

        if value.startswith("http://") or value.startswith("https://"):
            if self._extract_mid(value):
                return ""
            return ""

        return value.strip()

    async def resolve_mid_names(self, mids: list[str]) -> dict[str, str]:
        """批量解析 MID 对应的可读名称。

        Args:
            mids: MID 列表，如 ["m.01abc", "m.0xyz"]

        Returns:
            仅包含成功解析项的映射字典 {mid: name}
        """
        uniq_mids = [
            mid.strip()
            for mid in dict.fromkeys(mids)
            if mid and mid.strip() and re.fullmatch(r"[mg]\.[A-Za-z0-9_]+", mid.strip())
        ]
        if not uniq_mids:
            return {}

        values = " ".join(f"ns:{mid}" for mid in uniq_mids)
        sparql = f"""
        PREFIX ns: <http://rdf.freebase.com/ns/>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        SELECT DISTINCT ?mid ?name
        WHERE {{
            VALUES ?mid {{ {values} }}
            OPTIONAL {{
                ?mid ns:type.object.name ?nameFb .
                FILTER(lang(?nameFb) = '' || langMatches(lang(?nameFb), 'en'))
            }}
            OPTIONAL {{
                ?mid rdfs:label ?nameRdfs .
                FILTER(lang(?nameRdfs) = '' || langMatches(lang(?nameRdfs), 'en'))
            }}
            OPTIONAL {{
                ?mid ns:common.topic.alias ?nameAlias .
                FILTER(lang(?nameAlias) = '' || langMatches(lang(?nameAlias), 'en'))
            }}
            BIND(COALESCE(?nameFb, ?nameRdfs, ?nameAlias) AS ?name)
            FILTER(BOUND(?name))
        }}
        """

        result = await self.query(sparql)
        bindings = result.get("results", {}).get("bindings", [])
        resolved: dict[str, str] = {}

        for item in bindings:
            mid_uri = item.get("mid", {}).get("value", "")
            name = item.get("name", {}).get("value", "").strip()
            if not mid_uri or not name:
                continue

            mid = ""
            if "/ns/" in mid_uri:
                mid = mid_uri.split("/ns/")[-1].strip()
            elif mid_uri.startswith("m.") or mid_uri.startswith("g."):
                mid = mid_uri.strip()

            if mid and mid not in resolved:
                resolved[mid] = name

        unresolved = [mid for mid in uniq_mids if mid not in resolved]
        if not unresolved:
            return resolved

        fallback_values = " ".join(f"ns:{mid}" for mid in unresolved)
        fallback_sparql = f"""
        PREFIX ns: <http://rdf.freebase.com/ns/>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        SELECT ?mid (SAMPLE(?fallbackName) AS ?name)
        WHERE {{
            VALUES ?mid {{ {fallback_values} }}
            {{
                ?mid ?p ?neighbor .
                FILTER(STRSTARTS(STR(?neighbor), "http://rdf.freebase.com/ns/"))
            }}
            UNION
            {{
                ?neighbor ?p ?mid .
                FILTER(STRSTARTS(STR(?neighbor), "http://rdf.freebase.com/ns/"))
            }}

            OPTIONAL {{
                ?neighbor ns:type.object.name ?neighborNameFb .
                FILTER(lang(?neighborNameFb) = '' || langMatches(lang(?neighborNameFb), 'en'))
            }}
            OPTIONAL {{
                ?neighbor rdfs:label ?neighborNameRdfs .
                FILTER(lang(?neighborNameRdfs) = '' || langMatches(lang(?neighborNameRdfs), 'en'))
            }}
            OPTIONAL {{
                ?neighbor ns:common.topic.alias ?neighborAlias .
                FILTER(lang(?neighborAlias) = '' || langMatches(lang(?neighborAlias), 'en'))
            }}

            BIND(COALESCE(?neighborNameFb, ?neighborNameRdfs, ?neighborAlias) AS ?fallbackName)
            FILTER(BOUND(?fallbackName))
        }}
        GROUP BY ?mid
        """

        fallback_result = await self.query(fallback_sparql)
        fallback_bindings = fallback_result.get("results", {}).get("bindings", [])
        for item in fallback_bindings:
            mid_uri = item.get("mid", {}).get("value", "")
            name = item.get("name", {}).get("value", "").strip()
            if not mid_uri or not name:
                continue

            mid = ""
            if "/ns/" in mid_uri:
                mid = mid_uri.split("/ns/")[-1].strip()
            elif mid_uri.startswith("m.") or mid_uri.startswith("g."):
                mid = mid_uri.strip()

            if mid and mid not in resolved:
                resolved[mid] = f"[{name}]"

        return resolved