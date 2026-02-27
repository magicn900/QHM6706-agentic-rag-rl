from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class RelationEdge:
    edge_id: str
    relation: str
    src_id: str | None
    tgt_id: str | None
    next_entity: str | None
    direction: str
    description: str = ""
    keywords: str = ""
    weight: float = 1.0


@dataclass(slots=True)
class RelationOption:
    relation: str
    count: int = 0


@dataclass(slots=True)
class PathTrace:
    nodes: list[str]
    relations: list[str]
    score: float = 0.0

    @property
    def tail_entity(self) -> str:
        return self.nodes[-1] if self.nodes else ""

    def extend(self, relation: str, next_entity: str | None, score_delta: float = 0.0) -> "PathTrace":
        extended_nodes = list(self.nodes)
        if next_entity:
            extended_nodes.append(next_entity)
        return PathTrace(
            nodes=extended_nodes,
            relations=[*self.relations, relation],
            score=self.score + score_delta,
        )

    def to_text(self) -> str:
        if not self.nodes:
            return ""
        segments: list[str] = [self.nodes[0]]
        for idx, relation in enumerate(self.relations):
            next_idx = min(idx + 1, len(self.nodes) - 1)
            segments.append(f"-{relation}->")
            segments.append(self.nodes[next_idx])
        return " ".join(segments)


@dataclass(slots=True)
class SeedSnapshot:
    question: str
    keywords: dict[str, list[str]]
    entity_edges: dict[str, list[RelationEdge]]
    processing_info: dict[str, Any] = field(default_factory=dict)
    raw_data: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class RelationEnvState:
    question: str
    knowledge: str
    relation_set: list[str]
    active_paths: list[PathTrace]
    history: list[dict[str, str]]
    step_index: int
    done: bool = False


@dataclass(slots=True)
class RelationEnvAction:
    relation_select: str | None = None
    answer: str | None = None

    @classmethod
    def select_relation(cls, relation: str) -> "RelationEnvAction":
        return cls(relation_select=relation)

    @classmethod
    def answer_now(cls, answer: str) -> "RelationEnvAction":
        return cls(answer=answer)


@dataclass(slots=True)
class StepResult:
    state: RelationEnvState
    reward: float
    done: bool
    info: dict[str, Any] = field(default_factory=dict)
