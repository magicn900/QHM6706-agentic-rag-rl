from __future__ import annotations

import re
from typing import Any

from openai import AsyncOpenAI

from ..config import CoreAPIConfig
from ..contracts import CandidateEdge, EdgeEnvAction, EdgeEnvState
from ..prompts import (
    ANSWER_REGEX,
    EDGE_SELECT_REGEX,
    THINK_EMPTY_EDGE_FALLBACK,
    THINK_PARSE_FALLBACK_TEMPLATE,
    build_action_prompt,
)


class OpenAIActionPolicy:
    def __init__(
        self,
        *,
        model: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        temperature: float = 0.0,
    ) -> None:
        core_api = CoreAPIConfig.from_env()
        resolved_model = model or core_api.action_model
        resolved_base_url = base_url or core_api.action_base_url
        resolved_api_key = api_key or core_api.action_api_key

        if not resolved_api_key:
            raise ValueError("Missing action model API key. Set ACTION_LLM_API_KEY or LIGHTRAG_LLM_API_KEY.")

        self.model = resolved_model
        self.temperature = temperature
        self.client = AsyncOpenAI(base_url=resolved_base_url, api_key=resolved_api_key)

    @staticmethod
    def _normalize_edge_text(text: str) -> str:
        normalized = (text or "").strip().lower()
        normalized = normalized.replace("；", ";").replace("，", ",")
        normalized = normalized.replace("（", "(").replace("）", ")")
        normalized = re.sub(r"^[-*]\s*", "", normalized)
        normalized = re.sub(r"\s+", " ", normalized)
        return normalized

    def _extract_edge_block(self, content: str) -> str | None:
        edge_match = re.search(EDGE_SELECT_REGEX, content, flags=re.DOTALL)
        if edge_match:
            return edge_match.group(1).strip()

        loose_open = re.search(r"<edge_select[^>]*>(.*)$", content, flags=re.DOTALL)
        if loose_open:
            return loose_open.group(1).strip()

        return None

    @staticmethod
    def _token_set(text: str) -> set[str]:
        return {t for t in re.findall(r"[a-z0-9_]+", (text or "").lower()) if len(t) >= 2}

    def _select_fallback_edges(self, state: EdgeEnvState, k: int) -> list[CandidateEdge]:
        question_tokens = self._token_set(state.question)

        scored: list[tuple[float, int, CandidateEdge]] = []
        for idx, edge in enumerate(state.candidate_edges):
            edge_tokens = self._token_set(edge.to_display_text())
            overlap = 0.0
            if question_tokens and edge_tokens:
                overlap = len(question_tokens.intersection(edge_tokens)) / max(len(question_tokens), 1)
            scored.append((overlap, -idx, edge))

        scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return [item[2] for item in scored[: max(k, 1)]]

    def _parse_edge_selection(
        self, raw_text: str, candidate_edges: list[CandidateEdge]
    ) -> list[CandidateEdge]:
        """解析边选择文本，返回匹配的CandidateEdge列表（支持多选，用分号分隔）"""
        raw_text = (raw_text or "").strip()
        raw_text = raw_text.replace("；", ";").replace("，", ",").replace("、", ",")
        raw_text = raw_text.replace("：", ":")

        # 编号模式优先：当输出不包含边文本箭头时，优先按数字解析
        if "->" not in raw_text and candidate_edges:
            indexed_matches = re.findall(r"(?:边\s*)?(\d+)", raw_text)
            if indexed_matches:
                selected_by_index: list[CandidateEdge] = []
                seen_ids: set[str] = set()
                for token in indexed_matches:
                    idx = int(token) - 1
                    if 0 <= idx < len(candidate_edges):
                        edge = candidate_edges[idx]
                        if edge.edge_id in seen_ids:
                            continue
                        seen_ids.add(edge.edge_id)
                        selected_by_index.append(edge)
                if selected_by_index:
                    return selected_by_index

        edge_texts = [e.strip() for e in re.split(r"[;,\n]", raw_text) if e.strip()]

        if not edge_texts:
            return []

        if len(edge_texts) == 1 and edge_texts[0].isdigit():
            idx = int(edge_texts[0]) - 1
            if 0 <= idx < len(candidate_edges):
                return [candidate_edges[idx]]
            return []

        display_map = {edge.to_display_text(): edge for edge in candidate_edges}
        normalized_map = {
            self._normalize_edge_text(edge.to_display_text()): edge
            for edge in candidate_edges
        }

        matched_edges: list[CandidateEdge] = []
        for edge_text in edge_texts:
            edge_text = re.sub(r"^[-*]\s*", "", edge_text.strip())

            indexed_match = re.match(r"^边\s*(\d+)$", edge_text)
            if indexed_match:
                idx = int(indexed_match.group(1)) - 1
                if 0 <= idx < len(candidate_edges):
                    matched_edges.append(candidate_edges[idx])
                    continue

            indexed_match_dot = re.match(r"^(\d+)\.?$", edge_text)
            if indexed_match_dot:
                idx = int(indexed_match_dot.group(1)) - 1
                if 0 <= idx < len(candidate_edges):
                    matched_edges.append(candidate_edges[idx])
                    continue

            if edge_text in display_map:
                matched_edges.append(display_map[edge_text])
                continue

            normalized_text = self._normalize_edge_text(edge_text)
            if normalized_text in normalized_map:
                matched_edges.append(normalized_map[normalized_text])
                continue

            # 尝试部分匹配（双向）
            for candidate_norm, edge in normalized_map.items():
                if normalized_text and (
                    normalized_text in candidate_norm or candidate_norm in normalized_text
                ):
                    matched_edges.append(edge)
                    break

        dedup: list[CandidateEdge] = []
        seen = set()
        for edge in matched_edges:
            if edge.edge_id in seen:
                continue
            seen.add(edge.edge_id)
            dedup.append(edge)

        return dedup

    @staticmethod
    def _encode_edge_indices(selected_edges: list[CandidateEdge], candidate_edges: list[CandidateEdge]) -> str:
        """将选中的边编码为编号串（1-based）。"""
        edge_id_to_index = {
            edge.edge_id: idx for idx, edge in enumerate(candidate_edges, start=1)
        }
        indexes: list[int] = []
        seen: set[int] = set()
        for edge in selected_edges:
            idx = edge_id_to_index.get(edge.edge_id)
            if idx is None or idx in seen:
                continue
            seen.add(idx)
            indexes.append(idx)
        return "; ".join(str(i) for i in indexes)

    async def decide(self, state: EdgeEnvState) -> tuple[EdgeEnvAction, str]:
        """根据环境状态决定下一步动作"""
        action, content, _trace = await self.decide_with_trace(state)
        return action, content

    async def decide_with_trace(self, state: EdgeEnvState) -> tuple[EdgeEnvAction, str, dict[str, Any]]:
        """根据环境状态决定下一步动作（带trace）"""
        prompt = build_action_prompt(
            question=state.question,
            knowledge=state.knowledge,
            candidate_edges=state.candidate_edges,
            selection_k=max(state.selection_k, 1),
        )

        response = await self.client.chat.completions.create(
            model=self.model,
            temperature=self.temperature,
            messages=[{"role": "user", "content": prompt}],
        )
        content = response.choices[0].message.content or ""

        # 尝试解析 edge_select 标签（含半结构化容错）
        edge_block = self._extract_edge_block(content)
        answer_match = re.search(ANSWER_REGEX, content, flags=re.DOTALL)
        loose_answer_match = re.search(r"<answer>(.*)$", content, flags=re.DOTALL)

        if edge_block:
            raw_edges = edge_block
            selected_edges = self._parse_edge_selection(raw_edges, state.candidate_edges)

            if selected_edges:
                edge_indices = self._encode_edge_indices(selected_edges, state.candidate_edges)
                action = EdgeEnvAction.select_edge(edge_indices)
                edge_ids = [e.edge_id for e in selected_edges]
                return action, content, {
                    "agent_prompt": prompt,
                    "agent_raw_response": content,
                    "agent_action_type": "edge_select",
                    "agent_action_value": edge_indices,
                    "agent_action_value_text": "; ".join(e.to_display_text() for e in selected_edges),
                    "prompt": prompt,
                    "model_output": content,
                    "action_type": "edge_select",
                    "action_value": edge_indices,
                    "edge_ids": edge_ids,
                }

        if answer_match or loose_answer_match:
            answer = (answer_match.group(1) if answer_match else loose_answer_match.group(1)).strip()
            action = EdgeEnvAction.answer_now(answer)
            return action, content, {
                "agent_prompt": prompt,
                "agent_raw_response": content,
                "agent_action_type": "answer",
                "agent_action_value": answer,
                "prompt": prompt,
                "model_output": content,
                "action_type": "answer",
                "action_value": answer,
            }

        # 回退逻辑：按问题词面重叠选 top-k 候选
        if state.candidate_edges:
            fallback_k = max(state.selection_k, 1)
            fallback_edges = self._select_fallback_edges(state, fallback_k)
            fallback_value = self._encode_edge_indices(fallback_edges, state.candidate_edges)
            fallback_think = THINK_PARSE_FALLBACK_TEMPLATE.format(edge=fallback_value)
            action = EdgeEnvAction.select_edge(fallback_value)
            return action, fallback_think, {
                "agent_prompt": prompt,
                "agent_raw_response": content,
                "agent_action_type": "edge_select_fallback",
                "agent_action_value": fallback_value,
                "agent_action_value_text": "; ".join(edge.to_display_text() for edge in fallback_edges),
                "fallback_reason": "parse_failed",
                "prompt": prompt,
                "model_output": content,
                "action_type": "edge_select_fallback",
                "action_value": fallback_value,
                "edge_ids": [edge.edge_id for edge in fallback_edges],
            }

        # 无候选边，回退到回答
        fallback_answer = "信息不足，暂无法确定答案。"
        action = EdgeEnvAction.answer_now(fallback_answer)
        return action, THINK_EMPTY_EDGE_FALLBACK, {
            "agent_prompt": prompt,
            "agent_raw_response": content,
            "agent_action_type": "answer_fallback",
            "agent_action_value": fallback_answer,
            "fallback_reason": "empty_candidates",
            "prompt": prompt,
            "model_output": content,
            "action_type": "answer_fallback",
            "action_value": fallback_answer,
        }
