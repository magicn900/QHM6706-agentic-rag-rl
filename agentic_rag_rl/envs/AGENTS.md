# AGENTS.md - 环境层 (envs/)

本目录负责 Edge-Select 环境执行链路，实现文件为 `edge_selection_env.py`。

## 当前实现

### 文件：`edge_selection_env.py`

**类**：`EdgeSelectionEnv`

**职责**：
- 维护活跃路径（`PathTrace`）与候选边（`candidate_edges`）
- 执行 `EdgeEnvAction.edge_select`（支持分号分隔多边）
- 管理去环、路径剪枝、步数终止
- 输出标准化 `termination_reason`

**核心方法**：
```python
async def reset(self, question: str) -> EdgeEnvState
async def step(self, action: EdgeEnvAction) -> StepResult
```

## 关键行为约束

1. Env 不调用 LLM。
2. Env 不拼装 SPARQL。
3. Provider 异常或空结果时，Env 维持 episode 可继续/可终止，不直接崩溃。

## 终止信息规范

`StepResult.info` 统一输出 `termination_reason`，常见值：
- `answer_provided`
- `max_steps_reached`
- `invalid_action`
- `continue`
- `episode_finished`

## 依赖关系

```
envs/
  ├── contracts/ (CandidateEdge, EdgeEnvAction, EdgeEnvState, PathTrace, StepResult)
  ├── providers/ (GraphProvider)
  ├── prompts/ (format_knowledge_body)
  └── utils/ (EmbeddingPruner)
```

## 快速验证

- `python -m agentic_rag_rl.runners.test_edge_selection_env`
- `python -m agentic_rag_rl.runners.edge_env_demo`

## 相关文档

- [../AGENTS.md](../AGENTS.md)
- [../contracts/AGENTS.md](../contracts/AGENTS.md)
- [../providers/AGENTS.md](../providers/AGENTS.md)
- [../../docs/freebase_rebuild_guide.md](../../docs/freebase_rebuild_guide.md)