# LightRAG Third-Party Integration

This folder is the integration layer for using LightRAG as a third-party component in your graduation project.

## Why this folder exists

- Keep the upstream LightRAG source untouched as much as possible.
- Put all local integration logic (wrappers, smoke tests, docs) in one place.
- Make migration and maintenance easier when LightRAG is upgraded.

## Structure

- `wrappers/lightrag_adapter.py`: real-model adapter (LLM + embedding + optional rerank).
- `wrappers/lightrag_adapter_mock.py`: mock adapter for offline sanity checks.
- `wrappers/contracts.py`: stable integration contract types (graph seed payload + adapter protocol).
- `wrappers/factory.py`: unified adapter factory for real/mock mode.
- `scripts/functional_test_lightrag.py`: real stack functional test entrypoint.
- `scripts/smoke_test_lightrag_mock.py`: mock smoke test entrypoint.
- `scripts/functional_test_lightrag_mock.py`: mock functional test entrypoint.
- `docs/README.md`: this document.

## Boundary contract (important)

- All direct interaction with LightRAG third-party internals must stay in `third_party_integration/lightrag_integration/`.
- Main project modules should only consume:
  - `create_lightrag_adapter(...)` / `create_lightrag_adapter_from_env(...)`
  - contract types in `wrappers/contracts.py`.
- Do not import from `LightRAG/` in main project orchestration code.

Example (main project side):

```python
from third_party_integration.lightrag_integration import create_lightrag_adapter_from_env

adapter = create_lightrag_adapter_from_env(working_dir="./temp/runtime", use_mock=False)
```

## Real integration first (recommended)

Create your local env file first:

```powershell
Copy-Item third_party_integration/lightrag_integration/.env.example third_party_integration/lightrag_integration/.env
```

```bash
cp third_party_integration/lightrag_integration/.env.example third_party_integration/lightrag_integration/.env
```

Set required environment variables before running real tests:

- `LIGHTRAG_LLM_API_KEY` (required)
- `LIGHTRAG_EMBED_API_KEY` (required)

For third-party OpenAI-compatible APIs, you can use one shared endpoint/key instead:

- `LIGHTRAG_BASE_URL`
- `LIGHTRAG_API_KEY`

Optional environment variables:

- `LIGHTRAG_LLM_BASE_URL` (OpenAI-compatible endpoint)
- `LIGHTRAG_EMBED_BASE_URL` (OpenAI-compatible embedding endpoint)
- `LIGHTRAG_RERANK_PROVIDER` (`cohere` | `jina` | `ali`)
- `LIGHTRAG_RERANK_MODEL`
- `RERANK_BINDING_API_KEY` (or provider-specific keys)
- `LIGHTRAG_LLM_MODEL` / `LIGHTRAG_EMBED_MODEL` / `LIGHTRAG_EMBED_DIM`

Run functional test (real stack):

```powershell
conda activate agentic-rl
Set-Location <repo-root>
python -m third_party_integration.lightrag_integration.scripts.functional_test_lightrag
```

```bash
conda activate agentic-rl
cd <repo-root>
python -m third_party_integration.lightrag_integration.scripts.functional_test_lightrag
```

Success marker:

- `[OK] LightRAG functional test passed.`

> Note: mock scripts are kept only for offline sanity check and CI fallback (`*_mock.py`).

## Run mock smoke test (offline)

```powershell
conda activate agentic-rl
Set-Location <repo-root>
python -m third_party_integration.lightrag_integration.scripts.smoke_test_lightrag_mock
```

```bash
conda activate agentic-rl
cd <repo-root>
python -m third_party_integration.lightrag_integration.scripts.smoke_test_lightrag_mock
```

Success marker:

- `[OK] LightRAG mock smoke test passed.`

## Run mock functional test (offline)

```powershell
conda activate agentic-rl
Set-Location <repo-root>
python -m third_party_integration.lightrag_integration.scripts.functional_test_lightrag_mock
```

```bash
conda activate agentic-rl
cd <repo-root>
python -m third_party_integration.lightrag_integration.scripts.functional_test_lightrag_mock
```

Success marker:

- `[OK] LightRAG mock functional test passed.`

## Graph exploration seed API

To reuse LightRAG's entity/relationship selection logic without modifying upstream code,
both adapters now provide:

- `query_graph_seed(question, mode="hybrid", ...)`

This API runs keyword extraction + KG search + token truncation, and returns graph seeds
(`entities` and candidate relationships connected to these entities) directly,
without generating final LLM answer text.

The primary payload is now entity-centric for agent exploration:

- `data.entity_relation_candidates[]`
  - one object per entity
  - each entity contains `candidate_edges[]` as direct child objects
  - each edge includes `next_entity` and `direction`, so an agent can directly choose next hop

Typical response shape:

```json
{
  "status": "success",
  "message": "Graph seed extracted from entity/relation selection pipeline.",
  "data": {
    "keywords": {
      "high_level": ["..."],
      "low_level": ["..."]
    },
    "entity_relation_candidates": [
      {
        "entity_id": "...",
        "entity_type": "...",
        "description": "...",
        "source_id": "...",
        "candidate_edges": [
          {
            "edge_id": "...",
            "src_id": "...",
            "tgt_id": "...",
            "next_entity": "...",
            "direction": "outgoing",
            "description": "...",
            "keywords": "...",
            "weight": 1.0
          }
        ]
      }
    ],
    "processing_info": {
      "mode": "hybrid",
      "total_entities_found": 0,
      "total_relations_found": 0,
      "entities_after_truncation": 0,
      "relations_after_truncation": 0,
      "connected_relations_count": 0,
      "entity_candidates_count": 0
    }
  }
}
```

## Windows / Linux notes

- Prefer `pathlib.Path` in all integration scripts.
- Keep env handling shell-specific (`$env:KEY=...` vs `export KEY=...`).
- If Linux runs service scripts, remember executable permissions (`chmod +x`).
