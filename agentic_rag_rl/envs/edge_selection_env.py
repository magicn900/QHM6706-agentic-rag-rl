"""
Edge-Select 模式的环境实现
基于候选边（而非仅关系名）进行多跳推理

职责：
1. 维护活跃路径和候选边
2. 执行边扩展动作（多边分叉）
3. 管理去环、剪枝逻辑
4. 提供标准化终止信息

注意：
- Env 不调用 LLM
- Env 不拼装 SPARQL
- Provider 差异（LightRAG/Freebase）在 Integration 层处理
"""
from __future__ import annotations

from collections import Counter

from ..contracts import (
    CandidateEdge,
    EdgeEnvAction,
    EdgeEnvState,
    PathTrace,
    RelationEdge,
    SeedSnapshot,
    StepResult,
)
from ..prompts import EMPTY_KNOWLEDGE, format_knowledge_body
from ..providers import GraphProvider
from ..utils.embedding_pruner import EmbeddingPruner


class EdgeSelectionEnv:
    """Edge-Select 模式的环境类
    
    与 RelationSelectionEnv 的核心区别：
    - Agent 选择的是完整边（src -relation-> tgt），而非仅关系名
    - 状态中包含 candidate_edges（可读边列表），而非 relation_set
    - 支持多边同时扩展（分叉推理）
    """
    
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
        self._candidate_edges: list[CandidateEdge] = []  # 当前候选边

    async def reset(self, question: str) -> EdgeEnvState:
        """重置环境到初始状态
        
        Args:
            question: 用户问题
            
        Returns:
            EdgeEnvState: 初始环境状态
        """
        self._question = question.strip()
        self._step_index = 0
        self._done = False
        self._history = []

        # 获取 provider 的快照
        snapshot = await self.provider.get_snapshot(question=self._question, top_k=self.top_k)
        self._snapshot = snapshot
        
        # 将 provider 返回的 RelationEdge 转换为 CandidateEdge
        self._candidate_edges = self._convert_edges(snapshot)
        
        # 初始化活跃路径（从召回的实体出发）
        self._active_paths = [
            PathTrace(nodes=[entity_name], relations=[], score=0.0)
            for entity_name in snapshot.entity_edges.keys()
        ]
        self._active_paths = await self._prune_paths(self._active_paths)

        return self._build_state()

    async def step(self, action: EdgeEnvAction) -> StepResult:
        """执行一步动作
        
        Args:
            action: EdgeEnvAction，包含 edge_select 或 answer
            
        Returns:
            StepResult: 执行结果
        """
        # 已经结束的情况
        if self._done:
            return StepResult(
                state=self._build_state(),
                reward=0.0,
                done=True,
                info={"reason": "episode_finished", "termination_reason": "episode_finished"},
            )

        # 处理 answer 动作
        if action.answer:
            self._done = True
            self._history.append({"action": "answer", "value": action.answer})
            reward = 1.0 if action.answer.strip() else -1.0
            return StepResult(
                state=self._build_state(done_override=True),
                reward=reward,
                done=True,
                info={
                    "final_answer": action.answer,
                    "termination_reason": "answer_provided",
                },
            )

        # 处理边选择动作
        edge_text = (action.edge_select or "").strip()
        if not edge_text:
            return StepResult(
                state=self._build_state(),
                reward=-0.5,
                done=False,
                info={"reason": "empty_edge_select", "termination_reason": "invalid_action"},
            )

        # 解析选中的边（支持多边，用分号分隔）
        selected_edges = self._parse_edge_selection(edge_text)
        if not selected_edges:
            return StepResult(
                state=self._build_state(),
                reward=-0.5,
                done=False,
                info={"reason": "no_matching_edges", "termination_reason": "invalid_action"},
            )

        # 执行边扩展
        result = await self._expand_with_edges(selected_edges)
        return result

    async def _expand_with_edges(self, selected_edges: list[CandidateEdge]) -> StepResult:
        """使用选中的边扩展图
        
        Args:
            selected_edges: 选中的候选边列表
            
        Returns:
            StepResult: 扩展结果
        """
        if self._snapshot is None:
            return StepResult(
                state=self._build_state(),
                reward=-1.0,
                done=False,
                info={"reason": "missing_snapshot", "termination_reason": "internal_error"},
            )

        expanded_paths: list[PathTrace] = []
        cycle_pruned = 0
        new_keywords: list[str] = []

        # 多边分叉扩展
        for edge in selected_edges:
            tail = edge.tgt_name if edge.direction == "forward" else edge.src_name
            
            for path in self._active_paths:
                # 检查是否形成环
                if tail and tail in path.nodes:
                    cycle_pruned += 1
                    continue
                
                # 扩展路径（relation 使用纯关系名，用于 to_text() 显示）
                expanded_paths.append(
                    path.extend(
                        relation=edge.relation,
                        next_entity=tail,
                        score_delta=edge.weight,
                    )
                )
                
                # 收集关键词用于下一轮查询
                if edge.keywords:
                    new_keywords.extend([k.strip() for k in edge.keywords.split(",") if k.strip()])

        # 如果没有有效扩展，回退到原路径
        if not expanded_paths:
            expanded_paths = [
                PathTrace(nodes=list(path.nodes), relations=list(path.relations), score=path.score - 0.1)
                for path in self._active_paths
            ]

        # 获取 frontier 用于构建查询关键词
        frontier = [path.tail_entity for path in expanded_paths if path.tail_entity]
        ll_keywords = self._build_ll_keywords(selected_edges=selected_edges, frontier=frontier)
        
        # 重新查询获取新边
        self._snapshot = await self.provider.get_snapshot(
            question=self._question,
            top_k=self.top_k,
            ll_keywords=ll_keywords,
        )

        # 更新候选边
        self._candidate_edges = self._convert_edges(self._snapshot)

        # 剪枝活跃路径
        self._active_paths = await self._prune_paths(expanded_paths)
        self._step_index += 1
        
        # 记录历史
        edge_values = "; ".join(e.to_display_text() for e in selected_edges)
        self._history.append({"action": "edge_select", "value": edge_values})

        # 检查是否达到最大步数
        fallback_answer: str | None = None
        if self._step_index >= self.max_steps:
            self._done = True
            fallback_answer = await self._generate_fallback_answer()
            self._history.append({"action": "auto_answer", "value": fallback_answer})

        # 计算奖励
        reward = 0.1 if expanded_paths else -0.2
        done = self._done
        
        info = {
            "edges_selected": [e.edge_id for e in selected_edges],
            "edges_count": len(selected_edges),
            "frontier_count": len(frontier),
            "cycle_pruned": cycle_pruned,
        }
        
        if fallback_answer is not None:
            info.update({
                "reason": "max_steps_reached",
                "final_answer": fallback_answer,
                "auto_generated": True,
                "termination_reason": "max_steps_reached",
            })
        else:
            info["termination_reason"] = "continue"

        return StepResult(
            state=self._build_state(done_override=done),
            reward=reward,
            done=done,
            info=info,
        )

    def _parse_edge_selection(self, edge_text: str) -> list[CandidateEdge]:
        """解析边选择文本
        
        支持格式：
        - 完整边文本：实体A -关系-> 实体B
        - 数字索引：1 或 1;2
        - 混合：1; 实体A -关系-> 实体B
        
        Args:
            edge_text: 边选择文本
            
        Returns:
            匹配的 CandidateEdge 列表
        """
        selected: list[CandidateEdge] = []
        
        # 先尝试按分号分割
        parts = [p.strip() for p in edge_text.split(";") if p.strip()]
        
        for part in parts:
            # 尝试解析为数字索引
            if part.isdigit():
                idx = int(part) - 1  # 转换为 0 索引
                if 0 <= idx < len(self._candidate_edges):
                    selected.append(self._candidate_edges[idx])
                continue
            
            # 尝试精确匹配显示文本
            matched = [e for e in self._candidate_edges if e.to_display_text() == part]
            if matched:
                selected.append(matched[0])
                continue
                
            # 尝试模糊匹配（包含关系名）
            if "-" in part and "->" in part:
                # 提取关系部分
                for edge in self._candidate_edges:
                    if edge.to_display_text() == part:
                        selected.append(edge)
                        break
        
        # 去重（按 edge_id）
        seen = set()
        unique = []
        for e in selected:
            if e.edge_id not in seen:
                seen.add(e.edge_id)
                unique.append(e)
        
        return unique

    def _convert_edges(self, snapshot: SeedSnapshot) -> list[CandidateEdge]:
        """将 provider 返回的 RelationEdge 转换为 CandidateEdge
        
        这是翻译墙的关键：把内部机器标识转换为 Agent 可读的形式。
        
        Args:
            snapshot: provider 返回的快照
            
        Returns:
            CandidateEdge 列表
        """
        candidate_edges: list[CandidateEdge] = []
        
        for entity_name, edges in snapshot.entity_edges.items():
            for rel_edge in edges:
                # 确定边的方向和端点
                # forward: 从 entity_name 指向 next_entity
                # backward: 从 next_entity 指向 entity_name
                if rel_edge.direction == "forward":
                    src_name = entity_name
                    tgt_name = rel_edge.next_entity or entity_name
                else:
                    src_name = rel_edge.next_entity or entity_name
                    tgt_name = entity_name
                
                # 构建 CandidateEdge
                candidate_edges.append(
                    CandidateEdge(
                        edge_id=rel_edge.edge_id,
                        src_name=src_name,
                        relation=rel_edge.relation,
                        tgt_name=tgt_name,
                        direction=rel_edge.direction,
                        description=rel_edge.description,
                        keywords=rel_edge.keywords,
                        weight=rel_edge.weight,
                        # 内部引用（对 Agent 不可见）
                        internal_src_ref=rel_edge.src_id,
                        internal_tgt_ref=rel_edge.tgt_id,
                    )
                )
        
        return candidate_edges

    async def _generate_fallback_answer(self) -> str:
        """生成回退答案（达到最大步数时）"""
        try:
            answer = (await self.provider.answer(self._question, mode=self.answer_mode)).strip()
            if answer:
                return answer
        except Exception:
            pass

        knowledge = self._format_knowledge().strip()
        if not knowledge or knowledge == EMPTY_KNOWLEDGE:
            return "已达到最大推理步数，当前证据不足以给出确定答案。"

        # 收集当前候选边的关系作为提示
        edge_hints = [e.to_display_text() for e in self._candidate_edges[:5]]
        edge_hint = "\n".join(f"- {h}" for h in edge_hints) if edge_hints else "无"
        
        return (
            "已达到最大推理步数，以下是基于当前探索结果的基础回复：\n"
            f"- 问题：{self._question}\n"
            f"- 候选边：\n{edge_hint}\n"
            f"- 已探索知识：\n{knowledge}"
        )

    def _build_ll_keywords(self, *, selected_edges: list[CandidateEdge], frontier: list[str]) -> list[str]:
        """构建低层关键词用于图查询"""
        unique: list[str] = []
        
        # 从选中的边提取关键词
        for edge in selected_edges:
            if edge.keywords:
                for kw in edge.keywords.split(","):
                    normalized = kw.strip()
                    if normalized and normalized not in unique:
                        unique.append(normalized)
                        if len(unique) >= 12:
                            break
            # 也添加关系名
            if edge.relation and edge.relation not in unique:
                unique.append(edge.relation)
                if len(unique) >= 12:
                    break
            
            if len(unique) >= 12:
                break
        
        # 添加 frontier 实体
        for entity in frontier:
            if entity and entity not in unique:
                unique.append(entity)
                if len(unique) >= 12:
                    break
        
        return unique

    async def _prune_paths(self, paths: list[PathTrace]) -> list[PathTrace]:
        """剪枝路径（Beam Search）"""
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

    def _build_state(self, *, done_override: bool | None = None) -> EdgeEnvState:
        """构建环境状态"""
        knowledge = self._format_knowledge()
        return EdgeEnvState(
            question=self._question,
            knowledge=knowledge,
            candidate_edges=self._candidate_edges,
            active_paths=self._active_paths,
            history=list(self._history),
            step_index=self._step_index,
            done=self._done if done_override is None else done_override,
        )

    def _format_knowledge(self) -> str:
        """格式化知识块"""
        if not self._active_paths:
            return EMPTY_KNOWLEDGE

        lines = [f"当前有 {len(self._active_paths)} 条活跃路径：", ""]
        for idx, path in enumerate(self._active_paths, start=1):
            if path.relations:
                lines.append(f"- 路径{idx}：{path.to_text()}（末端：{path.tail_entity}）")
            else:
                lines.append(f"- 路径{idx}：从 {path.tail_entity} 出发，暂无扩展。")

        return format_knowledge_body(lines)