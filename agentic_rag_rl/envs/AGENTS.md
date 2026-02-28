# AGENTS.md - 环境层 (envs/)

本目录包含RL环境实现，负责管理推理状态和执行动作。

## 当前实现

### 文件：`relation_selection_env.py`

**类**：`RelationSelectionEnv`

**职责**：
- 管理多路径推理过程
- 维护活动路径（`PathTrace`）列表
- 执行动作并更新状态
- 处理答案生成和终止条件

**核心方法**：
```python
async def reset(self, question: str) -> RelationEnvState
async def step(self, action: RelationEnvAction) -> StepResult
```

**当前数据流**：
1. `reset()` 调用 `provider.get_snapshot()` 获取初始实体和边
2. 从 `entity_edges` 提取关系名构建 `relation_set`
3. `step()` 接收 `RelationEnvAction.relation_select`（关系名字符串）
4. 根据关系名匹配边，扩展路径
5. 调用 `provider.get_snapshot()` 获取新数据

**关键代码片段**：
```python
# 从边数据提取关系名列表
def _collect_relation_set(self) -> list[str]:
    relations: set[str] = set()
    for edges in self._snapshot.entity_edges.values():
        for edge in edges:
            if edge.relation:
                relations.add(edge.relation)
    return sorted(relations)

# 根据关系名匹配边
matched = [edge for edge in edges if edge.relation == relation]
```

## 差距分析（与rebuild文档对比）

### 1. 选择模式差距
| 当前实现 | 目标架构 | 说明 |
|---------|---------|------|
| `RelationSelectionEnv` | `EdgeSelectionEnv` | 类名需重命名 |
| `relation_select: str` | `edge_select: EdgeOption` | 动作类型需重构 |
| `relation_set: list[str]` | `candidate_edges: list[CandidateEdge]` | 状态数据需重构 |

### 2. 边匹配逻辑差距
**当前**：
```python
# 只能根据关系名匹配，无法区分同一关系的不同目标
matched = [edge for edge in edges if edge.relation == relation]
```

**问题**：当一个实体有多个相同关系指向不同目标时，无法区分选择哪条边。

**目标**：Agent直接选择完整边，无需关系名匹配。

### 3. 噪音过滤差距
**当前**：无任何过滤逻辑，所有边都会被传递给Agent。

**目标**：需要硬编码黑名单过滤Freebase系统关系：
- `type.object.*`
- `kg.*`
- `base.math.*`
- `common.*`
- 其他不可读系统关系

**注意**：噪音过滤逻辑应在集成层实现，Env层只负责传递过滤后的数据。

### 4. 数据结构差距
**当前状态**：
```python
@dataclass
class RelationEnvState:
    question: str
    knowledge: str
    relation_set: list[str]  # 只有关系名
    active_paths: list[PathTrace]
    history: list[dict[str, str]]
    step_index: int
    done: bool = False
```

**目标状态**：
```python
@dataclass
class EdgeEnvState:
    question: str
    knowledge: str
    candidate_edges: list[CandidateEdge]  # 完整边信息
    active_paths: list[PathTrace]
    history: list[dict[str, str]]
    step_index: int
    done: bool = False
```

### 5. 职责边界检查
| 职责 | 当前状态 | 合规性 |
|-----|---------|-------|
| 过滤逻辑 | 无实现 | ✅ 应在集成层 |
| 文本拼接 | `_format_knowledge()` | ✅ 合规 |
| 图剪枝 | `_prune_paths()` | ✅ 合规 |
| 调用LLM | 无 | ✅ 合规 |
| 拼装SPARQL | 无 | ✅ 合规 |

## 依赖关系

```
envs/
  ├── contracts/ (RelationEnvAction, RelationEnvState, SeedSnapshot, PathTrace, StepResult)
  ├── providers/ (GraphProvider)
  ├── prompts/ (format_knowledge_body)
  └── utils/ (EmbeddingPruner)
```

## 待重构清单

1. **类重命名**：`RelationSelectionEnv` → `EdgeSelectionEnv`
2. **动作类型重构**：支持 `edge_select` 而非 `relation_select`
3. **状态数据重构**：`relation_set` → `candidate_edges`
4. **边匹配逻辑移除**：不再根据关系名匹配，直接使用Agent选择的边

## 相关文档

- [../AGENTS.md](../AGENTS.md) - 核心包总览
- [../contracts/AGENTS.md](../contracts/AGENTS.md) - 数据类型定义
- [../providers/AGENTS.md](../providers/AGENTS.md) - 数据提供者
- [../../docs/freebase_rebuild_guide.md](../../docs/freebase_rebuild_guide.md) - 重构指南