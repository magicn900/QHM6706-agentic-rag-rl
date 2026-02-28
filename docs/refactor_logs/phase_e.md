# Phase E - Freebase 外部服务集成

> 完成时间: 2026-03-01
> 状态: ✅ 已完成并验证

---

## T13 - Freebase 集成目录结构

**新建目录**:
```
third_party_integration/freebase_integration/
├── __init__.py
├── clients/
│   ├── __init__.py
│   ├── entity_search_client.py
│   └── sparql_client.py
├── adapters/
│   ├── __init__.py
│   └── freebase_adapter.py
├── utils/
│   ├── __init__.py
│   ├── mid_mapper.py
│   └── noise_filter.py
└── scripts/
    ├── __init__.py
    └── test_freebase_integration.py
```

**验证**: ✅ 目录结构创建完成

---

## T14 - EntitySearchClient 实现

**新增文件**: `clients/entity_search_client.py`

**核心功能**:
```python
class EntitySearchClient:
    """Freebase 实体向量搜索客户端
    
    调用 POST /search 接口，返回实体召回结果。
    """
    
    async def search(
        self,
        query: str,
        *,
        top_k: int = 5,
    ) -> list[EntitySearchResult]:
        """实体向量召回
        
        Args:
            query: 搜索查询词
            top_k: 返回结果数量
            
        Returns:
            实体列表，每项包含 name 和 freebase_ids
        """
```

**验证**: ✅ py_compile通过，功能测试通过

---

## T15 - SPARQLClient 实现

**新增文件**: `clients/sparql_client.py`

**核心功能**:
```python
class SPARQLClient:
    """Freebase SPARQL 端点客户端
    
    调用 GET /sparql 接口，执行图查询。
    """
    
    async def query(self, sparql: str) -> list[dict]:
        """执行 SPARQL 查询"""
        
    async def expand_edges(
        self,
        mid: str,
        direction: str = "forward",
        max_edges: int = 10,
    ) -> list[dict[str, Any]]:
        """图扩展 - 根据 MID 获取关联边"""
```

**验证**: ✅ py_compile通过，功能测试通过（SPARQL服务正常响应）

---

## T16 - NoiseFilter 实现

**新增文件**: `utils/noise_filter.py`

**核心功能**:
```python
class NoiseFilter:
    """Freebase 噪音关系过滤器
    
    过滤系统级噪音关系（type.object.*, kg.*, common.*等）。
    当前状态: 暂时禁用黑名单，待后续测试后启用。
    """
    
    def is_noisy(self, relation: str) -> bool:
        """判断关系是否为噪音"""
        
    def filter_edges(self, edges: list[dict]) -> list[dict]:
        """过滤边列表中的噪音边"""
```

**黑名单配置（当前已注释，备用）**:
```python
# DEFAULT_BLACKLIST_PREFIXES = (
#     "type.object",
#     "kg.",
#     "common.",
#     "freebase.",
#     "user.",
#     "base.",
#     "conversion.",
# )
```

**验证**: ✅ py_compile通过，功能测试通过

---

## T17 - MidMapper 实现

**新增文件**: `utils/mid_mapper.py`

**核心功能**:
```python
class MidMapper:
    """Freebase MID 到显示名称的映射器
    
    内部使用 MID，外部输出可读名称（双轨制）。
    """
    
    def add_mapping(self, mid: str, name: str) -> None:
        """添加 MID -> 名称映射"""
        
    def get_name(self, mid: str) -> str | None:
        """根据 MID 获取显示名称"""
        
    def get_mids(self, name: str) -> list[str]:
        """根据名称获取 MID 列表"""
        
    def batch_add(self, mappings: list[dict[str, str]]) -> None:
        """批量添加映射"""
```

**验证**: ✅ py_compile通过，功能测试通过

---

## T18 - FreebaseAdapter 实现

**新增文件**: `adapters/freebase_adapter.py`

**核心功能**:
```python
class FreebaseAdapter(GraphAdapterProtocol):
    """Freebase 图适配器
    
    整合实体搜索、SPARQL查询、噪音过滤和MID映射，
    实现统一的图查询接口。
    """
    
    async def initialize(self) -> None:
        """初始化适配器"""
        
    async def finalize(self) -> None:
        """清理资源"""
        
    async def search_entities(
        self,
        query: str,
        *,
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        """实体向量召回"""
        
    async def expand_edges(
        self,
        entity_ref: str,
        *,
        direction: str = "forward",
        max_edges: int = 10,
    ) -> list[CandidateEdge]:
        """图扩展 - 获取关联边"""
        
    async def answer_question(
        self,
        question: str,
        *,
        mode: str = "hybrid",
    ) -> str:
        """基于图知识回答问题（暂未实现）"""
```

**验证**: ✅ py_compile通过，功能测试通过，GraphAdapterProtocol 兼容

---

## 测试结果

**功能测试** (`test_freebase_integration.py`):
```
✅ Test 0: 模块导入检查
✅ Test 1: EntitySearchClient (实际调用成功，返回3个实体)
✅ Test 2: SPARQLClient (实际查询成功，返回2个bindings)
✅ Test 3: NoiseFilter (过滤逻辑正常，暂时禁用黑名单)
✅ Test 4: MidMapper (映射功能正常)
✅ Test 5: FreebaseAdapter (集成测试，异常处理正常)
✅ Test 6: GraphAdapterProtocol 兼容性检查
```

**总计**: 7/7 通过

---

## 架构对齐

**多数据源可插拔架构**:
```
Env (agentic_rag_rl/envs/)
  ↓ 统一接口
Provider (agentic_rag_rl/providers/)
  ↓ GraphAdapterProtocol
Integration (third_party_integration/)
  ├── lightrag_integration/  (LightRAG内部调用)
  └── freebase_integration/  (HTTP: localhost:8000/8890)
```

**模块职责边界**:
- **Env层**: 过滤逻辑、文本拼接、图剪枝（禁止调用LLM）
- **Policy层**: 提示词构建、XML解析（禁止拼装SPARQL）
- **Integration层**: HTTP调用、异常处理、超时重试、MID映射

---

## 产物清单

| 文件 | 类型 | 说明 |
|------|------|------|
| `freebase_integration/__init__.py` | 新建 | 模块入口，导出所有组件 |
| `freebase_integration/clients/entity_search_client.py` | 新建 | 实体搜索客户端 |
| `freebase_integration/clients/sparql_client.py` | 新建 | SPARQL查询客户端 |
| `freebase_integration/utils/mid_mapper.py` | 新建 | MID映射器 |
| `freebase_integration/utils/noise_filter.py` | 新建 | 噪音过滤器 |
| `freebase_integration/adapters/freebase_adapter.py` | 新建 | 主适配器 |
| `freebase_integration/scripts/test_freebase_integration.py` | 新建 | 功能测试 |

---

## 下一步

Phase E 完成。Freebase 外部服务集成已就绪：

- ✅ Phase A: 类型与接口骨架
- ✅ Phase B: Prompt与Policy迁移
- ✅ Phase C: Env主链路替换
- ✅ Phase D: Provider适配
- ✅ Phase E: Freebase外部服务集成

**待后续工作**:
1. 启用 NoiseFilter 黑名单（取消注释即可）
2. 实现 Env 层对 FreebaseAdapter 的调用
3. 完成 Provider 层的 FreebaseProvider 实现