from __future__ import annotations

import json
import re

from openai import AsyncOpenAI

from ..config import CoreAPIConfig
from ..contracts import CandidateEdge


class EdgeReranker:
    """候选边重排器。

    优先使用外接重排模型；不可用或解析失败时自动回退到词面打分。
    """

    def __init__(
        self,
        *,
        model: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
    ) -> None:
        core_api = CoreAPIConfig.from_env()
        resolved_model = model or core_api.rerank_model
        resolved_base_url = base_url or core_api.rerank_base_url
        resolved_api_key = api_key or core_api.rerank_api_key

        self.model = resolved_model
        self.client: AsyncOpenAI | None = None
        if resolved_api_key:
            self.client = AsyncOpenAI(base_url=resolved_base_url, api_key=resolved_api_key)

    async def rank(self, question: str, candidate_edges: list[CandidateEdge]) -> list[CandidateEdge]:
        """按相关性对候选边排序（降序）。"""
        if len(candidate_edges) <= 1:
            return list(candidate_edges)

        if self.client is None:
            return self._lexical_rank(question, candidate_edges)

        try:
            ranked = await self._rank_with_model(question, candidate_edges)
            if ranked:
                return ranked
        except Exception:
            pass

        return self._lexical_rank(question, candidate_edges)

    async def _rank_with_model(self, question: str, candidate_edges: list[CandidateEdge]) -> list[CandidateEdge]:
        lines = [f"{idx}. {edge.to_display_text()}" for idx, edge in enumerate(candidate_edges, start=1)]
        prompt = (
            "你是知识图边重排器。请根据问题相关性给候选边打分并排序。\n"
            "输出必须是 JSON 对象，格式："
            '{"ranking":[{"edge_index":1,"score":0.98}]}，'
            "不要输出任何额外文本。\n"
            "score 范围 [0,1]，数值越大越相关。\n\n"
            f"问题：{question}\n\n"
            "候选边：\n"
            f"{chr(10).join(lines)}"
        )

        response = await self.client.chat.completions.create(
            model=self.model,
            temperature=0.0,
            messages=[{"role": "user", "content": prompt}],
        )
        content = (response.choices[0].message.content or "").strip()

        data = self._extract_json(content)
        ranking = data.get("ranking") if isinstance(data, dict) else None
        if not isinstance(ranking, list):
            return []

        score_by_index: dict[int, float] = {}
        for item in ranking:
            if not isinstance(item, dict):
                continue
            idx = item.get("edge_index")
            score = item.get("score")
            if not isinstance(idx, int) or not isinstance(score, (int, float)):
                continue
            if 1 <= idx <= len(candidate_edges):
                score_by_index[idx - 1] = float(score)

        if not score_by_index:
            return []

        scored_items: list[tuple[float, int, CandidateEdge]] = []
        for idx, edge in enumerate(candidate_edges):
            scored_items.append((score_by_index.get(idx, 0.0), idx, edge))

        scored_items.sort(key=lambda item: (item[0], -item[1]), reverse=True)
        return [item[2] for item in scored_items]

    def _lexical_rank(self, question: str, candidate_edges: list[CandidateEdge]) -> list[CandidateEdge]:
        q_tokens = self._tokens(question)
        scored: list[tuple[float, int, CandidateEdge]] = []

        for idx, edge in enumerate(candidate_edges):
            edge_text = edge.to_display_text()
            e_tokens = self._tokens(edge_text)
            overlap = 0.0
            if q_tokens and e_tokens:
                overlap = len(q_tokens.intersection(e_tokens)) / len(q_tokens)
            scored.append((overlap, idx, edge))

        scored.sort(key=lambda item: (item[0], -item[1]), reverse=True)
        return [item[2] for item in scored]

    @staticmethod
    def _extract_json(content: str) -> dict:
        content = content.strip()
        if not content:
            return {}

        try:
            loaded = json.loads(content)
            return loaded if isinstance(loaded, dict) else {}
        except Exception:
            pass

        match = re.search(r"\{.*\}", content, flags=re.DOTALL)
        if not match:
            return {}

        try:
            loaded = json.loads(match.group(0))
            return loaded if isinstance(loaded, dict) else {}
        except Exception:
            return {}

    @staticmethod
    def _tokens(text: str) -> set[str]:
        return {token for token in re.findall(r"[a-zA-Z0-9_]+", (text or "").lower()) if len(token) >= 2}
