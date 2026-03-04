# AGENTS.md - 集成层 (third_party_integration/)

本目录负责第三方图源接入与外部服务封装，避免主工程直接依赖上游实现细节。

## 当前结构

```
third_party_integration/
├── lightrag_integration/
│   ├── wrappers/
│   └── scripts/
└── freebase_integration/
  ├── clients/
  │   ├── entity_search_client.py
  │   └── sparql_client.py
  ├── adapters/
  │   └── freebase_adapter.py
  ├── utils/
  │   ├── mid_mapper.py
  │   └── noise_filter.py
  └── scripts/
```

## Freebase 集成约束

1. 实体召回通过 `POST /search`。
2. 图扩展通过 `GET /sparql`。
3. 网络异常/服务不可达时返回空结果，不抛出导致 episode 中断的未处理异常。
4. MID 仅内部使用，对 Agent 暴露可读实体名。
5. 当实体缺少可读名称时使用匿名占位（如 `Unknown Entity#N`），并保留内部 MID 追踪。
6. 对外暴露可选 MID 命名探测能力（`resolve_mid_names`）供 Provider 层转发。

## 与主工程的边界

- 集成层负责 HTTP 调用、超时重试、响应解析、降级策略。
- Env/Policy 不可直接引用集成层 HTTP 客户端。
- 主工程通过 Provider 与工厂接入，不直连具体上游 SDK 细节。

补充约束：
- Runner 不得直接调用集成层 client（例如 `SPARQLClient`）；如需能力必须经 Provider 抽象暴露。

## 运行与验证

- LightRAG 功能验证：`python -m third_party_integration.lightrag_integration.scripts.functional_test_lightrag`
- Freebase 集成脚本：`python -m third_party_integration.freebase_integration.scripts.test_freebase_integration`
- Freebase 端到端烟测：`python -m agentic_rag_rl.runners.webqsp_freebase_smoke_test --question-ids WebQTest-1092,WebQTest-1198 --max-steps 5 --policy llm`

## 相关文档

- [../AGENTS.md](../AGENTS.md)
- [../agentic_rag_rl/providers/AGENTS.md](../agentic_rag_rl/providers/AGENTS.md)
- [../agentic_rag_rl/config/AGENTS.md](../agentic_rag_rl/config/AGENTS.md)
- [../docs/freebase_rebuild_guide.md](../docs/freebase_rebuild_guide.md)