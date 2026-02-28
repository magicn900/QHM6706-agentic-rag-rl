# Freebase 环境重构架构与开发指南（纯净重置版）

本文档是一切重构工作的基础蓝图。下一轮迭代的模型必须**带有批判性地审视**项目中原有的残留代码和老旧文档（如已废弃的 relation_set 等概念），**一切实现以本指南描述的概念框架为准**。不要给错误的旧代码打补丁，遇到冲突直接推翻重写。

> **当前阶段说明（重要）**：本阶段的主要目标是**梳理现有架构并标记与目标架构的差距**，防止文档误导后续模型。实现细节与代码落地可在下一阶段执行。

---

## 一、 宏观架构设计：Agent 交互流程与框架执行顺序

系统由两个完全隔离的域组成：**框架环境层（Env & Provider）** 与 **智能代理层（Agent / Policy）**。
它们之间存在一道严格的“翻译墙”，Agent 不应看到底层机器标识（如 Freebase 的 MID），也不应该关心图合并、剪枝等工程细节。

补充架构约束：
- Provider 层应保持**统一主逻辑**，不按图源复制一套业务流程。
- LightRAG 与 Freebase 的主要差异应尽量收敛在 Integration 层（适配器/客户端实现差异）。
- Env/Policy 依赖统一输出行为，不感知底层图源类型。

### 1. 核心执行循环（Data Flow）

这是一个基于“边”（Edge）的推理循环，**废弃了以往的纯关系（Relation）选择**。

1. **第 0 步：初始化与实体召回**
   - 框架收到 User Question。
   - 框架通过向量数据库/外部服务（`/search`）召回初始实体（如 `m.0c9075n`）。
   - 框架查询 SPARQL 获取这些实体的“一跳完整边”。

2. **第 1 步：渲染语义状态（翻译墙：内 -> 外）**
   - 框架将自己内部维护的 `[MID, raw_relation, MID]` 转换为人类和 Agent 可读的语言。
   - 构造 **当前知识 (Knowledge)**：纯文本描述活跃的图路径起点（如 `已选路径: 谷歌`）。
   - 构造 **候选边 (Candidate Edges)**：将所有下一步可走的边渲染为 `<candidate_edges> 实体A -关系名-> 实体B </candidate_edges>`。
   - *（注：无名称映射的无效边在此阶段直接丢弃，绝不透传给 Agent）*。

3. **第 2 步：Agent 思考与决策（Agent 域）**
   - Agent 接收纯净的上下文（只有语义化的题面、Knowledge、Candidate Edges）。
   - Agent 发挥纯粹的逻辑推理能力，输出思考过程 `<think>...</think>`。
   - Agent 仅允许产生两种法定动作：
     - **动作 A**：选择继续探索。基于候选池发出选边指令，允许多选。格式：`<edge_select>实体A -关系1-> 实体B ; 实体C -关系2-> 实体D</edge_select>`。
     - **动作 B**：信息已充分或步数耗尽，直接作答。格式：`<answer>最终答案</answer>`。

4. **第 3 步：框架执行图更新（翻译墙：外 -> 内）**
   - 框架解析 `<edge_select>` 的文本，将其反向映射回底层的 `[MID, raw_relation, MID]`。
   - 框架将选中的多条边**分叉扩展**到当前的状态图上。
   - 框架执行**图工程管理**：去重、处理环路、并使用启发式规则或评分机制将分支数**剪枝**到规定的 `beam_width`。
   - 回到第 1 步，直到 Agent 输出 `<answer>` 或达到最大步数（`max_steps`）。

---

## 二、 用户可见的日志系统：期望输出示例

良好的日志是掌控 Agent 行为的唯一途径。不需要输出冗长的 JSON 或冗余变量名，实时控制台日志应该高度语义化、人类可读，展现出双方清晰的交互过程。

**【控制台交互日志示例】**

```text
[Episode Start] 题号: Q-1021 | 问题: Who is the original creator of the famous Linux operating system kernel?

--- Step 0 ---
[框架构建状态] 
活跃路径数: 1
候选池规模: 45 条边

[发给 Agent 的提示池摘要]
<knowledge>
当前无活跃路径，初始起点：Linux (操作系统)
</knowledge>
<candidate_edges>
  - Linux -基于-> Unix
  - Linux -编程语言-> C语言
  - Linux -最初由...开发-> 林纳斯·托瓦兹
  - Linux -当前维护者-> Linux基金会
  ... (剩余 41 条省略)
</candidate_edges>

[Agent 输出]
<think>
问题询问的是 Linux 系统的原始创建者 (original creator)。在候选边中，"Linux -最初由...开发-> 林纳斯·托瓦兹" 完美契合了 original creator 这个意图，且指向一个具体的人名实体。我需要选出这条边进行验证。
</think>
<edge_select>Linux -最初由...开发-> 林纳斯·托瓦兹</edge_select>

[框架执行反馈]
成功反解边 IDs，图边界已扩展。奖励: +0.5。当前深度: 1. 未触发终止。

--- Step 1 ---
[框架构建状态] 
活跃路径数: 1
候选池规模: 12 条边

[发给 Agent 的提示池摘要]
<knowledge>
路径1: Linux -最初由...开发-> 林纳斯·托瓦兹
</knowledge>
<candidate_edges>
  - 林纳斯·托瓦兹 -出生地-> 赫尔辛基
  - 林纳斯·托瓦兹 -职业-> 程序员
  - 林纳斯·托瓦兹 -国籍-> 芬兰
  ... 
</candidate_edges>

[Agent 输出]
<think>
当前的知识路径已经锁定了“林纳斯·托瓦兹”作为 Linux 的最初开发者。问题只需要知道是谁，现在信息已经足够了，不需要继续探索他的国籍或出生地。我将直接给出答案。
</think>
<answer>林纳斯·托瓦兹 (Linus Torvalds)</answer>

[Episode End] 
交互结束。总步数: 2 | 评估结果: HIT (True)
```

---

## 三、 当前开发环境与 Freebase 的见解 (坑与反思)

在上一轮的开发中，项目因为忽视了真实环境与理想设计的偏差而变乱。撤回重新开发时，必须明确以下洞察：

1. **关系 vs. 边的核心矛盾（重要转折）**
   - **痛点**：因为本地向量数据库**缺乏针对“关系 (Relation)”的向量索引能力**，如果让 Agent 只抛出一个概念性的“关系名”（比如 `<relation_select>开发</relation_select>`），框架和数据库根本不知道它对应向图里的哪条具体的路线走。当一个实体连接了几十个目标时，这会引发巨大的歧义。
   - **解法**：废弃单纯的“关系选择”，**改为必须连带起始点和目标点的“完整边推演 (Edge Selection)”**。Agent 看到的是明确的 `A -关系-> B` ，选的也是完整的边。这让 Agent 能将实体语义（目标 B 是不是符合预期的人）加入考量，从而彻底规避底层无法进行高精度关系匹配的问题。

2. **Freebase 的数据形状与剧毒噪音**
   - Freebase 中充斥着大量的不可读系统关系（例如 `type.object.*`, `kg.*`, `base.math.*`, `common.*`）。
   - **教训**：绝对不能指望大模型自己去忽略这些。框架在生成 `candidate_edges` 之前，必须有一个强大的**硬编码黑名单/过滤层**。只让有意义的、人类可读的边流入大模型的提示词中。

3. **MID 裸奔导致大模型“失智”（Freebase 语境）**
   - MID（如 `m.0c9075n`）是 Freebase 侧标识，不应外露到 Agent 提示词；否则会明显破坏自然语言推理能力。
   - **教训**：在 Freebase 集成中，边结构应采用内外双轨制：内部保留机器标识（MID/edge_id），对模型侧只暴露 `名称 -别名-> 名称`。
   - **边界说明**：LightRAG 不以 MID 为核心对象，不应被强行套用 MID 字段语义。

4. **弱并发环境下的超时隐患**
   - 外部 `/search` 向量接口和 `SPARQL` 服务都可能遭遇网络拥塞或查询超时，返回的数据未必立等可取。
   - **教训**：所有的外部请求必须增加异常捕获和并发控制，遇到无数据时优雅回退（返回空列表并告诉 Agent 无处可去），而不能抛异常让整个 Agent 循环崩溃。

5. **外部接口调用规范（重要：撤回代码后必需的连接知识）**
   撤回代码后，原有的连接逻辑会丢失，下一轮迭代必须按以下方式调用服务：
   - **实体向量召回 (Entity Server)**：通过 HTTP POST 发送至 `http://localhost:8000/search`。Payload 格式为 `{"query": "搜索词", "top_k": 5}`。返回的数据通常是以 `{"results": [{"name": "实体名", "freebase_ids": ["m.xxx"]}]}` 出现的列表。
   - **SPARQL 图扩展 (Virtuoso)**：通过 HTTP GET 请求 `http://localhost:8890/sparql`，Query Parameter 带上 `query=URL编码后的SPARQL` 以及 `format=application/sparql-results+json`。
   - 这两个接口是整个图环境的唯一数据输入源，任何内部代码逻辑都不应该模拟图状态，必须真实请求这俩接口获取 `[MID, raw_relation, MID]` 结构。

6. **WebQSP 数据集**
   - WebQSP 数据集的 JSON 文件位于 `data/WebQSP.json`。数据结构有待探索理解。

---

## 四、 提高代码可维护性的 AI 开发纪律

在指导下一轮 AI 重写代码时，AI 必须遵循以下原则以抗击上下文漂移：

1. **废弃即删除，严禁叠加补丁**
   - 新架构采用 `candidate_edges` 和 `<edge_select>`。不要在代码里留着 `if legacy_relation_mode:` 的分支，**直接移除**一切跟纯 `relation_set` 与 `relation_select` 相关的代码结构和提示词模板。保持 codebase 清脆短小。
2. **警惕旧文档的误导**
   - 现存环境里的一些 `xxx_spec.md` 或 `AGENTS.md` 是在旧探索中生成的，里面的变量名或字段解释如果是围绕旧模式的，**不要遵循它**。任何代码行为均以**本重定义文档**的业务意图为绝对准绳。
3. **隔离领域，各司其职**
   - `Env` 里面只写过滤逻辑、拼接文本逻辑、图层级的剪枝逻辑。绝不写带有 `openai_client` 的调用。
   - `Policy/Agent` 里面只写 prompt 构建、提取正则 `<think>` 和 `<edge...>` 的逻辑，绝不写带有 SPARQL 字符串拼装的代码。
   - `Provider` 维持统一主流程与统一输出契约；图源差异（LightRAG/Freebase）尽量放在 Integration 层实现。
4. **统一日志字段（明确指代）**
   - 日志的字典中应使用语义明确的 `agent_prompt`, `agent_raw_response`, `environment_reward`, `candidate_edges_length` 等名词。一旦发现名称如 `llm_output` 无法分辨是实体提取 LLM 还是决断 Agent LLM 时，重命名它，以免看 log 时南辕北辙。