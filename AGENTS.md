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
- Preferred functional test command (from repo root):（这是旧的，基于 LightRAG 的测试）
  - `python -m third_party_integration.lightrag_integration.scripts.functional_test_lightrag`
- Success marker:
  - `[OK] LightRAG functional test passed.`

- Preferred Freebase route smoke test command (from repo root):
  - `python -m agentic_rag_rl.runners.webqsp_freebase_smoke_test --question-ids WebQTest-1092,WebQTest-1198 --max-steps 5 --policy llm`
- Freebase smoke success marker:
  - summary 中 `route_healthy: true`

- Diagnostic report path:
  - `agentic_rag_rl/temp/freebase_webqsp_smoke/report.json`

## Naming Convention
- Use default names for real integration paths (no `-real` / `_real` suffix).
- Use `_mock` suffix for simulation-only scripts and wrappers.

## Documentation Maintenance
- When integration behavior changes, update docs in the same PR.
- Keep this file synchronized with the latest workflow and constraints.
- If a new constraint appears in chat, add it here as a durable rule.
- For project-owned code, every new/modified class and method must include concise chinese functional comments/docstrings describing purpose, inputs/outputs, and boundary assumptions to reduce ambiguity for low-context models.

## 重构日志索引

> Edge-Select重构进度追踪，详见 [docs/refactor_logs/README.md](docs/refactor_logs/README.md)

| Phase | 状态 | 说明 |
|-------|------|------|
| A | ✅ | 类型定义、协议、配置 |
| B | ✅ | Prompt/Policy迁移（已完成模拟测试验证） |
| C | ✅ | Env主链路替换（已完成集成测试验证） |
| D | ✅ | Provider适配（已完成集成测试验证） |
| E | ✅ | Freebase外部服务集成（已完成集成测试验证） |
| F | ✅ | 迁移完成与清理（已删除旧relation链路，完成全部测试验证） |
| G | ✅ | 文档与验收（AGENTS同步、runbook、edge smoke脚本） |

---

## 架构重构要求

> **关键文档**：`docs/freebase_rebuild_guide.md` 是架构变更的权威来源。
> **AI开发纪律**：废弃即删除，严禁叠加补丁。所有变更以rebuild文档为准。

### 当前状态
项目主链路已完成 **edge_select（边选择）** 架构，`relation_select` 已退出可执行主链路。

### 核心变革点（来自rebuild文档）

| 已落地能力 | 说明 |
|---------|------|
| `edge_select` (完整边) | Agent选择`A -关系-> B`，支持多边分号分隔 |
| `<candidate_edges>` 提示词 | Policy 对 Agent 只暴露可读边文本 |
| `EdgeEnvAction` / `EdgeEnvState` | 合约、Prompt、Policy、Env 全链路统一 |
| Freebase集成可插拔 | 通过 provider factory 在 `lightrag/freebase` 间切换 |
| 外部服务对接 | `POST /search` + `GET /sparql` 封装在 integration 层 |
| 异常回退 | 外部请求失败返回空候选，不中断 episode |

### 数据源架构
```
┌─────────────────────────────────────────────────────────────┐
│  Env (agentic_rag_rl/envs/)                                 │
│    ↓ 统一接口                                                │
│  Provider (agentic_rag_rl/providers/)                       │
│    ↓ GraphAdapterProtocol                                   │
│  Integration (third_party_integration/)                     │
│    ├── lightrag_integration/  (LightRAG内部调用)            │
│    └── freebase_integration/  (HTTP: localhost:8000/8890)  │
└─────────────────────────────────────────────────────────────┘
```

### Freebase外部服务接口
- **实体向量召回**：`POST http://localhost:8000/search`
  - Payload: `{"query": "搜索词", "top_k": 5}`
  - Response: `{"results": [{"name": "实体名", "freebase_ids": ["m.xxx"]}]}`
- **SPARQL图扩展**：`GET http://localhost:8890/sparql`
  - Params: `query=URL编码SPARQL&format=application/sparql-results+json`

### 模块职责边界
- **Env层**：过滤逻辑、文本拼接、图剪枝。禁止调用LLM。
- **Policy层**：提示词构建、XML解析。禁止拼装SPARQL。
- **Integration层**：HTTP调用、异常处理、超时重试、MID映射。

补充边界约束：
- Runner 不得直接依赖 Integration 层 client（如 `SPARQLClient`）；
- Runner 需要的图源能力（例如 MID 名称探测）必须经 Provider 抽象暴露（如 `GraphProvider.resolve_mid_names`）。

### 当前烟测指标口径（WebQSP）
- `cases_with_zero_overlap_selection` 仅统计 `edge_select*` 动作（不包含 `answer*`）。
- `route_healthy` 判定需同时满足：无异常、全部 `reset_ok`、全部至少一次有效扩展、`mid_exposed=0`、`invalid_action=0`。
- 结果正确性使用 `answer_hit_rate`（仅在可评估样本上计算）。

### 子模块AGENTS.md导航
- [agentic_rag_rl/](agentic_rag_rl/AGENTS.md) - 核心包总览
- [agentic_rag_rl/envs/](agentic_rag_rl/envs/AGENTS.md) - 环境层
- [agentic_rag_rl/policies/](agentic_rag_rl/policies/AGENTS.md) - 策略层
- [agentic_rag_rl/prompts/](agentic_rag_rl/prompts/AGENTS.md) - 提示词层
- [agentic_rag_rl/providers/](agentic_rag_rl/providers/AGENTS.md) - 提供者层
- [agentic_rag_rl/contracts/](agentic_rag_rl/contracts/AGENTS.md) - 合约层
- [agentic_rag_rl/config/](agentic_rag_rl/config/AGENTS.md) - 配置层
- [third_party_integration/](third_party_integration/AGENTS.md) - 集成层
