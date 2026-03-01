from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class PathTrace:
    """路径轨迹数据结构。

    nodes 保存实体序列，relations 保存边关系序列，
    两者共同描述一条从起点到当前节点的推理路径。
    """
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
    """Provider 输出的统一图快照。"""
    question: str
    keywords: dict[str, list[str]]
    entity_edges: dict[str, list["CandidateEdge"]]
    processing_info: dict[str, Any] = field(default_factory=dict)
    raw_data: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class CandidateEdge:
    """候选边定义。

    对 Agent 暴露 src_name/relation/tgt_name，
    对系统保留 internal_*_ref 作为内部追踪引用。
    """
    edge_id: str
    src_name: str
    relation: str
    tgt_name: str
    direction: str
    description: str = ""
    keywords: str = ""
    weight: float = 1.0
    internal_src_ref: str | None = None
    internal_tgt_ref: str | None = None

    def to_display_text(self) -> str:
        """返回 Agent 可读边文本。"""
        if self.direction == "forward":
            return f"{self.src_name} -{self.relation}-> {self.tgt_name}"
        else:
            return f"{self.tgt_name} <-{self.relation}- {self.src_name}"


@dataclass(slots=True)
class EdgeEnvState:
    """Env 暴露给 Policy 的状态载体。"""
    question: str
    knowledge: str
    candidate_edges: list[CandidateEdge]
    active_paths: list[PathTrace]
    history: list[dict[str, str]]
    step_index: int
    done: bool = False

    def get_candidate_edges_text(self) -> str:
        """生成候选边可读文本（供日志与调试使用）。"""
        if not self.candidate_edges:
            return "（无候选边）"
        lines = []
        for idx, edge in enumerate(self.candidate_edges, 1):
            lines.append(f"{idx}. {edge.to_display_text()}")
        return "\n".join(lines)


@dataclass(slots=True)
class EdgeEnvAction:
    """Edge-Select 模式的环境动作。"""
    edge_select: str | None = None
    answer: str | None = None

    @property
    def action_type(self) -> str:
        """返回动作类型。"""
        if self.edge_select is not None:
            return "edge_select"
        elif self.answer is not None:
            return "answer_now"
        return "unknown"

    @property
    def action_value(self) -> str | None:
        """返回动作的值。"""
        if self.edge_select is not None:
            return self.edge_select
        elif self.answer is not None:
            return self.answer
        return None

    @classmethod
    def select_edge(cls, edge_text: str) -> "EdgeEnvAction":
        """构造边选择动作。"""
        return cls(edge_select=edge_text)

    @classmethod
    def answer_now(cls, answer: str) -> "EdgeEnvAction":
        """构造直接回答动作。"""
        return cls(answer=answer)


@dataclass(slots=True)
class StepResult:
    """Env 单步执行结果。"""
    state: EdgeEnvState
    reward: float
    done: bool
    info: dict[str, Any] = field(default_factory=dict)
