"""Frontend demo page (Streamlit).

Purpose:
1. Provide a question input box and showcase quick-fill.
2. Run step-by-step reasoning with EdgeSelectionEnv + Policy.
3. Visualize context changes, model outputs, and actions in real time.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import streamlit as st

# 兼容 streamlit 从脚本目录启动导致的模块导入路径问题
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agentic_rag_rl.config import CoreAPIConfig
from agentic_rag_rl.contracts import EdgeEnvAction, EdgeEnvState
from agentic_rag_rl.envs import EdgeSelectionEnv
from agentic_rag_rl.policies.openai_action_policy import OpenAIActionPolicy
from agentic_rag_rl.providers import create_graph_provider_from_env


SHOWCASE_FILE = REPO_ROOT / "reports" / "webqsp_smoke_30_showcase_cases.json"


def load_showcase_cases(path: Path) -> list[dict[str, Any]]:
    """Load showcase samples.

    Input: JSON file path.
    Output: A list of cases, or an empty list on failure.
    Boundary: Never raises for missing/invalid files, so the page can still start.
    """
    if not path.exists():
        return []

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []

    raw_cases = payload.get("showcase_cases")
    if not isinstance(raw_cases, list):
        return []

    valid_cases: list[dict[str, Any]] = []
    for item in raw_cases:
        if not isinstance(item, dict):
            continue
        question = str(item.get("question", "")).strip()
        if not question:
            continue
        valid_cases.append(item)
    return valid_cases


def build_showcase_label(case: dict[str, Any]) -> str:
    """Build the select-box display label."""
    question_id = str(case.get("question_id", "NA")).strip() or "NA"
    question = str(case.get("question", "")).strip()
    return f"{question_id} | {question}"


def ensure_state_defaults() -> None:
    """Initialize session-state defaults for the page."""
    defaults: dict[str, Any] = {
        "selected_showcase": "Custom",
        "question": "",
        "topic_entity": "",
        "graph_adapter": "freebase",
        "freebase_entity_api_url": "http://localhost:8000",
        "freebase_sparql_api_url": "http://localhost:8890",
        "max_steps": 5,
        "beam_width": 3,
        "top_k": 8,
        "selection_k": 3,
        "start_mode": "hybrid",
        "policy": "llm",
        "temperature": 0.0,
        "print_prompt": False,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def apply_showcase_selection(showcase_cases: list[dict[str, Any]]) -> None:
    """Apply selected showcase values to input fields."""
    selected = st.session_state.get("selected_showcase", "Custom")
    if selected == "Custom":
        return

    hit_case = next((c for c in showcase_cases if build_showcase_label(c) == selected), None)
    if not hit_case:
        return

    st.session_state["question"] = str(hit_case.get("question", "")).strip()
    st.session_state["topic_entity"] = str(hit_case.get("topic_entity", "")).strip()


def format_candidate_edges(state: EdgeEnvState) -> str:
    """Format candidate edges into a readable multi-line string."""
    if not state.candidate_edges:
        return "(no candidate edges)"

    lines = [
        f"{idx}. {edge.to_display_text()}"
        for idx, edge in enumerate(state.candidate_edges, start=1)
    ]
    return "\n".join(lines)


def extract_final_answer(events: list[dict[str, Any]]) -> str:
    """Extract the final answer from recorded events."""
    for event in reversed(events):
        if event.get("type") != "step":
            continue
        answer_from_action = str(event.get("action_value") or "").strip()
        if str(event.get("action_type") or "").startswith("answer") and answer_from_action:
            return answer_from_action
        answer_from_env = str(event.get("env_final_answer") or "").strip()
        if answer_from_env:
            return answer_from_env
    return ""


def render_events(placeholder: st.delta_generator.DeltaGenerator, events: list[dict[str, Any]]) -> None:
    """Render live event traces inside the placeholder container."""
    with placeholder.container():
        st.subheader("Live Trace")
        if not events:
            st.info("No events yet.")
            return

        for event in events:
            event_type = str(event.get("type") or "")
            if event_type == "reset":
                st.markdown("### Reset")
                cols = st.columns(3)
                cols[0].metric("Step Index", int(event.get("step_index", 0)))
                cols[1].metric("Candidate (shown)", int(event.get("candidate_shown", 0)))
                cols[2].metric("Candidate (total)", int(event.get("candidate_total", 0)))

                with st.expander("Knowledge", expanded=False):
                    st.code(str(event.get("knowledge") or ""), language="text")

                with st.expander("Candidate Edges", expanded=True):
                    st.code(str(event.get("candidate_edges") or ""), language="text")

            elif event_type == "step":
                step_index = int(event.get("step_index", 0))
                action_type = str(event.get("action_type") or "unknown")
                title = f"Step {step_index} | {action_type}"
                with st.expander(title, expanded=True):
                    c1, c2 = st.columns(2)

                    with c1:
                        st.markdown("**Agent Context**")
                        st.caption("Knowledge before action")
                        st.code(str(event.get("knowledge") or ""), language="text")
                        st.caption("Candidate edges before action")
                        st.code(str(event.get("candidate_edges") or ""), language="text")

                    with c2:
                        st.markdown("**Model Output**")
                        if event.get("agent_prompt"):
                            with st.expander("Prompt", expanded=False):
                                st.code(str(event.get("agent_prompt") or ""), language="text")
                        st.caption("Raw response")
                        st.code(str(event.get("agent_raw_response") or ""), language="xml")
                        st.caption("Parsed action")
                        st.code(
                            f"type={event.get('action_type')}\nvalue={event.get('action_value')}",
                            language="text",
                        )

                    st.markdown("**Environment Feedback**")
                    f1, f2, f3, f4 = st.columns(4)
                    f1.metric("Reward", float(event.get("reward", 0.0)))
                    f2.metric("Done", str(bool(event.get("done", False))))
                    f3.metric("Next Candidate", int(event.get("next_candidate_count", 0)))
                    f4.metric("Termination", str(event.get("termination_reason") or "continue"))


def decide_heuristic_action(state: EdgeEnvState) -> tuple[EdgeEnvAction, dict[str, Any]]:
    """Heuristic action: pick the first candidate edge, else answer directly."""
    if state.candidate_edges:
        edge_text = state.candidate_edges[0].to_display_text()
        action = EdgeEnvAction.select_edge(edge_text)
        trace = {
            "agent_prompt": "",
            "agent_raw_response": f"<think>heuristic select first edge</think>\n<edge_select>{edge_text}</edge_select>",
            "agent_action_type": "edge_select_heuristic",
            "agent_action_value": edge_text,
        }
        return action, trace

    action = EdgeEnvAction.answer_now("Insufficient evidence.")
    trace = {
        "agent_prompt": "",
        "agent_raw_response": "<think>heuristic fallback to answer</think>\n<answer>Insufficient evidence.</answer>",
        "agent_action_type": "answer_heuristic",
        "agent_action_value": "Insufficient evidence.",
    }
    return action, trace


def run_episode(
    *,
    question: str,
    topic_entity: str,
    max_steps: int,
    beam_width: int,
    top_k: int,
    selection_k: int,
    start_mode: str,
    policy_name: str,
    temperature: float,
    graph_adapter: str,
    freebase_entity_api_url: str,
    freebase_sparql_api_url: str,
    search_timeout: float,
    sparql_timeout: float,
    events: list[dict[str, Any]],
    trace_placeholder: st.delta_generator.DeltaGenerator,
    progress_placeholder: st.delta_generator.DeltaGenerator,
) -> dict[str, Any]:
    """Run one episode and stream events in real time.

    Input: Page parameters, event cache, and render placeholders.
    Output: Final run summary.
    Boundary: Returns an error field on exceptions instead of crashing the page.
    """
    os.environ["AGENTIC_RAG_GRAPH_ADAPTER"] = graph_adapter
    os.environ["FREEBASE_ENTITY_API_URL"] = freebase_entity_api_url
    os.environ["FREEBASE_SPARQL_API_URL"] = freebase_sparql_api_url

    provider = create_graph_provider_from_env(
        search_timeout=search_timeout,
        sparql_timeout=sparql_timeout,
    )

    config = CoreAPIConfig.from_env()
    policy: OpenAIActionPolicy | None = None

    if policy_name == "llm":
        policy = OpenAIActionPolicy(
            model=config.action_model,
            base_url=config.action_base_url,
            api_key=config.action_api_key,
            temperature=temperature,
        )

    env = EdgeSelectionEnv(
        provider=provider,
        beam_width=beam_width,
        max_steps=max_steps,
        top_k=top_k,
        selection_k=selection_k,
    )

    summary: dict[str, Any] = {
        "success": False,
        "error": "",
        "final_answer": "",
        "steps": 0,
        "done": False,
        "graph_adapter": graph_adapter,
    }

    asyncio.run(provider.initialize())
    try:
        seed_entities = [topic_entity] if topic_entity else []
        state = asyncio.run(
            env.reset(
                question=question,
                start_mode=start_mode,
                seed_entities=seed_entities,
            )
        )

        events.append(
            {
                "type": "reset",
                "step_index": state.step_index,
                "knowledge": state.knowledge,
                "candidate_edges": format_candidate_edges(state),
                "candidate_shown": len(state.candidate_edges),
                "candidate_total": int(state.candidate_edges_total or 0),
            }
        )
        render_events(trace_placeholder, events)
        progress_placeholder.progress(0.05)

        for idx in range(max_steps):
            if state.done:
                break

            if policy is not None:
                action, _reasoning, trace = asyncio.run(policy.decide_with_trace(state))
            else:
                action, trace = decide_heuristic_action(state)

            result = asyncio.run(env.step(action))

            events.append(
                {
                    "type": "step",
                    "step_index": state.step_index,
                    "knowledge": state.knowledge,
                    "candidate_edges": format_candidate_edges(state),
                    "action_type": str(trace.get("agent_action_type") or "unknown"),
                    "action_value": str(trace.get("agent_action_value") or ""),
                    "agent_prompt": str(trace.get("agent_prompt") or ""),
                    "agent_raw_response": str(trace.get("agent_raw_response") or ""),
                    "reward": float(result.reward),
                    "done": bool(result.done),
                    "termination_reason": str(result.info.get("termination_reason") or "continue"),
                    "env_final_answer": str(result.info.get("final_answer") or ""),
                    "next_candidate_count": len(result.state.candidate_edges),
                }
            )

            state = result.state
            summary["steps"] = idx + 1
            summary["done"] = bool(result.done)

            render_events(trace_placeholder, events)
            progress_placeholder.progress(min(0.1 + (idx + 1) / max(max_steps, 1) * 0.85, 0.99))
            time.sleep(0.05)

            if result.done:
                break

        summary["final_answer"] = extract_final_answer(events)
        summary["success"] = True
        progress_placeholder.progress(1.0)
        return summary

    except Exception as exc:
        summary["error"] = f"{type(exc).__name__}: {exc}"
        return summary
    finally:
        asyncio.run(provider.finalize())


def main() -> None:
    """Main entrypoint for the frontend page."""
    st.set_page_config(page_title="Agentic RAG RL Demo", layout="wide")
    st.title("Agentic RAG RL Frontend Demo")
    st.caption("Input a question, quick-fill with showcase examples, and observe step-by-step agent traces.")

    ensure_state_defaults()
    config = CoreAPIConfig.from_env()
    if st.session_state.get("freebase_entity_api_url") == "http://localhost:8000" and config.freebase_entity_api_url:
        st.session_state["freebase_entity_api_url"] = config.freebase_entity_api_url
    if st.session_state.get("freebase_sparql_api_url") == "http://localhost:8890" and config.freebase_sparql_api_url:
        st.session_state["freebase_sparql_api_url"] = config.freebase_sparql_api_url

    showcase_cases = load_showcase_cases(SHOWCASE_FILE)

    with st.sidebar:
        st.header("Controls")
        options = ["Custom"] + [build_showcase_label(case) for case in showcase_cases]
        st.selectbox(
            "Showcase Quick Fill",
            options=options,
            key="selected_showcase",
            help="Select one showcase case to auto-fill the question and topic entity.",
        )
        apply_showcase_selection(showcase_cases)

        st.text_input("Question", key="question")
        st.text_input("Topic Entity (optional)", key="topic_entity")

        st.divider()
        st.selectbox("Graph Adapter", options=["freebase", "lightrag"], key="graph_adapter")
        if st.session_state.get("graph_adapter") == "freebase":
            st.text_input("Freebase Entity API URL", key="freebase_entity_api_url")
            st.text_input("Freebase SPARQL API URL", key="freebase_sparql_api_url")

        st.divider()
        st.selectbox("Policy", options=["llm", "heuristic"], key="policy")
        st.slider("Temperature", min_value=0.0, max_value=1.0, step=0.1, key="temperature")

        st.divider()
        st.selectbox("Start Mode", options=["question", "webqsp", "hybrid"], key="start_mode")
        st.slider("Max Steps", min_value=1, max_value=10, step=1, key="max_steps")
        st.slider("Beam Width", min_value=1, max_value=10, step=1, key="beam_width")
        st.slider("Top-K", min_value=1, max_value=20, step=1, key="top_k")
        st.slider("Selection-K", min_value=0, max_value=6, step=1, key="selection_k")

    run_button = st.button("Send", type="primary", use_container_width=True)

    trace_placeholder = st.empty()
    progress_placeholder = st.empty()

    if run_button:
        question = str(st.session_state.get("question") or "").strip()
        topic_entity = str(st.session_state.get("topic_entity") or "").strip()
        graph_adapter = str(st.session_state.get("graph_adapter") or "freebase").strip().lower()
        if not question:
            st.error("Please input a question first.")
            return

        if graph_adapter == "lightrag":
            st.warning("You are using `lightrag`. If its working directory has no indexed data, the agent will likely return fallback answers.")

        events: list[dict[str, Any]] = []
        with st.spinner("Running episode..."):
            summary = run_episode(
                question=question,
                topic_entity=topic_entity,
                max_steps=int(st.session_state["max_steps"]),
                beam_width=int(st.session_state["beam_width"]),
                top_k=int(st.session_state["top_k"]),
                selection_k=int(st.session_state["selection_k"]),
                start_mode=str(st.session_state["start_mode"]),
                policy_name=str(st.session_state["policy"]),
                temperature=float(st.session_state["temperature"]),
                graph_adapter=graph_adapter,
                freebase_entity_api_url=str(st.session_state.get("freebase_entity_api_url") or "http://localhost:8000"),
                freebase_sparql_api_url=str(st.session_state.get("freebase_sparql_api_url") or "http://localhost:8890"),
                search_timeout=60.0,
                sparql_timeout=120.0,
                events=events,
                trace_placeholder=trace_placeholder,
                progress_placeholder=progress_placeholder,
            )

        st.divider()
        st.subheader("Run Summary")
        if summary.get("success"):
            a1, a2, a3, a4 = st.columns(4)
            a1.metric("Success", "True")
            a2.metric("Steps", int(summary.get("steps", 0)))
            a3.metric("Done", str(bool(summary.get("done", False))))
            a4.metric("Graph Adapter", str(summary.get("graph_adapter", "")))
            st.text_area("Final Answer", value=str(summary.get("final_answer", "")), height=100)
        else:
            st.error(str(summary.get("error") or "Unknown error"))
    else:
        st.info("Select a showcase case or type your own question, then click Send.")


if __name__ == "__main__":
    main()
