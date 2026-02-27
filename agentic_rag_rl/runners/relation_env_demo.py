from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from ..contracts import RelationEnvAction
from ..envs import RelationSelectionEnv
from ..policies import OpenAIActionPolicy
from ..prompts import (
    MANUAL_INPUT_PROMPT,
    THINK_HEURISTIC_FALLBACK_ANSWER,
    THINK_HEURISTIC_SELECT_TEMPLATE,
    THINK_MANUAL_ANSWER,
    THINK_MANUAL_SELECT_TEMPLATE,
    format_relation_set,
)
from ..providers import create_lightrag_graph_provider_from_env


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run relation-selection environment demo with LightRAG provider.")
    parser.add_argument("--question", required=True, help="User question for one episode.")
    parser.add_argument("--beam-width", type=int, default=4, help="Max active path count after pruning.")
    parser.add_argument("--max-steps", type=int, default=4, help="Maximum relation-selection steps before stop.")
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
        help="Action policy: llm for external API model, heuristic for auto first-relation, manual for terminal input.",
    )
    return parser


async def run_episode(args: argparse.Namespace) -> None:
    provider = create_lightrag_graph_provider_from_env(
        working_dir=args.working_dir,
        use_mock=args.use_mock,
        default_mode=args.mode,
    )
    env = RelationSelectionEnv(
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
        print(format_relation_set(state.relation_set))

        while not state.done:
            if args.policy == "manual":
                user_input = input(MANUAL_INPUT_PROMPT).strip()
                if user_input.startswith("answer:"):
                    action = RelationEnvAction.answer_now(user_input.split("answer:", 1)[1].strip())
                    reasoning = THINK_MANUAL_ANSWER
                else:
                    action = RelationEnvAction.select_relation(user_input)
                    reasoning = THINK_MANUAL_SELECT_TEMPLATE.format(relation=user_input)
            elif args.policy == "heuristic":
                if state.relation_set and state.step_index < args.max_steps:
                    selected_relation = state.relation_set[0]
                    action = RelationEnvAction.select_relation(selected_relation)
                    reasoning = THINK_HEURISTIC_SELECT_TEMPLATE.format(relation=selected_relation)
                else:
                    auto_answer = await provider.answer(state.question, mode=args.mode)
                    action = RelationEnvAction.answer_now(auto_answer)
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
            print(format_relation_set(state.relation_set))

            if step_result.done:
                final_answer = step_result.info.get("final_answer", "")
                if final_answer:
                    print(f"<answer>{final_answer}</answer>")
                print("[OK] Core relation env episode passed.")
                break
    finally:
        await provider.finalize()


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    asyncio.run(run_episode(args))


if __name__ == "__main__":
    main()
