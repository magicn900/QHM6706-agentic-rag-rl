from __future__ import annotations

from collections import Counter

from ..contracts import PathTrace, RelationEnvAction, RelationEnvState, SeedSnapshot, StepResult
from ..prompts import EMPTY_KNOWLEDGE, format_knowledge_body
from ..providers import GraphProvider
from ..utils.embedding_pruner import EmbeddingPruner


class RelationSelectionEnv:
    def __init__(
        self,
        *,
        provider: GraphProvider,
        beam_width: int = 4,
        max_steps: int = 4,
        top_k: int = 20,
        answer_mode: str = "hybrid",
    ) -> None:
        self.provider = provider
        self.beam_width = beam_width
        self.max_steps = max_steps
        self.top_k = top_k
        self.answer_mode = answer_mode
        self.pruner = EmbeddingPruner()

        self._question = ""
        self._step_index = 0
        self._done = False
        self._history: list[dict[str, str]] = []
        self._active_paths: list[PathTrace] = []
        self._snapshot: SeedSnapshot | None = None

    async def reset(self, question: str) -> RelationEnvState:
        self._question = question.strip()
        self._step_index = 0
        self._done = False
        self._history = []

        snapshot = await self.provider.get_snapshot(question=self._question, top_k=self.top_k)
        self._snapshot = snapshot
        self._active_paths = [
            PathTrace(nodes=[entity_name], relations=[], score=0.0)
            for entity_name in snapshot.entity_edges.keys()
        ]
        self._active_paths = await self._prune_paths(self._active_paths)

        return self._build_state()

    async def step(self, action: RelationEnvAction) -> StepResult:
        if self._done:
            return StepResult(state=self._build_state(), reward=0.0, done=True, info={"reason": "episode_finished"})

        if action.answer:
            self._done = True
            self._history.append({"action": "answer", "value": action.answer})
            reward = 1.0 if action.answer.strip() else -1.0
            return StepResult(
                state=self._build_state(done_override=True),
                reward=reward,
                done=True,
                info={"final_answer": action.answer},
            )

        relation = (action.relation_select or "").strip()
        if not relation:
            return StepResult(
                state=self._build_state(),
                reward=-0.5,
                done=False,
                info={"reason": "empty_relation"},
            )

        if self._snapshot is None:
            return StepResult(
                state=self._build_state(),
                reward=-1.0,
                done=False,
                info={"reason": "missing_snapshot"},
            )

        expanded_paths: list[PathTrace] = []
        cycle_pruned = 0
        for path in self._active_paths:
            tail = path.tail_entity
            edges = self._snapshot.entity_edges.get(tail, [])
            matched = [edge for edge in edges if edge.relation == relation]
            for edge in matched:
                next_entity = edge.next_entity or tail
                if next_entity and next_entity in path.nodes:
                    cycle_pruned += 1
                    continue
                expanded_paths.append(path.extend(relation=edge.relation, next_entity=next_entity, score_delta=edge.weight))

        if not expanded_paths:
            expanded_paths = [PathTrace(nodes=list(path.nodes), relations=list(path.relations), score=path.score - 0.1) for path in self._active_paths]

        frontier = [path.tail_entity for path in expanded_paths if path.tail_entity]
        ll_keywords = self._build_ll_keywords(relation=relation, frontier=frontier)
        self._snapshot = await self.provider.get_snapshot(
            question=self._question,
            top_k=self.top_k,
            ll_keywords=ll_keywords,
        )

        self._active_paths = await self._prune_paths(expanded_paths)
        self._step_index += 1
        self._history.append({"action": "relation_select", "value": relation})

        fallback_answer: str | None = None
        if self._step_index >= self.max_steps:
            self._done = True
            fallback_answer = await self._generate_fallback_answer()
            self._history.append({"action": "auto_answer", "value": fallback_answer})

        reward = 0.1 if expanded_paths else -0.2
        done = self._done
        info = {
            "relation_selected": relation,
            "frontier_count": len(frontier),
            "cycle_pruned": cycle_pruned,
        }
        if fallback_answer is not None:
            info.update(
                {
                    "reason": "max_steps_reached",
                    "final_answer": fallback_answer,
                    "auto_generated": True,
                }
            )

        return StepResult(
            state=self._build_state(done_override=done),
            reward=reward,
            done=done,
            info=info,
        )

    async def _generate_fallback_answer(self) -> str:
        try:
            answer = (await self.provider.answer(self._question, mode=self.answer_mode)).strip()
            if answer:
                return answer
        except Exception:
            pass

        knowledge = self._format_knowledge().strip()
        if not knowledge or knowledge == EMPTY_KNOWLEDGE:
            return "已达到最大推理步数，当前证据不足以给出确定答案。"

        relation_set = self._collect_relation_set()
        relation_hint = "、".join(relation_set[:5]) if relation_set else "无"
        return (
            "已达到最大推理步数，以下是基于当前探索结果的基础回复：\n"
            f"- 问题：{self._question}\n"
            f"- 候选关系：{relation_hint}\n"
            f"- 已探索知识：\n{knowledge}"
        )

    def _build_ll_keywords(self, *, relation: str, frontier: list[str]) -> list[str]:
        unique: list[str] = []
        for item in [relation, *frontier]:
            normalized = item.strip()
            if normalized and normalized not in unique:
                unique.append(normalized)
            if len(unique) >= 12:
                break
        return unique

    async def _prune_paths(self, paths: list[PathTrace]) -> list[PathTrace]:
        if len(paths) <= self.beam_width:
            return paths

        path_texts = [path.to_text() for path in paths]
        similarities = await self.pruner.score_texts(self._question, path_texts)
        scored = []
        for idx, path in enumerate(paths):
            similarity = similarities[idx] if idx < len(similarities) else 0.0
            scored.append((path.score + similarity, idx, path))

        scored.sort(key=lambda item: item[0], reverse=True)
        return [item[2] for item in scored[: self.beam_width]]

    def _build_state(self, *, done_override: bool | None = None) -> RelationEnvState:
        relation_set = self._collect_relation_set()
        knowledge = self._format_knowledge()
        return RelationEnvState(
            question=self._question,
            knowledge=knowledge,
            relation_set=relation_set,
            active_paths=self._active_paths,
            history=list(self._history),
            step_index=self._step_index,
            done=self._done if done_override is None else done_override,
        )

    def _collect_relation_set(self) -> list[str]:
        if self._snapshot is None:
            return []

        counter: Counter[str] = Counter()
        for path in self._active_paths:
            edges = self._snapshot.entity_edges.get(path.tail_entity, [])
            for edge in edges:
                if edge.relation:
                    counter[edge.relation] += 1

        return [relation for relation, _ in counter.most_common()]

    def _format_knowledge(self) -> str:
        if not self._active_paths:
            return EMPTY_KNOWLEDGE

        lines = [f"当前有 {len(self._active_paths)} 条活跃路径：", ""]
        for idx, path in enumerate(self._active_paths, start=1):
            if path.relations:
                lines.append(f"- 路径{idx}：{path.to_text()}（末端：{path.tail_entity}）")
            else:
                lines.append(f"- 路径{idx}：从 {path.tail_entity} 出发，暂无扩展。")

        return format_knowledge_body(lines)
