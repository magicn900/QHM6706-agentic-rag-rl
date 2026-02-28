# AGENTS.md - 提示词层 (prompts/)

本目录包含提示词模板和格式化函数。

## 当前实现

### 文件：`templates.py`

**常量定义**：
```python
SYSTEM_PROMPT = "你是一个在知识图上进行多路径推理的智能助手。"
ACTION_FORMAT_PROMPT = "请用XML格式回复：<relation_select>关系名</relation_select> 或 <answer>答案</answer>。"
RELATION_CONSTRAINT_PROMPT = "只能从<relation_set>里选择关系。"
DECISION_HINT_PROMPT = "如果信息还不足请选关系扩展；如果足够请直接回答。"

RELATION_SET_TEMPLATE = "<relation_set>{relations}</relation_set>"
KNOWLEDGE_BLOCK_TEMPLATE = "<knowledge>\n{body}\n</knowledge>"

RELATION_SELECT_REGEX = r"<relation_select>(.*?)</relation_select>"
ANSWER_REGEX = r"<answer>(.*?)</answer>"
```

**格式化函数**：
```python
def format_relation_set(relation_set: list[str]) -> str:
    return RELATION_SET_TEMPLATE.format(relations=", ".join(relation_set))

def build_action_prompt(*, question: str, knowledge: str, relation_set: list[str]) -> str:
    return (
        f"{SYSTEM_PROMPT}"
        f"{ACTION_FORMAT_PROMPT}"
        f"{RELATION_CONSTRAINT_PROMPT}\n\n"
        f"问题：{question}\n"
        f"{knowledge}\n"
        f"{format_relation_set(relation_set)}\n"
        f"{DECISION_HINT_PROMPT}"
    )

def format_knowledge_body(lines: list[str]) -> str:
    return KNOWLEDGE_BLOCK_TEMPLATE.format(body="\n".join(lines))
```

**当前提示词示例**：
```
你是一个在知识图上进行多路径推理的智能助手。
请用XML格式回复：<relation_select>关系名</relation_select> 或 <answer>答案</answer>。
只能从<relation_set>里选择关系。

问题：谁影响了塞缪尔·泰勒·柯勒律治？
<knowledge>
爱因斯坦 -导师-> 玻尔
</knowledge>
<relation_set>导师, 学生, 合作</relation_set>
如果信息还不足请选关系扩展；如果足够请直接回答。
```

## 差距分析（与rebuild文档对比）

### 1. XML标签差距
| 当前实现 | 目标架构 | 说明 |
|---------|---------|------|
| `<relation_select>关系名</relation_select>` | `<edge_select edge_id="xxx"/>` | 动作标签格式需改变 |
| `RELATION_SELECT_REGEX` | `EDGE_SELECT_REGEX` | 正则常量需更新 |

### 2. 数据展示差距
**当前**：
```python
RELATION_SET_TEMPLATE = "<relation_set>{relations}</relation_set>"
# 输出：<relation_set>导师, 学生, 合作</relation_set>
```

**问题**：LLM只能看到关系名，无法看到边的目标实体，无法做出有语义的判断。

**目标**：
```python
CANDIDATE_EDGES_TEMPLATE = "<candidate_edges>\n{edges}\n</candidate_edges>"
# 输出：
# <candidate_edges>
# [1] 爱因斯坦 -导师-> 玻尔
# [2] 爱因斯坦 -学生-> 费米
# </candidate_edges>
```

### 3. 指令格式差距
**当前**：
```python
ACTION_FORMAT_PROMPT = "请用XML格式回复：<relation_select>关系名</relation_select> 或 <answer>答案</answer>。"
```

**目标**：
```python
ACTION_FORMAT_PROMPT = "请用XML格式回复：<edge_select id=\"边编号\"/> 或 <answer>答案</answer>。"
```

### 4. 约束条件差距
**当前**：
```python
RELATION_CONSTRAINT_PROMPT = "只能从<relation_set>里选择关系。"
```

**目标**：
```python
EDGE_CONSTRAINT_PROMPT = "只能从<candidate_edges>里选择一条边。"
```

### 5. 函数签名差距
**当前**：
```python
def build_action_prompt(*, question: str, knowledge: str, relation_set: list[str]) -> str
```

**目标**：
```python
def build_action_prompt(*, question: str, knowledge: str, candidate_edges: list[CandidateEdge]) -> str
```

## 依赖关系

```
prompts/
  └── contracts/ (CandidateEdge - 目标架构需要)
```

## 待重构清单

1. **正则常量更新**：
   - 重命名 `RELATION_SELECT_REGEX` → `EDGE_SELECT_REGEX`
   - 新格式：`r'<edge_select[^>]*id=["\']([^"\']+)["\'][^/]*/>'`

2. **模板常量更新**：
   - `RELATION_SET_TEMPLATE` → `CANDIDATE_EDGES_TEMPLATE`
   - `RELATION_CONSTRAINT_PROMPT` → `EDGE_CONSTRAINT_PROMPT`
   - `ACTION_FORMAT_PROMPT` 更新为边选择格式

3. **格式化函数重构**：
   - `format_relation_set()` → `format_candidate_edges()`
   - 输出格式：编号列表，每条边一行

4. **主函数签名更新**：
   - `build_action_prompt()` 参数从 `relation_set` 改为 `candidate_edges`

5. **导出更新** (`__init__.py`)：
   - 移除 `RELATION_SELECT_REGEX`, `format_relation_set`
   - 新增 `EDGE_SELECT_REGEX`, `format_candidate_edges`

## 注意事项

- **MID隐藏**：提示词层不应暴露MID或其他内部标识符
- 边的展示格式应为 `实体A -关系-> 实体B`，只包含可读名称
- 编号（如 `[1]`）用于Agent引用，对应 `edge_id`

## 相关文档

- [../AGENTS.md](../AGENTS.md) - 核心包总览
- [../policies/AGENTS.md](../policies/AGENTS.md) - 策略层（使用提示词）
- [../contracts/AGENTS.md](../contracts/AGENTS.md) - 数据类型定义
- [../../docs/freebase_rebuild_guide.md](../../docs/freebase_rebuild_guide.md) - 重构指南