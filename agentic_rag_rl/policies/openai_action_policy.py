from __future__ import annotations

import re

from openai import AsyncOpenAI

from ..config import CoreAPIConfig
from ..contracts import RelationEnvAction, RelationEnvState
from ..prompts import (
    ANSWER_REGEX,
    RELATION_SELECT_REGEX,
    THINK_EMPTY_RELATION_FALLBACK,
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

    async def decide(self, state: RelationEnvState) -> tuple[RelationEnvAction, str]:
        action, content, _trace = await self.decide_with_trace(state)
        return action, content

    async def decide_with_trace(self, state: RelationEnvState) -> tuple[RelationEnvAction, str, dict[str, str]]:
        prompt = build_action_prompt(
            question=state.question,
            knowledge=state.knowledge,
            relation_set=state.relation_set,
        )

        response = await self.client.chat.completions.create(
            model=self.model,
            temperature=self.temperature,
            messages=[{"role": "user", "content": prompt}],
        )
        content = response.choices[0].message.content or ""

        relation_match = re.search(RELATION_SELECT_REGEX, content, flags=re.DOTALL)
        answer_match = re.search(ANSWER_REGEX, content, flags=re.DOTALL)

        if relation_match:
            relation = relation_match.group(1).strip()
            if relation in state.relation_set:
                action = RelationEnvAction.select_relation(relation)
                return action, content, {
                    "prompt": prompt,
                    "model_output": content,
                    "action_type": "relation_select",
                    "action_value": relation,
                }

        if answer_match:
            answer = answer_match.group(1).strip()
            action = RelationEnvAction.answer_now(answer)
            return action, content, {
                "prompt": prompt,
                "model_output": content,
                "action_type": "answer",
                "action_value": answer,
            }

        fallback_relation = state.relation_set[0] if state.relation_set else ""
        if fallback_relation:
            fallback_think = THINK_PARSE_FALLBACK_TEMPLATE.format(relation=fallback_relation)
            action = RelationEnvAction.select_relation(fallback_relation)
            return action, fallback_think, {
                "prompt": prompt,
                "model_output": content,
                "action_type": "relation_select_fallback",
                "action_value": fallback_relation,
            }

        fallback_answer = "信息不足，暂无法确定答案。"
        action = RelationEnvAction.answer_now(fallback_answer)
        return action, THINK_EMPTY_RELATION_FALLBACK, {
            "prompt": prompt,
            "model_output": content,
            "action_type": "answer_fallback",
            "action_value": fallback_answer,
        }
