# AGENTS.md - 策略层 (policies/)

本目录包含Agent策略实现，负责构建提示词和解析LLM响应。

## 当前实现

### 文件：`openai_action_policy.py`

**类**：`OpenAIActionPolicy`

**职责**：
- 构建发送给LLM的动作提示词
- 调用OpenAI兼容API获取响应
- 解析XML标签提取动作

**核心方法**：
```python
async def decide(self, state: RelationEnvState) -> tuple[RelationEnvAction, str]
async def decide_with_trace(self, state: RelationEnvState) -> tuple[RelationEnvAction, str, dict[str, str]]
```

**当前XML解析正则**：
```python
RELATION_SELECT_REGEX = r"<relation_select>(.*?)</relation_select>"
ANSWER_REGEX = r"<answer>(.*?)</answer>"
```

**当前解析逻辑**：
```python
# 解析关系选择
relation_match = re.search(RELATION_SELECT_REGEX, content, flags=re.DOTALL)
if relation_match:
    relation = relation_match.group(1).strip()
    if relation in state.relation_set:  # 验证关系名在列表中
        action = RelationEnvAction.select_relation(relation)

# 解析答案
answer_match = re.search(ANSWER_REGEX, content, flags=re.DOTALL)
if answer_match:
    answer = answer_match.group(1).strip()
    action = RelationEnvAction.answer_now(answer)
```

**当前提示词构建**：
```python
prompt = build_action_prompt(
    question=state.question,
    knowledge=state.knowledge,
    relation_set=state.relation_set,  # 只传入关系名列表
)
```

## 差距分析（与rebuild文档对比）

### 1. XML标签差距
| 当前实现 | 目标架构 | 说明 |
|---------|---------|------|
| `<relation_select>关系名</relation_select>` | `<edge_select edge_id="xxx"/>` | 标签格式需改变 |
| 内容是关系名字符串 | 内容是边的唯一标识 | 解析逻辑需重构 |

### 2. 验证逻辑差距
**当前**：
```python
if relation in state.relation_set:  # 验证关系名是否有效
```

**目标**：
```python
if edge_id in [e.edge_id for e in state.candidate_edges]:  # 验证边ID是否有效
```

### 3. 提示词数据差距
**当前**：`relation_set` 只包含关系名，LLM无法看到目标实体。

**问题**：LLM选择关系时无法判断哪条路径更合理，因为没有目标实体信息。

**目标**：`candidate_edges` 包含完整边信息，LLM可以看到 `A -关系-> B` 格式。

### 4. 回退逻辑差距
**当前**：
```python
# 解析失败时选择第一个关系
fallback_relation = state.relation_set[0] if state.relation_set else ""
```

**目标**：需要根据 `candidate_edges` 实现合理的回退策略。

### 5. 职责边界检查
| 职责 | 当前状态 | 合规性 |
|-----|---------|-------|
| 提示词构建 | `build_action_prompt()` | ✅ 合规 |
| XML解析 | 正则匹配 | ✅ 合规 |
| 调用LLM | `AsyncOpenAI` | ✅ 合规 |
| 拼装SPARQL | 无 | ✅ 合规 |
| 直接访问数据库 | 无 | ✅ 合规 |

## 依赖关系

```
policies/
  ├── config/ (CoreAPIConfig)
  ├── contracts/ (RelationEnvAction, RelationEnvState)
  └── prompts/ (build_action_prompt, RELATION_SELECT_REGEX, ANSWER_REGEX)
```

## 待重构清单

1. **正则表达式更新**：
   - `RELATION_SELECT_REGEX` → `EDGE_SELECT_REGEX`
   - 支持解析 `edge_id` 属性

2. **验证逻辑重构**：
   - 从验证关系名改为验证边ID
   - 需要访问 `state.candidate_edges`

3. **提示词数据源改变**：
   - 从 `relation_set` 改为 `candidate_edges`
   - 需要更新 `build_action_prompt` 函数签名

4. **回退逻辑更新**：
   - 适配新的数据结构

## 相关文档

- [../AGENTS.md](../AGENTS.md) - 核心包总览
- [../prompts/AGENTS.md](../prompts/AGENTS.md) - 提示词模板
- [../contracts/AGENTS.md](../contracts/AGENTS.md) - 数据类型定义
- [../../docs/freebase_rebuild_guide.md](../../docs/freebase_rebuild_guide.md) - 重构指南