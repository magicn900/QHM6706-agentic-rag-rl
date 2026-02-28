# AGENTS.md - 策略层 (policies/)

本目录负责动作决策，当前主策略为 `OpenAIActionPolicy`。

## 当前实现

### 文件：`openai_action_policy.py`

**输入/输出合约**：
- 输入：`EdgeEnvState`
- 输出：`EdgeEnvAction`

**职责**：
- 基于 `candidate_edges` 构建提示词
- 调用 OpenAI 兼容接口获取模型响应
- 解析 `<edge_select>` / `<answer>`
- 在解析失败时执行可控回退

**关键解析行为**：
- `<edge_select>` 支持多边选择（分号分隔）
- 支持数字索引与边文本两种匹配方式
- 无法解析时优先回退到首条候选边，若无候选边则回退到保守回答

## Trace 规范

`decide_with_trace()` 至少记录以下字段：
- `agent_prompt`
- `agent_raw_response`
- `agent_action_type`
- `agent_action_value`

可选增强字段：`edge_ids`、`action_type`、`action_value`。

## 职责边界

- 允许：提示词拼接、模型调用、XML解析、动作回退。
- 禁止：SPARQL构造、图扩展、Provider业务逻辑。

## 快速验证

- `python -m agentic_rag_rl.runners.mock_edge_select_test`

## 相关文档

- [../AGENTS.md](../AGENTS.md)
- [../prompts/AGENTS.md](../prompts/AGENTS.md)
- [../contracts/AGENTS.md](../contracts/AGENTS.md)
- [../../docs/freebase_rebuild_guide.md](../../docs/freebase_rebuild_guide.md)