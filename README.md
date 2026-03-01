# QHM6706-agentic-rag-rl

## Core Environment Layer

The core agent environment is implemented as a first-class project package:

- Core root: `agentic_rag_rl/`
- Purpose: environment contracts, multi-path relation-selection environment, pruning logic, and runner interfaces
- Provider model: core environment depends on provider abstraction only
- LightRAG role: one concrete provider implementation via integration factory, not the core environment itself

Quick run (core env + LightRAG provider):

```powershell
conda activate agentic-rl
python -m agentic_rag_rl.runners.relation_env_demo --question "What is mascot Phillie Phanatic's team's spring training stadium?"
```

```bash
conda activate agentic-rl
python -m agentic_rag_rl.runners.relation_env_demo --question "What is mascot Phillie Phanatic's team's spring training stadium?"
```

Success marker:

- `[OK] Core relation env episode passed.`

### Relation env behavior notes

- Cycle handling: path expansion prunes candidates when the next entity already exists in the same path (avoid loop expansion).
- Max-step fallback: when `max_steps` is reached without explicit `<answer>`, env auto-generates a fallback answer via provider query; if provider fails, it returns a knowledge-based baseline response.
- Runtime trace fields: step info includes `cycle_pruned`; max-step termination includes `reason=max_steps_reached`, `final_answer`, and `auto_generated=true`.

### Core API Config (preferred)

Core environment now supports project-owned API config envs (preferred):

- Preferred local file: `agentic_rag_rl/.env` (template: `agentic_rag_rl/.env.example`)

- `AGENTIC_RAG_LLM_API_KEY`
- `AGENTIC_RAG_LLM_BASE_URL`
- `AGENTIC_RAG_LLM_MODEL`
- `AGENTIC_RAG_EMBED_API_KEY`
- `AGENTIC_RAG_EMBED_BASE_URL`
- `AGENTIC_RAG_EMBED_MODEL`
- `AGENTIC_RAG_ACTION_API_KEY`
- `AGENTIC_RAG_ACTION_BASE_URL`
- `AGENTIC_RAG_ACTION_MODEL`

Backward compatibility is kept with `LIGHTRAG_*` envs.

Env loading order:

1. `agentic_rag_rl/.env`
2. `<repo-root>/.env`

Legacy `third_party_integration/lightrag_integration/.env` is no longer loaded by core config.
Please migrate values to `agentic_rag_rl/.env`.

### External API multihop test (build/query separated)

Runner:

```powershell
python -m agentic_rag_rl.runners.external_api_multihop_test --phase build --graph-id demo --clear-working-dir
python -m agentic_rag_rl.runners.external_api_multihop_test --phase query --graph-id demo --max-steps 4 --beam-width 4 --top-k 20
```

```bash
python -m agentic_rag_rl.runners.external_api_multihop_test --phase build --graph-id demo --clear-working-dir
python -m agentic_rag_rl.runners.external_api_multihop_test --phase query --graph-id demo --max-steps 4 --beam-width 4 --top-k 20
```

Phases:

- `all`: build graph and then query (legacy one-shot behavior)
- `build`: only build graph cache
- `query`: only run QA from existing graph cache

Directory layout (default root: `agentic_rag_rl/temp/external_api_multihop`):

- Graph cache: `graphs/<graph-id>/`
- Logs: `logs/<graph-id>/step_logs.json`
- Metadata: `graphs/<graph-id>/graph_meta.json`

Typical lightweight workflow:

1. Build once with a chosen `graph-id`
2. Iterate query tests many times with the same `graph-id`

### WebQSP Freebase smoke test

Runner:

```bash
conda activate agentic-rl
python -m agentic_rag_rl.runners.webqsp_freebase_smoke_test --question-ids WebQTest-1092,WebQTest-1198 --max-steps 5 --policy llm
```

Common options:

- `--policy llm|heuristic`: decide via LLM or first-edge heuristic
- `--search-timeout` / `--sparql-timeout`: Freebase HTTP timeouts (default 60s / 120s)
- `--print-trace`: print step-level `agent_prompt` and `agent_raw_response`
- `--disable-unknown-probe`: disable unknown MID name probing

Report output:

- `agentic_rag_rl/temp/freebase_webqsp_smoke/report.json`
- Summary contains: `route_healthy`, `answer_hit_rate`, `cases_with_invalid_action`, `cases_with_mid_exposure`

## Third-party LightRAG Integration

This project integrates LightRAG as a third-party component without modifying upstream source code by default.

- Integration root: `third_party_integration/lightrag_integration/`
- Integration guide: `third_party_integration/lightrag_integration/docs/README.md`
- Agent rules: `AGENTS.md`

### Quick mock smoke test (offline)

From `<repo-root>`:

```powershell
conda activate agentic-rl
python -m third_party_integration.lightrag_integration.scripts.smoke_test_lightrag_mock
```

```bash
conda activate agentic-rl
python -m third_party_integration.lightrag_integration.scripts.smoke_test_lightrag_mock
```

Success marker:

- `[OK] LightRAG mock smoke test passed.`

### Functional test (LLM + embedding + optional rerank)

Required env vars:

- `LIGHTRAG_LLM_API_KEY`
- `LIGHTRAG_EMBED_API_KEY`

If you use a third-party OpenAI-compatible API, you can use:

- `LIGHTRAG_BASE_URL`
- `LIGHTRAG_API_KEY`

Env template:

- `third_party_integration/lightrag_integration/.env.example`

Command:

```powershell
conda activate agentic-rl
python -m third_party_integration.lightrag_integration.scripts.functional_test_lightrag
```

Success marker:

- `[OK] LightRAG functional test passed.`

## Project Tree (key parts)

```text
<repo-root>/
├─ AGENTS.md
├─ README.md
├─ environment.yml
├─ agentic_rag_rl/                 # core environment layer (project-owned)
├─ LightRAG/                      # upstream third-party source
└─ third_party_integration/
	└─ lightrag_integration/
		├─ docs/
		│  └─ README.md                     # integration runbook
		├─ wrappers/
		│  ├─ lightrag_adapter.py           # real adapter (default)
		│  └─ lightrag_adapter_mock.py      # mock adapter
		├─ scripts/
		│  ├─ functional_test_lightrag.py   # real functional test
		│  └─ *_mock.py                     # offline mock tests
		└─ temp/                            # local runtime artifacts (gitignored)
```

