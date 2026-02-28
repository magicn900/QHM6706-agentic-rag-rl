# AGENTS.md - 集成层 (third_party_integration/)

本目录包含第三方服务的集成代码，负责封装外部服务的调用细节。

## 目录结构

```
third_party_integration/
├── __init__.py
└── lightrag_integration/
    ├── __init__.py
    ├── .env.example
    ├── docs/
    ├── scripts/
    │   ├── functional_test_lightrag.py        # 功能测试
    │   ├── functional_test_lightrag_mock.py   # Mock测试
    │   └── smoke_test_lightrag_mock.py        # 快速验证
    └── wrappers/
        ├── __init__.py
        ├── contracts.py        # 类型定义
        ├── factory.py          # 工厂函数
        ├── lightrag_adapter.py # 真实适配器
        └── lightrag_adapter_mock.py  # Mock适配器
```

## 当前实现：lightrag_integration/

### 文件：`wrappers/contracts.py`

**类型定义**：
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

class GraphSeedEntityCandidate(TypedDict):
    entity_name: str
    entity_type: str
    description: str
    source_id: str
    candidate_edges: list[GraphSeedCandidateEdge]

class GraphSeedResponse(TypedDict):
    status: Literal["success", "failure"]
    message: str
    data: dict[str, Any] | GraphSeedData
```

**注意**：集成层已定义完整的边数据结构，包含 `src_id`, `tgt_id`, `next_entity` 等字段。

### 文件：`wrappers/lightrag_adapter.py`

**类**：`LightRAGIntegrationAdapter`

**职责**：
- 封装LightRAG内部调用
- 提供统一的 `query_graph_seed()` 方法
- 返回 `GraphSeedResponse` 格式数据

### 文件：`wrappers/factory.py`

**工厂函数**：`create_lightrag_adapter(config: LightRAGAdapterConfig)`

### 文件：`scripts/functional_test_lightrag.py`

**验证命令**：
```bash
python -m third_party_integration.lightrag_integration.scripts.functional_test_lightrag
```

**成功标记**：`[OK] LightRAG functional test passed.`

## 差距分析（与rebuild文档对比）

### 1. 数据源架构差距
| 当前实现 | 目标架构 | 说明 |
|---------|---------|------|
| 仅 `lightrag_integration/` | 增加 `freebase_integration/` | 需新增目录和实现 |

**目标结构**：
```
third_party_integration/
├── lightrag_integration/     # LightRAG集成（保留）
│   └── wrappers/
│       └── lightrag_adapter.py
├── freebase_integration/     # Freebase集成（新增）
│   ├── clients/
│   │   ├── entity_search_client.py  # localhost:8000/search
│   │   └── sparql_client.py         # localhost:8890/sparql
│   ├── adapters/
│   │   └── freebase_adapter.py      # 实现 GraphAdapterProtocol
│   └── utils/
│       ├── mid_mapper.py            # MID <-> 名称映射
│       └── noise_filter.py          # 关系噪音过滤
└── shared/                   # 共享代码（可选）
    └── contracts.py          # 统一接口定义
```

### 2. Freebase外部服务对接差距

**实体向量召回服务**：
- **URL**: `POST http://localhost:8000/search`
- **Payload**: `{"query": "搜索词", "top_k": 5}`
- **Response**: 
  ```json
  {
    "results": [
      {"name": "实体名", "freebase_ids": ["m.xxx"]}
    ]
  }
  ```

**SPARQL图扩展服务**：
- **URL**: `GET http://localhost:8890/sparql`
- **Params**: `query=URL编码SPARQL&format=application/sparql-results+json`

### 3. MID双轨制差距
**当前**：LightRAG无MID概念，使用实体名称作为标识。

**Freebase需要**：
- 内部使用MID进行查询（如 `m.0c9075n`）
- 外部展示使用可读名称（如 `爱因斯坦`）
- 需要MID到名称的双向映射

**实现位置**：`freebase_integration/utils/mid_mapper.py`

### 4. 噪音过滤差距
**当前**：无过滤逻辑。

**Freebase需要**：过滤以下系统关系：
- `type.object.*`
- `kg.*`
- `base.math.*`
- `common.*`
- 其他不可读系统关系

**实现位置**：`freebase_integration/utils/noise_filter.py`

**黑名单示例**：
```python
FREEBASE_NOISE_RELATIONS = {
    "type.object.type",
    "type.object.name",
    "type.object.id",
    "kg.object_key",
    "base.math.number",
    "common.topic",
    # ... 更多系统关系
}
```

### 5. 统一接口差距
**当前**：`LightRAGIntegrationAdapter` 有自己的接口。

**目标**：定义 `GraphAdapterProtocol` 供两个集成实现：

```python
class GraphAdapterProtocol(Protocol):
    async def search_entities(self, query: str, top_k: int) -> list[EntityResult]: ...
    async def expand_edges(self, entity_ref: str) -> list[CandidateEdge]: ...
    async def get_edge_details(self, edge_id: str) -> CandidateEdge | None: ...
```

### 6. 异常处理差距
**当前**：基础异常处理。

**Freebase需要**：
- HTTP请求超时处理
- 重试机制（指数退避）
- 优雅降级（返回空列表而非抛异常）
- 网络错误日志记录

### 7. 职责边界检查
| 职责 | 当前状态 | 合规性 |
|-----|---------|-------|
| HTTP调用 | LightRAG内部 | ✅ Freebase需实现 |
| 异常处理 | 基础 | ⚠️ 需增强 |
| 超时重试 | 无 | ⚠️ Freebase需实现 |
| MID映射 | 无 | ⚠️ Freebase需实现 |
| 噪音过滤 | 无 | ⚠️ Freebase需实现 |

## 依赖关系

```
third_party_integration/
  ├── agentic_rag_rl/contracts/ (目标: GraphAdapterProtocol)
  ├── agentic_rag_rl/config/ (目标: Freebase配置)
  └── LightRAG/ (第三方库)
```

## 待重构清单

### LightRAG集成（保留现有实现）
1. 确保输出格式与新接口兼容
2. 添加 `GraphAdapterProtocol` 实现

### Freebase集成（新增）
1. **目录创建**：`freebase_integration/`
2. **客户端实现**：
   - `entity_search_client.py` - 封装向量搜索
   - `sparql_client.py` - 封装SPARQL查询
3. **适配器实现**：
   - `freebase_adapter.py` - 实现统一接口
4. **工具实现**：
   - `mid_mapper.py` - MID双轨制
   - `noise_filter.py` - 噪音过滤
5. **异常处理**：
   - 超时控制
   - 重试机制
   - 优雅降级

## Freebase噪音关系黑名单

根据rebuild文档，以下关系类型应被过滤：

```python
FREEBASE_NOISE_PATTERNS = [
    "type.object.",      # 类型系统
    "kg.",               # 知识图谱元数据
    "base.math.",        # 数学基础
    "common.",           # 通用主题
    "freebase.",         # Freebase内部
    "dataworld.",        # 数据世界
    "user.",             # 用户数据
]
```

## 相关文档

- [../AGENTS.md](../AGENTS.md) - 项目总览
- [../agentic_rag_rl/providers/AGENTS.md](../agentic_rag_rl/providers/AGENTS.md) - 提供者层
- [../agentic_rag_rl/config/AGENTS.md](../agentic_rag_rl/config/AGENTS.md) - 配置层
- [../docs/freebase_rebuild_guide.md](../docs/freebase_rebuild_guide.md) - 重构指南