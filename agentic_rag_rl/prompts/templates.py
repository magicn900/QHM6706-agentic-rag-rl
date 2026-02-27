from __future__ import annotations

SYSTEM_PROMPT = "你是一个在知识图上进行多路径推理的智能助手。"
ACTION_FORMAT_PROMPT = (
    "输出必须先给<think>，然后给一个动作："
    "<relation_select>关系名</relation_select> 或 <answer>答案</answer>。"
)
RELATION_CONSTRAINT_PROMPT = "只能从<relation_set>里选择关系。"
DECISION_HINT_PROMPT = "如果信息还不足请选关系扩展；如果足够请直接回答。"

EMPTY_KNOWLEDGE = "<knowledge>当前无活跃路径。</knowledge>"
KNOWLEDGE_BLOCK_TEMPLATE = "<knowledge>\n{body}\n</knowledge>"
RELATION_SET_TEMPLATE = "<relation_set>{relations}</relation_set>"

RELATION_SELECT_REGEX = r"<relation_select>(.*?)</relation_select>"
ANSWER_REGEX = r"<answer>(.*?)</answer>"

MANUAL_INPUT_PROMPT = "输入关系名（或输入 answer:你的答案）："
THINK_MANUAL_ANSWER = "<think>manual answer</think>"
THINK_MANUAL_SELECT_TEMPLATE = "<think>manual select relation: {relation}</think>"
THINK_HEURISTIC_SELECT_TEMPLATE = "<think>heuristic select first relation: {relation}</think>"
THINK_HEURISTIC_FALLBACK_ANSWER = "<think>heuristic fallback to provider answer</think>"
THINK_PARSE_FALLBACK_TEMPLATE = "<think>无法解析标准标签，回退选择首个关系：{relation}</think>"
THINK_EMPTY_RELATION_FALLBACK = "<think>候选关系为空，回退回答。</think>"


def format_relation_set(relation_set: list[str]) -> str:
    return RELATION_SET_TEMPLATE.format(relations=", ".join(relation_set))


def build_action_prompt(*, question: str, knowledge: str, relation_set: list[str]) -> str:
    return (
        f"{SYSTEM_PROMPT}"
        f"{ACTION_FORMAT_PROMPT}"
        f"{RELATION_CONSTRAINT_PROMPT}\n\n"
        f"问题：{question}\n"
        f"{knowledge}\n"
        f"{format_relation_set(relation_set)}\n"
        f"{DECISION_HINT_PROMPT}"
    )


def format_knowledge_body(lines: list[str]) -> str:
    return KNOWLEDGE_BLOCK_TEMPLATE.format(body="\n".join(lines))
