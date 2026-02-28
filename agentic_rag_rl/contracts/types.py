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


# ========== Edge-Select 类型定义 ==========

@dataclass(slots=True)
class CandidateEdge:
    """可读边：包含语义化显示信息和内部引用字段"""
    edge_id: str
    src_name: str  # 源实体可读名称
    relation: str  # 关系名
    tgt_name: str  # 目标实体可读名称
    direction: str  # "forward" | "backward"
    description: str = ""
    keywords: str = ""
    weight: float = 1.0
    # 内部引用字段（对Agent不可见，仅内部使用）
    internal_src_ref: str | None = None  # 内部ID，如Freebase MID
    internal_tgt_ref: str | None = None  # 内部ID，如Freebase MID

    def to_display_text(self) -> str:
        """转换为Agent可见的可读文本"""
        if self.direction == "forward":
            return f"{self.src_name} -{self.relation}-> {self.tgt_name}"
        else:
            return f"{self.tgt_name} <-{self.relation}- {self.src_name}"


@dataclass(slots=True)
class EdgeEnvState:
    """Edge-Select模式的环境状态"""
    question: str
    knowledge: str  # 当前累积的知识/路径
    candidate_edges: list[CandidateEdge]  # 候选边列表
    active_paths: list[PathTrace]  # 活跃路径
    history: list[dict[str, str]]  # 动作历史
    step_index: int
    done: bool = False

    def get_candidate_edges_text(self) -> str:
        """生成候选边的可读文本（供Agent查看）"""
        if not self.candidate_edges:
            return "（无候选边）"
        lines = []
        for idx, edge in enumerate(self.candidate_edges, 1):
            lines.append(f"{idx}. {edge.to_display_text()}")
        return "\n".join(lines)


@dataclass(slots=True)
class EdgeEnvAction:
    """Edge-Select模式的环境动作"""
    edge_select: str | None = None  # 选中的边（可读文本）
    answer: str | None = None

    @classmethod
    def select_edge(cls, edge_text: str) -> "EdgeEnvAction":
        return cls(edge_select=edge_text)

    @classmethod
    def answer_now(cls, answer: str) -> "EdgeEnvAction":
        return cls(answer=answer)
