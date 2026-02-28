# AGENTS.md - 配置层 (config/)

本目录负责环境变量加载与统一配置对象构建。

## 当前实现

### 文件：`api_config.py`

**核心配置对象**：`CoreAPIConfig`

主要分组字段：
- LLM：`llm_model` / `llm_base_url` / `llm_api_key`
- Embedding：`embed_model` / `embed_dim` / `embed_base_url` / `embed_api_key`
- Action Model：`action_model` / `action_base_url` / `action_api_key`
- Graph Adapter：`graph_adapter_type`
- Freebase：`freebase_entity_api_url` / `freebase_sparql_api_url` / 对应 API key

## 环境变量策略

1. 自动加载 `<repo-root>/agentic_rag_rl/.env`，若不存在再尝试 `<repo-root>/.env`。
2. `AGENTIC_RAG_*` 优先级高于通用 `LIGHTRAG_*`。
3. 图源类型由 `AGENTIC_RAG_GRAPH_ADAPTER` 或 `GRAPH_ADAPTER_TYPE` 控制。

## 校验约束

- `validate()` 校验 `graph_adapter_type` 必须在 `lightrag/freebase`。
- 缺少核心密钥会返回可读错误列表，调用方决定是否中断。

## 职责边界

- 允许：配置加载、默认值回退、字段级校验。
- 禁止：业务流程控制、Provider 创建逻辑（由 `providers/factory.py` 处理）。

## 相关文档

- [../AGENTS.md](../AGENTS.md)
- [../providers/AGENTS.md](../providers/AGENTS.md)
- [../../third_party_integration/AGENTS.md](../../third_party_integration/AGENTS.md)
- [../../docs/freebase_rebuild_guide.md](../../docs/freebase_rebuild_guide.md)