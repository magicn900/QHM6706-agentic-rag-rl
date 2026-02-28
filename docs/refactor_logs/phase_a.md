# Phase A - 类型与接口骨架

> 完成时间: 2026-02-28
> 状态: ✅ 已完成并验证

---

## T01 - Edge 类型定义

**修改文件**:
- `agentic_rag_rl/contracts/types.py`
- `agentic_rag_rl/contracts/__init__.py`

**核心变更**:
```python
CandidateEdge    # 可读边: src_name -relation-> tgt_name + internal_ref
EdgeEnvState     # 状态: candidate_edges列表
EdgeEnvAction    # 动作: edge_select | answer
```

**验证**: ✅ py_compile通过

---

## T02 - GraphAdapterProtocol

**新增文件**:
- `agentic_rag_rl/contracts/graph_adapter.py`

**核心变更**:
```python
GraphAdapterProtocol
├── initialize() / finalize()
├── search_entities(query, top_k)
├── expand_edges(entity_ref, direction)
└── answer_question(question, mode)
```

**验证**: ✅ py_compile通过

---

## T03 - 配置层多图源

**修改文件**:
- `agentic_rag_rl/config/api_config.py`

**新增字段**:
| 字段 | 环境变量 | 默认值 |
|------|----------|--------|
| `graph_adapter_type` | `AGENTIC_RAG_GRAPH_ADAPTER` | `lightrag` |
| `freebase_entity_api_url` | `FREEBASE_ENTITY_API_URL` | `http://localhost:8000` |
| `freebase_sparql_api_url` | `FREEBASE_SPARQL_API_URL` | `http://localhost:8890` |

**验证**: ✅ 配置加载成功，validate()通过

---

## 集成验证

```
[OK] 新类型可直接导入
[OK] 配置读取成功
    graph_adapter_type: lightrag
    验证错误: 无
```