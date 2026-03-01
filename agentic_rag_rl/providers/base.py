from __future__ import annotations

from abc import ABC, abstractmethod

from ..contracts import SeedSnapshot


class GraphProvider(ABC):
    @abstractmethod
    async def initialize(self) -> None:
        raise NotImplementedError

    @abstractmethod
    async def finalize(self) -> None:
        raise NotImplementedError

    @abstractmethod
    async def insert_texts(self, texts: list[str]) -> None:
        raise NotImplementedError

    @abstractmethod
    async def get_snapshot(
        self,
        question: str,
        *,
        top_k: int,
        hl_keywords: list[str] | None = None,
        ll_keywords: list[str] | None = None,
    ) -> SeedSnapshot:
        raise NotImplementedError

    @abstractmethod
    async def answer(self, question: str, *, mode: str = "hybrid") -> str:
        raise NotImplementedError

    async def resolve_mid_names(self, mids: list[str]) -> dict[str, str]:
        """解析 MID 到可读名称（可选能力）。

        默认返回空映射，表示当前 provider 不支持该能力。
        """
        _ = mids
        return {}
