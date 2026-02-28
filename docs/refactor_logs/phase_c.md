# Phase C - Env主链路替换

> 完成时间: 2026-03-01
> 状态: ✅ 已完成并验证

---

## T07 - 新建EdgeSelectionEnv骨架

**修改文件**:
- `agentic_rag_rl/envs/edge_selection_env.py` (新建)
- `agentic_rag_rl/envs/__init__.py`

**核心变更**:
```python
# 1. 新增 EdgeSelectionEnv 类
class EdgeSelectionEnv:
    async def reset(self, question: str) -> EdgeEnvState
    async def step(self, action: EdgeEnvAction) -> StepResult

# 2. 导出更新
from .edge_selection_env import EdgeSelectionEnv
```

**验证**: ✅ py_compile通过

---

## T08 - Env状态构建改为candidate_edges

**修改文件**:
- `agentic_rag_rl/envs/edge_selection_env.py`

**核心变更**:
```python
# 1. _build_state() 返回 EdgeEnvState（含 candidate_edges）
def _build_state(self) -> EdgeEnvState:
    return EdgeEnvState(
        question=self._question,
        knowledge=self._format_knowledge(),
        candidate_edges=self._candidate_edges,  # 候选边列表
        active_paths=self._active_paths,
        history=self._history,
        step_index=self._step_index,
        done=self._done,
    )

# 2. 翻译墙：RelationEdge -> CandidateEdge
def _convert_edges(self, snapshot: SeedSnapshot) -> list[CandidateEdge]:
    # 将内部机器标识转换为 Agent 可读形式
    # forward: entity_name -> next_entity
    # backward: next_entity -> entity_name
```

**验证**: ✅ py_compile通过，集成测试6/6通过

---

## T09 - edge_select动作执行

**修改文件**:
- `agentic_rag_rl/envs/edge_selection_env.py`

**核心变更**:
```python
# 1. 边选择动作解析
_parse_edge_selection(edge_text: str) -> list[CandidateEdge]
# 支持: 完整文本、索引号、混合模式

# 2. 多边分叉扩展
async def _expand_with_edges(self, selected_edges: list[CandidateEdge]):
    # 为每条选中的边扩展路径
    # 支持多选: semicolon(;) 分隔
    # 收集关键词用于下一轮查询
```

**验证**: ✅ 集成测试通过（单边/多边/索引选择）

---

## T10 - 终止信息字段标准化

**修改文件**:
- `agentic_rag_rl/envs/edge_selection_env.py`

**核心变更**:
```python
# 统一 termination_reason 字段
info = {
    "termination_reason": "continue" | "answer_provided" | "max_steps_reached" | "invalid_action",
    "final_answer": answer_text,
    "edges_count": len(selected_edges),
    "edges_selected": [e.edge_id for e in selected_edges],
}
```

**验证**: ✅ 集成测试验证各终止场景

---

## 测试结果

**集成测试** (`test_edge_selection_env.py`):
```
✅ 测试1: 环境重置 - 正确显示候选边
✅ 测试2: 边选择动作 - 步数增加，新边扩展
✅ 测试3: 回答动作 - 正确终止并返回答案
✅ 测试4: 最大步数终止 - 达到限制后触发
✅ 测试5: 空边选择 - 惩罚无效动作
✅ 测试6: 多边同时选择 - 分号分隔多边支持
```

**Bug修复**:
- 边方向转换逻辑修复：forward时源为entity_name，target为next_entity
- 知识块路径显示修复：relation使用纯关系名而非完整display_text

---

## 产物清单

| 文件 | 类型 | 说明 |
|------|------|------|
| `envs/edge_selection_env.py` | 新建 | EdgeSelectionEnv完整实现(~450行) |
| `runners/test_edge_selection_env.py` | 新建 | 集成测试(6个测试用例) |
| `envs/__init__.py` | 修改 | 导出EdgeSelectionEnv |