# AGENTS.md - 合约层 (contracts/)

本目录包含核心数据类型定义，是各模块之间的"合约"。

## 当前实现

### 文件：`types.py`

**数据类定义**：

#### `RelationEdge` - 边数据结构
```python
@dataclass(slots=True)
class RelationEdge:
    edge_id: str
    relation: str
    src_id: str | None
    tgt_id: str | None
    next_entity: str | None
    direction: str
    description: str = ""
    keywords: str = ""
    weight: float = 1.0
```

#### `RelationEnvAction` - 环境动作
```python
@dataclass(slots=True)
class RelationEnvAction:
    relation_select: str | None = None  # 只有关系选择
    answer: str | None = None

    @classmethod
    def select_relation(cls, relation: str) -> "RelationEnvAction":
        return cls(relation_select=relation)

    @classmethod
    def answer_now(cls, answer: str) -> "RelationEnvAction":
        return cls(answer=answer)
```

#### `RelationEnvState` - 环境状态
```python
@dataclass(slots=True)
class RelationEnvState:
    question: str
    knowledge: str
    relation_set: list[str]  # 只有关系名列表
    active_paths: list[PathTrace]
    history: list[dict[str, str]]
    step_index: int
    done: bool = False
```

#### `PathTrace` - 路径追踪
```python
@dataclass(slots=True)
class PathTrace:
    nodes: list[str]
    relations: list[str]
    score: float = 0.0

    @property
    def tail_entity(self) -> str:
        return self.nodes[-1] if self.nodes else ""

    def extend(self, relation: str, next_entity: str | None, score_delta: float = 0.0) -> "PathTrace":
        ...

    def to_text(self) -> str:
        # 输出格式: 实体A -关系-> 实体B -关系-> 实体C
        ...
```

#### `SeedSnapshot` - 种子快照
```python
@dataclass(slots=True)
class SeedSnapshot:
    question: str
    keywords: dict[str, list[str]]
    entity_edges: dict[str, list[RelationEdge]]  # 实体 -> 边列表
    processing_info: dict[str, Any] = field(default_factory=dict)
    raw_data: dict[str, Any] = field(default_factory=dict)
```

#### `StepResult` - 步骤结果
```python
@dataclass(slots=True)
class StepResult:
    state: RelationEnvState
    reward: float
    done: bool
    info: dict[str, Any] = field(default_factory=dict)
```

## 差距分析（与rebuild文档对比）

### 1. 动作类型差距
| 当前实现 | 目标架构 | 说明 |
|---------|---------|------|
| `RelationEnvAction` | `EdgeEnvAction` | 类名需重命名 |
| `relation_select: str` | `edge_select: EdgeOption` | 字段类型需改变 |

**目标定义**：
```python
@dataclass(slots=True)
class EdgeEnvAction:
    edge_select: EdgeOption | None = None  # 选择完整边
    answer: str | None = None

    @classmethod
    def select_edge(cls, edge: EdgeOption) -> "EdgeEnvAction":
        return cls(edge_select=edge)
```

### 2. 状态数据差距
| 当前实现 | 目标架构 | 说明 |
|---------|---------|------|
| `relation_set: list[str]` | `candidate_edges: list[CandidateEdge]` | 数据结构需重构 |

**目标定义**：
```python
@dataclass(slots=True)
class EdgeEnvState:
    question: str
    knowledge: str
    candidate_edges: list[CandidateEdge]  # 完整边列表
    active_paths: list[PathTrace]
    history: list[dict[str, str]]
    step_index: int
    done: bool = False
```

### 3. 候选边数据结构差距
**当前**：无专门的候选边结构，只有 `RelationEdge`。

**目标**：需要定义 `CandidateEdge` 结构，支持：
- 内部标识（edge_id，供代码使用）
- 展示文本（display_text，供LLM查看）
- 内部引用（internal_ref，可选，Freebase存MID）

**目标定义**：
```python
@dataclass(slots=True)
class CandidateEdge:
    edge_id: str                    # 唯一标识，Agent选择时引用
    src_name: str                   # 源实体名称（可读）
    relation: str                   # 关系名称
    tgt_name: str                   # 目标实体名称（可读）
    internal_src_ref: str | None    # 内部引用（Freebase MID，LightRAG可为空）
    internal_tgt_ref: str | None    # 内部引用
    weight: float = 1.0

    @property
    def display_text(self) -> str:
        """返回LLM可见的可读格式"""
        return f"{self.src_name} -{self.relation}-> {self.tgt_name}"

    def __str__(self) -> str:
        return self.display_text
```

### 4. 边数据保留差距
**当前**：`RelationEdge` 包含完整信息，但Provider只提取关系名。

**问题**：数据已存在但未被正确使用。

**目标**：`CandidateEdge` 应充分利用现有字段，添加可读名称映射。

### 5. MID处理说明
**重要**：MID是Freebase特有的概念，LightRAG没有MID。

- `internal_src_ref` / `internal_tgt_ref` 为可选字段
- Freebase集成层：填充MID值
- LightRAG集成层：可留空或使用其他标识

## 依赖关系

```
contracts/
  └── 无外部依赖（纯数据定义）
```

## 待重构清单

1. **类重命名**：
   - `RelationEnvAction` → `EdgeEnvAction`
   - `RelationEnvState` → `EdgeEnvState`

2. **新增数据类**：
   - `CandidateEdge` - 候选边结构

3. **字段重构**：
   - `relation_select` → `edge_select`
   - `relation_set` → `candidate_edges`

4. **方法更新**：
   - `select_relation()` → `select_edge()`

5. **导出更新** (`__init__.py`)：
   - 新增 `CandidateEdge`, `EdgeEnvAction`, `EdgeEnvState`
   - 保留旧名称或标记废弃

## 相关文档

- [../AGENTS.md](../AGENTS.md) - 核心包总览
- [../envs/AGENTS.md](../envs/AGENTS.md) - 环境层（使用状态和动作）
- [../policies/AGENTS.md](../policies/AGENTS.md) - 策略层（使用动作）
- [../providers/AGENTS.md](../providers/AGENTS.md) - 提供者层（构建边数据）
- [../../docs/freebase_rebuild_guide.md](../../docs/freebase_rebuild_guide.md) - 重构指南