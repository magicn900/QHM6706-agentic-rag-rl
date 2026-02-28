# Phase B - Prompt与Policy迁移到Edge-Select

> 完成时间: 2026-02-28
> 状态: ✅ 已完成并验证

---

## T04 - Prompt常量切换到candidate_edges

**修改文件**:
- `agentic_rag_rl/prompts/templates.py`
- `agentic_rag_rl/prompts/__init__.py`

**核心变更**:
```python
# 1. 新增多选指导
ACTION_FORMAT_PROMPT = (
    "如需选择多条边，用分号(;)分隔每条边，可选1-3条。"
)

# 2. 边格式改为 "-" 前缀
EDGE_SELECT_REGEX = r"<edge_select>(.*?)</edge_select>"
format_candidate_edges()  # 输出: "- 实体A -关系-> 实体B"

# 3. prompt构建改为 candidate_edges
build_action_prompt(*, question, knowledge, candidate_edges)
```

**验证**: ✅ py_compile通过

---

## T05 - Policy输入类型切换

**修改文件**:
- `agentic_rag_rl/policies/openai_action_policy.py`

**核心变更**:
```python
# 1. 输入改为 EdgeEnvState（含 candidate_edges）
async def decide_with_trace(self, state: EdgeEnvState)

# 2. 支持多边解析（分号分隔）
_parse_edge_selection() -> list[CandidateEdge]

# 3. 返回改为 EdgeEnvAction
EdgeEnvAction.select_edge(edge_text)
EdgeEnvAction.answer_now(answer)
```

**验证**: ✅ py_compile通过

---

## T06 - Policy解析与回退策略

**修改文件**:
- `agentic_rag_rl/policies/openai_action_policy.py`

**核心变更**:
```python
# 1. edge_select 解析
edge_match = re.search(EDGE_SELECT_REGEX, content)
selected_edges = self._parse_edge_selection(raw_edges, candidate_edges)

# 2. 多边返回格式
edge_texts = "; ".join(e.to_display_text() for e in selected_edges)
edge_ids = [e.edge_id for e in selected_edges]

# 3. 完整trace字段
{
    "prompt": prompt,
    "model_output": content,
    "action_type": "edge_select",  # | "answer" | "edge_select_fallback"
    "action_value": edge_texts,
    "edge_ids": edge_ids,
}
```

**验证**: ✅ 模拟测试通过（`mock_edge_select_test.py`）

---

## 模拟测试验证结果

| 测试项 | 输入 | 解析结果 |
|--------|------|----------|
| 单边选择 | `牛顿 -发明-> 微积分` | `['e1']` ✅ |
| 多边选择 | `边1; 边2` | `['e1', 'e2']` ✅ |
| 数字索引 | `1` | `['e1']` ✅ |
| 回答 | `<answer>牛顿发明了微积分</answer>` | 正常解析 ✅ |
| 输出格式 | `<think>\n...` `\n<edge_select>...` | 正确解析 ✅ |

---

## 输出格式规范（与LLM实际输出一致）

```
<think>
我需要选择第一条边来扩展信息。
</think>
<edge_select>牛顿 -发明-> 微积分; 牛顿 -发现-> 万有引力</edge_select>
```

或

```
<think>
根据现有知识，我可以回答这个问题。
</think>
<answer>牛顿发明了微积分</answer>
```