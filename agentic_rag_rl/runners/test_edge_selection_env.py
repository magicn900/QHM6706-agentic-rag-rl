"""
EdgeSelectionEnv 集成测试
用途：验证 Edge-Select 模式的环境完整流程（reset/step）
"""
import asyncio
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from agentic_rag_rl.envs import EdgeSelectionEnv
from agentic_rag_rl.contracts import (
    CandidateEdge,
    EdgeEnvAction,
    PathTrace,
    SeedSnapshot,
)


@dataclass
class MockGraphProvider:
    """模拟 GraphProvider 用于测试"""
    
    mock_edges: dict[str, list[dict]] = field(default_factory=dict)
    call_count: int = 0
    
    async def initialize(self) -> None:
        pass
    
    async def finalize(self) -> None:
        pass
    
    async def insert_texts(self, texts: list[str]) -> None:
        pass
    
    async def get_snapshot(
        self,
        question: str,
        *,
        top_k: int,
        hl_keywords: list[str] | None = None,
        ll_keywords: list[str] | None = None,
    ) -> SeedSnapshot:
        self.call_count += 1
        
        # 构建返回数据（使用 CandidateEdge）
        entity_edges: dict[str, list[CandidateEdge]] = defaultdict(list)
        
        # 第一轮：返回初始实体及其边
        if self.call_count == 1:
            # 初始实体：Linux
            entity_edges["Linux"] = [
                CandidateEdge(
                    edge_id="e1",
                    src_name="Linux",
                    relation="基于",
                    tgt_name="Unix",
                    direction="forward",
                    description="Linux基于Unix",
                    keywords="操作系统,Unix",
                    weight=0.9,
                    internal_src_ref="m.0x9",
                    internal_tgt_ref="m.0y2",
                ),
                CandidateEdge(
                    edge_id="e2",
                    src_name="Linux",
                    relation="最初由...开发",
                    tgt_name="林纳斯·托瓦兹",
                    direction="forward",
                    description="Linux由林纳斯·托瓦兹开发",
                    keywords="Linux,创始人",
                    weight=0.95,
                    internal_src_ref="m.0x9",
                    internal_tgt_ref="m.0z1",
                ),
            ]
        else:
            # 后续轮次：返回扩展的实体边
            for keyword in (ll_keywords or []):
                if "林纳斯" in keyword:
                    entity_edges["林纳斯·托瓦兹"] = [
                        CandidateEdge(
                            edge_id="e3",
                            src_name="林纳斯·托瓦兹",
                            relation="出生地",
                            tgt_name="赫尔辛基",
                            direction="forward",
                            description="林纳斯出生于赫尔辛基",
                            keywords="芬兰,城市",
                            weight=0.8,
                            internal_src_ref="m.0z1",
                            internal_tgt_ref="m.0w3",
                        ),
                    ]
                elif "Unix" in keyword:
                    entity_edges["Unix"] = [
                        CandidateEdge(
                            edge_id="e4",
                            src_name="Unix",
                            relation="发明",
                            tgt_name="肯·汤普逊",
                            direction="forward",
                            description="Unix由肯·汤普逊发明",
                            keywords="Unix,贝尔实验室",
                            weight=0.85,
                            internal_src_ref="m.0y2",
                            internal_tgt_ref="m.0v4",
                        ),
                    ]
        
        return SeedSnapshot(
            question=question,
            keywords={"high_level": [], "low_level": ll_keywords or []},
            entity_edges=dict(entity_edges),
            processing_info={},
            raw_data={},
        )
    
    async def answer(self, question: str, *, mode: str = "hybrid") -> str:
        return "（Mock答案）"


async def test_reset():
    """测试 reset 方法"""
    print("=" * 60)
    print("【测试1】环境重置")
    print("=" * 60)
    
    provider = MockGraphProvider()
    env = EdgeSelectionEnv(provider=provider, beam_width=4, max_steps=4, top_k=10)
    
    state = await env.reset("谁发明了Linux?")
    
    print(f"问题: {state.question}")
    print(f"步数: {state.step_index}")
    print(f"完成: {state.done}")
    print(f"候选边数量: {len(state.candidate_edges)}")
    print(f"活跃路径数量: {len(state.active_paths)}")
    print()
    
    for idx, edge in enumerate(state.candidate_edges, 1):
        print(f"  边{idx}: {edge.to_display_text()}")
    
    print()
    print("知识块:")
    print(state.knowledge)
    print()
    
    assert state.question == "谁发明了Linux?"
    assert state.step_index == 0
    assert len(state.candidate_edges) == 2
    print("✅ 测试1 通过")
    print()


async def test_step_edge_select():
    """测试边选择动作"""
    print("=" * 60)
    print("【测试2】边选择动作")
    print("=" * 60)
    
    provider = MockGraphProvider()
    env = EdgeSelectionEnv(provider=provider, beam_width=4, max_steps=4, top_k=10)
    
    # 重置环境
    state = await env.reset("谁发明了Linux?")
    print(f"初始候选边数量: {len(state.candidate_edges)}")
    
    # 选择第一条边
    action = EdgeEnvAction.select_edge("Linux -最初由...开发-> 林纳斯·托瓦兹")
    result = await env.step(action)
    
    print(f"执行动作: edge_select")
    print(f"新候选边数量: {len(result.state.candidate_edges)}")
    print(f"新步数: {result.state.step_index}")
    print(f"奖励: {result.reward}")
    print(f"完成: {result.done}")
    print(f"终止原因: {result.info.get('termination_reason', 'N/A')}")
    print()
    
    print("知识块:")
    print(result.state.knowledge)
    print()
    
    for idx, edge in enumerate(result.state.candidate_edges, 1):
        print(f"  边{idx}: {edge.to_display_text()}")
    
    print()
    assert result.state.step_index == 1
    assert len(result.state.candidate_edges) > 0
    print("✅ 测试2 通过")
    print()


async def test_step_answer():
    """测试回答动作"""
    print("=" * 60)
    print("【测试3】回答动作")
    print("=" * 60)
    
    provider = MockGraphProvider()
    env = EdgeSelectionEnv(provider=provider, beam_width=4, max_steps=4, top_k=10)
    
    # 重置环境
    await env.reset("谁发明了Linux?")
    
    # 直接回答
    action = EdgeEnvAction.answer_now("林纳斯·托瓦兹发明了Linux")
    result = await env.step(action)
    
    print(f"执行动作: answer")
    print(f"答案: {result.info.get('final_answer')}")
    print(f"奖励: {result.reward}")
    print(f"完成: {result.done}")
    print(f"终止原因: {result.info.get('termination_reason')}")
    
    assert result.done is True
    assert result.info.get("termination_reason") == "answer_provided"
    print()
    print("✅ 测试3 通过")
    print()


async def test_max_steps_termination():
    """测试最大步数终止"""
    print("=" * 60)
    print("【测试4】最大步数终止")
    print("=" * 60)
    
    provider = MockGraphProvider()
    # 设置 max_steps=2 以快速触发
    env = EdgeSelectionEnv(provider=provider, beam_width=4, max_steps=2, top_k=10)
    
    # 重置环境
    await env.reset("谁发明了Linux?")
    
    # 第一次边选择
    action1 = EdgeEnvAction.select_edge("Linux -最初由...开发-> 林纳斯·托瓦兹")
    result1 = await env.step(action1)
    print(f"第1步 - 完成: {result1.done}, 步数: {result1.state.step_index}")
    
    # 第二次边选择（将触发 max_steps）
    action2 = EdgeEnvAction.select_edge("林纳斯·托瓦兹 -出生地-> 赫尔辛基")
    result2 = await env.step(action2)
    print(f"第2步 - 完成: {result2.done}, 步数: {result2.state.step_index}")
    print(f"终止原因: {result2.info.get('termination_reason')}")
    print(f"自动生成答案: {result2.info.get('auto_generated', False)}")
    
    assert result2.done is True
    assert result2.info.get("termination_reason") == "max_steps_reached"
    print()
    print("✅ 测试4 通过")
    print()


async def test_empty_edge_selection():
    """测试空边选择"""
    print("=" * 60)
    print("【测试5】空边选择")
    print("=" * 60)
    
    provider = MockGraphProvider()
    env = EdgeSelectionEnv(provider=provider, beam_width=4, max_steps=4, top_k=10)
    
    await env.reset("谁发明了Linux?")
    
    # 发送空的边选择
    action = EdgeEnvAction(edge_select="", answer=None)
    result = await env.step(action)
    
    print(f"奖励: {result.reward}")
    print(f"完成: {result.done}")
    print(f"终止原因: {result.info.get('termination_reason')}")
    
    assert result.done is False
    assert result.reward < 0
    print()
    print("✅ 测试5 通过")
    print()


async def test_multi_edge_selection():
    """测试多边同时选择"""
    print("=" * 60)
    print("【测试6】多边同时选择")
    print("=" * 60)
    
    provider = MockGraphProvider()
    env = EdgeSelectionEnv(provider=provider, beam_width=4, max_steps=4, top_k=10)
    
    # 重置环境
    await env.reset("谁发明了Linux?")
    
    # 选择两条边（分号分隔）
    action = EdgeEnvAction.select_edge("Linux -基于-> Unix; Linux -最初由...开发-> 林纳斯·托瓦兹")
    result = await env.step(action)
    
    print(f"选中边数: {result.info.get('edges_count')}")
    print(f"选中边ID: {result.info.get('edges_selected')}")
    print(f"步数: {result.state.step_index}")
    print(f"奖励: {result.reward}")
    
    assert result.info.get("edges_count") == 2
    print()
    print("✅ 测试6 通过")
    print()


async def main():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("EdgeSelectionEnv 集成测试")
    print("=" * 60 + "\n")
    
    await test_reset()
    await test_step_edge_select()
    await test_step_answer()
    await test_max_steps_termination()
    await test_empty_edge_selection()
    await test_multi_edge_selection()
    
    print("=" * 60)
    print("✅ 所有测试通过")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())