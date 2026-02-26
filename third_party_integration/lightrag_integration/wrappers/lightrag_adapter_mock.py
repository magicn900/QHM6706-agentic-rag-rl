from __future__ import annotations

import asyncio
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np

from .contracts import GraphSeedResponse


class _SimpleTokenizerImpl:
    def encode(self, content: str) -> list[int]:
        return [ord(ch) for ch in content]

    def decode(self, tokens: list[int]) -> str:
        return "".join(chr(token) for token in tokens)


async def _mock_llm(
    prompt: str,
    system_prompt: str | None = None,
    history_messages: list[dict[str, str]] | None = None,
    keyword_extraction: bool = False,
    **kwargs: Any,
) -> str:
    if keyword_extraction:
        return (
            '{"high_level_keywords": ["LightRAG", "Knowledge Graph"], '
            '"low_level_keywords": ["LightRAG", "graph retrieval", "knowledge graph"]}'
        )

    normalized_prompt = prompt.lower()
    if "based on the last extraction task" in normalized_prompt:
        return "<|COMPLETE|>"

    if "extract entities and relationships" in normalized_prompt:
        return (
            "entity<|#|>LightRAG<|#|>framework<|#|>LightRAG is a graph-based retrieval-augmented generation framework.\n"
            "entity<|#|>Knowledge Graph<|#|>concept<|#|>A graph structure that stores entities and their relationships.\n"
            "relation<|#|>LightRAG<|#|>Knowledge Graph<|#|>uses,represents<|#|>LightRAG uses a knowledge graph to improve retrieval quality.\n"
            "<|COMPLETE|>"
        )

    return "LightRAG uses a Knowledge Graph to represent entities and relations, improving retrieval quality through graph-aware context."


async def _mock_embedding(texts: list[str]) -> np.ndarray:
    vectors = np.zeros((len(texts), 384), dtype=np.float32)
    for idx, text in enumerate(texts):
        normalized = text.lower()

        if "lightrag" in normalized:
            vectors[idx, 0] += 1.0
        if "knowledge graph" in normalized or "graph" in normalized:
            vectors[idx, 1] += 1.0
        if "retrieval" in normalized:
            vectors[idx, 2] += 1.0

        if not np.any(vectors[idx]):
            seed = sum(ord(ch) for ch in text) % 997
            vectors[idx, seed % 384] = 1.0

    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    vectors = vectors / norms
    return vectors


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


class LightRAGMockAdapter:
    def __init__(self, working_dir: str = "./temp/adapter_storage") -> None:
        _ensure_lightrag_importable()

        from lightrag import LightRAG
        from lightrag.utils import EmbeddingFunc, Tokenizer

        self._working_dir = Path(working_dir)
        self._working_dir.mkdir(parents=True, exist_ok=True)

        self._rag = LightRAG(
            working_dir=str(self._working_dir),
            llm_model_func=_mock_llm,
            embedding_func=EmbeddingFunc(
                embedding_dim=384,
                max_token_size=8192,
                func=_mock_embedding,
                model_name="mock-embedding",
            ),
            tokenizer=Tokenizer("mock-tokenizer", _SimpleTokenizerImpl()),
        )

    async def initialize(self) -> None:
        await self._rag.initialize_storages()

    async def insert(self, text: str) -> None:
        await self._rag.ainsert(text)

    async def query(self, question: str, mode: str = "hybrid") -> str:
        from lightrag import QueryParam

        result = await self._rag.aquery(
            question,
            param=QueryParam(mode=mode, top_k=5, chunk_top_k=5),
        )
        return str(result)

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
            top_k=top_k if top_k is not None else 5,
            max_entity_tokens=max_entity_tokens if max_entity_tokens is not None else 6000,
            max_relation_tokens=max_relation_tokens if max_relation_tokens is not None else 8000,
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


async def quick_demo() -> None:
    adapter = LightRAGMockAdapter()
    await adapter.initialize()
    try:
        await adapter.insert("LightRAG combines vector retrieval and graph retrieval for better answers.")
        result = await adapter.query("LightRAG和知识图谱有什么关系？")
        print(result)
    finally:
        await adapter.finalize()


if __name__ == "__main__":
    asyncio.run(quick_demo())
