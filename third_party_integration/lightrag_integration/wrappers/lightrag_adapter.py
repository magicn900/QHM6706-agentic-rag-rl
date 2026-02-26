from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict
from functools import partial
from pathlib import Path
from typing import Any

from .contracts import GraphSeedResponse


def _ensure_lightrag_importable() -> None:
    try:
        import lightrag  # noqa: F401
        return
    except Exception:
        pass

    repo_root = Path(__file__).resolve().parents[3]
    lightrag_root = repo_root / "LightRAG"
    if lightrag_root.exists():
        sys.path.insert(0, str(lightrag_root))


def _build_rerank_func(provider: str | None):
    if not provider:
        return None

    _ensure_lightrag_importable()
    from lightrag.rerank import ali_rerank, cohere_rerank, generic_rerank_api, jina_rerank

    provider_norm = provider.lower().strip()
    top_n = int(os.getenv("LIGHTRAG_RERANK_TOP_N", "10"))

    if provider_norm == "cohere":
        return partial(
            cohere_rerank,
            api_key=os.getenv("COHERE_API_KEY") or os.getenv("RERANK_BINDING_API_KEY"),
            model=os.getenv("LIGHTRAG_RERANK_MODEL", "rerank-v3.5"),
            top_n=top_n,
        )

    if provider_norm == "jina":
        return partial(
            jina_rerank,
            api_key=os.getenv("JINA_API_KEY") or os.getenv("RERANK_BINDING_API_KEY"),
            model=os.getenv("LIGHTRAG_RERANK_MODEL", "jina-reranker-v2-base-multilingual"),
            top_n=top_n,
        )

    if provider_norm in {"ali", "aliyun", "dashscope"}:
        return partial(
            ali_rerank,
            api_key=os.getenv("DASHSCOPE_API_KEY") or os.getenv("RERANK_BINDING_API_KEY"),
            model=os.getenv("LIGHTRAG_RERANK_MODEL", "gte-rerank-v2"),
            top_n=top_n,
        )

    if provider_norm in {"openai_compatible", "openai-compatible", "compat"}:
        rerank_base_url = os.getenv("LIGHTRAG_RERANK_BASE_URL")
        if not rerank_base_url:
            common_base_url = os.getenv("LIGHTRAG_BASE_URL", "").rstrip("/")
            if common_base_url:
                rerank_base_url = f"{common_base_url}/rerank"

        rerank_api_key = (
            os.getenv("LIGHTRAG_RERANK_API_KEY")
            or os.getenv("RERANK_BINDING_API_KEY")
            or os.getenv("LIGHTRAG_API_KEY")
        )

        default_top_n = top_n

        async def _compat_rerank(query: str, documents: list[str], top_n: int | None = None):
            if not rerank_base_url:
                raise ValueError(
                    "LIGHTRAG_RERANK_BASE_URL is required for openai_compatible rerank provider."
                )
            return await generic_rerank_api(
                query=query,
                documents=documents,
                model=os.getenv("LIGHTRAG_RERANK_MODEL", "BAAI/bge-reranker-v2-m3"),
                base_url=rerank_base_url,
                api_key=rerank_api_key,
                top_n=top_n if top_n is not None else default_top_n,
                response_format="standard",
            )

        return _compat_rerank

    raise ValueError(
        f"Unsupported rerank provider: {provider}. Use one of: cohere, jina, ali, openai_compatible"
    )


class LightRAGAdapter:
    def __init__(
        self,
        *,
        working_dir: str,
        llm_model: str,
        embedding_model: str,
        embedding_dim: int,
        llm_base_url: str | None = None,
        llm_api_key: str | None = None,
        embedding_base_url: str | None = None,
        embedding_api_key: str | None = None,
        rerank_provider: str | None = None,
        llm_model_kwargs: dict[str, Any] | None = None,
    ) -> None:
        _ensure_lightrag_importable()

        from lightrag import LightRAG
        from lightrag.llm.openai import openai_complete_if_cache, openai_embed
        from lightrag.utils import EmbeddingFunc

        self._working_dir = Path(working_dir)
        self._working_dir.mkdir(parents=True, exist_ok=True)

        llm_base_url = llm_base_url or os.getenv("LIGHTRAG_LLM_BASE_URL")
        llm_api_key = llm_api_key or os.getenv("LIGHTRAG_LLM_API_KEY")
        embedding_base_url = embedding_base_url or os.getenv("LIGHTRAG_EMBED_BASE_URL")
        embedding_api_key = embedding_api_key or os.getenv("LIGHTRAG_EMBED_API_KEY")

        common_base_url = os.getenv("LIGHTRAG_BASE_URL")
        common_api_key = os.getenv("LIGHTRAG_API_KEY")

        llm_base_url = llm_base_url or common_base_url
        embedding_base_url = embedding_base_url or common_base_url
        llm_api_key = llm_api_key or common_api_key
        embedding_api_key = embedding_api_key or common_api_key

        if not llm_api_key:
            raise ValueError(
                "LIGHTRAG_LLM_API_KEY is required for adapter execution."
            )
        if not embedding_api_key:
            raise ValueError(
                "LIGHTRAG_EMBED_API_KEY is required for adapter execution."
            )

        async def llm_model_func(
            prompt,
            system_prompt=None,
            history_messages=None,
            keyword_extraction=False,
            **kwargs,
        ) -> str:
            if keyword_extraction:
                lower_prompt = prompt.lower()
                keywords = [
                    token
                    for token in [
                        "lightrag",
                        "knowledge graph",
                        "graph retrieval",
                        "vector retrieval",
                    ]
                    if token in lower_prompt
                ]
                if not keywords:
                    keywords = ["lightrag", "knowledge graph"]
                return json.dumps(
                    {
                        "high_level_keywords": keywords[:2],
                        "low_level_keywords": keywords,
                    },
                    ensure_ascii=False,
                )

            kwargs.pop("response_format", None)
            return await openai_complete_if_cache(
                llm_model,
                prompt,
                system_prompt=system_prompt,
                history_messages=history_messages or [],
                keyword_extraction=keyword_extraction,
                base_url=llm_base_url,
                api_key=llm_api_key,
                **kwargs,
            )

        embedding_func = EmbeddingFunc(
            embedding_dim=embedding_dim,
            max_token_size=int(os.getenv("LIGHTRAG_EMBED_MAX_TOKENS", "8192")),
            model_name=embedding_model,
            func=partial(
                openai_embed.func,
                model=embedding_model,
                base_url=embedding_base_url,
                api_key=embedding_api_key,
            ),
        )

        rerank_func = _build_rerank_func(
            rerank_provider or os.getenv("LIGHTRAG_RERANK_PROVIDER")
        )

        self._rag = LightRAG(
            working_dir=str(self._working_dir),
            llm_model_func=llm_model_func,
            embedding_func=embedding_func,
            rerank_model_func=rerank_func,
            llm_model_kwargs=llm_model_kwargs or {},
        )

    async def initialize(self) -> None:
        await self._rag.initialize_storages()

    async def insert(self, text: str) -> None:
        await self._rag.ainsert(text)

    async def query(self, question: str, mode: str = "hybrid", enable_rerank: bool = True) -> str:
        from lightrag import QueryParam

        response = await self._rag.aquery(
            question,
            param=QueryParam(mode=mode, enable_rerank=enable_rerank),
        )
        return str(response)

    async def query_graph_seed(
        self,
        question: str,
        mode: str = "hybrid",
        *,
        top_k: int | None = None,
        max_entity_tokens: int | None = None,
        max_relation_tokens: int | None = None,
        hl_keywords: list[str] | None = None,
        ll_keywords: list[str] | None = None,
    ) -> GraphSeedResponse:
        """
        Extract graph exploration seeds (entities + relationships) using LightRAG's
        internal selection pipeline, without LLM answer generation.

        This method intentionally stops before chunk merge and context construction,
        and is designed as a graph-exploration starting point for custom architectures.
        """

        if not question or not question.strip():
            return {
                "status": "failure",
                "message": "Query cannot be empty.",
                "data": {},
            }

        from lightrag import QueryParam
        from lightrag.operate import (
            _apply_token_truncation,
            _perform_kg_search,
            get_keywords_from_query,
        )

        if mode not in {"local", "global", "hybrid", "mix"}:
            raise ValueError("mode must be one of: local, global, hybrid, mix")

        param = QueryParam(
            mode=mode,
            top_k=top_k if top_k is not None else int(os.getenv("TOP_K", "40")),
            max_entity_tokens=(
                max_entity_tokens
                if max_entity_tokens is not None
                else int(os.getenv("MAX_ENTITY_TOKENS", "6000"))
            ),
            max_relation_tokens=(
                max_relation_tokens
                if max_relation_tokens is not None
                else int(os.getenv("MAX_RELATION_TOKENS", "8000"))
            ),
            hl_keywords=hl_keywords or [],
            ll_keywords=ll_keywords or [],
        )

        global_config = asdict(self._rag)
        extracted_hl, extracted_ll = await get_keywords_from_query(
            question.strip(),
            param,
            global_config,
            self._rag.llm_response_cache,
        )

        if extracted_ll == [] and mode in {"local", "hybrid", "mix"}:
            pass
        if extracted_hl == [] and mode in {"global", "hybrid", "mix"}:
            pass
        if extracted_hl == [] and extracted_ll == []:
            if len(question.strip()) < 50:
                extracted_ll = [question.strip()]
            else:
                return {
                    "status": "failure",
                    "message": "Both high-level and low-level keywords are empty.",
                    "data": {},
                }

        ll_keywords_str = ", ".join(extracted_ll) if extracted_ll else ""
        hl_keywords_str = ", ".join(extracted_hl) if extracted_hl else ""

        search_result = await _perform_kg_search(
            question.strip(),
            ll_keywords_str,
            hl_keywords_str,
            self._rag.chunk_entity_relation_graph,
            self._rag.entities_vdb,
            self._rag.relationships_vdb,
            self._rag.text_chunks,
            param,
            self._rag.chunks_vdb,
        )

        if not search_result["final_entities"] and not search_result["final_relations"]:
            return {
                "status": "failure",
                "message": "No entities or relationships found for this query.",
                "data": {
                    "keywords": {
                        "high_level": extracted_hl,
                        "low_level": extracted_ll,
                    }
                },
            }

        truncation_result = await _apply_token_truncation(
            search_result,
            param,
            self._rag.text_chunks.global_config,
        )

        filtered_entities = truncation_result["filtered_entities"]
        filtered_relations = truncation_result["filtered_relations"]

        entity_names = {
            entity.get("entity_name")
            for entity in filtered_entities
            if entity.get("entity_name")
        }

        connected_relations = []
        for relation in filtered_relations:
            src_id = relation.get("src_id")
            tgt_id = relation.get("tgt_id")
            if (src_id is None or tgt_id is None) and relation.get("src_tgt"):
                src_tgt = relation.get("src_tgt")
                if isinstance(src_tgt, (list, tuple)) and len(src_tgt) == 2:
                    src_id, tgt_id = src_tgt[0], src_tgt[1]
            if src_id in entity_names or tgt_id in entity_names:
                normalized_relation = {
                    **relation,
                    "src_id": src_id,
                    "tgt_id": tgt_id,
                }
                connected_relations.append(normalized_relation)

        relation_candidates_by_entity: dict[str, list[dict[str, Any]]] = {
            entity_name: [] for entity_name in entity_names
        }
        for relation in connected_relations:
            src_id = relation.get("src_id")
            tgt_id = relation.get("tgt_id")
            if src_id in relation_candidates_by_entity:
                relation_candidates_by_entity[src_id].append(relation)
            if tgt_id in relation_candidates_by_entity and tgt_id != src_id:
                relation_candidates_by_entity[tgt_id].append(relation)

        entity_relation_candidates = []
        entity_index = {
            entity.get("entity_name"): entity
            for entity in filtered_entities
            if entity.get("entity_name")
        }
        for entity_name, relation_candidates in relation_candidates_by_entity.items():
            candidate_edges = []
            for relation in relation_candidates:
                src_id = relation.get("src_id")
                tgt_id = relation.get("tgt_id")
                if src_id == entity_name:
                    next_entity = tgt_id
                    direction = "outgoing"
                elif tgt_id == entity_name:
                    next_entity = src_id
                    direction = "incoming"
                else:
                    next_entity = None
                    direction = "unknown"

                edge_id = (
                    relation.get("edge_id")
                    or relation.get("id")
                    or f"{src_id}->{tgt_id}"
                )

                candidate_edges.append(
                    {
                        "edge_id": edge_id,
                        "src_id": src_id,
                        "tgt_id": tgt_id,
                        "next_entity": next_entity,
                        "direction": direction,
                        "description": relation.get("description", ""),
                        "keywords": relation.get("keywords", ""),
                        "weight": relation.get("weight", 1.0),
                        "created_at": relation.get("created_at"),
                    }
                )

            entity_relation_candidates.append(
                {
                    **entity_index.get(entity_name, {"entity_name": entity_name}),
                    "candidate_edges": candidate_edges,
                }
            )

        return {
            "status": "success",
            "message": "Graph seed extracted from entity/relation selection pipeline.",
            "data": {
                "keywords": {
                    "high_level": extracted_hl,
                    "low_level": extracted_ll,
                },
                "entity_relation_candidates": entity_relation_candidates,
                "processing_info": {
                    "mode": mode,
                    "total_entities_found": len(search_result.get("final_entities", [])),
                    "total_relations_found": len(search_result.get("final_relations", [])),
                    "entities_after_truncation": len(
                        filtered_entities
                    ),
                    "relations_after_truncation": len(
                        filtered_relations
                    ),
                    "connected_relations_count": len(
                        connected_relations
                    ),
                    "entity_candidates_count": len(entity_relation_candidates),
                },
            },
        }

    async def finalize(self) -> None:
        await self._rag.finalize_storages()
