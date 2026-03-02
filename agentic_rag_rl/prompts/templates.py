from __future__ import annotations

from agentic_rag_rl.contracts import CandidateEdge

# ========== System & Format Prompts ==========
SYSTEM_PROMPT = "You are an intelligent assistant that performs multi-path reasoning over a knowledge graph."
ACTION_FORMAT_PROMPT = (
    "You must strictly follow this output procedure:\n"
    "1) Inside <think>, analyze each candidate edge and judge whether it provides useful evidence for the question.\n"
    "2) At the end of <think>, clearly summarize the decision: either select edge indices to continue expansion or answer directly if evidence is sufficient.\n"
    "3) After </think>, output exactly one action tag and nothing else: "
    "<edge_select>1; 2; ...</edge_select> or <answer>your answer</answer>.\n"
    "Each edge in <candidate_edges> has a numeric index (starting from 1).\n"
    "If information is insufficient, <edge_select> must contain only numeric indices (e.g., 1;3), not full edge text.\n"
    "If information is already sufficient, output <answer> directly."
)
EDGE_CONSTRAINT_PROMPT = "You can only select one or more edge indices from <candidate_edges>. Separate multiple indices with semicolons (;)."
DECISION_HINT_PROMPT_TEMPLATE = (
    "If evidence is still insufficient, prefer selecting the top {selection_k} most relevant edges for expansion; otherwise answer directly."
)
ONE_SHOT_EDGE_SELECT_EXAMPLE = (
    "[One-shot Example 1: Continue Expansion]\n"
    "Question: who was queen elizabeth ii mom?\n"
    "<knowledge>\n"
    "There is 1 active path:\n"
    "- Path 1: starting from Queen Elizabeth The Queen Mother, no expansion yet.\n"
    "</knowledge>\n"
    "<candidate_edges>\n"
    "1. Queen Elizabeth The Queen Mother -people.person.children-> Elizabeth II\n"
    "2. Queen Elizabeth II -music.release_track.recording-> Queen Elizabeth II\n"
    "3. Queen Elizabeth The Queen Mother -people.person.gender-> Female\n"
    "</candidate_edges>\n"
    "Example output:\n"
    "<think>Edge-by-edge analysis: Edge 1 directly provides the parent-child relation and is highly relevant; "
    "Edge 2 is music-related and irrelevant; Edge 3 only gives gender information and is insufficient to answer who the mother is. "
    "Decision: select index 1 for expansion.</think>\n"
    "<edge_select>1</edge_select>"
)
ONE_SHOT_ANSWER_EXAMPLE = (
    "[One-shot Example 2: Answer Directly]\n"
    "Question: what currency does kenya use?\n"
    "<knowledge>\n"
    "There is 1 active path:\n"
    "- Path 1: Rift Valley Province -location.administrative_division.country-> Kenya"
    " -location.country.currency_used-> Kenyan shilling (tail: Kenyan shilling)\n"
    "</knowledge>\n"
    "<candidate_edges>\n"
    "1. Kenya -location.country.currency_used-> Kenyan shilling\n"
    "2. Kenya -location.country.official_language-> Swahili\n"
    "3. Kenya -location.country.population-> 53771300\n"
    "</candidate_edges>\n"
    "Example output:\n"
    "<think>Edge-by-edge analysis: Edge 1 directly gives the currency and is sufficient to answer; "
    "Edge 2 is about language and Edge 3 is about population, both irrelevant to the question. "
    "Decision: evidence is sufficient, answer directly.</think>\n"
    "<answer>Kenyan shilling</answer>"
)

# ========== Knowledge Block Templates ==========
EMPTY_KNOWLEDGE = "<knowledge>No active paths yet.</knowledge>"
KNOWLEDGE_BLOCK_TEMPLATE = "<knowledge>\n{body}\n</knowledge>"
CANDIDATE_EDGES_TEMPLATE = "<candidate_edges>\n{edges}\n</candidate_edges>"

# ========== Regex Patterns ==========
EDGE_SELECT_REGEX = r"<edge_select>(.*?)</edge_select>"
ANSWER_REGEX = r"<answer>(.*?)</answer>"
THINK_REGEX = r"<think>(.*?)</think>"

# ========== Fallback & Manual Input Templates ==========
MANUAL_INPUT_PROMPT = "Input edge indices or answer: your answer:"
THINK_MANUAL_ANSWER = "<think>manual answer</think>"
THINK_MANUAL_SELECT_TEMPLATE = "<think>manual select edge: {edge}</think>"
THINK_HEURISTIC_SELECT_TEMPLATE = "<think>heuristic select first edge: {edge}</think>"
THINK_HEURISTIC_FALLBACK_ANSWER = "<think>heuristic fallback to provider answer</think>"
THINK_PARSE_FALLBACK_TEMPLATE = "<think>Failed to parse standard tags. Fallback to candidate edge indices: {edge}</think>"
THINK_EMPTY_EDGE_FALLBACK = "<think>Candidate edges are empty. Fallback to answer.</think>"


def format_candidate_edges(candidate_edges: list[CandidateEdge]) -> str:
    """将候选边渲染为<candidate_edges>内部列表文本（与预期输出一致）"""
    if not candidate_edges:
        return "(no candidate edges)"
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
        f"Question: {question}\n\n"
        f"{knowledge}\n\n"
        f"{format_candidate_edges(candidate_edges)}\n\n"
        f"{DECISION_HINT_PROMPT_TEMPLATE.format(selection_k=max(selection_k, 1))}"
    )


def format_knowledge_body(lines: list[str]) -> str:
    """将knowledge行列表拼装为<knowledge>块"""
    return KNOWLEDGE_BLOCK_TEMPLATE.format(body="\n".join(lines))
