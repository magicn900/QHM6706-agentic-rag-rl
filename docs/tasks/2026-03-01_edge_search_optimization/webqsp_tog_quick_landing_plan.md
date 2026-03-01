# WebQSP 快速改进方案（参考 ToG，可直接落地）

## 1. 目标与范围

目标：在不大改架构的前提下，把 `WebQSP` 的“可答率 + 命中率”快速拉升，并减少“扩展到第2步后仍未收敛”的失败模式。

范围：只改你当前主链路（`EdgeSelectionEnv + OpenAIActionPolicy + FreebaseProvider + smoke runner`），不改 `LightRAG/`。

---

## 2. 当前症状（结合你现有报告）

来自 `reports/webqsp_ab_k3_no_rerank.json` 与复盘文档：

- `answer_hit_rate = 0.2143`（可评估样本 28 题中仅 6 题命中）。
- 典型失败是：首轮被噪声候选带偏，第二轮 `max_steps_reached` 结束。
- 存在 `action_parse_fallback`，且 fallback 发生后常会继续偏离问题语义。
- `unknown_mid` 解析能力不足，导致路径在“匿名实体节点”处断裂。

这些现象和 ToG 论文代码里的“先剪枝后扩展、再做可答判定”的思路高度匹配，说明你现在缺的是**分阶段约束**，不是缺单点技巧。

---

## 3. ToG 中最值得迁移的 4 个机制

## 3.1 关系先剪枝（Relation Prune）

ToG 的做法：先从关系集合里选 top-k 关系，再展开实体。

你这边可迁移为：

- 对 `candidate_edges` 先做“关系层聚合打分”，每个关系只保留 1~2 条代表边；
- 再把压缩后的边集喂给策略模型。

价值：降低提示词噪声密度，避免模型在同一关系的重复边里浪费注意力。

---

## 3.2 实体二次打分（Entity Score）

ToG 的做法：关系通过后，再对候选实体做二次打分。

你这边可迁移为：

- 当同一关系对应多个 target（例如 `tv_program.episodes` 连出大量宾语）时，先做轻量 lexical/BM25 打分，保留 top-n；
- LLM 只在“压缩后的实体候选”上做选择。

价值：显著降低“长尾无关实体”造成的路径漂移。

---

## 3.3 可答性判定（Sufficiency Gate）

ToG 的做法：每一深度后有 `Yes/No` 充足性判定，`Yes` 就直接回答，`No` 再继续扩展。

你这边可迁移为：

- 在每步 `edge_select` 前增加一个极轻量 gate：
  - 输入：`question + 当前knowledge`；
  - 输出：`<sufficient>yes/no</sufficient>`；
- 若 `yes`，直接触发 `<answer>` 分支，不再强行扩展到 `selection_k`。

价值：解决你现在“明明已有答案线索但仍扩展到超步数”的问题。

---

## 3.4 非LLM兜底剪枝（BM25/Sentence-BERT）

ToG 的做法：剪枝可用 LLM，也可用 BM25/SBERT。

你这边可迁移为：

- 当模型输出不可解析或返回“无有效选边”时，兜底不走“首边”，改走 `BM25(query, candidate_edges)` top-k；
- 仅在 top-k 全部低分时才触发“保守回答”。

价值：让 fallback 变成“弱语义检索”而不是“随机首条”。

---

## 4. 与你现有代码的映射（直接可改）

## 4.1 Prompt 层（最小改动，高收益）

文件：`agentic_rag_rl/prompts/templates.py`

建议新增两段约束：

1. **先判定是否足够回答**（ToG 的 evaluate 思路）
2. **若扩展，优先选“关系多样化”而非同关系重复边**

可直接加在 `DECISION_HINT_PROMPT_TEMPLATE`：

```text
先判断当前<knowledge>是否已足够回答：若足够，请直接输出<answer>。
若不足再输出<edge_select>。
若选择多条边，优先覆盖不同关系类型，避免选择同一关系下的重复候选。
```

---

## 4.2 Policy 层（fallback 从“首条”升级到“检索式兜底”）

文件：`agentic_rag_rl/policies/openai_action_policy.py`

你已经有 `_select_fallback_edges()`，但建议再加两点：

- 把关系去重作为第一优先级（同关系最多1条，除非不足 k）；
- 对 `question` 做模板词增强（如 `mom/mother -> parents/children`，`where -> location/country`），再计算 overlap。

这一步是 ToG “关系优先”思想的低成本版实现。

---

## 4.3 Env 层（改成“自适应 selection_k”）

文件：`agentic_rag_rl/envs/edge_selection_env.py`

当前固定 `selection_k=3` 在 WebQSP 上偏激进。建议改成：

- `step_index == 0`：`k=1`（先稳住主路径）
- `step_index >= 1`：`k=2`（再做受控扩展）
- 仅在候选质量高（噪声比低于阈值）时升到 `k=3`

这是最符合你当前失败分布的“快修参数策略”。

---

## 4.4 Provider 层（ToG式“先关系后实体”压缩）

文件：`agentic_rag_rl/providers/freebase_provider.py`

在 `get_snapshot()` 返回前增加一层轻量压缩：

- 按 relation 分桶；
- 每桶按 lexical score 取 top-1/2；
- 全局再取 top-N。

这等价于把 ToG 的 relation prune + entity score 以工程友好方式嵌到你当前流程中。

---

## 5. 三天可执行落地计划（建议按优先级）

## Day 1（P0，必须做）

1. Prompt 增加“先判可答，再扩展”规则。  
2. Policy fallback 改为“关系去重 + overlap/BM25 top-k”。  
3. Env 改自适应 `selection_k`（1 -> 2，条件升3）。

预期：`max_steps_reached` 占比下降，`action_parse_fallback` 造成的偏航减轻。

## Day 2（P0+）

1. Provider 加 relation-bucket 压缩。  
2. unknown MID probe 做“问题词命中优先解析”（先解与问题词重合的 MID）。

预期：`unknown_mid_resolved` 上升，候选边噪声占比下降。

## Day 3（P1，补强）

1. 增加轻量 sufficiency gate（可复用现有 action model）。  
2. 增加一个 `--ablation-mode`（baseline / gate / gate+bucket）方便回归。

预期：在同样 `max_steps` 下，命中率提升且回答更早收敛。

---

## 6. 建议的 A/B 实验矩阵

固定参数：`sample_size=30, seed=42, max_steps=2, selection_k=3(仅baseline), rerank=off`。

建议新增 3 组：

1. `adaptive_k`：`k0=1,k1=2`  
2. `adaptive_k + relation_bucket`  
3. `adaptive_k + relation_bucket + sufficiency_gate`

重点比较指标：

- `answer_hit_rate`（主指标）
- `cases_with_invalid_action`
- `cases_with_zero_overlap_selection`
- `max_steps_reached` 占比
- `unknown_mid_resolved / unknown_mid_total`

验收建议：

- 主指标至少提升到 `>= 0.30`；
- 且 `invalid_action` 不上升。

---

## 7. 可直接复用的提示词片段（ToG风格，适配你当前标签）

```text
你需要先判断：当前<knowledge>是否足够回答问题。
若足够，直接输出<answer>...</answer>。
若不足，再输出<edge_select>...</edge_select>。

选择边时遵循：
1) 优先与问题谓词直接匹配的关系；
2) 优先覆盖不同关系类型，避免同关系重复边；
3) 若候选边大多为出版/元数据关系，优先跳过这些关系。
```

---

## 8. 风险与回退

风险1：过强关系去重可能误伤真实多跳链。  
应对：先限制为“同关系最多2条”，并在日志记录被裁剪数量。

风险2：sufficiency gate 误判“可答”。  
应对：先只在 `step>=1` 启用 gate，首步不启用。

风险3：BM25 fallback 与 LLM 选择冲突。  
应对：只在解析失败时触发，不干预可解析输出。

---

## 9. 结论

你当前系统已经具备 ToG 思路的一部分（多跳扩展、候选重排、解析容错），但还缺“阶段化决策约束”：

- 先压噪（relation/entity）
- 再扩展（adaptive k）
- 再判断是否收敛（sufficiency gate）

按本文 P0 改造，你可以在不重写框架的情况下，快速把 WebQSP 表现从“能跑通”推进到“更稳定可答”。