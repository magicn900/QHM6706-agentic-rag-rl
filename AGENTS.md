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

---

## 架构重构要求

> **关键文档**：`docs/freebase_rebuild_guide.md` 是架构变更的权威来源。
> **AI开发纪律**：废弃即删除，严禁叠加补丁。所有变更以rebuild文档为准。

### 当前状态
项目当前基于 **relation_select（关系选择）** 模式实现，需要迁移到 **edge_select（边选择）** 模式。

### 核心变革点（来自rebuild文档）

| 当前实现 | 目标架构 | 说明 |
|---------|---------|------|
| `relation_select` (关系名) | `edge_select` (完整边) | Agent选择`A -关系-> B`而非仅关系名 |
| `<relation_set>` 提示词 | `<candidate_edges>` 提示词 | LLM看到完整边信息 |
| `RelationEnvAction` | `EdgeEnvAction` | 动作类型重构 |
| 无噪音过滤 | Freebase黑名单过滤 | 过滤`type.object.*`、`kg.*`等系统关系 |
| 无MID处理 | MID双轨制(Freebase) | 内部MID，外部可读名称 |
| LightRAG单一数据源 | 多数据源可插拔 | Freebase通过外部HTTP服务对接 |

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

### 子模块AGENTS.md导航
- [agentic_rag_rl/](agentic_rag_rl/AGENTS.md) - 核心包总览
- [agentic_rag_rl/envs/](agentic_rag_rl/envs/AGENTS.md) - 环境层
- [agentic_rag_rl/policies/](agentic_rag_rl/policies/AGENTS.md) - 策略层
- [agentic_rag_rl/prompts/](agentic_rag_rl/prompts/AGENTS.md) - 提示词层
- [agentic_rag_rl/providers/](agentic_rag_rl/providers/AGENTS.md) - 提供者层
- [agentic_rag_rl/contracts/](agentic_rag_rl/contracts/AGENTS.md) - 合约层
- [agentic_rag_rl/config/](agentic_rag_rl/config/AGENTS.md) - 配置层
- [third_party_integration/](third_party_integration/AGENTS.md) - 集成层
