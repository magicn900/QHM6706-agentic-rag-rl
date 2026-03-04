# Phase G - 文档与验收

> 完成时间: 2026-03-01
> 状态: ✅ 已完成并验证

---

## T22 - AGENTS.md 文档同步

**修改文件**:
- `AGENTS.md` (根目录)
- `agentic_rag_rl/AGENTS.md`
- `agentic_rag_rl/envs/AGENTS.md`
- `agentic_rag_rl/policies/AGENTS.md`
- `agentic_rag_rl/prompts/AGENTS.md`
- `agentic_rag_rl/providers/AGENTS.md`
- `agentic_rag_rl/contracts/AGENTS.md`
- `agentic_rag_rl/config/AGENTS.md`
- `third_party_integration/AGENTS.md`

**核心变更**:
- 移除 `relation_select` 相关文档，聚焦 `edge_select` 架构
- 添加 Freebase 集成约束说明（POST /search, GET /sparql, fallback 行为）
- 明确模块职责边界：Env 过滤、Policy 提示词、Integration HTTP 调用

**验证**: ✅ 所有文件通过语法检查，无错误

---

## T23 - Freebase 集成 Runbook

**新增文件**:
- `third_party_integration/freebase_integration/docs/runbook.md`

**核心内容**:
- 服务依赖说明（/search at localhost:8000, /sparql at localhost:8890）
- 环境变量配置
- 验证命令
- Fallback 行为说明
- 常见问题排查

**验证**: ✅ 文件已创建并完成内容编写

---

## T24 - Edge-Select Smoke Test

**新增文件**:
- `agentic_rag_rl/runners/edge_env_demo.py`

**核心变更**:
- 创建 DemoMockProvider 用于离线测试
- 实现 EdgeSelectionEnv 完整流程验证
- 测试 reset() 和 step() 动作序列

**验证**: ✅ Smoke test 通过

---

## 测试结果

**Smoke Test** (`edge_env_demo.py`):
```
候选边数量(reset): 2
动作(step1): edge_select -> Linux -最初由...开发-> 林纳斯·托瓦兹
动作(step2): answer -> 结束episode
终止原因: answer_provided
[OK] Edge-select smoke passed.
```

---

## 验收清单

| 验收项 | 状态 |
|--------|------|
| AGENTS.md 文档同步 | ✅ |
| Freebase Runbook | ✅ |
| Edge-Select Smoke Test | ✅ |
| 无语法错误 | ✅ |
| 功能流程验证 | ✅ |

---

## 遗留问题

无

---

## 下一步

- 持续迭代优化
- 监控外部服务可用性

---

## T25 - WebQSP Freebase 烟测文档回填与边界纠偏

**修改文件**:
- `AGENTS.md`
- `README.md`
- `agentic_rag_rl/AGENTS.md`
- `third_party_integration/AGENTS.md`
- `third_party_integration/freebase_integration/docs/runbook.md`

**核心变更**:
- 新增 WebQSP Freebase 烟测命令与成功口径（`route_healthy: true`）
- 文档化报告输出路径：`agentic_rag_rl/temp/freebase_webqsp_smoke/report.json`
- 明确边界约束：Runner 禁止直连 Integration client，附加能力经 Provider 抽象暴露
- 同步当前指标口径：`cases_with_zero_overlap_selection` 仅统计 `edge_select*`
- 补充Unknown Entity策略：对 Agent 使用 `Unknown Entity#N` 占位，内部保留 MID 可追踪

**验证**: ✅ 文档内容与当前实现一致（含 smoke 脚本、Provider 能力、集成层行为）