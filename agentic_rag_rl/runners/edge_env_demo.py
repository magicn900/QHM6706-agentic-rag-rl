"""Edge-Select 环境烟测脚本。

用途：
1. 验证 EdgeSelectionEnv 的 reset/step 主链路。
2. 输出候选边数量、动作、终止原因。
3. 作为 Phase G 的最小验收脚本。
"""
from __future__ import annotations

import asyncio
from collections import defaultdict
from dataclasses import dataclass

from agentic_rag_rl.contracts import CandidateEdge, EdgeEnvAction, SeedSnapshot
from agentic_rag_rl.envs import EdgeSelectionEnv


@dataclass(slots=True)
class DemoMockProvider:
    """用于 smoke 的最小 Provider。

    输入：question 与可选 ll_keywords。
    输出：固定结构的 SeedSnapshot，保证脚本在离线环境可复现。
    边界：不依赖外部服务，不调用真实模型。
    """

    call_count: int = 0

    async def initialize(self) -> None:
        """初始化接口占位。"""

    async def finalize(self) -> None:
        """释放接口占位。"""

    async def insert_texts(self, texts: list[str]) -> None:
        """写入接口占位。"""
        _ = texts

    async def get_snapshot(
        self,
        question: str,
        *,
        top_k: int,
        hl_keywords: list[str] | None = None,
        ll_keywords: list[str] | None = None,
    ) -> SeedSnapshot:
        """返回用于演示的快照数据。

        第一轮返回 Linux 的两条边；
        第二轮按 ll_keywords 返回一条扩展边。
        """
        _ = top_k
        _ = hl_keywords
        self.call_count += 1

        entity_edges: dict[str, list[CandidateEdge]] = defaultdict(list)
        if self.call_count == 1:
            entity_edges["Linux"].append(
                CandidateEdge(
                    edge_id="e1",
                    src_name="Linux",
                    relation="最初由...开发",
                    tgt_name="林纳斯·托瓦兹",
                    direction="forward",
                    keywords="Linux,创始人",
                    weight=0.95,
                )
            )
            entity_edges["Linux"].append(
                CandidateEdge(
                    edge_id="e2",
                    src_name="Linux",
                    relation="基于",
                    tgt_name="Unix",
                    direction="forward",
                    keywords="Linux,Unix",
                    weight=0.88,
                )
            )
        else:
            for keyword in ll_keywords or []:
                if "林纳斯" in keyword:
                    entity_edges["林纳斯·托瓦兹"].append(
                        CandidateEdge(
                            edge_id="e3",
                            src_name="林纳斯·托瓦兹",
                            relation="出生地",
                            tgt_name="赫尔辛基",
                            direction="forward",
                            keywords="芬兰,城市",
                            weight=0.82,
                        )
                    )

        return SeedSnapshot(
            question=question,
            keywords={"high_level": hl_keywords or [], "low_level": ll_keywords or []},
            entity_edges=dict(entity_edges),
            processing_info={"provider": "demo_mock"},
            raw_data={},
        )

    async def answer(self, question: str, *, mode: str = "hybrid") -> str:
        """返回固定兜底答案。"""
        _ = question
        _ = mode
        return "（demo mock answer）"


async def main() -> None:
    """执行一次最小 episode 并打印验收信息。"""
    provider = DemoMockProvider()
    env = EdgeSelectionEnv(provider=provider, beam_width=4, max_steps=2, top_k=10)

    state = await env.reset("谁开发了 Linux？")
    print(f"候选边数量(reset): {len(state.candidate_edges)}")

    if not state.candidate_edges:
        print("动作(step1): answer（无候选边，直接回答）")
        result = await env.step(EdgeEnvAction.answer_now("信息不足"))
    else:
        chosen_edge = state.candidate_edges[0].to_display_text()
        print(f"动作(step1): edge_select -> {chosen_edge}")
        result = await env.step(EdgeEnvAction.select_edge(chosen_edge))

        if not result.done:
            print("动作(step2): answer -> 结束episode")
            result = await env.step(EdgeEnvAction.answer_now("林纳斯·托瓦兹开发了 Linux。"))

    print(f"终止原因: {result.info.get('termination_reason', 'unknown')}")
    print("[OK] Edge-select smoke passed.")


if __name__ == "__main__":
    asyncio.run(main())
