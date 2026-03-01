from __future__ import annotations

from agentic_rag_rl.contracts import CandidateEdge

# ========== System & Format Prompts ==========
SYSTEM_PROMPT = "你是一个在知识图上进行多路径推理的智能助手。"
ACTION_FORMAT_PROMPT = (
    "你必须严格按以下流程输出：\n"
    "1) 在<think>内先逐边分析每条候选边是否提供回答问题的有效信息；\n"
    "2) 在<think>结尾明确总结决策：要么选择哪些编号继续扩展，要么信息已足够可直接回答；\n"
    "3) </think>后只输出且仅输出一个动作标签："
    "<edge_select>编号1; 编号2; ...</edge_select> 或 <answer>答案</answer>。\n"
    "<candidate_edges>中的每条候选边都带有数字编号（从1开始）。\n"
    "当信息不足时，<edge_select>中只能输出数字编号（如 1;3），禁止输出整段边文本。\n"
    "当信息已足够回答时，直接输出<answer>。"
)
EDGE_CONSTRAINT_PROMPT = "只能从<candidate_edges>里选择一条或多条边编号。多条编号用分号(;)分隔。"
DECISION_HINT_PROMPT_TEMPLATE = (
    "如果信息还不足请优先选择{selection_k}条最相关边扩展；如果足够请直接回答。"
)
ONE_SHOT_EDGE_SELECT_EXAMPLE = (
    "【One-shot 示例1：继续扩展】\n"
    "问题：who was queen elizabeth ii mom?\n"
    "<knowledge>\n"
    "当前有 1 条活跃路径：\n"
    "- 路径1：从 Queen Elizabeth The Queen Mother 出发，暂无扩展。\n"
    "</knowledge>\n"
    "<candidate_edges>\n"
    "1. Queen Elizabeth The Queen Mother -people.person.children-> Elizabeth II\n"
    "2. Queen Elizabeth II -music.release_track.recording-> Queen Elizabeth II\n"
    "3. Queen Elizabeth The Queen Mother -people.person.gender-> Female\n"
    "</candidate_edges>\n"
    "示例输出：\n"
    "<think>逐边分析：边1直接提供母子关系，和问题强相关；边2是音乐信息无关；"
    "边3仅给性别信息，不足以直接回答“母亲是谁”。总结：优先选择编号1继续扩展。</think>\n"
    "<edge_select>1</edge_select>"
)
ONE_SHOT_ANSWER_EXAMPLE = (
    "【One-shot 示例2：直接回答】\n"
    "问题：what currency does kenya use?\n"
    "<knowledge>\n"
    "当前有 1 条活跃路径：\n"
    "- 路径1：Rift Valley Province -location.administrative_division.country-> Kenya"
    " -location.country.currency_used-> Kenyan shilling（末端：Kenyan shilling）\n"
    "</knowledge>\n"
    "<candidate_edges>\n"
    "1. Kenya -location.country.currency_used-> Kenyan shilling\n"
    "2. Kenya -location.country.official_language-> Swahili\n"
    "3. Kenya -location.country.population-> 53771300\n"
    "</candidate_edges>\n"
    "示例输出：\n"
    "<think>逐边分析：边1直接给出货币，已经可回答；边2是语言信息，边3是人口信息，"
    "都不是问题所问。总结：信息已足够，直接回答。</think>\n"
    "<answer>Kenyan shilling</answer>"
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
THINK_PARSE_FALLBACK_TEMPLATE = "<think>无法解析标准标签，回退选择候选边编号：{edge}</think>"
THINK_EMPTY_EDGE_FALLBACK = "<think>候选边为空，回退回答。</think>"


def format_candidate_edges(candidate_edges: list[CandidateEdge]) -> str:
    """将候选边渲染为<candidate_edges>内部列表文本（与预期输出一致）"""
    if not candidate_edges:
        return "（无候选边）"
    lines = []
    for idx, edge in enumerate(candidate_edges, start=1):
        lines.append(f"{idx}. {edge.to_display_text()}")
    return CANDIDATE_EDGES_TEMPLATE.format(edges="\n".join(lines))


def build_action_prompt(
    *,
    question: str,
    knowledge: str,
    candidate_edges: list[CandidateEdge],
    selection_k: int = 1,
) -> str:
    """构造给 Agent 的完整提示词（Edge-Select模式）"""
    return (
        f"{SYSTEM_PROMPT}\n"
        f"{ACTION_FORMAT_PROMPT}\n"
        f"{EDGE_CONSTRAINT_PROMPT}\n\n"
        f"{ONE_SHOT_EDGE_SELECT_EXAMPLE}\n\n"
        f"{ONE_SHOT_ANSWER_EXAMPLE}\n\n"
        f"问题：{question}\n\n"
        f"{knowledge}\n\n"
        f"{format_candidate_edges(candidate_edges)}\n\n"
        f"{DECISION_HINT_PROMPT_TEMPLATE.format(selection_k=max(selection_k, 1))}"
    )


def format_knowledge_body(lines: list[str]) -> str:
    """将knowledge行列表拼装为<knowledge>块"""
    return KNOWLEDGE_BLOCK_TEMPLATE.format(body="\n".join(lines))
