from __future__ import annotations

import argparse
import asyncio
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..config import CoreAPIConfig
from ..contracts import EdgeEnvAction
from ..envs import EdgeSelectionEnv
from ..policies import OpenAIActionPolicy
from ..prompts import format_candidate_edges
from ..providers import create_lightrag_graph_provider_from_env

DEFAULT_KG_TEXTS = [
    "Phillie Phanatic is the mascot of the baseball team Philadelphia Phillies.",
    "Philadelphia Phillies use Bright House Field as their spring training stadium.",
    "Bright House Field is located in Clearwater, Florida.",
    "Citizens Bank Park is the home stadium of Philadelphia Phillies in MLB regular season.",
]

DEFAULT_QUESTION = "What city is mascot Phillie Phanatic's team's spring training stadium located in?"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="External API end-to-end multihop test with step-by-step logs.")
    parser.add_argument(
        "--working-dir",
        default=str(Path("agentic_rag_rl") / "temp" / "external_api_multihop"),
        help="Workspace root for this runner. Graph cache and logs are separated under this directory.",
    )
    parser.add_argument("--graph-id", default="default", help="Graph cache ID. Runtime directory is <working-dir>/<graph-id>.")
    parser.add_argument(
        "--phase",
        choices=["all", "build", "query"],
        default="all",
        help="all: build graph then query; build: only build graph cache; query: only run QA from existing graph cache.",
    )
    parser.add_argument(
        "--log-file",
        default="",
        help="Optional log path. Default: <working-dir>/logs/<graph-id>/step_logs.json",
    )
    parser.add_argument("--question", default=DEFAULT_QUESTION)
    parser.add_argument("--beam-width", type=int, default=4)
    parser.add_argument("--max-steps", type=int, default=4)
    parser.add_argument("--top-k", type=int, default=20)
    parser.add_argument("--mode", default="hybrid")
    parser.add_argument("--use-mock", action="store_true")
    parser.add_argument("--policy", choices=["llm", "heuristic"], default="llm")
    parser.add_argument("--clear-working-dir", action="store_true")
    return parser


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def run_test(args: argparse.Namespace) -> int:
    working_root = Path(args.working_dir)
    graph_id = args.graph_id.strip() or "default"
    graph_dir = working_root / "graphs" / graph_id
    logs_dir = working_root / "logs" / graph_id
    log_file = Path(args.log_file) if args.log_file else logs_dir / "step_logs.json"
    metadata_file = graph_dir / "graph_meta.json"

    if args.clear_working_dir and graph_dir.exists():
        shutil.rmtree(graph_dir)
    graph_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)
    _ensure_parent(log_file)

    core_api = CoreAPIConfig.from_env()

    if not args.use_mock and not core_api.has_provider_credentials:
        print("[ERROR] Missing provider API key.")
        print("        Set AGENTIC_RAG_LLM_API_KEY (preferred), or LIGHTRAG_LLM_API_KEY / LIGHTRAG_API_KEY.")
        return 2

    if args.policy == "llm" and not core_api.has_action_credentials:
        print("[ERROR] Missing action model API key for llm policy.")
        print("        Set AGENTIC_RAG_ACTION_API_KEY (preferred), or ACTION_LLM_API_KEY / LIGHTRAG_LLM_API_KEY.")
        return 2

    provider = create_lightrag_graph_provider_from_env(
        working_dir=str(graph_dir),
        use_mock=args.use_mock,
        default_mode=args.mode,
    )
    env = EdgeSelectionEnv(
        provider=provider,
        beam_width=args.beam_width,
        max_steps=args.max_steps,
        top_k=args.top_k,
        answer_mode=args.mode,
    )
    policy = OpenAIActionPolicy() if args.policy == "llm" else None

    logs: dict[str, Any] = {
        "started_at": _now_iso(),
        "phase": args.phase,
        "graph_id": graph_id,
        "working_root": str(working_root),
        "graph_dir": str(graph_dir),
        "logs_dir": str(logs_dir),
        "question": args.question,
        "kg_texts": DEFAULT_KG_TEXTS if args.phase in {"all", "build"} else [],
        "steps": [],
    }

    await provider.initialize()
    try:
        if args.phase in {"all", "build"}:
            await provider.insert_texts(DEFAULT_KG_TEXTS)
            metadata = {
                "graph_id": graph_id,
                "created_at": _now_iso(),
                "graph_dir": str(graph_dir),
                "kg_texts": DEFAULT_KG_TEXTS,
            }
            metadata_file.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"[INFO] Graph cache built: {graph_dir}")
            print(f"[INFO] Graph metadata written to: {metadata_file}")
            if args.phase == "build":
                logs["finished_at"] = _now_iso()
                logs["final_state"] = {"done": True, "step_index": 0, "history": []}
                logs["final_answer"] = ""
                log_file.write_text(json.dumps(logs, ensure_ascii=False, indent=2), encoding="utf-8")
                print(f"[INFO] Step logs written to: {log_file}")
                print("[OK] Graph build phase passed.")
                return 0
        else:
            if not metadata_file.exists():
                print("[ERROR] Graph cache metadata not found for query phase.")
                print(f"        Expected: {metadata_file}")
                print("        Run with --phase build first, using the same --graph-id.")
                return 3

            metadata = json.loads(metadata_file.read_text(encoding="utf-8"))
            loaded_texts = metadata.get("kg_texts")
            if isinstance(loaded_texts, list):
                logs["kg_texts"] = loaded_texts

            print(f"[INFO] Using existing graph cache: {graph_dir}")
            print(f"[INFO] Loaded graph metadata: {metadata_file}")

        state = await env.reset(args.question)
        logs["initial_state"] = {
            "knowledge": state.knowledge,
            "candidate_edges": [edge.to_display_text() for edge in state.candidate_edges],
            "candidate_edges_length": len(state.candidate_edges),
            "active_path_count": len(state.active_paths),
        }

        print("[INFO] Initial state")
        print(state.knowledge)
        print(format_candidate_edges(state.candidate_edges))

        for _ in range(args.max_steps + 1):
            if args.policy == "llm":
                if policy is None:
                    raise RuntimeError("LLM policy is not initialized.")
                action, reasoning, trace = await policy.decide_with_trace(state)
            else:
                if state.candidate_edges and state.step_index < args.max_steps:
                    selected = state.candidate_edges[0].to_display_text()
                    action = EdgeEnvAction.select_edge(selected)
                    reasoning = f"<think>heuristic select first edge: {selected}</think>"
                    trace = {
                        "agent_prompt": "",
                        "agent_raw_response": "",
                        "agent_action_type": "heuristic_edge_select",
                        "agent_action_value": selected,
                    }
                else:
                    auto_answer = await provider.answer(state.question, mode=args.mode)
                    action = EdgeEnvAction.answer_now(auto_answer)
                    reasoning = "<think>heuristic fallback to provider answer</think>"
                    trace = {
                        "agent_prompt": "",
                        "agent_raw_response": "",
                        "agent_action_type": "heuristic_answer",
                        "agent_action_value": auto_answer,
                    }
            step_result = await env.step(action)

            step_log = {
                "step_index": state.step_index,
                "timestamp": _now_iso(),
                "state_context": {
                    "question": state.question,
                    "knowledge": state.knowledge,
                    "candidate_edges": [edge.to_display_text() for edge in state.candidate_edges],
                    "candidate_edges_length": len(state.candidate_edges),
                    "history": list(state.history),
                },
                "agent_prompt": trace.get("agent_prompt", trace.get("prompt", "")),
                "agent_raw_response": trace.get("agent_raw_response", trace.get("model_output", "")),
                "parsed_reasoning": reasoning,
                "action": {
                    "type": trace.get("agent_action_type", trace.get("action_type", "unknown")),
                    "value": trace.get("agent_action_value", trace.get("action_value", "")),
                },
                "env_feedback": {
                    "reward": step_result.reward,
                    "done": step_result.done,
                    "info": step_result.info,
                    "next_knowledge": step_result.state.knowledge,
                    "next_candidate_edges": [edge.to_display_text() for edge in step_result.state.candidate_edges],
                    "next_candidate_edges_length": len(step_result.state.candidate_edges),
                },
            }
            logs["steps"].append(step_log)

            print(f"[STEP {state.step_index}] action={step_log['action']['type']}:{step_log['action']['value']}")
            print(f"reward={step_result.reward:.3f}, done={step_result.done}")
            print(step_result.state.knowledge)
            print(format_candidate_edges(step_result.state.candidate_edges))

            state = step_result.state
            if step_result.done:
                break

        logs["finished_at"] = _now_iso()
        logs["final_state"] = {
            "done": state.done,
            "step_index": state.step_index,
            "history": list(state.history),
        }

        if logs["steps"]:
            final_info = logs["steps"][-1]["env_feedback"]["info"]
            logs["final_answer"] = final_info.get("final_answer", "")

        log_file.write_text(json.dumps(logs, ensure_ascii=False, indent=2), encoding="utf-8")

        print(f"[INFO] Step logs written to: {log_file}")
        print("[OK] External API multihop test passed.")
        return 0
    finally:
        await provider.finalize()


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    exit_code = asyncio.run(run_test(args))
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
