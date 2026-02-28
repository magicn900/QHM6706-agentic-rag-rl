# Edge-Select 重构与新增功能规范（Spec v1）

> 状态：Draft v1（架构与职责版）
> 
> 依据：`docs/freebase_rebuild_guide.md`（权威）+ 当前仓库实现现状（relation_select）
> 
> 目的：统一下一阶段重构方向，先定义“做什么、谁负责、边界在哪”，不落实现细节。

---

## 1. 背景与目标

当前主链路为 `relation_select`（关系名选择），与目标架构 `edge_select`（完整边选择）不一致。该差异会导致：

- Agent 缺乏目标实体语义，选择歧义高。
- Freebase 噪音关系直接暴露给 Agent，推理质量不稳定。
- Provider 与具体数据源耦合，难以扩展多图源。

本 Spec 的目标是：

1. 将系统统一到 **Edge-Select 推理范式**。
2. 明确 **Env / Policy / Provider / Integration / Contracts / Prompts / Config** 的职责边界。
3. 定义新增功能的归属层级与最小验收标准。
4. 建立后续代码重构的唯一对齐口径，避免旧模式补丁化演进。

---

## 2. 总体架构（目标）

```text
User Question
   ↓
Env（状态机、候选边管理、路径扩展与剪枝）
   ↓ uses
Policy（Prompt构建 + XML动作解析 + LLM决策）
   ↓ returns action
Env 执行动作（edge_select/answer）
   ↓ calls
Provider（统一主流程 + 统一输出契约）
   ↓ via protocol
Integration（LightRAG / Freebase 适配实现）
   ↓
外部图数据源（LightRAG内部接口 / Freebase HTTP服务）
```

关键原则：

- **翻译墙**：Agent 只看可读语义，不看 MID 或底层系统字段。
- **单一主流程**：Provider/Env/Policy 不按图源复制流程。
- **差异下沉**：图源差异尽量收敛在 Integration。
- **废弃即删除**：移除 relation_select / relation_set 旧路径，不保留 legacy 分支。

---

## 3. 分层职责规范（核心）

## 3.1 Env 层（`agentic_rag_rl/envs/`）

### 必须负责

- Episode 生命周期：`reset -> step -> done`。
- 活跃路径维护与扩展（基于完整边）。
- 候选边聚合、去重、图环路处理、剪枝（beam）。
- `knowledge` 与 `candidate_edges` 的语义状态构建。
- reward 与终止条件的框架侧判定。

### 禁止负责

- 任何 LLM 调用。
- SPARQL 字符串拼接或 HTTP 细节。
- Freebase MID 映射细节。

### 目标主对象

- `EdgeSelectionEnv`
- `EdgeEnvState`
- `StepResult`

## 3.2 Policy 层（`agentic_rag_rl/policies/`）

### 必须负责

- 根据 `question + knowledge + candidate_edges` 构建提示词。
- 解析 Agent 输出中的：
  - `<think>...</think>`（保留原文）
  - `<edge_select>...</edge_select>`（允许多边）
  - `<answer>...</answer>`
- 将解析结果映射为统一动作对象（`EdgeEnvAction`）。

### 禁止负责

- 图扩展、路径管理、剪枝。
- SPARQL 构建与任何图源调用。

### 目标主对象

- `OpenAIActionPolicy`（保留命名可讨论）
- `EdgeEnvAction`

## 3.3 Prompts 层（`agentic_rag_rl/prompts/`）

### 必须负责

- 模板常量与格式化函数。
- `<candidate_edges>` 块的文本渲染规范。
- XML 标签解析 regex 常量的统一出口。

### 禁止负责

- 业务决策逻辑。
- 数据源相关字段拼接（如 MID）。

### 强约束

- 旧模板 `<relation_set>` 全量废弃。
- 对 Agent 暴露边格式：`实体A -关系-> 实体B`。

## 3.4 Contracts 层（`agentic_rag_rl/contracts/`）

### 必须负责

- 统一数据结构定义（跨层类型契约）。
- 内外字段语义区分（展示字段 vs 内部引用字段）。

### 禁止负责

- 任意方法实现的业务逻辑。

### 目标关键类型（命名级别）

- `CandidateEdge`（可读边 + 内部引用）
- `EdgeEnvState`
- `EdgeEnvAction`
- `PathTrace`
- `SeedSnapshot`

## 3.5 Provider 层（`agentic_rag_rl/providers/`）

### 必须负责

- 对 Env 提供统一图查询主流程入口。
- 对接 `GraphAdapterProtocol`，屏蔽底层图源差异。
- 统一把 Integration 输出映射为 Contracts 类型。

### 禁止负责

- Prompt/LLM 决策。
- Freebase 特有过滤规则硬编码（应在 Integration）。

### 目标结构

- `GraphProvider`（统一接口）
- provider 工厂（根据配置加载对应 adapter）

## 3.6 Integration 层（`third_party_integration/`）

### 必须负责

- 外部服务调用、超时、重试、异常降级。
- 图源特定映射（如 Freebase MID 双轨制）。
- 图源特定噪音过滤（尤其 Freebase 黑名单关系）。
- 实现统一适配协议：`GraphAdapterProtocol`。

### 禁止负责

- Env 状态机逻辑。
- Policy 提示词与 XML 解析。

### 子域分工

- `lightrag_integration/`：保留并适配协议。
- `freebase_integration/`：新增，封装 `/search` 与 `/sparql`。

## 3.7 Config 层（`agentic_rag_rl/config/`）

### 必须负责

- 图源类型配置（`lightrag | freebase`）。
- Freebase 接口地址、超时、重试等参数加载与验证。
- 保持对 OpenAI-compatible base_url/api_key 的兼容策略。

### 禁止负责

- 运行时状态管理。
- 业务逻辑分支执行。

---

## 4. 新增功能清单（按层归属）

## F1. Edge-Select 动作链路（核心）

- 归属层：`contracts/envs/policies/prompts`
- 目标：从 `relation_select` 迁移为 `edge_select`。
- 结果：Agent 基于完整边进行选择，允许多选。

## F2. Candidate Edges 语义提示池

- 归属层：`envs/prompts/policies`
- 目标：提示词统一使用 `<candidate_edges>`，替换 `<relation_set>`。
- 结果：Agent 可见目标实体语义，降低歧义。

## F3. Freebase 噪音关系过滤

- 归属层：`third_party_integration/freebase_integration`
- 目标：过滤 `type.object.*`、`kg.*`、`common.*` 等系统关系。
- 结果：减少无效边进入 Agent 上下文。

## F4. MID 双轨制（Freebase）

- 归属层：`contracts + freebase_integration`
- 目标：内部保留 MID，外部展示可读实体名。
- 结果：保证机器可追踪与模型可理解兼容。

## F5. 多图源可插拔

- 归属层：`providers/config/third_party_integration`
- 目标：通过统一协议接入 LightRAG 与 Freebase。
- 结果：Env/Policy 无需感知图源类型。

## F6. 统一日志字段规范

- 归属层：全链路（env/policy/provider）
- 目标：日志语义统一，便于追踪 Episode。
- 结果：避免 `llm_output` 等歧义命名。

建议字段（最小集）：

- `agent_prompt`
- `agent_raw_response`
- `agent_action_type`
- `agent_action_value`
- `candidate_edges_length`
- `active_paths_length`
- `environment_reward`
- `termination_reason`

---

## 5. 协议与数据边界（概念级）

本节仅定义语义，不给实现细节。

- `CandidateEdge`：
  - 对 Agent 可读字段：`src_name`, `relation`, `tgt_name`, `display_text`
  - 对系统可追踪字段：`edge_id`, `internal_src_ref`, `internal_tgt_ref`（Freebase 为 MID）
- `EdgeEnvAction`：
  - `edge_select`（一条或多条候选边引用）
  - `answer`（终止回答）
- `EdgeEnvState`：
  - `question`, `knowledge`, `candidate_edges`, `active_paths`, `history`, `step_index`, `done`

边界约束：

- Agent 输入不得出现 MID。
- Env 不可直接调用 Integration HTTP 客户端。
- Policy 不可构建 SPARQL。

---

## 6. 模块迁移映射（现状 -> 目标）

- `RelationSelectionEnv` -> `EdgeSelectionEnv`
- `RelationEnvState.relation_set` -> `EdgeEnvState.candidate_edges`
- `RelationEnvAction.relation_select` -> `EdgeEnvAction.edge_select`
- `RELATION_SELECT_REGEX` -> `EDGE_SELECT_REGEX`
- Prompt 块 `<relation_set>` -> `<candidate_edges>`
- `third_party_integration/` 新增 `freebase_integration/`

迁移策略：

- 不保留 legacy 双栈运行。
- 所有 relation_select 相关入口、常量、分支、文档应被移除或替换。

---

## 7. 分阶段验收标准（仅架构阶段）

当前阶段为“规范与边界对齐”，不要求功能完全可运行。

### A. 规范一致性验收

- 各层 `AGENTS.md` 的职责描述与本 Spec 一致。
- 所有新文档不再使用 relation_set/relation_select 作为目标术语。
- 明确标注 Freebase 相关职责在 Integration 层。

### B. 接口准备度验收

- Contracts/Provider 层具备 Edge-Select 命名与协议占位定义（可为草图）。
- 配置层明确多图源选择项及 Freebase 参数项。

### C. 日志语义验收

- 示例日志字段与命名规范可在文档中追溯。

---

## 8. 非目标（本阶段不做）

- 不在本 Spec 内定义具体代码实现、算法细节、重试参数调优值。
- 不在本阶段编写 Freebase SPARQL 模板细节。
- 不扩展与 Edge-Select 无关的新能力（UI、可视化等）。

---

## 9. 决策优先级

发生冲突时按以下优先级执行：

1. `docs/freebase_rebuild_guide.md`
2. 本文档（`docs/edge_select_refactor_spec_v1.md`）
3. 各层 `AGENTS.md`
4. 现有代码实现

如现有代码与 1/2 冲突：按“废弃即删除”原则处理。

---

## 10. 文档落地状态（更新）

- 已产出逐层接口草案文档：`docs/edge_select_interface_draft_v1.md`
- 已产出细粒度迁移任务清单：`docs/edge_select_task_breakdown_v1.md`
- 待产出文档：Freebase 集成运行手册（含错误回退策略）
