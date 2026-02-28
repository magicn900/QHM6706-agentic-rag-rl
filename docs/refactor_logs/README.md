# Edge-Select 重构日志索引

> 简洁摘要索引，快速定位各阶段进度与关键变更。

---

## 日志规范

- 每个Phase一个日志文件：`phase_X.md`
- 每条记录包含：任务编号、修改文件、核心变更、验证状态
- 废弃即删除，不保留历史包袱

---

## 进度总览

| Phase | 状态 | 日志文件 |
|-------|------|----------|
| A - 类型与接口骨架 | ✅ 完成 | [phase_a.md](./phase_a.md) |
| B - Prompt与Policy迁移 | ✅ 完成 | [phase_b.md](./phase_b.md) |
| C - Env主链路替换 | ⏳ 待开始 | phase_c.md |

---

## 快速摘要

### Phase A - 类型与接口骨架
- 新增 `CandidateEdge`、`EdgeEnvState`、`EdgeEnvAction` 类型
- 定义 `GraphAdapterProtocol` 多图源协议
- 配置层支持 `graph_adapter_type` + Freebase参数