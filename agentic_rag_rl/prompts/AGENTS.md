# AGENTS.md - 提示词层 (prompts/)

本目录负责 Edge-Select 提示词模板与格式化函数。

## 当前实现

### 文件：`templates.py`

**核心常量**：
- `EDGE_SELECT_REGEX`
- `ANSWER_REGEX`
- `EMPTY_KNOWLEDGE`

**核心函数**：
- `format_candidate_edges(candidate_edges)`：将候选边渲染为 `<candidate_edges>` 文本块
- `build_action_prompt(question, knowledge, candidate_edges)`：生成 Policy 输入提示词
- `format_knowledge_body(lines)`：生成 `<knowledge>` 文本块

## 输出规范

1. 对 Agent 仅暴露可读边文本，不暴露 MID。
2. 边文本格式保持 `实体A -关系-> 实体B`（或反向箭头）。
3. Action 指令与 Policy 解析保持一致：`<edge_select>...</edge_select>` 或 `<answer>...</answer>`。

## 职责边界

- 允许：模板定义、文本格式化、正则常量维护。
- 禁止：候选边有效性校验、图扩展逻辑、外部服务调用。

## 相关文档

- [../AGENTS.md](../AGENTS.md)
- [../policies/AGENTS.md](../policies/AGENTS.md)
- [../contracts/AGENTS.md](../contracts/AGENTS.md)
- [../../docs/freebase_rebuild_guide.md](../../docs/freebase_rebuild_guide.md)