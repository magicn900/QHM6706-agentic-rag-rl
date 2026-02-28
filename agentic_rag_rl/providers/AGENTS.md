# AGENTS.md - 提供者层 (providers/)

本目录负责图源抽象与快照组装，向 Env 提供统一 `GraphProvider` 接口。

## 当前实现

### `base.py`
- `GraphProvider` 抽象基类（initialize/finalize/insert_texts/get_snapshot/answer）。

### `lightrag_provider.py`
- `LightRAGGraphProvider`：封装 `lightrag_integration`，将集成层边数据转换为 `CandidateEdge`。

### `freebase_provider.py`
- `FreebaseGraphProvider`：封装 `FreebaseAdapter`，统一输出 `SeedSnapshot`。

### `factory.py`
- `create_graph_provider_from_env()`：按 `graph_adapter_type` 选择 `lightrag/freebase`。
- 错误类型：`UnsupportedProviderError`、`ProviderInitError`。

## 输出契约

- `get_snapshot()` 必须返回 `SeedSnapshot`。
- `SeedSnapshot.entity_edges` 的元素必须是 `CandidateEdge`。
- Provider 内部可使用源特有字段，但对 Env 暴露统一字段。

## 职责边界

- 允许：适配器调用、数据转换、统一快照结构。
- 禁止：Prompt 拼接、Policy 解析、Env 路径扩展策略。

## 快速验证

- `python -m agentic_rag_rl.runners.edge_env_demo`

## 相关文档

- [../AGENTS.md](../AGENTS.md)
- [../contracts/AGENTS.md](../contracts/AGENTS.md)
- [../../third_party_integration/AGENTS.md](../../third_party_integration/AGENTS.md)
- [../../docs/freebase_rebuild_guide.md](../../docs/freebase_rebuild_guide.md)