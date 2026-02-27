from __future__ import annotations

import math
from collections.abc import Sequence

from openai import AsyncOpenAI

from ..config import CoreAPIConfig


class EmbeddingPruner:
    def __init__(
        self,
        *,
        model: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
    ) -> None:
        core_api = CoreAPIConfig.from_env()
        resolved_model = model or core_api.embed_model
        resolved_base_url = base_url or core_api.embed_base_url
        resolved_api_key = api_key or core_api.embed_api_key

        self.model = resolved_model
        self.client: AsyncOpenAI | None = None
        if resolved_api_key:
            self.client = AsyncOpenAI(base_url=resolved_base_url, api_key=resolved_api_key)

    async def score_texts(self, query: str, texts: Sequence[str]) -> list[float]:
        if not texts:
            return []

        if self.client is None:
            return [self._lexical_score(query, text) for text in texts]

        payload = [query, *texts]
        response = await self.client.embeddings.create(model=self.model, input=payload)
        vectors = [item.embedding for item in response.data]
        query_vec = vectors[0]
        text_vecs = vectors[1:]
        return [self._cosine(query_vec, vec) for vec in text_vecs]

    @staticmethod
    def _cosine(v1: Sequence[float], v2: Sequence[float]) -> float:
        dot = sum(a * b for a, b in zip(v1, v2))
        norm1 = math.sqrt(sum(a * a for a in v1))
        norm2 = math.sqrt(sum(b * b for b in v2))
        if norm1 == 0.0 or norm2 == 0.0:
            return 0.0
        return dot / (norm1 * norm2)

    @staticmethod
    def _lexical_score(query: str, text: str) -> float:
        query_tokens = {token.strip().lower() for token in query.split() if token.strip()}
        text_tokens = {token.strip().lower() for token in text.split() if token.strip()}
        if not query_tokens or not text_tokens:
            return 0.0
        inter = len(query_tokens.intersection(text_tokens))
        union = len(query_tokens.union(text_tokens))
        return inter / union if union else 0.0
