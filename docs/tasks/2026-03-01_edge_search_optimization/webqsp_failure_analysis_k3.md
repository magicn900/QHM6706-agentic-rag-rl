# WebQSP 失败复盘（selection_k=3，无 rerank）

## 实验上下文

- 报告文件：`reports/webqsp_ab_k3_no_rerank.json`
- 采样参数：`--sample-size 30 --seed 42 --selection-k 3`
- 现象：命中率偏低，且大量 case 在两步后以 `max_steps_reached` 结束。

## 关键发现（逐题级，不仅看 summary）

### 1) 候选边语义域漂移是首要问题

- 在失败样本中，首步候选边包含大量噪声域关系（`music.* / book.* / tv.tv_series_episode.* / type.user.* / wordnet`）。
- 对比统计（首步候选噪声占比）：
  - 成功样本均值：约 `0.3556`
  - 失败样本均值：约 `0.6083`
- 代表样本：
  - `WebQTest-1695`（Truman）候选中混入 music/book/wordnet
  - `WebQTest-1249`（state flower）候选被 TV/music 关系干扰
  - `WebQTest-111`（Carpathian location）候选几乎全是 music 轨迹

### 2) 动作解析失败触发 fallback，放大了漂移

- 多个失败 case 在 trace 中出现：`无法解析标准标签，回退选择首个边`。
- 当首屏候选本身噪声高时，fallback 进一步把路径推向无关边。
- 代表样本：`WebQTest-1050 / 1695 / 1249 / 133 / 1616`。

### 3) selection_k=3 + max_steps=2 造成“扩展优先但未收敛回答”

- 提示词要求信息不足时优先选 3 条边，模型倾向继续扩展而不是回答。
- 大量 case 在第 2 步结束时触发 `max_steps_reached`，输出模板化 fallback answer。

### 4) unknown MID 解析阻塞

- 若路径命中 `Unknown Entity#N`，且 name probe 未解析成功，后续可回答性显著下降。
- 多个失败题出现 `unknown_mid_count > 0` 且 `resolved_name_count = 0`。

## 本轮改进计划（P0）

1. **候选边域去噪（Env）**
   - 在候选排序阶段增加“问题语义感知”的噪声域降权：
     - 非媒体问句中，降低 `music.* / book.* / tv_episode.* / wordnet / type.user.* / pipeline.*`。
   - 不直接删除边，只做强降权，避免误伤真实答案域。

2. **动作解析容错（Policy）**
   - 支持半结构化标签解析（闭合标签缺失、中文分号、换行列表）。
   - 对未精确命中的边文本，做规范化匹配（大小写、空白、标点）。
   - 解析失败 fallback 时，不再盲目取首条，改为基于问题词面重叠选择更相关边。

## 复测判定标准

- 维持同参数再次运行：`sample-size=30, seed=42, selection_k=3, rerank=off`。
- 重点观察：
  - `action_parse_fallback` 次数是否下降；
  - 失败样本候选噪声占比是否下降；
  - `zero_overlap_selected` 是否下降；
  - `answer_hit_rate` 是否改善或至少不退化明显。
