from __future__ import annotations

from typing import Any, Literal, Protocol, TypedDict


class GraphSeedKeywords(TypedDict):
    high_level: list[str]
    low_level: list[str]


class GraphSeedCandidateEdge(TypedDict):
    edge_id: str
    src_id: str | None
    tgt_id: str | None
    next_entity: str | None
    direction: Literal["outgoing", "incoming", "unknown"]
    description: str
    keywords: str
    weight: float
    created_at: str | None


class GraphSeedEntityCandidate(TypedDict):
    entity_name: str
    entity_type: str
    description: str
    source_id: str
    candidate_edges: list[GraphSeedCandidateEdge]


class GraphSeedProcessingInfo(TypedDict):
    mode: str
    total_entities_found: int
    total_relations_found: int
    entities_after_truncation: int
    relations_after_truncation: int
    connected_relations_count: int
    entity_candidates_count: int


class GraphSeedData(TypedDict):
    keywords: GraphSeedKeywords
    entity_relation_candidates: list[GraphSeedEntityCandidate]
    processing_info: GraphSeedProcessingInfo


class GraphSeedResponse(TypedDict):
    status: Literal["success", "failure"]
    message: str
    data: dict[str, Any] | GraphSeedData


class LightRAGIntegrationAdapter(Protocol):
    async def initialize(self) -> None: ...

    async def insert(self, text: str) -> None: ...

    async def query(self, question: str, mode: str = "hybrid", **kwargs: Any) -> str: ...

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
    ) -> GraphSeedResponse: ...

    async def finalize(self) -> None: ...
