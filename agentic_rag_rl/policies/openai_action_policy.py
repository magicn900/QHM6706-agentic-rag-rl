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

    def _parse_edge_selection(
        self, raw_text: str, candidate_edges: list[CandidateEdge]
    ) -> list[CandidateEdge]:
        """解析边选择文本，返回匹配的CandidateEdge列表（支持多选，用分号分隔）"""
        raw_text = raw_text.strip()
        
        # 处理多选：用分号分割
        edge_texts = [e.strip() for e in raw_text.split(";") if e.strip()]
        
        if not edge_texts:
            return []
        
        # 如果只有一个元素且是数字，处理单选
        if len(edge_texts) == 1 and edge_texts[0].isdigit():
            idx = int(edge_texts[0]) - 1  # 转换为0-based
            if 0 <= idx < len(candidate_edges):
                return [candidate_edges[idx]]
            return []
        
        # 匹配每个边文本
        matched_edges: list[CandidateEdge] = []
        for edge_text in edge_texts:
            # 支持“边1 / 边 2”等编号占位写法
            indexed_match = re.match(r"^边\s*(\d+)$", edge_text)
            if indexed_match:
                idx = int(indexed_match.group(1)) - 1
                if 0 <= idx < len(candidate_edges):
                    matched_edges.append(candidate_edges[idx])
                    continue

            # 优先精确匹配
            for edge in candidate_edges:
                if edge.to_display_text() == edge_text:
                    matched_edges.append(edge)
                    break
            else:
                # 尝试部分匹配
                for edge in candidate_edges:
                    if edge_text in edge.to_display_text():
                        matched_edges.append(edge)
                        break
        
        return matched_edges

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
        )

        response = await self.client.chat.completions.create(
            model=self.model,
            temperature=self.temperature,
            messages=[{"role": "user", "content": prompt}],
        )
        content = response.choices[0].message.content or ""

        # 尝试解析 edge_select 标签
        edge_match = re.search(EDGE_SELECT_REGEX, content, flags=re.DOTALL)
        
        # 尝试解析 answer 标签
        answer_match = re.search(ANSWER_REGEX, content, flags=re.DOTALL)
        loose_answer_match = re.search(r"<answer>(.*)$", content, flags=re.DOTALL)

        if edge_match:
            raw_edges = edge_match.group(1).strip()
            selected_edges = self._parse_edge_selection(raw_edges, state.candidate_edges)
            
            if selected_edges:
                # 多选：用分号连接所有边的显示文本
                edge_texts = "; ".join(e.to_display_text() for e in selected_edges)
                action = EdgeEnvAction.select_edge(edge_texts)
                edge_ids = [e.edge_id for e in selected_edges]
                return action, content, {
                    "agent_prompt": prompt,
                    "agent_raw_response": content,
                    "agent_action_type": "edge_select",
                    "agent_action_value": edge_texts,
                    "prompt": prompt,
                    "model_output": content,
                    "action_type": "edge_select",
                    "action_value": edge_texts,
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

        # 回退逻辑：优先尝试选择第一个候选边
        if state.candidate_edges:
            fallback_edge = state.candidate_edges[0]
            fallback_think = THINK_PARSE_FALLBACK_TEMPLATE.format(edge=fallback_edge.to_display_text())
            action = EdgeEnvAction.select_edge(fallback_edge.to_display_text())
            return action, fallback_think, {
                "agent_prompt": prompt,
                "agent_raw_response": content,
                "agent_action_type": "edge_select_fallback",
                "agent_action_value": fallback_edge.to_display_text(),
                "prompt": prompt,
                "model_output": content,
                "action_type": "edge_select_fallback",
                "action_value": fallback_edge.to_display_text(),
                "edge_ids": [fallback_edge.edge_id],
            }

        # 无候选边，回退到回答
        fallback_answer = "信息不足，暂无法确定答案。"
        action = EdgeEnvAction.answer_now(fallback_answer)
        return action, THINK_EMPTY_EDGE_FALLBACK, {
            "agent_prompt": prompt,
            "agent_raw_response": content,
            "agent_action_type": "answer_fallback",
            "agent_action_value": fallback_answer,
            "prompt": prompt,
            "model_output": content,
            "action_type": "answer_fallback",
            "action_value": fallback_answer,
        }
