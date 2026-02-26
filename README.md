# QHM6706-agentic-rag-rl

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

