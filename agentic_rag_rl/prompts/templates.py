from __future__ import annotations

from agentic_rag_rl.contracts import CandidateEdge

# ========== System & Format Prompts ==========
SYSTEM_PROMPT = "你是一个在知识图上进行多路径推理的智能助手。"
ACTION_FORMAT_PROMPT = (
    "输出必须先在<think></think>中进行逐步思考，然后给一个动作："
    "<edge_select>边1; 边2; ...</edge_select> 或 <answer>答案</answer>。\n"
    "边的格式为：实体A -关系-> 实体B\n"
    "如需选择多条边，用分号(;)分隔每条边，可选1-3条。\n"
    "<edge_select>中必须逐字复制<candidate_edges>里的完整边文本，不允许输出“边1/边2/编号”占位词。"
)
EDGE_CONSTRAINT_PROMPT = "只能从<candidate_edges>里选择一条或多条边。多条边用分号(;)分隔。"
DECISION_HINT_PROMPT = (
    "如果信息还不足请选与最相关的边扩展（建议1-3条）；如果足够请直接回答。\n"
    "优先选择与问题谓词语义直接匹配的关系；出版、版本、日期、许可证等元数据关系通常不构成最终答案依据。"
)

# ========== Knowledge Block Templates ==========
EMPTY_KNOWLEDGE = "<knowledge>当前无活跃路径。</knowledge>"
KNOWLEDGE_BLOCK_TEMPLATE = "<knowledge>\n{body}\n</knowledge>"
CANDIDATE_EDGES_TEMPLATE = "<candidate_edges>\n{edges}\n</candidate_edges>"

# ========== Regex Patterns ==========
EDGE_SELECT_REGEX = r"<edge_select>(.*?)</edge_select>"
ANSWER_REGEX = r"<answer>(.*?)</answer>"
THINK_REGEX = r"<think>(.*?)</think>"

# ========== Fallback & Manual Input Templates ==========
MANUAL_INPUT_PROMPT = "输入边编号或 answer:你的答案："
THINK_MANUAL_ANSWER = "<think>manual answer</think>"
THINK_MANUAL_SELECT_TEMPLATE = "<think>manual select edge: {edge}</think>"
THINK_HEURISTIC_SELECT_TEMPLATE = "<think>heuristic select first edge: {edge}</think>"
THINK_HEURISTIC_FALLBACK_ANSWER = "<think>heuristic fallback to provider answer</think>"
THINK_PARSE_FALLBACK_TEMPLATE = "<think>无法解析标准标签，回退选择首个边：{edge}</think>"
THINK_EMPTY_EDGE_FALLBACK = "<think>候选边为空，回退回答。</think>"


def format_candidate_edges(candidate_edges: list[CandidateEdge]) -> str:
    """将候选边渲染为<candidate_edges>内部列表文本（与预期输出一致）"""
    if not candidate_edges:
        return "（无候选边）"
    lines = []
    for edge in candidate_edges:
        lines.append(f"- {edge.to_display_text()}")
    return CANDIDATE_EDGES_TEMPLATE.format(edges="\n".join(lines))


def build_action_prompt(*, question: str, knowledge: str, candidate_edges: list[CandidateEdge]) -> str:
    """构造给 Agent 的完整提示词（Edge-Select模式）"""
    return (
        f"{SYSTEM_PROMPT}\n"
        f"{ACTION_FORMAT_PROMPT}\n"
        f"{EDGE_CONSTRAINT_PROMPT}\n\n"
        f"问题：{question}\n\n"
        f"{knowledge}\n\n"
        f"{format_candidate_edges(candidate_edges)}\n\n"
        f"{DECISION_HINT_PROMPT}"
    )


def format_knowledge_body(lines: list[str]) -> str:
    """将knowledge行列表拼装为<knowledge>块"""
    return KNOWLEDGE_BLOCK_TEMPLATE.format(body="\n".join(lines))
