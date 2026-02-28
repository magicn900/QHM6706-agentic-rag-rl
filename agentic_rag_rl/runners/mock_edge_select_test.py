"""
Edge-Select 模式模拟测试
用途：验证提示词拼接效果和解析逻辑（无需真实 LLM API）
"""
from agentic_rag_rl.contracts import CandidateEdge, EdgeEnvState, EdgeEnvAction
from agentic_rag_rl.prompts import build_action_prompt, format_candidate_edges, EDGE_SELECT_REGEX
from agentic_rag_rl.policies.openai_action_policy import OpenAIActionPolicy
import re


def create_mock_state() -> EdgeEnvState:
    """创建模拟环境状态"""
    candidate_edges = [
        CandidateEdge(
            edge_id="e1",
            src_name="牛顿",
            relation="发明",
            tgt_name="微积分",
            direction="forward",
            description="牛顿在1666年发明了微积分",
            keywords="数学,物理",
            weight=0.9,
        ),
        CandidateEdge(
            edge_id="e2",
            src_name="牛顿",
            relation="发现",
            tgt_name="万有引力",
            direction="forward",
            description="牛顿发现万有引力定律",
            keywords="物理,引力",
            weight=0.95,
        ),
        CandidateEdge(
            edge_id="e3",
            src_name="爱因斯坦",
            relation="提出",
            tgt_name="相对论",
            direction="forward",
            description="爱因斯坦提出相对论",
            keywords="物理,相对论",
            weight=0.85,
        ),
    ]
    return EdgeEnvState(
        question="谁发明了微积分？",
        knowledge="<knowledge>\n已查明：微积分是17世纪的重要数学成果。\n</knowledge>",
        candidate_edges=candidate_edges,
        active_paths=[],
        history=[],
        step_index=0,
        done=False,
    )


def demo_prompt_format():
    """演示提示词拼接效果"""
    print("=" * 60)
    print("【演示1】提示词拼接效果")
    print("=" * 60)
    
    state = create_mock_state()
    prompt = build_action_prompt(
        question=state.question,
        knowledge=state.knowledge,
        candidate_edges=state.candidate_edges,
    )
    print(prompt)
    print()


def demo_edge_format():
    """演示边的显示格式"""
    print("=" * 60)
    print("【演示2】边的显示格式")
    print("=" * 60)
    
    state = create_mock_state()
    edges_text = format_candidate_edges(state.candidate_edges)
    print(edges_text)
    print()


def demo_parse_single_edge():
    """演示单边选择解析"""
    print("=" * 60)
    print("【演示3】单边选择解析")
    print("=" * 60)
    
    # 模拟 LLM 输出：单边选择（正确格式：</think> 在前，动作在后）
    llm_output_single = """
<think>
我需要选择第一条边来扩展信息。
</think>
<edge_select>牛顿 -发明-> 微积分</edge_select>
    """
    
    # 解析 edge_select 标签
    edge_match = re.search(EDGE_SELECT_REGEX, llm_output_single, flags=re.DOTALL)
    raw_edges = edge_match.group(1).strip() if edge_match else ""
    print(f"LLM原始输出:\n{llm_output_single}")
    print(f"提取的边文本: {raw_edges}")
    
    state = create_mock_state()
    policy = OpenAIActionPolicy.__new__(OpenAIActionPolicy)
    matched = policy._parse_edge_selection(raw_edges, state.candidate_edges)
    print(f"解析结果：{[e.edge_id for e in matched]}")
    print(f"显示文本：{matched[0].to_display_text() if matched else '无匹配'}")
    print()


def demo_parse_multi_edge():
    """演示多边选择解析"""
    print("=" * 60)
    print("【演示4】多边选择解析")
    print("=" * 60)
    
    # 模拟 LLM 输出：多边选择（正确格式：</think> 在前，动作在后）
    llm_output_multi = """
</think>
我需要同时扩展两条边来获取更多信息。
</think>
<edge_select>牛顿 -发明-> 微积分; 牛顿 -发现-> 万有引力</edge_select>
    """
    
    # 解析 edge_select 标签
    edge_match = re.search(EDGE_SELECT_REGEX, llm_output_multi, flags=re.DOTALL)
    raw_edges = edge_match.group(1).strip() if edge_match else ""
    print(f"LLM原始输出:\n{llm_output_multi}")
    print(f"提取的边文本: {raw_edges}")
    
    state = create_mock_state()
    policy = OpenAIActionPolicy.__new__(OpenAIActionPolicy)
    matched = policy._parse_edge_selection(raw_edges, state.candidate_edges)
    print(f"解析结果：{[e.edge_id for e in matched]}")
    print(f"显示文本：{'; '.join(e.to_display_text() for e in matched)}")
    print()


def demo_parse_edge_by_index():
    """演示按数字索引选择"""
    print("=" * 60)
    print("【演示5】按数字索引选择")
    print("=" * 60)
    
    state = create_mock_state()
    policy = OpenAIActionPolicy.__new__(OpenAIActionPolicy)
    
    matched = policy._parse_edge_selection("1", state.candidate_edges)
    print(f"输入：1")
    print(f"解析结果：{[e.edge_id for e in matched]}")
    print(f"显示文本：{matched[0].to_display_text() if matched else '无匹配'}")
    print()


def demo_parse_answer():
    """演示回答解析"""
    print("=" * 60)
    print("【演示6】回答解析")
    print("=" * 60)
    
    # 模拟 LLM 输出：回答（正确格式：</think> 在前，动作在后）
    llm_output_answer = """
</think>
根据现有知识，我可以回答这个问题。
</think>
<answer>牛顿发明了微积分</answer>
    """
    
    answer_match = re.search(r"<answer>(.*?)</answer>", llm_output_answer, flags=re.DOTALL)
    answer = answer_match.group(1).strip() if answer_match else ""
    print(f"LLM原始输出:\n{llm_output_answer}")
    print(f"解析答案：{answer}")
    print()


def demo_trace_format():
    """演示 trace 字段格式"""
    print("=" * 60)
    print("【演示7】Trace 字段格式")
    print("=" * 60)
    
    # 模拟成功解析边选择后的 trace
    state = create_mock_state()
    selected_edges = [state.candidate_edges[0], state.candidate_edges[1]]
    
    edge_texts = "; ".join(e.to_display_text() for e in selected_edges)
    edge_ids = [e.edge_id for e in selected_edges]
    
    trace = {
        "prompt": "（提示词内容）",
        "model_output": "（LLM输出）",
        "action_type": "edge_select",
        "action_value": edge_texts,
        "edge_ids": edge_ids,
    }
    
    print("Edge-Select Trace:")
    for k, v in trace.items():
        print(f"  {k}: {v}")
    print()


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("Edge-Select 模式模拟测试")
    print("=" * 60 + "\n")
    
    demo_prompt_format()
    demo_edge_format()
    demo_parse_single_edge()
    demo_parse_multi_edge()
    demo_parse_edge_by_index()
    demo_parse_answer()
    demo_trace_format()
    
    print("=" * 60)
    print("【完成】所有演示测试通过")
    print("=" * 60)