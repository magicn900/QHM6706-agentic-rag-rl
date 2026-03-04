"""WebQSP 多题 Freebase 烟测脚本。

用途：
1. 从 WebQSP 数据集中抽样若干问题；
2. 逐题执行 Freebase Provider + EdgeSelectionEnv 主链路；
3. 验证 /search 与 /sparql 线路在真实请求下是否可跑通；
4. 输出结构化汇总，便于快速定位异常题目。

运行示例：
    python -m agentic_rag_rl.runners.webqsp_freebase_smoke_test
    python -m agentic_rag_rl.runners.webqsp_freebase_smoke_test --sample-size 8 --seed 7
    python -m agentic_rag_rl.runners.webqsp_freebase_smoke_test --question-ids WebQTest-1092,WebQTest-1198
"""
from __future__ import annotations

import argparse
import asyncio
import json
import random
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..config import CoreAPIConfig
from ..contracts import EdgeEnvAction
from ..envs import EdgeSelectionEnv
from ..policies import OpenAIActionPolicy
from ..providers import create_freebase_graph_provider_from_env


@dataclass(slots=True)
class WebQSPCase:
    """WebQSP 单题样本。

    Attributes:
        question_id: WebQSP 题号。
        question: 自然语言问题。
        topic_entity: 题面主题实体（若存在）。
        expected_answers: 标注答案名称列表（仅用于观察，不参与判定）。
    """

    question_id: str
    question: str
    topic_entity: str
    expected_answers: list[str]
    topic_entity_mid: str = ""


MID_PATTERN = re.compile(r"\b(?:m|g)\.[a-zA-Z0-9_]+\b")
NOISY_RELATION_PREFIXES = (
    "type.object.",
    "kg.",
    "common.",
    "base.",
)


def _extract_question_tokens(question: str) -> set[str]:
    """提取问题词元，用于粗粒度相关性诊断。"""
    raw_tokens = re.findall(r"[a-zA-Z0-9]+", question.lower())
    stopwords = {
        "the", "is", "a", "an", "of", "in", "on", "at", "to", "for", "and", "or",
        "who", "what", "when", "where", "why", "how", "did", "does", "was", "were", "isn",
    }
    return {tok for tok in raw_tokens if len(tok) >= 2 and tok not in stopwords}


def _token_overlap_score(question: str, edge_text: str) -> float:
    """计算题面和选边文本的词元重叠率。"""
    q_tokens = _extract_question_tokens(question)
    if not q_tokens:
        return 0.0

    edge_tokens = set(re.findall(r"[a-zA-Z0-9]+", edge_text.lower()))
    if not edge_tokens:
        return 0.0

    overlap = len(q_tokens.intersection(edge_tokens))
    return overlap / len(q_tokens)


def _resolve_selected_edge_texts(selected_text: str, candidate_edges_text: list[str]) -> list[str]:
    """将 edge_select 输出解析为真实候选边文本列表。

    支持数字编号（如 1;2）、"边1"、"1." 以及直接边文本。
    """
    normalized_text = (selected_text or "").strip()
    if not normalized_text:
        return []

    normalized_text = normalized_text.replace("；", ";").replace("，", ",").replace("、", ",")
    parts = [p.strip() for p in re.split(r"[;,\n]", normalized_text) if p.strip()]

    selected: list[str] = []
    for part in parts:
        if part.isdigit():
            idx = int(part) - 1
            if 0 <= idx < len(candidate_edges_text):
                selected.append(candidate_edges_text[idx])
            continue

        match_edge_num = re.match(r"^边\s*(\d+)$", part)
        if match_edge_num:
            idx = int(match_edge_num.group(1)) - 1
            if 0 <= idx < len(candidate_edges_text):
                selected.append(candidate_edges_text[idx])
            continue

        match_num_dot = re.match(r"^(\d+)\.?$", part)
        if match_num_dot:
            idx = int(match_num_dot.group(1)) - 1
            if 0 <= idx < len(candidate_edges_text):
                selected.append(candidate_edges_text[idx])
            continue

        if part in candidate_edges_text:
            selected.append(part)

    unique: list[str] = []
    seen = set()
    for text in selected:
        if text not in seen:
            seen.add(text)
            unique.append(text)
    return unique


def _has_noisy_relation(edge_text: str) -> bool:
    """判断边文本中的关系是否命中噪声前缀。"""
    if " -" not in edge_text or "-> " not in edge_text:
        return False

    try:
        relation = edge_text.split(" -", 1)[1].split("->", 1)[0].strip()
    except Exception:
        return False

    if any(relation.startswith(prefix) for prefix in NOISY_RELATION_PREFIXES):
        return True

    return False


def _is_unknown_name(name: str) -> bool:
    """判断是否为匿名占位实体名。"""
    normalized = (name or "").strip()
    return normalized == "Unknown Entity" or normalized.startswith("Unknown Entity#")


def _normalize_text(text: str) -> str:
    """归一化文本用于宽松命中比较。"""
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _evaluate_answer_hit(final_answer: str, expected_answers: list[str]) -> tuple[bool | None, str]:
    """评估最终答案是否命中标注答案。

    Returns:
        (是否命中/是否可评估, 命中或未命中原因)
    """
    normalized_answer = _normalize_text(final_answer)
    if not normalized_answer:
        return None, "empty_final_answer"

    cleaned_expected = [ans for ans in expected_answers if (ans or "").strip()]
    if not cleaned_expected:
        return None, "missing_expected_answers"

    for expected in cleaned_expected:
        normalized_expected = _normalize_text(expected)
        if not normalized_expected:
            continue

        # 采用双向包含，兼容“答案+附加说明”或“简称/全称”
        if normalized_expected in normalized_answer or normalized_answer in normalized_expected:
            return True, expected

    return False, cleaned_expected[0]


def build_parser() -> argparse.ArgumentParser:
    """构建命令行参数解析器。"""
    parser = argparse.ArgumentParser(description="WebQSP 多题 Freebase 烟测")
    parser.add_argument(
        "--dataset",
        default=str(Path("data") / "WebQSP.json"),
        help="WebQSP 数据集路径（默认 data/WebQSP.json）",
    )
    parser.add_argument("--sample-size", type=int, default=5, help="随机抽样题数")
    parser.add_argument("--seed", type=int, default=42, help="随机种子")
    parser.add_argument(
        "--question-ids",
        default="",
        help="指定题号列表，逗号分隔（优先级高于 sample-size）",
    )
    parser.add_argument("--beam-width", type=int, default=3, help="环境 beam_width")
    parser.add_argument("--max-steps", type=int, default=3, help="每题最多推理步数")
    parser.add_argument("--top-k", type=int, default=8, help="每轮实体召回数量")
    parser.add_argument("--selection-k", type=int, default=3, help="每步边选择数量目标（0 表示不强制）")
    parser.add_argument(
        "--start-mode",
        choices=["question", "webqsp", "hybrid"],
        default="question",
        help="首轮起点模式：question(问题检索) / webqsp(TopicEntity) / hybrid(并行)",
    )
    parser.add_argument("--enable-rerank", action="store_true", help="启用候选边重排")
    parser.add_argument("--rerank-trigger-n", type=int, default=20, help="候选边数量达到该阈值时触发重排")
    parser.add_argument("--rerank-top-k", type=int, default=12, help="重排后保留的候选边数量")
    parser.add_argument("--policy", choices=["llm", "heuristic"], default="llm", help="动作策略：llm 或 heuristic")
    parser.add_argument("--temperature", type=float, default=0.0, help="LLM 策略温度")
    parser.add_argument(
        "--print-trace",
        action="store_true",
        help="打印每步 agent_prompt 与 agent_raw_response（llm模式建议开启）",
    )
    parser.add_argument("--search-timeout", type=float, default=60.0, help="/search 请求超时（秒）")
    parser.add_argument("--sparql-timeout", type=float, default=120.0, help="/sparql 请求超时（秒）")
    parser.add_argument("--probe-max-mids", type=int, default=80, help="Unknown Entity名称探测时每次最多探测的 MID 数")
    parser.add_argument(
        "--disable-unknown-probe",
        action="store_true",
        help="关闭Unknown Entity名称探测（默认开启）",
    )
    parser.add_argument(
        "--report-file",
        default=str(Path("agentic_rag_rl") / "temp" / "freebase_webqsp_smoke" / "report.json"),
        help="测试报告输出文件",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="严格模式：只要有一题抛异常即返回非 0 退出码",
    )
    return parser


def _now_iso() -> str:
    """返回 UTC ISO 时间戳。"""
    return datetime.now(timezone.utc).isoformat()


def _load_cases(dataset_path: Path) -> list[WebQSPCase]:
    """加载 WebQSP 并转换为内部样本列表。"""
    raw_items = json.loads(dataset_path.read_text(encoding="utf-8"))
    cases: list[WebQSPCase] = []

    for item in raw_items:
        question_id = str(item.get("QuestionId", "")).strip()
        question = str(item.get("RawQuestion", "")).strip() or str(item.get("ProcessedQuestion", "")).strip()
        parses = item.get("Parses") or []

        topic_entity = ""
        topic_entity_mid = ""
        expected_answers: list[str] = []
        if parses and isinstance(parses, list):
            first_parse = parses[0] or {}
            topic_entity = str(first_parse.get("TopicEntityName", "")).strip()
            topic_entity_mid = str(first_parse.get("TopicEntityMid", "")).strip()

            answers = first_parse.get("Answers") or []
            for ans in answers:
                name = str((ans or {}).get("EntityName", "")).strip()
                if name and name not in expected_answers:
                    expected_answers.append(name)

        if question_id and question:
            cases.append(
                WebQSPCase(
                    question_id=question_id,
                    question=question,
                    topic_entity=topic_entity,
                    expected_answers=expected_answers,
                    topic_entity_mid=topic_entity_mid,
                )
            )

    return cases


def _pick_cases(all_cases: list[WebQSPCase], *, sample_size: int, seed: int, question_ids: str) -> list[WebQSPCase]:
    """按题号或随机方式选择待测样本。"""
    if question_ids.strip():
        targets = {qid.strip() for qid in question_ids.split(",") if qid.strip()}
        return [case for case in all_cases if case.question_id in targets]

    if sample_size <= 0:
        return []

    if sample_size >= len(all_cases):
        return list(all_cases)

    rng = random.Random(seed)
    return rng.sample(all_cases, k=sample_size)


async def _run_one_case(
    env: EdgeSelectionEnv,
    case: WebQSPCase,
    *,
    max_steps: int,
    policy: OpenAIActionPolicy | None,
    print_trace: bool,
    start_mode: str,
) -> dict[str, Any]:
    """执行单题测试并返回结构化结果。"""
    started_at = _now_iso()
    case_result: dict[str, Any] = {
        "question_id": case.question_id,
        "question": case.question,
        "topic_entity": case.topic_entity,
        "topic_entity_mid": case.topic_entity_mid,
        "expected_answers_sample": case.expected_answers[:5],
        "started_at": started_at,
        "reset_ok": False,
        "step_count": 0,
        "initial_candidate_edges_length": 0,
        "expanded_once": False,
        "mid_exposed": False,
        "noisy_relation_hit": False,
        "zero_overlap_selected": False,
        "final_answer": "",
        "answer_hit": None,
        "answer_hit_ref": "",
        "unknown_mid_refs": [],
        "unknown_name_probe": {},
        "candidate_truncation_observed": False,
        "candidate_drop_total": 0,
        "candidate_drop_max": 0,
        "candidate_drop_avg": 0.0,
        "history": [],
        "error": "",
    }

    try:
        seed_entities = [case.topic_entity] if case.topic_entity else []
        seed_mids = [case.topic_entity_mid] if case.topic_entity_mid else []
        state = await env.reset(
            case.question,
            start_mode=start_mode,
            seed_entities=seed_entities,
            seed_mids=seed_mids,
        )
        case_result["reset_ok"] = True
        case_result["initial_candidate_edges_length"] = len(state.candidate_edges)

        for _ in range(max_steps):
            if state.done:
                break

            candidate_total = int(state.candidate_edges_total or 0)
            candidate_shown = len(state.candidate_edges)
            candidate_drop = max(candidate_total - candidate_shown, 0)

            case_result["candidate_drop_total"] = int(case_result.get("candidate_drop_total", 0)) + candidate_drop
            case_result["candidate_drop_max"] = max(int(case_result.get("candidate_drop_max", 0)), candidate_drop)
            if candidate_drop > 0:
                case_result["candidate_truncation_observed"] = True

            unknown_mid_refs = {
                (edge.internal_src_ref or "").strip()
                for edge in state.candidate_edges
                if _is_unknown_name(edge.src_name) and (edge.internal_src_ref or "").strip()
            }
            unknown_mid_refs.update(
                {
                    (edge.internal_tgt_ref or "").strip()
                    for edge in state.candidate_edges
                    if _is_unknown_name(edge.tgt_name) and (edge.internal_tgt_ref or "").strip()
                }
            )
            existing_refs = set(case_result.get("unknown_mid_refs") or [])
            case_result["unknown_mid_refs"] = sorted(existing_refs.union(unknown_mid_refs))

            if policy is not None:
                action, reasoning_text, trace = await policy.decide_with_trace(state)
                selected_text = str(trace.get("agent_action_value") or "")
                action_type = str(trace.get("agent_action_type") or "unknown")
                agent_prompt = str(trace.get("agent_prompt") or "")
                agent_raw_response = str(trace.get("agent_raw_response") or "")

                if print_trace:
                    print(f"\n[TRACE][{case.question_id}] Step {state.step_index}")
                    print("[AGENT PROMPT]")
                    print(agent_prompt)
                    print("[AGENT RAW RESPONSE]")
                    print(agent_raw_response)
                    print("[AGENT PARSED ACTION]")
                    print(f"type={action_type} value={selected_text}")
            else:
                if state.candidate_edges:
                    selected_text = state.candidate_edges[0].to_display_text()
                    action = EdgeEnvAction.select_edge(selected_text)
                    action_type = "edge_select_heuristic"
                else:
                    action = EdgeEnvAction.answer_now("[smoke-test] 无候选边，提前结束")
                    selected_text = ""
                    action_type = "answer_heuristic"
                reasoning_text = ""
                agent_prompt = ""
                agent_raw_response = ""

            result = await env.step(action)
            case_result["step_count"] += 1

            termination_reason = str(result.info.get("termination_reason", ""))
            if action.edge_select and termination_reason != "invalid_action":
                case_result["expanded_once"] = True

            current_edges_text = [edge.to_display_text() for edge in state.candidate_edges]
            selected_edge_texts = (
                _resolve_selected_edge_texts(selected_text, current_edges_text)
                if action.edge_select
                else []
            )
            overlap_texts = selected_edge_texts if selected_edge_texts else ([selected_text] if selected_text else [])

            mid_in_candidates = any(MID_PATTERN.search(edge_text) for edge_text in current_edges_text)
            mid_in_selection = any(MID_PATTERN.search(edge_text) for edge_text in overlap_texts)
            noisy_relation_hit = any(_has_noisy_relation(edge_text) for edge_text in overlap_texts)
            overlap_score = (
                max(_token_overlap_score(case.question, edge_text) for edge_text in overlap_texts)
                if overlap_texts
                else 0.0
            )

            if mid_in_candidates or mid_in_selection:
                case_result["mid_exposed"] = True
            if noisy_relation_hit:
                case_result["noisy_relation_hit"] = True
            if action_type.startswith("edge_select") and selected_text and overlap_score <= 0.0:
                case_result["zero_overlap_selected"] = True

            case_result["history"].append(
                {
                    "step_index": state.step_index,
                    "action_type": action_type,
                    "action_value": selected_text if action.edge_select else action.answer,
                    "agent_prompt": agent_prompt,
                    "agent_raw_response": agent_raw_response,
                    "agent_reasoning": reasoning_text,
                    "reward": result.reward,
                    "done": result.done,
                    "termination_reason": termination_reason,
                    "env_final_answer": str(result.info.get("final_answer", "")),
                    "mid_in_candidates": mid_in_candidates,
                    "mid_in_selection": mid_in_selection,
                    "noisy_relation_hit": noisy_relation_hit,
                    "question_edge_overlap": overlap_score,
                    "selected_edge_texts": selected_edge_texts,
                    "candidate_edges_total": candidate_total,
                    "candidate_edges_shown": candidate_shown,
                    "candidate_drop_count": candidate_drop,
                    "next_candidate_edges_length": len(result.state.candidate_edges),
                }
            )

            print(
                f"[STEP] idx={state.step_index} action={action_type} "
                f"overlap={overlap_score:.2f} mid={mid_in_candidates or mid_in_selection} noisy={noisy_relation_hit}"
            )

            state = result.state

        # 提取最终答案（优先最后一步信息中的final_answer，其次最后一个answer动作）
        final_answer = ""
        for step in reversed(case_result["history"]):
            if (step.get("action_type") or "").startswith("answer"):
                final_answer = str(step.get("action_value") or "").strip()
                if final_answer:
                    break
            env_answer = str(step.get("env_final_answer") or "").strip()
            if env_answer:
                final_answer = env_answer
                break

        if not final_answer and case_result["history"]:
            last_step = case_result["history"][-1]
            if last_step.get("done") and str(last_step.get("termination_reason")) == "max_steps_reached":
                final_answer = ""

        hit, hit_ref = _evaluate_answer_hit(final_answer, case.expected_answers)
        case_result["final_answer"] = final_answer
        case_result["answer_hit"] = hit
        case_result["answer_hit_ref"] = hit_ref

        if case_result["step_count"] > 0:
            case_result["candidate_drop_avg"] = round(
                float(case_result.get("candidate_drop_total", 0)) / float(case_result["step_count"]),
                4,
            )

        case_result["final_done"] = state.done
        case_result["finished_at"] = _now_iso()
        return case_result

    except Exception as exc:
        case_result["error"] = f"{type(exc).__name__}: {exc}"
        case_result["finished_at"] = _now_iso()
        return case_result


def _summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    """汇总多题测试结果并给出线路健康结论。"""
    total = len(results)
    reset_ok = sum(1 for item in results if item.get("reset_ok"))
    with_candidates = sum(1 for item in results if (item.get("initial_candidate_edges_length") or 0) > 0)
    expanded_once = sum(1 for item in results if item.get("expanded_once"))
    error_count = sum(1 for item in results if item.get("error"))
    mid_exposed = sum(1 for item in results if item.get("mid_exposed"))
    noisy_relation_hit = sum(1 for item in results if item.get("noisy_relation_hit"))
    zero_overlap_selected = sum(1 for item in results if item.get("zero_overlap_selected"))
    truncation_observed_cases = sum(1 for item in results if item.get("candidate_truncation_observed"))
    candidate_drop_total = sum(int(item.get("candidate_drop_total") or 0) for item in results)
    candidate_drop_avg = (candidate_drop_total / total) if total > 0 else 0.0
    invalid_action_cases = sum(
        1
        for item in results
        if any(step.get("termination_reason") == "invalid_action" for step in item.get("history") or [])
    )

    unknown_mid_total = 0
    unknown_mid_resolved = 0
    for item in results:
        probe = item.get("unknown_name_probe") or {}
        unknown_mid_total += int(probe.get("unknown_mid_count", 0))
        unknown_mid_resolved += int(probe.get("resolved_name_count", 0))

    unknown_mid_unresolved = max(unknown_mid_total - unknown_mid_resolved, 0)

    answer_evaluable_cases = sum(1 for item in results if item.get("answer_hit") is not None)
    answer_hit_cases = sum(1 for item in results if item.get("answer_hit") is True)
    answer_hit_rate = (answer_hit_cases / answer_evaluable_cases) if answer_evaluable_cases > 0 else 0.0

    route_healthy = (
        error_count == 0
        and reset_ok == total
        and expanded_once == total
        and mid_exposed == 0
        and invalid_action_cases == 0
    )

    return {
        "total_cases": total,
        "reset_ok_cases": reset_ok,
        "cases_with_initial_candidates": with_candidates,
        "cases_expanded_once": expanded_once,
        "cases_with_mid_exposure": mid_exposed,
        "cases_with_noisy_relation_selected": noisy_relation_hit,
        "cases_with_zero_overlap_selection": zero_overlap_selected,
        "cases_with_candidate_truncation": truncation_observed_cases,
        "candidate_drop_total": candidate_drop_total,
        "candidate_drop_avg_per_case": round(candidate_drop_avg, 4),
        "cases_with_invalid_action": invalid_action_cases,
        "unknown_mid_total": unknown_mid_total,
        "unknown_mid_resolved": unknown_mid_resolved,
        "unknown_mid_unresolved": unknown_mid_unresolved,
        "answer_evaluable_cases": answer_evaluable_cases,
        "answer_hit_cases": answer_hit_cases,
        "answer_hit_rate": round(answer_hit_rate, 4),
        "error_cases": error_count,
        "route_healthy": route_healthy,
    }


async def run_smoke(args: argparse.Namespace) -> int:
    """执行 WebQSP 多题 Freebase 烟测主流程。"""
    dataset_path = Path(args.dataset)
    if not dataset_path.exists():
        print(f"[ERROR] 数据集不存在: {dataset_path}")
        return 2

    all_cases = _load_cases(dataset_path)
    selected = _pick_cases(
        all_cases,
        sample_size=args.sample_size,
        seed=args.seed,
        question_ids=args.question_ids,
    )
    if not selected:
        print("[ERROR] 未选中任何可测试题目，请检查 --sample-size 或 --question-ids。")
        return 2

    report_file = Path(args.report_file)
    report_file.parent.mkdir(parents=True, exist_ok=True)

    core_api = CoreAPIConfig.from_env()
    policy: OpenAIActionPolicy | None = None
    if args.policy == "llm":
        if not core_api.has_action_credentials:
            print("[ERROR] LLM 模式缺少 Action API Key。")
            print("        请设置 AGENTIC_RAG_ACTION_API_KEY 或 ACTION_LLM_API_KEY。")
            return 2
        policy = OpenAIActionPolicy(temperature=args.temperature)

    provider = create_freebase_graph_provider_from_env(
        search_timeout=args.search_timeout,
        sparql_timeout=args.sparql_timeout,
    )
    env = EdgeSelectionEnv(
        provider=provider,
        beam_width=args.beam_width,
        max_steps=args.max_steps,
        top_k=args.top_k,
        answer_mode="hybrid",
        selection_k=args.selection_k,
        enable_rerank=args.enable_rerank,
        rerank_trigger_n=args.rerank_trigger_n,
        rerank_top_k=args.rerank_top_k,
    )

    print("[INFO] WebQSP Freebase 烟测开始")
    print(f"[INFO] 数据集: {dataset_path}")
    print(f"[INFO] 测试题数: {len(selected)}")
    print(f"[INFO] 决策策略: {args.policy}")
    print(f"[INFO] 起点模式: {args.start_mode}")
    print(f"[INFO] Freebase /search 超时: {args.search_timeout}s, /sparql 超时: {args.sparql_timeout}s")

    results: list[dict[str, Any]] = []
    await provider.initialize()
    try:
        for index, case in enumerate(selected, start=1):
            print("-" * 72)
            print(f"[CASE {index}/{len(selected)}] {case.question_id}")
            print(f"Q: {case.question}")
            if case.topic_entity:
                print(f"Topic: {case.topic_entity}")

            case_result = await _run_one_case(
                env,
                case,
                max_steps=args.max_steps,
                policy=policy,
                print_trace=args.print_trace,
                start_mode=args.start_mode,
            )

            if not args.disable_unknown_probe:
                unknown_refs = list(case_result.get("unknown_mid_refs") or [])
                probe_refs = unknown_refs[: max(args.probe_max_mids, 0)]
                resolved_map = await provider.resolve_mid_names(probe_refs) if probe_refs else {}
                unresolved_refs = [mid for mid in probe_refs if mid not in resolved_map]
                case_result["unknown_name_probe"] = {
                    "unknown_mid_count": len(unknown_refs),
                    "probed_mid_count": len(probe_refs),
                    "resolved_name_count": len(resolved_map),
                    "unresolved_mid_count": len(unresolved_refs),
                    "resolved_samples": [
                        {"mid": mid, "name": name}
                        for mid, name in list(resolved_map.items())[:8]
                    ],
                    "unresolved_samples": unresolved_refs[:8],
                }

            results.append(case_result)

            status = "OK" if not case_result.get("error") else "ERROR"
            print(
                f"[RESULT] {status} | reset={case_result.get('reset_ok')} "
                f"| init_edges={case_result.get('initial_candidate_edges_length')} "
                f"| expanded_once={case_result.get('expanded_once')} "
                f"| mid_exposed={case_result.get('mid_exposed')} "
                f"| noisy={case_result.get('noisy_relation_hit')}"
            )
            print(
                f"[ANSWER] hit={case_result.get('answer_hit')} "
                f"| ref={case_result.get('answer_hit_ref', '')}"
            )
            if not args.disable_unknown_probe:
                probe = case_result.get("unknown_name_probe") or {}
                print(
                    "[UNKNOWN-PROBE] "
                    f"unknown_mid={probe.get('unknown_mid_count', 0)} "
                    f"resolved={probe.get('resolved_name_count', 0)} "
                    f"unresolved={probe.get('unresolved_mid_count', 0)}"
                )
            if case_result.get("error"):
                print(f"[ERROR] {case_result['error']}")
    finally:
        await provider.finalize()

    summary = _summarize(results)
    report = {
        "started_at": results[0].get("started_at") if results else _now_iso(),
        "finished_at": _now_iso(),
        "config": {
            "dataset": str(dataset_path),
            "sample_size": len(selected),
            "seed": args.seed,
            "question_ids": args.question_ids,
            "beam_width": args.beam_width,
            "max_steps": args.max_steps,
            "top_k": args.top_k,
            "selection_k": args.selection_k,
            "start_mode": args.start_mode,
            "enable_rerank": args.enable_rerank,
            "rerank_trigger_n": args.rerank_trigger_n,
            "rerank_top_k": args.rerank_top_k,
            "policy": args.policy,
            "temperature": args.temperature,
            "print_trace": args.print_trace,
            "disable_unknown_probe": args.disable_unknown_probe,
            "probe_max_mids": args.probe_max_mids,
            "search_timeout": args.search_timeout,
            "sparql_timeout": args.sparql_timeout,
        },
        "summary": summary,
        "cases": results,
    }
    report_file.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=" * 72)
    print("[SUMMARY]")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"[INFO] 详细报告: {report_file}")

    if args.strict and summary["error_cases"] > 0:
        print("[FAIL] 严格模式下存在异常题目。")
        return 1

    if summary["route_healthy"]:
        print("[OK] Freebase 线路可用：多题 reset 正常，且至少一题完成有效边扩展。")
        return 0

    print("[WARN] Freebase 线路未达到健康阈值，请查看报告定位。")
    return 1


def main() -> None:
    """命令行入口。"""
    parser = build_parser()
    args = parser.parse_args()
    exit_code = asyncio.run(run_smoke(args))
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
