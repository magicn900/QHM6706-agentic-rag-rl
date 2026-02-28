# AGENTS.md - 合约层 (contracts/)

本目录定义模块间稳定数据合约，当前以 Edge-Select 类型为主。

## 当前核心类型

### `types.py`
- `CandidateEdge`：候选边（含可读字段与内部引用字段）
- `EdgeEnvAction`：环境动作（`edge_select` / `answer`）
- `EdgeEnvState`：策略输入状态（`candidate_edges`、`knowledge`、路径与历史）
- `PathTrace`：路径轨迹
- `SeedSnapshot`：Provider 输出快照
- `StepResult`：Env 单步执行结果

### `graph_adapter.py`
- `GraphAdapterProtocol`
- `AdapterMetadata`

## 合约设计约束

1. `CandidateEdge` 的展示字段对 Agent 可读，内部引用字段供系统追踪。
2. `SeedSnapshot.entity_edges` 统一为 `dict[str, list[CandidateEdge]]`。
3. 合约层仅放类型与轻量辅助方法，不引入外部服务调用。

## 导出策略

统一通过 `contracts/__init__.py` 暴露外部可用符号，避免上层直接深度依赖内部文件路径。

## 相关文档

- [../AGENTS.md](../AGENTS.md)
- [../envs/AGENTS.md](../envs/AGENTS.md)
- [../policies/AGENTS.md](../policies/AGENTS.md)
- [../providers/AGENTS.md](../providers/AGENTS.md)
- [../../docs/freebase_rebuild_guide.md](../../docs/freebase_rebuild_guide.md)