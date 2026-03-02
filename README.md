# Agentic-RAG-RL

A project for knowledge-graph question answering with an **Agentic RAG + RL-style environment** design.

This project models multi-hop QA as an interactive environment (Env). At each step, the agent selects actions from candidate graph edges (`edge_select`), incrementally expands reasoning paths, and produces an answer. The main pipeline has been migrated to the `edge_select` architecture and supports switching between LightRAG and Freebase graph providers.

## Project Goals

- Convert multi-hop KGQA into a unified environment interface that is trainable, evaluable, and provider-switchable
- Replace one-shot black-box generation with structured actions (edge selection / answer) for better interpretability
- Provide a reusable experimental foundation for RL training, policy comparison, and route diagnostics

## Core Features

- **Unified environment interface**: reset/step interaction based on `EdgeSelectionEnv`
- **Edge-level action space**: the agent directly selects full edge text in the form `A -relation-> B`
- **Pluggable providers**: switch between `lightrag` and `freebase` via factory-based providers
- **Decoupled external services**: Freebase is integrated through `/search` + `/sparql` HTTP endpoints
- **Engineering smoke tests**: built-in demo/smoke scripts for quick pipeline health checks

## Project Structure (Simplified)

```text
agentic_rag_rl/
  contracts/   # actions, states, graph adapter protocols
  envs/        # EdgeSelectionEnv core logic
  policies/    # LLM action policy and parsing
  prompts/     # prompt templates
  providers/   # graph providers and factory
  runners/     # demo and smoke scripts

third_party_integration/
  lightrag_integration/
  freebase_integration/
```

## Quick Start

### 1) Create environment

```bash
conda env create -f environment.yml
conda activate agentic-rl
```

### 2) Configure API (recommended: create `.env` in repo root)

Minimal example:

```env
AGENTIC_RAG_LLM_API_KEY=your_api_key
AGENTIC_RAG_LLM_BASE_URL=https://your-openai-compatible-endpoint/v1
AGENTIC_RAG_GRAPH_ADAPTER=freebase
FREEBASE_ENTITY_API_URL=http://localhost:8000
FREEBASE_SPARQL_API_URL=http://localhost:8890
```

### 3) Run the minimal demo

```bash
python -m agentic_rag_rl.runners.edge_env_demo
```

If you see `[OK] Edge-select smoke passed.`, the main environment pipeline is working.

## Freebase Smoke Test (Recommended for Demo)

```bash
python -m agentic_rag_rl.runners.webqsp_freebase_smoke_test --question-ids WebQTest-1092,WebQTest-1198 --max-steps 5 --policy llm
```

On success, the summary should show `route_healthy: true`, and a report will be generated at:

`agentic_rag_rl/temp/freebase_webqsp_smoke/report.json`

## Use Cases

- Multi-hop knowledge graph QA (e.g., WebQSP)
- Interpretability analysis of agent reasoning paths
- Comparative experiments across policies (LLM/heuristic) and graph routes

## Notes

- `LightRAG/` is treated as upstream third-party code. Project-owned environment and integration logic is implemented in `agentic_rag_rl/` and `third_party_integration/`.
- The executable main pipeline is now based on `edge_select`; the legacy `relation_select` path is retired.
