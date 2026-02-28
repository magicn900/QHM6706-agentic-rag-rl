# AGENTS.md - 提供者层 (providers/)

本目录包含数据提供者抽象层，负责从数据源获取图数据并转换为统一格式。

## 当前实现

### 文件：`base.py`

**类**：`GraphProvider` (抽象基类)

**抽象方法**：
```python
async def initialize(self) -> None
async def finalize(self) -> None
async def insert_texts(self, texts: list[str]) -> None
async def get_snapshot(self, question: str, *, top_k: int, hl_keywords: list[str] | None, ll_keywords: list[str] | None) -> SeedSnapshot
async def answer(self, question: str, *, mode: str = "hybrid") -> str
```

### 文件：`lightrag_provider.py`

**类**：`LightRAGGraphProvider(GraphProvider)`

**职责**：
- 封装 `LightRAGIntegrationAdapter`
- 将适配器响应转换为 `SeedSnapshot`
- 提供实体边数据给环境层

**数据转换逻辑**：
```python
async def get_snapshot(self, question: str, ...) -> SeedSnapshot:
    response = await self._adapter.query_graph_seed(question, ...)
    
    # 转换边数据
    for edge in entity_candidate.get("candidate_edges", []):
        relation = self._extract_relation_name(edge)  # 提取关系名
        entity_edges[entity_name].append(
            RelationEdge(
                edge_id=str(edge.get("edge_id", "")),
                relation=relation,  # 只保留关系名
                src_id=edge.get("src_id"),
                tgt_id=edge.get("tgt_id"),
                next_entity=edge.get("next_entity"),
                direction=str(edge.get("direction", "unknown")),
                description=str(edge.get("description", "")),
                keywords=str(edge.get("keywords", "")),
                weight=float(edge.get("weight", 1.0)),
            )
        )
```

**关系名提取逻辑**：
```python
@staticmethod
def _extract_relation_name(edge: dict) -> str:
    # 优先从keywords提取
    raw_keywords = str(edge.get("keywords", "")).strip()
    if raw_keywords:
        parts = [part.strip() for part in raw_keywords.replace(";", ",").split(",") if part.strip()]
        if parts:
            return parts[0]
    
    # 回退到edge_id
    edge_id = str(edge.get("edge_id", "")).strip()
    if edge_id:
        return edge_id
    
    # 最终回退
    return f"{src_id}->{tgt_id}".strip("->") or "unknown_relation"
```

## 差距分析（与rebuild文档对比）

### 1. 数据源架构差距
| 当前实现 | 目标架构 | 说明 |
|---------|---------|------|
| 仅 `LightRAGGraphProvider` | 统一Provider + 可插拔适配器 | 需要抽象接口支持多数据源 |
| 直接依赖 `lightrag_integration` | 通过 `GraphAdapterProtocol` 解耦 | 依赖注入模式 |

### 2. 接口设计差距
**当前**：`GraphProvider` 是抽象基类，具体实现直接依赖集成层适配器。

**目标架构**：
```
providers/
  ├── base.py          # GraphProvider (统一实现，非抽象)
  └── graph_provider.py  # 通过依赖注入接收集成层适配器

third_party_integration/
  ├── lightrag_integration/  # 实现 GraphAdapterProtocol
  └── freebase_integration/  # 实现 GraphAdapterProtocol
```

### 3. 数据转换差距
**当前**：`_extract_relation_name()` 只提取关系名，丢失了边的完整信息。

**问题**：环境层无法获得完整边数据来构建 `candidate_edges`。

**目标**：保留完整边信息，包括源实体、目标实体、关系等，供环境层构建候选边列表。

### 4. Freebase服务对接差距
**当前**：无Freebase外部服务调用。

**目标**：集成层需要实现：
- `POST http://localhost:8000/search` - 实体向量召回
- `GET http://localhost:8890/sparql` - SPARQL图扩展

### 5. 职责边界检查
| 职责 | 当前状态 | 合规性 |
|-----|---------|-------|
| 数据获取抽象 | ✅ 实现 | ✅ 合规 |
| 格式转换 | ✅ 实现 | ⚠️ 只提取关系名 |
| 业务逻辑 | 无 | ✅ 合规 |
| 调用LLM | 无 | ✅ 合规 |

## 依赖关系

```
providers/
  ├── contracts/ (RelationEdge, SeedSnapshot)
  ├── config/ (CoreAPIConfig)
  └── third_party_integration/lightrag_integration/ (LightRAGIntegrationAdapter, LightRAGAdapterConfig)
```

## 集成层合约（来自 lightrag_integration/wrappers/contracts.py）

```python
class GraphSeedCandidateEdge(TypedDict):
    edge_id: str
    src_id: str | None
    tgt_id: str | None
    next_entity: str | None
    direction: Literal["outgoing", "incoming", "unknown"]
    description: str
    keywords: str
    weight: float
    created_at: str | None
```

**注意**：集成层已经提供了完整的边数据结构，但Provider层只使用了部分字段。

## 待重构清单

1. **接口重构**：
   - 定义 `GraphAdapterProtocol` 供集成层实现
   - Provider通过依赖注入接收适配器
   - 支持运行时切换数据源

2. **数据保留**：
   - 保留完整边信息，不再只提取关系名
   - 构建 `candidate_edges` 列表供环境层使用

3. **工厂函数**：
   - 根据配置创建对应数据源的适配器
   - 支持 `GRAPH_ADAPTER_TYPE=lightrag|freebase`

4. **统一输出**：
   - LightRAG和Freebase适配器输出统一的 `CandidateEdge` 格式
   - Freebase适配器需实现MID到可读名称的映射

## 相关文档

- [../AGENTS.md](../AGENTS.md) - 核心包总览
- [../contracts/AGENTS.md](../contracts/AGENTS.md) - 数据类型定义
- [../../third_party_integration/AGENTS.md](../../third_party_integration/AGENTS.md) - 集成层
- [../../docs/freebase_rebuild_guide.md](../../docs/freebase_rebuild_guide.md) - 重构指南