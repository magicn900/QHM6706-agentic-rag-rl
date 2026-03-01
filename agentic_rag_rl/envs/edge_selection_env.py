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
import re

from ..contracts import (
    CandidateEdge,
    EdgeEnvAction,
    EdgeEnvState,
    PathTrace,
    SeedSnapshot,
    StepResult,
)
from ..prompts import EMPTY_KNOWLEDGE, format_knowledge_body
from ..providers import GraphProvider
from ..utils import EdgeReranker, EmbeddingPruner


class EdgeSelectionEnv:
    """Edge-Select 模式的环境类
    
    - Agent 选择的是完整边（src -relation-> tgt），而非仅关系名
    - 状态中使用 candidate_edges（可读边列表）
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
        selection_k: int = 0,
        enable_rerank: bool = False,
        rerank_trigger_n: int = 20,
        rerank_top_k: int = 12,
    ) -> None:
        self.provider = provider
        self.beam_width = beam_width
        self.max_steps = max_steps
        self.top_k = top_k
        self.answer_mode = answer_mode
        self.selection_k = max(selection_k, 0)
        self.enable_rerank = enable_rerank
        self.rerank_trigger_n = max(rerank_trigger_n, 1)
        self.rerank_top_k = max(rerank_top_k, 1)
        self.pruner = EmbeddingPruner()
        self.reranker = EdgeReranker()

        self._question = ""
        self._step_index = 0
        self._done = False
        self._history: list[dict[str, str]] = []
        self._active_paths: list[PathTrace] = []
        self._snapshot: SeedSnapshot | None = None
        self._candidate_edges: list[CandidateEdge] = []  # 当前候选边
        self._candidate_edges_total: int = 0

    async def reset(
        self,
        question: str,
        *,
        start_mode: str | None = None,
        seed_entities: list[str] | None = None,
        seed_mids: list[str] | None = None,
    ) -> EdgeEnvState:
        """重置环境到初始状态。

        默认保持历史行为：未提供起始点时走 question 检索。
        若提供起始点且未显式指定 start_mode，则自动切换到 webqsp。

        Args:
            question: 用户问题
            start_mode: question/webqsp/hybrid/auto 或 None
            seed_entities: 显式起始实体名列表
            seed_mids: 显式起始 MID 列表

        Returns:
            EdgeEnvState: 初始环境状态
        """
        has_seed = bool(seed_entities or seed_mids)

        normalized_mode = (start_mode or "auto").strip().lower()
        if normalized_mode == "auto":
            normalized_mode = "webqsp" if has_seed else "question"
        if normalized_mode not in {"question", "webqsp", "hybrid"}:
            normalized_mode = "question"

        self._question = question.strip()
        self._step_index = 0
        self._done = False
        self._history = []

        hl_keywords: list[str] = [f"__start_mode__:{normalized_mode}"]
        if normalized_mode in {"webqsp", "hybrid"}:
            for mid in seed_mids or []:
                normalized_mid = (mid or "").strip()
                if normalized_mid:
                    hl_keywords.append(f"mid:{normalized_mid}")
            for name in seed_entities or []:
                normalized_name = (name or "").strip()
                if normalized_name:
                    hl_keywords.append(f"name:{normalized_name}")

        snapshot = await self.provider.get_snapshot(
            question=self._question,
            top_k=self.top_k,
            hl_keywords=hl_keywords,
        )
        self._snapshot = snapshot

        # 收集 provider 返回的候选边
        await self._refresh_candidate_edges(snapshot)

        # 初始化活跃路径（从召回的实体出发）
        self._active_paths = [
            PathTrace(nodes=[entity_name], relations=[], score=0.0)
            for entity_name in snapshot.entity_edges.keys()
        ]
        self._active_paths = await self._prune_paths(self._active_paths)

        return self._build_state()

    async def reset_with_starting_points(
        self,
        question: str,
        *,
        start_mode: str = "question",
        seed_entities: list[str] | None = None,
        seed_mids: list[str] | None = None,
    ) -> EdgeEnvState:
        """兼容旧调用：转发到 reset。"""
        return await self.reset(
            question,
            start_mode=start_mode,
            seed_entities=seed_entities,
            seed_mids=seed_mids,
        )

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

        # 选边策略：候选不足时全选，候选充足时对齐 selection_k
        selected_edges, selection_meta = self._apply_selection_policy(selected_edges)
        if not selected_edges:
            return StepResult(
                state=self._build_state(),
                reward=-0.5,
                done=False,
                info={"reason": "no_matching_edges", "termination_reason": "invalid_action"},
            )

        # 执行边扩展
        result = await self._expand_with_edges(selected_edges, selection_meta=selection_meta)
        return result

    async def _expand_with_edges(
        self,
        selected_edges: list[CandidateEdge],
        *,
        selection_meta: dict[str, int | bool] | None = None,
    ) -> StepResult:
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

        # 多边分叉扩展（边-路径可达性约束）
        for path in self._active_paths:
            for edge in selected_edges:
                if not self._is_edge_reachable_from_path(edge=edge, path=path):
                    continue

                tail = self._edge_next_entity(edge)

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
        await self._refresh_candidate_edges(self._snapshot, selected_edges=selected_edges)

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
            "effective_edges_count": len(selected_edges),
            "frontier_count": len(frontier),
            "cycle_pruned": cycle_pruned,
            "selection_k": self.selection_k,
            "auto_selected_all": bool((selection_meta or {}).get("auto_selected_all", False)),
            "auto_filled_edges": int((selection_meta or {}).get("auto_filled_edges", 0)),
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
        
        normalized_text = (edge_text or "").strip()
        normalized_text = normalized_text.replace("；", ";").replace("，", ",").replace("、", ",")

        # 先尝试按分号/逗号/换行分割
        parts = [p.strip() for p in re.split(r"[;,\n]", normalized_text) if p.strip()]
        
        for part in parts:
            # 尝试解析为数字索引
            if part.isdigit():
                idx = int(part) - 1  # 转换为 0 索引
                if 0 <= idx < len(self._candidate_edges):
                    selected.append(self._candidate_edges[idx])
                continue

            # 支持“边1”或“1.”
            match_edge_num = re.match(r"^边\s*(\d+)$", part)
            if match_edge_num:
                idx = int(match_edge_num.group(1)) - 1
                if 0 <= idx < len(self._candidate_edges):
                    selected.append(self._candidate_edges[idx])
                continue

            match_num_dot = re.match(r"^(\d+)\.?$", part)
            if match_num_dot:
                idx = int(match_num_dot.group(1)) - 1
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

    def _apply_selection_policy(self, selected_edges: list[CandidateEdge]) -> tuple[list[CandidateEdge], dict[str, int | bool]]:
        """应用每步选边数量策略。"""
        target = self.selection_k
        meta: dict[str, int | bool] = {
            "auto_selected_all": False,
            "auto_filled_edges": 0,
        }

        if target <= 0:
            return selected_edges, meta

        # 当候选边不足 selection_k，且动作是 edge_select，直接全选
        if self._candidate_edges and len(self._candidate_edges) <= target:
            meta["auto_selected_all"] = True
            return list(self._candidate_edges), meta

        if not selected_edges:
            return [], meta

        trimmed = list(selected_edges[:target])
        if len(trimmed) < target:
            selected_ids = {edge.edge_id for edge in trimmed}
            for edge in self._candidate_edges:
                if edge.edge_id in selected_ids:
                    continue
                trimmed.append(edge)
                selected_ids.add(edge.edge_id)
                meta["auto_filled_edges"] = int(meta["auto_filled_edges"]) + 1
                if len(trimmed) >= target:
                    break

        return trimmed[:target], meta

    @staticmethod
    def _edge_start_entity(edge: CandidateEdge) -> str:
        """返回边扩展时的起始实体（需与路径尾实体匹配）。"""
        if edge.direction == "forward":
            return edge.src_name
        return edge.tgt_name

    @staticmethod
    def _edge_next_entity(edge: CandidateEdge) -> str:
        """返回边扩展时的下一跳实体。"""
        if edge.direction == "forward":
            return edge.tgt_name
        return edge.src_name

    def _is_edge_reachable_from_path(self, *, edge: CandidateEdge, path: PathTrace) -> bool:
        """判断候选边是否可从当前路径末端扩展。"""
        tail = (path.tail_entity or "").strip()
        start = (self._edge_start_entity(edge) or "").strip()
        if not tail or not start:
            return False
        return tail == start

    async def _refresh_candidate_edges(
        self,
        snapshot: SeedSnapshot,
        *,
        selected_edges: list[CandidateEdge] | None = None,
    ) -> None:
        """刷新候选边：排序 -> 可选重排 -> Top-K 剪枝 -> 去除已选。"""
        converted_edges = self._convert_edges(snapshot)
        self._candidate_edges_total = len(converted_edges)

        ranked_edges = converted_edges
        rerank_applied = False
        if self.enable_rerank and len(ranked_edges) >= self.rerank_trigger_n:
            ranked_edges = await self.reranker.rank(self._question, ranked_edges)
            rerank_applied = True

        # 仅在触发重排后应用 rerank_top_k，避免常规路径下过早截断候选边。
        if rerank_applied and len(ranked_edges) > self.rerank_top_k:
            ranked_edges = ranked_edges[: self.rerank_top_k]

        if selected_edges:
            selected_texts = {edge.to_display_text() for edge in selected_edges}
            filtered_edges = [edge for edge in ranked_edges if edge.to_display_text() not in selected_texts]
            self._candidate_edges = filtered_edges if filtered_edges else ranked_edges
            return

        self._candidate_edges = ranked_edges

    def _convert_edges(self, snapshot: SeedSnapshot) -> list[CandidateEdge]:
        """将 provider 返回的 CandidateEdge 收集为列表
        
        Provider 已经返回 CandidateEdge（翻译墙在 Provider 层），
        这里只需要收集和去重。
        
        Args:
            snapshot: provider 返回的快照
            
        Returns:
            CandidateEdge 列表
        """
        all_edges: list[CandidateEdge] = []
        seen_keys: set[tuple[str, str, str, str]] = set()
        
        for entity_name, edges in snapshot.entity_edges.items():
            for edge in edges:
                dedupe_key = (
                    edge.src_name,
                    edge.relation,
                    edge.tgt_name,
                    edge.direction,
                )
                if dedupe_key in seen_keys:
                    continue
                seen_keys.add(dedupe_key)
                all_edges.append(edge)

        # 按问题语义相关性重排，提升 Agent 首屏候选质量
        all_edges.sort(key=self._score_edge_relevance, reverse=True)
        return all_edges

    def _score_edge_relevance(self, edge: CandidateEdge) -> float:
        """计算候选边与问题的相关性分数。

        目标：
        1. 提升与问题谓词语义一致的边排序；
        2. 降低出版/许可证/节目元数据边对决策的干扰；
        3. 不改变边集合，仅改变呈现顺序。
        """
        question = (self._question or "").lower()
        relation = (edge.relation or "").lower()
        edge_text = edge.to_display_text().lower()

        # 基础词面重叠分
        query_tokens = {t for t in re.findall(r"[a-z0-9_]+", question) if len(t) >= 2}
        edge_tokens = {t for t in re.findall(r"[a-z0-9_]+", edge_text) if len(t) >= 2}
        lexical = 0.0
        if query_tokens and edge_tokens:
            lexical = len(query_tokens.intersection(edge_tokens)) / max(len(query_tokens), 1)

        score = lexical

        # 关系语义匹配加权
        if "influenc" in question and "influenc" in relation:
            score += 3.0

        if any(word in question for word in ["mom", "mother", "father", "parent"]):
            if any(word in relation for word in ["parent", "children", "mother", "father"]):
                score += 2.5

        if any(word in question for word in ["play", "played", "actor", "film", "movie"]):
            if any(word in relation for word in ["film", "actor", "performance", "character", "starring"]):
                score += 2.0
            if relation.startswith("tv.tv_series_episode"):
                score -= 1.5

        # 常见元数据降权
        metadata_markers = [
            "publication_date",
            "place_of_publication",
            "editions",
            "license",
            "tvrage_id",
            "episode_number",
            "air_date",
        ]
        if any(marker in relation for marker in metadata_markers):
            score -= 0.8

        # 问句意图增强（地点/时间/职位/政党）
        if any(word in question for word in ["where", "located", "location", "border", "country", "state", "city"]):
            if any(word in relation for word in ["location.", "containedby", "country", "place_of", "region", "timezone", "time_zone"]):
                score += 1.8

        if any(word in question for word in ["when", "year", "date", "born", "died"]):
            if any(word in relation for word in ["date", "start_date", "end_date", "time", "birth", "death", "inauguration"]):
                score += 2.0

        if any(word in question for word in ["who", "leader", "governor", "husband", "wife", "mom", "mother", "father"]):
            if any(word in relation for word in ["office_holders", "spouse", "parents", "children", "person", "actor"]):
                score += 1.6

        if "party" in question and any(word in relation for word in ["political", "party", "ideology", "affiliation"]):
            score += 2.2

        # 对与问题意图明显不匹配的高噪声域做强降权（不直接删除，仅压后）
        if self._is_noisy_relation_for_question(question=question, relation=relation):
            score -= 2.4

        return score

    def _is_noisy_relation_for_question(self, *, question: str, relation: str) -> bool:
        """判断关系是否是当前问句下的噪声域关系。"""
        relation = relation.lower()
        question = question.lower()

        # 若用户问题本身是媒体/出版领域，避免误伤对应关系
        media_q = any(k in question for k in [
            "music", "song", "album", "track", "singer", "band",
            "book", "novel", "author", "publisher",
            "movie", "film", "actor", "actress", "director",
            "tv", "episode", "series",
        ])

        noisy_prefixes = [
            "music.",
            "book.",
            "tv.tv_series_episode",
            "type.user.",
            "base.wordnet",
            "common.licensed_object",
            "cvg.",
            "pipeline.",
        ]
        hit_noisy = any(relation.startswith(prefix) for prefix in noisy_prefixes)
        if not hit_noisy:
            return False

        if media_q:
            return False

        return True

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
            # 优先注入内部实体引用（MID），保证后续扩展可被 Freebase 解析
            internal_refs = [edge.internal_src_ref, edge.internal_tgt_ref]
            for ref in internal_refs:
                normalized_ref = (ref or "").strip()
                if normalized_ref and normalized_ref not in unique:
                    unique.append(normalized_ref)
                    if len(unique) >= 12:
                        break

            if len(unique) >= 12:
                break

            if edge.keywords:
                for kw in edge.keywords.split(","):
                    normalized = kw.strip()
                    if normalized and normalized not in unique:
                        unique.append(normalized)
                        if len(unique) >= 12:
                            break
            # 也添加关系名（仅当看起来像实体名时，排除 book.written_work.author 格式）
            # 关系名会传递给 Freebase 实体搜索，导致 "Could not resolve MID" 错误
            if edge.relation and edge.relation not in unique and "." not in edge.relation:
                unique.append(edge.relation)
                if len(unique) >= 12:
                    break
            
            if len(unique) >= 12:
                break
        
        # 添加 frontier 实体
        for entity in frontier:
            # 匿名占位实体不可直接用于实体搜索，避免无效请求
            if entity.startswith("未知实体#"):
                continue
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
            selection_k=self.selection_k,
            candidate_edges_total=self._candidate_edges_total,
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