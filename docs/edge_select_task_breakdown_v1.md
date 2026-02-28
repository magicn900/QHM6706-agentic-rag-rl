# Edge-Select 重构实施任务清单（细粒度版 v1）

> 目的：给“能力较弱/上下文有限模型”直接执行。
>
> 使用方式：严格按任务编号顺序执行；每完成一个任务即提交一次最小变更（或最小PR）。
>
> 上位文档：
> - `docs/freebase_rebuild_guide.md`
> - `docs/edge_select_refactor_spec_v1.md`
> - `docs/edge_select_interface_draft_v1.md`

---

## 0. 执行总规则（强制）

1. 不修改 `LightRAG/` 目录。
2. 只在本仓库主代码和 `third_party_integration/` 内改动。
3. 废弃即删除：不要新增 `legacy_*` 分支兼容旧模式。
4. 每个任务只做该任务范围内的变更，不夹带无关重构。
5. 所有新增路径使用相对路径和 `pathlib.Path`（如果涉及路径逻辑）。
6. 失败回退策略：外部请求失败返回空结果，不让 episode 崩溃。

---

## Phase A：类型与接口骨架（先铺地基）

## T01 - 新建 Edge 类型定义

- 目标：在 contracts 中引入 `CandidateEdge/EdgeEnvAction/EdgeEnvState` 主类型。
- 修改文件：
  - `agentic_rag_rl/contracts/types.py`
  - `agentic_rag_rl/contracts/__init__.py`
- 完成标准：
  - 新类型可被 import。
  - 旧 `Relation*` 类型仍存在（临时），但新代码优先引用 `Edge*`。
- 禁止事项：
  - 不在此任务里改 env/policy 行为。
- 验证：
  - 运行 `python -m py_compile agentic_rag_rl/contracts/types.py`

## T02 - 引入 GraphAdapterProtocol

- 目标：定义 Provider 与 Integration 之间统一协议（仅协议，不实现）。
- 新增文件：
  - `agentic_rag_rl/contracts/graph_adapter.py`
- 修改文件：
  - `agentic_rag_rl/contracts/__init__.py`
- 完成标准：
  - 协议包含 initialize/finalize/search/expand/answer 方法签名。
- 禁止事项：
  - 不在协议层写 HTTP 细节。
- 验证：
  - `python -m py_compile agentic_rag_rl/contracts/graph_adapter.py`

## T03 - 配置层新增多图源字段

- 目标：`CoreAPIConfig` 增加 `graph_adapter_type` 和 Freebase 配置字段。
- 修改文件：
  - `agentic_rag_rl/config/api_config.py`
- 完成标准：
  - `from_env()` 可读出新环境变量。
  - `validate()` 存在并覆盖最小检查。
- 禁止事项：
  - 不在此任务创建 provider 工厂。
- 验证：
  - `python -m py_compile agentic_rag_rl/config/api_config.py`

---

## Phase B：Prompt 与 Policy 迁移到 Edge-Select

## T04 - Prompt 常量切换到 candidate_edges

- 目标：替换 relation 模板为 edge 模板。
- 修改文件：
  - `agentic_rag_rl/prompts/templates.py`
  - `agentic_rag_rl/prompts/__init__.py`
- 完成标准：
  - 存在 `EDGE_SELECT_REGEX`、`format_candidate_edges()`。
  - `build_action_prompt()` 参数改为 `candidate_edges`。
- 禁止事项：
  - 不在 prompt 层引入 MID 或 internal_ref。
- 验证：
  - `python -m py_compile agentic_rag_rl/prompts/templates.py`

## T05 - Policy 输入类型切换

- 目标：`OpenAIActionPolicy` 从 `RelationEnvState` 切到 `EdgeEnvState`。
- 修改文件：
  - `agentic_rag_rl/policies/openai_action_policy.py`
- 完成标准：
  - prompt 构建使用 `candidate_edges`。
  - 返回动作为 `EdgeEnvAction`。
- 禁止事项：
  - 不改 env 逻辑。
- 验证：
  - `python -m py_compile agentic_rag_rl/policies/openai_action_policy.py`

## T06 - Policy 解析 `<edge_select>` 与回退策略

- 目标：支持 `<edge_select>`，并记录规范 trace 字段。
- 修改文件：
  - `agentic_rag_rl/policies/openai_action_policy.py`
- 完成标准：
  - 可解析多边选择（最少支持 `;` 分隔）。
  - trace 包含：`agent_prompt/agent_raw_response/agent_action_type/agent_action_value`。
- 禁止事项：
  - 不把候选边校验逻辑塞进 prompt 层。
- 验证：
  - 最少新增 1 个简短解析自测（可放 runner/mock，不强制测试框架）。

---

## Phase C：Env 主链路替换

## T07 - 新建 `EdgeSelectionEnv` 骨架

- 目标：新增 env 文件，不在旧文件硬改到不可读。
- 新增文件：
  - `agentic_rag_rl/envs/edge_selection_env.py`
- 修改文件：
  - `agentic_rag_rl/envs/__init__.py`
- 完成标准：
  - 暴露 `reset/step` 接口，输入输出为 Edge 类型。
- 禁止事项：
  - 不删除旧 env（先并存一小步，后续任务删除）。
- 验证：
  - `python -m py_compile agentic_rag_rl/envs/edge_selection_env.py`

## T08 - Env 状态构建改为 candidate_edges

- 目标：`_build_state()` 输出 `EdgeEnvState`，含 `candidate_edges`。
- 修改文件：
  - `agentic_rag_rl/envs/edge_selection_env.py`
- 完成标准：
  - 不再生成 `relation_set`。
- 禁止事项：
  - 不在此任务接入 freebase 特殊逻辑。
- 验证：
  - 手动跑一次 reset（可用 mock provider）。

## T09 - Env 执行动作改为 edge_select

- 目标：`step()` 处理 `EdgeEnvAction.edge_select`，支持多边扩展。
- 修改文件：
  - `agentic_rag_rl/envs/edge_selection_env.py`
- 完成标准：
  - 多边分叉扩展可运行。
  - 去环 + 剪枝流程仍生效。
- 禁止事项：
  - 不在 step 里调用 LLM。
- 验证：
  - 运行最小 episode（mock provider）无异常。

## T10 - Env 终止信息字段标准化

- 目标：`StepResult.info` 添加 `termination_reason` 等关键字段。
- 修改文件：
  - `agentic_rag_rl/envs/edge_selection_env.py`
- 完成标准：
  - done 分支都能给出统一 reason。
- 禁止事项：
  - 不改奖励策略参数本身。
- 验证：
  - 检查 `answer/max_steps/no_candidate_edges` 三类分支。

---

## Phase D：Provider 与工厂可插拔

## T11 - Provider 保留统一接口，兼容 CandidateEdge

- 目标：更新 provider 输出为新 contracts 类型。
- 修改文件：
  - `agentic_rag_rl/providers/base.py`
  - `agentic_rag_rl/providers/lightrag_provider.py`
- 完成标准：
  - `SeedSnapshot.entity_edges` 中元素是 `CandidateEdge`。
- 禁止事项：
  - 不在此任务新增 freebase adapter。
- 验证：
  - lightrag provider 文件可编译。

## T12 - 新增 provider 工厂

- 目标：由配置选择 `lightrag/freebase` provider。
- 新增文件：
  - `agentic_rag_rl/providers/factory.py`
- 修改文件：
  - `agentic_rag_rl/providers/__init__.py`
- 完成标准：
  - `create_graph_provider_from_env()` 可用。
- 禁止事项：
  - 不在工厂里写具体 HTTP 调用。
- 验证：
  - 配置错误时抛可读异常。

---

## Phase E：Freebase Integration 新增

## T13 - 创建 freebase_integration 目录骨架

- 目标：建立 clients/adapters/utils 基本结构。
- 新增目录与文件：
  - `third_party_integration/freebase_integration/__init__.py`
  - `third_party_integration/freebase_integration/clients/entity_search_client.py`
  - `third_party_integration/freebase_integration/clients/sparql_client.py`
  - `third_party_integration/freebase_integration/adapters/freebase_adapter.py`
  - `third_party_integration/freebase_integration/utils/noise_filter.py`
  - `third_party_integration/freebase_integration/utils/mid_mapper.py`
- 完成标准：
  - 所有文件可 import，不报语法错误。
- 禁止事项：
  - 不在本任务完成全部业务逻辑。
- 验证：
  - `python -m py_compile` 覆盖新增文件。

## T14 - 实现 Entity Search Client

- 目标：封装 `POST /search` 调用。
- 修改文件：
  - `third_party_integration/freebase_integration/clients/entity_search_client.py`
- 完成标准：
  - 接口输入 `query/top_k`，输出标准化实体结果。
  - 网络异常返回空列表并记录错误。
- 禁止事项：
  - 不在 client 中做 Env 逻辑。
- 验证：
  - 新增最小 smoke script（可选）。

## T15 - 实现 SPARQL Client

- 目标：封装 `GET /sparql` 调用。
- 修改文件：
  - `third_party_integration/freebase_integration/clients/sparql_client.py`
- 完成标准：
  - 接口接收 query string，返回 json dict。
  - 超时 + 重试可配置。
- 禁止事项：
  - 不做候选边渲染。
- 验证：
  - 本地无服务时可优雅失败（空结果/可读错误）。

## T16 - 实现噪音过滤器

- 目标：落实 Freebase 黑名单过滤。
- 修改文件：
  - `third_party_integration/freebase_integration/utils/noise_filter.py`
- 完成标准：
  - 可按关系前缀过滤 `type.object.*`、`kg.*`、`common.*` 等。
- 禁止事项：
  - 不依赖 policy/env。
- 验证：
  - 增加 5~10 条样例断言（脚本或测试）。

## T17 - 实现 MID 映射器

- 目标：维护 MID -> display_name 映射能力。
- 修改文件：
  - `third_party_integration/freebase_integration/utils/mid_mapper.py`
- 完成标准：
  - 至少包含写入与读取 API。
- 禁止事项：
  - 不把 MID 暴露给 prompts。
- 验证：
  - 简单写入读取自测。

## T18 - 实现 Freebase Adapter（协议实现）

- 目标：将 search + sparql + filter + mapper 串成 `GraphAdapterProtocol` 实现。
- 修改文件：
  - `third_party_integration/freebase_integration/adapters/freebase_adapter.py`
- 完成标准：
  - 输出 `CandidateEdge`，display 字段无 MID。
  - 异常情况下返回空候选，不崩溃。
- 禁止事项：
  - 不在 adapter 中构建 prompt。
- 验证：
  - 至少一个 functional script 能跑到“空结果但不中断”。

---

## Phase F：接线与删除旧模式

## T19 - provider 工厂接入 Freebase adapter

- 目标：将 `graph_adapter_type=freebase` 真正连到 Freebase provider。
- 修改文件：
  - `agentic_rag_rl/providers/factory.py`
  - 相关 provider/adapters 构造代码
- 完成标准：
  - env 装配链路可切换图源。
- 禁止事项：
  - 不在这里改 prompt 文本。
- 验证：
  - 切换配置后 provider 类型符合预期。

## T20 - runner 迁移到新 env/action

- 目标：将 runner 引用换成 `EdgeSelectionEnv` 与新 action/policy。
- 修改文件：
  - `agentic_rag_rl/runners/*.py`（按实际使用逐个改）
- 完成标准：
  - runner 不再依赖 `RelationEnv*`。
- 禁止事项：
  - 不在 runner 写核心逻辑。
- 验证：
  - 至少 1 个 demo 可跑通到 episode 结束。

## T21 - 删除旧 relation_select 主链路

- 目标：移除 relation_set/relation_select 相关旧入口与导出。
- 修改文件：
  - `agentic_rag_rl/envs/relation_selection_env.py`（删除或替换）
  - `agentic_rag_rl/contracts/types.py`（删除旧类型）
  - `agentic_rag_rl/prompts/templates.py`（删除旧常量）
  - 各层 `__init__.py`
- 完成标准：
  - 全仓不再有可执行路径依赖旧模式。
- 禁止事项：
  - 不删除与旧模式无关代码。
- 验证：
  - 全仓 grep：`relation_select|relation_set|RelationEnv` 仅允许出现在迁移文档说明中。

---

## Phase G：文档与验收

## T22 - 更新分层 AGENTS 文档

- 目标：所有层级 AGENTS 与新架构一致。
- 修改文件：
  - `AGENTS.md`
  - `agentic_rag_rl/AGENTS.md`
  - `agentic_rag_rl/*/AGENTS.md`
  - `third_party_integration/AGENTS.md`
- 完成标准：
  - 不再将 relation_select 作为目标架构。
- 禁止事项：
  - 不写与代码冲突的未来时描述。
- 验证：
  - 文档自检（术语一致性）。

## T23 - 新增 Freebase 运行手册（最小版）

- 目标：说明依赖服务、配置项、故障回退行为。
- 新增文件：
  - `third_party_integration/freebase_integration/docs/runbook.md`
- 完成标准：
  - 包含 `/search` 与 `/sparql` 接口说明。
- 禁止事项：
  - 不写机器特定绝对路径。
- 验证：
  - 手册命令均可跨平台理解。

## T24 - 验收脚本与结果标记

- 目标：补一个 edge-select 功能验证脚本。
- 新增文件（建议）：
  - `agentic_rag_rl/runners/edge_env_demo.py`
- 完成标准：
  - 输出候选边数量、动作、终止原因。
  - 成功标记示例：`[OK] Edge-select smoke passed.`
- 禁止事项：
  - 不依赖 LightRAG 内部实现细节。
- 验证：
  - `python -m agentic_rag_rl.runners.edge_env_demo`

---

## 1. 任务依赖图（简版）

- 必须先做：`T01 -> T02 -> T03`
- Prompt/Policy：`T04 -> T05 -> T06`
- Env：`T07 -> T08 -> T09 -> T10`
- Provider：`T11 -> T12`
- Freebase：`T13 -> T14 -> T15 -> T16 -> T17 -> T18`
- 接线与收尾：`T19 -> T20 -> T21 -> T22 -> T23 -> T24`

---

## 2. 每个任务的提交信息建议模板

```text
feat(scope): short summary

- what changed
- what is intentionally not changed
- validation command(s)
```

示例：

```text
feat(contracts): add edge-select core types

- add CandidateEdge/EdgeEnvAction/EdgeEnvState
- keep Relation* types temporarily for migration
- validated with python -m py_compile agentic_rag_rl/contracts/types.py
```

---

## 3. 全局验收清单（最终完成时）

1. 代码主链路只使用 edge-select。
2. Prompt 对 Agent 展示 `candidate_edges`，不含 MID。
3. Freebase 噪音过滤在 Integration 生效。
4. graph adapter 可切换 `lightrag/freebase`。
5. 关键 runner 能完成一次 episode 并输出终止原因。
6. 分层 AGENTS 与 docs 术语一致。
