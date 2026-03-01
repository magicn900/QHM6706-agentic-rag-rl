# 任务文档：Edge 搜索性能优化（WebQSP导向）

## 2026-03-01 增量修正记录（最小侵入）

本轮基于 smoke 回归，采用“保守增量”策略，仅落地不改变接口签名与分层职责的修改。

### 已落地

1. `agentic_rag_rl/envs/edge_selection_env.py`
   - 修正 `_refresh_candidate_edges()` 的截断时机：
     - 仅在 **rerank 实际触发** 后才应用 `rerank_top_k`；
     - 未触发 rerank 时不再提前按 `rerank_top_k` 截断。
   - 目的：避免常规路径（`enable_rerank=false`）下的有效边被过早裁掉。

2. `agentic_rag_rl/providers/freebase_provider.py`
   - 在 `get_snapshot()` 内新增实体候选轻量重排（按 question/seed 词面重叠）；
   - 增强 `ll_keywords` 清洗（占位实体、关系样式 token、过短词、通用弱语义词）；
   - 保持 `get_snapshot()` 输入输出不变。

3. `agentic_rag_rl/runners/webqsp_freebase_smoke_test.py`
   - 新增候选池诊断字段（不影响主流程）：
     - case 级：`candidate_truncation_observed`、`candidate_drop_total`、`candidate_drop_max`、`candidate_drop_avg`
     - step 级：`candidate_edges_total`、`candidate_edges_shown`、`candidate_drop_count`
     - summary 级：`cases_with_candidate_truncation`、`candidate_drop_total`、`candidate_drop_avg_per_case`

### 行为语义更新

- `rerank_top_k` 的语义现在严格为“**重排后保留条数**”，不再被未重排路径复用。

### 当前结果（定向两题）

- 在 `--start-mode webqsp --top-k 8 --selection-k 3 --policy llm` 下：
  - `answer_hit_rate` 可稳定到 `0.5`（1/2）
  - `route_healthy=true`

### 后续建议

- 下一轮优先改“county 类问题的关系语义判定”（policy/prompt 侧）而非继续加硬过滤；
- 使用本轮新增诊断字段先确认“丢边发生在召回还是展示截断”。

## 背景

当前 `EdgeSelectionEnv` 主链路在 WebQSP 烟测中表现为“链路健康但答案命中低”，核心现象：

- Agent 往往每步只选 1 条边，导致搜索空间受限；
- 候选边较多时，噪声关系占据决策注意力；
- 路径扩展存在“边与路径未对齐”的扩展污染风险，影响多跳质量。

本任务目标是在不破坏现有分层边界（Env/Policy/Provider）的前提下，提升检索-决策-扩展闭环质量。

---

## 本次任务目标

1. 支持可手动配置每步路径选择数量（`selection_k`）；
2. 当候选边数量少于 `selection_k` 且动作为 `edge_select` 时，自动全选全部可扩展边；
3. 引入可选外接重排模型，在候选边过多时先重排并取 Top-K 后再交给 Agent；
4. 修复扩展过程中的路径可达性约束，避免边扩展到不匹配路径；
5. 在 WebQSP runner 中暴露新参数并写入报告配置，便于 A/B 验证。

---

## 文件级改动清单（精确到文件）

### 1) `agentic_rag_rl/envs/edge_selection_env.py`

**改动目标：**

- 在 `EdgeSelectionEnv.__init__` 新增参数：
  - `selection_k: int = 0`（默认不强制）
  - `enable_rerank: bool = False`
  - `rerank_trigger_n: int = 20`
  - `rerank_top_k: int = 12`
- 候选边刷新流程新增“可选重排 + Top-K剪枝”；
- `step()` 处理 `edge_select` 时执行“数量规则”：
  - 候选边数 `<= selection_k`：自动全选；
  - 模型选边 `< selection_k`：按当前候选排序补齐；
  - 模型选边 `> selection_k`：截断到 `selection_k`；
- `_expand_with_edges()` 修正为**边-路径可达性匹配扩展**：
  - 仅当候选边起点与路径尾实体一致时允许扩展；
  - 支持反向边方向的尾实体计算；
  - 防止“每条边广播到所有活跃路径”的污染。
- 在 `StepResult.info` 增加可观测字段：
  - `selection_k`, `auto_selected_all`, `auto_filled_edges`, `effective_edges_count`。

### 2) `agentic_rag_rl/utils/edge_reranker.py`（新文件）

**改动目标：**

- 新增 `EdgeReranker`：
  - 输入：`question` + `candidate_edges`；
  - 输出：按分数降序的 `candidate_edges`；
  - 实现策略：
    1. 优先调用外接 rerank 模型（OpenAI-compatible `/chat/completions` 结构化返回分数）；
    2. 调用失败或无配置时，降级到本地 lexical 分数；
- 保持纯工具层，不引入 Env/Provider 业务逻辑。

### 3) `agentic_rag_rl/utils/__init__.py`

**改动目标：**

- 导出 `EdgeReranker`，保持 `utils` 统一入口。

### 4) `agentic_rag_rl/prompts/templates.py`

**改动目标：**

- `build_action_prompt()` 新增参数 `selection_k: int = 1`；
- 提示词中注入动态约束：
  - 建议优先选择 `selection_k` 条；
  - 若候选不足则由系统自动全选；
  - 保留原有 `<edge_select>/<answer>` 语义。

### 5) `agentic_rag_rl/policies/openai_action_policy.py`

**改动目标：**

- `decide_with_trace()` 构建 prompt 时传入 `selection_k`（来自 `state` 扩展字段或安全默认）；
- 回退动作从“固定首条边”调整为“尊重候选顺序并返回可被 Env 二次裁剪的选择文本”；
- trace 增补 `fallback_reason`（当发生回退时）。

### 6) `agentic_rag_rl/contracts/types.py`

**改动目标：**

- 在 `EdgeEnvState` 增加可选字段：
  - `selection_k: int = 0`
  - `candidate_edges_total: int = 0`（用于标识重排前后差异）

### 7) `agentic_rag_rl/runners/webqsp_freebase_smoke_test.py`

**改动目标：**

- CLI 参数新增：
  - `--selection-k`
  - `--enable-rerank`
  - `--rerank-trigger-n`
  - `--rerank-top-k`
- 构造 `EdgeSelectionEnv` 时透传上述参数；
- 报告 `config` 段写入新增参数，便于实验回放。

### 8) `agentic_rag_rl/config/api_config.py`

**改动目标：**

- 维持现有 rerank 配置读取，修复当前 `from_env()` 中重复赋值问题（重复的 `rerank_*` 参数）；
- 补充属性：`has_rerank_credentials`（可选）。

---

## 验收标准

1. 功能验收：
   - `selection_k` 可配置并在 step 中生效；
   - 候选数不足时自动全选；
   - 候选数过大时可触发重排并剪枝；
   - 扩展不再出现不匹配路径广播。
2. 稳定性验收：
   - rerank 不可用时自动降级，不中断 episode；
   - WebQSP smoke 在默认参数下可继续运行。
3. 可观测性验收：
   - 报告中可查看新增参数与关键决策指标。

---

## 实施顺序

1. 先改 Env（规则与可达性）
2. 再接入 Reranker 工具
3. 同步 Prompt/Policy/Contracts
4. 最后改 Runner 参数并做一次 smoke 验证
