from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from ..contracts import EdgeEnvAction
from ..envs import EdgeSelectionEnv
from ..policies import OpenAIActionPolicy
from ..prompts import (
    MANUAL_INPUT_PROMPT,
    THINK_HEURISTIC_FALLBACK_ANSWER,
    THINK_HEURISTIC_SELECT_TEMPLATE,
    THINK_MANUAL_ANSWER,
    THINK_MANUAL_SELECT_TEMPLATE,
    format_candidate_edges,
)
from ..providers import create_lightrag_graph_provider_from_env


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run edge-selection environment demo with LightRAG provider.")
    parser.add_argument("--question", required=True, help="User question for one episode.")
    parser.add_argument("--beam-width", type=int, default=4, help="Max active path count after pruning.")
    parser.add_argument("--max-steps", type=int, default=4, help="Maximum edge-selection steps before stop.")
    parser.add_argument("--top-k", type=int, default=20, help="Top-k for graph retrieval.")
    parser.add_argument("--mode", default="hybrid", help="LightRAG query mode.")
    parser.add_argument("--use-mock", action="store_true", help="Use mock adapter instead of real API.")
    parser.add_argument(
        "--working-dir",
        default=str(Path("third_party_integration") / "lightrag_integration" / "temp"),
        help="Working directory for LightRAG adapter runtime files.",
    )
    parser.add_argument(
        "--policy",
        choices=["llm", "heuristic", "manual"],
        default="llm",
        help="Action policy: llm for external API model, heuristic for auto first-edge, manual for terminal input.",
    )
    return parser


async def run_episode(args: argparse.Namespace) -> None:
    provider = create_lightrag_graph_provider_from_env(
        working_dir=args.working_dir,
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

    await provider.initialize()
    try:
        state = await env.reset(args.question)
        print(state.knowledge)
        print(format_candidate_edges(state.candidate_edges))

        while not state.done:
            if args.policy == "manual":
                user_input = input(MANUAL_INPUT_PROMPT).strip()
                if user_input.startswith("answer:"):
                    action = EdgeEnvAction.answer_now(user_input.split("answer:", 1)[1].strip())
                    reasoning = THINK_MANUAL_ANSWER
                else:
                    action = EdgeEnvAction.select_edge(user_input)
                    reasoning = THINK_MANUAL_SELECT_TEMPLATE.format(edge=user_input)
            elif args.policy == "heuristic":
                if state.candidate_edges and state.step_index < args.max_steps:
                    selected_edge = state.candidate_edges[0].to_display_text()
                    action = EdgeEnvAction.select_edge(selected_edge)
                    reasoning = THINK_HEURISTIC_SELECT_TEMPLATE.format(edge=selected_edge)
                else:
                    auto_answer = await provider.answer(state.question, mode=args.mode)
                    action = EdgeEnvAction.answer_now(auto_answer)
                    reasoning = THINK_HEURISTIC_FALLBACK_ANSWER
            else:
                if policy is None:
                    raise RuntimeError("LLM policy is not initialized.")
                action, reasoning = await policy.decide(state)

            print(reasoning)
            step_result = await env.step(action)
            state = step_result.state

            print(f"reward={step_result.reward:.3f}, done={step_result.done}")
            print(state.knowledge)
            print(format_candidate_edges(state.candidate_edges))

            if step_result.done:
                final_answer = step_result.info.get("final_answer", "")
                if final_answer:
                    print(f"<answer>{final_answer}</answer>")
                print("[OK] Core edge env episode passed.")
                break
    finally:
        await provider.finalize()


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    asyncio.run(run_episode(args))


if __name__ == "__main__":
    main()
