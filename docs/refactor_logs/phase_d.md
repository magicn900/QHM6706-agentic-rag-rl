# Phase D - Provider适配

> 完成时间: 2026-03-01
> 状态: ✅ 已完成并验证

---

## T11 - Provider输出CandidateEdge

**修改文件**:
- `agentic_rag_rl/contracts/types.py`
- `agentic_rag_rl/providers/lightrag_provider.py`
- `agentic_rag_rl/envs/edge_selection_env.py`

**核心变更**:
```python
# 1. contracts/types.py - SeedSnapshot使用CandidateEdge
@dataclass
class SeedSnapshot:
    question: str
    entities: dict[str, EntityInfo]
    entity_edges: dict[str, list[CandidateEdge]]  # 原来是 list[RelationEdge]

# 2. lightrag_provider.py - Provider直接构造CandidateEdge
entity_edges[entity_name].append(
    CandidateEdge(
        edge_id=str(edge.get("edge_id", "")),
        src_name=src_name,
        relation=relation,
        tgt_name=tgt_name,
        direction=direction,
    )
)

# 3. edge_selection_env.py - 简化_convert_edges()
# 翻译墙已移到Provider层，Env直接透传
def _convert_edges(self, snapshot: SeedSnapshot) -> list[CandidateEdge]:
    # 直接从snapshot.entity_edges展开，不做转换
    edges = []
    for entity_name, edge_list in snapshot.entity_edges.items():
        edges.extend(edge_list)
    return edges
```

**验证**: ✅ py_compile通过，集成测试6/6通过

---

## T12 - Provider工厂模式

**新增文件**:
- `agentic_rag_rl/providers/factory.py` (新建)

**修改文件**:
- `agentic_rag_rl/providers/__init__.py`

**核心变更**:
```python
# 1. factory.py - 工厂函数
def create_graph_provider_from_env() -> GraphProvider:
    """根据配置创建对应的GraphProvider实例"""
    config = get_api_config()
    adapter_type = config.graph_adapter_type
    
    if adapter_type == "lightrag":
        return LightRAGProvider()
    elif adapter_type == "freebase":
        from .freebase_provider import FreebaseProvider
        return FreebaseProvider()
    else:
        raise UnsupportedProviderError(f"Unsupported graph_adapter_type: {adapter_type}")

# 2. 异常类
class ProviderFactoryError(Exception): ...
class UnsupportedProviderError(ProviderFactoryError): ...
class ProviderInitError(ProviderFactoryError): ...

# 3. __init__.py 导出
from .factory import create_graph_provider_from_env
from .factory import ProviderFactoryError, UnsupportedProviderError, ProviderInitError
```

**验证**: ✅ py_compile通过

---

## 测试结果

**单元测试** (`mock_edge_select_test.py`):
```
✅ demo_relation_selection - 关系选择模式测试
✅ demo_edge_selection - 边选择模式测试
✅ demo_invalid_action - 无效动作处理
✅ demo_multi_edge_selection - 多边同时选择
✅ demo_path_expansion - 路径扩展逻辑
✅ demo_answer_selection - 答案选择
✅ demo_max_steps - 最大步数限制
```

**集成测试** (`test_edge_selection_env.py`):
```
✅ 测试1: 环境重置 - 正确显示候选边
✅ 测试2: 边选择动作 - 步数增加，新边扩展
✅ 测试3: 回答动作 - 正确终止并返回答案
✅ 测试4: 最大步数终止 - 达到限制后触发
✅ 测试5: 空边选择 - 惩罚无效动作
✅ 测试6: 多边同时选择 - 分号分隔多边支持
```

---

## 架构清理

**翻译墙位置**:
- 旧架构: Env层负责RelationEdge -> CandidateEdge转换
- 新架构: Provider层直接输出CandidateEdge，Env透传

**产物清单**:

| 文件 | 类型 | 说明 |
|------|------|------|
| `providers/factory.py` | 新建 | Provider工厂模块 |
| `providers/__init__.py` | 修改 | 导出工厂函数和异常类 |
| `contracts/types.py` | 修改 | SeedSnapshot使用CandidateEdge |
| `providers/lightrag_provider.py` | 修改 | 直接构造CandidateEdge |
| `envs/edge_selection_env.py` | 修改 | 简化_convert_edges() |
| `runners/mock_edge_select_test.py` | 修改 | Mock返回CandidateEdge |
| `runners/test_edge_selection_env.py` | 修改 | Mock返回CandidateEdge |

---

## 下一步

Phase D 完成。Edge-Select重构全链路已通:
- ✅ Phase A: 类型与接口骨架
- ✅ Phase B: Prompt与Policy迁移
- ✅ Phase C: Env主链路替换
- ✅ Phase D: Provider适配

架构遵循模块边界:
- Env层: 过滤、拼接、图剪枝（不调用LLM）
- Policy层: 提示词构建、XML解析（不拼装SPARQL）
- Provider层: HTTP调用、异常处理、MID映射（翻译墙）