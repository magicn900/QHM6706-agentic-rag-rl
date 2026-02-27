# AGENTS.md

Repository-level guidance for AI coding agents (Copilot, Claude, etc.).
This file must be continuously updated as project constraints evolve.

## Scope and Ownership
- Treat `LightRAG/` as third-party upstream code.
- Do not modify files inside `LightRAG/` unless the user explicitly asks.
- Build project-owned core environment and RL-facing abstractions in `agentic_rag_rl/`.
- Put local integration code in `third_party_integration/lightrag_integration/`.
  - `wrappers/`: adapter and integration methods
  - `scripts/`: smoke tests and runnable checks
  - `docs/`: integration docs and runbooks
- Main project orchestration code must not import from `LightRAG/` directly.
- Main project should depend on integration contracts/factories only (for example, `create_lightrag_adapter*` and contract types).
- Treat LightRAG integration as one provider implementation of the core environment, not the environment layer itself.

## Environment Policy
- Use conda environment: `agentic-rl`.
- Prefer `python -m ...` module execution style.
- Avoid machine-specific interpreter paths (no hardcoded absolute paths).

## Path and Cross-Platform Rules
- Never hardcode local absolute paths in code or docs.
- Use `pathlib.Path` for all filesystem logic.
- Keep commands portable for both Windows and Linux.
- Use placeholders in docs (for example `<repo-root>`) instead of local full paths.

## API Provider Compatibility
- Treat OpenAI-compatible third-party providers as first-class targets.
- Support explicit `base_url` configuration via env vars for both LLM and embedding.
- Prefer unified envs (`LIGHTRAG_BASE_URL` / `LIGHTRAG_API_KEY`) with optional split envs when endpoints differ.

## Run and Validation
- Preferred functional test command (from repo root):
  - `python -m third_party_integration.lightrag_integration.scripts.functional_test_lightrag`
- Success marker:
  - `[OK] LightRAG functional test passed.`

## Naming Convention
- Use default names for real integration paths (no `-real` / `_real` suffix).
- Use `_mock` suffix for simulation-only scripts and wrappers.

## Documentation Maintenance
- When integration behavior changes, update docs in the same PR.
- Keep this file synchronized with the latest workflow and constraints.
- If a new constraint appears in chat, add it here as a durable rule.
