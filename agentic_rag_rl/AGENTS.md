# AGENTS.md - agentic_rag_rl 核心包

本目录包含项目的核心RL环境和相关抽象层。

## 目录结构

```
agentic_rag_rl/
├── config/        # API配置和环境变量
├── contracts/     # 数据类型定义（类型合约）
├── envs/          # RL环境实现
├── policies/      # 策略/动作决策
├── prompts/       # 提示词模板
├── providers/     # 数据提供者抽象层
├── runners/       # 运行脚本和演示
├── temp/          # 临时文件
└── utils/         # 工具函数
```

## 当前实现：数据流

```
┌────────────────────────────────────────────────────────────────┐
│  RelationSelectionEnv                                           │
│    - 接收 question                                              │
│    - 调用 provider.get_snapshot() 获取 SeedSnapshot            │
│    - 从 entity_edges 提取 relation_set                          │
│    - 构建 RelationEnvState                                      │
└─────────────────────────────────────────────────────────────────┘
                           ↓
┌────────────────────────────────────────────────────────────────┐
│  OpenAIActionPolicy                                             │
│    - 构建 prompt (question + knowledge + relation_set)         │
│    - 调用 LLM 获取响应                                          │
│    - 解析 <relation_select> 或 <answer> 标签                   │
│    - 返回 RelationEnvAction                                     │
└────────────────────────────────────────────────────────────────┘
                           ↓
┌────────────────────────────────────────────────────────────────┐
│  LightRAGGraphProvider                                          │
│    - 调用 lightrag_integration 适配器                          │
│    - 转换响应为 RelationEdge 列表                               │
│    - 返回 SeedSnapshot                                          │
└────────────────────────────────────────────────────────────────┘
```

## 模块职责边界

| 模块 | 职责 | 禁止事项 |
|-----|------|---------|
| `envs/` | 过滤逻辑、文本拼接、图剪枝 | 调用LLM、拼装SPARQL |
| `policies/` | 提示词构建、XML解析 | 拼装SPARQL、直接访问数据库 |
| `providers/` | 数据获取抽象、格式转换 | 包含业务逻辑 |
| `prompts/` | 模板常量、格式化函数 | 动态生成复杂逻辑 |
| `contracts/` | 数据类型定义 | 包含方法实现 |
| `config/` | 配置加载、环境变量 | 运行时状态管理 |

## 差距分析（与rebuild文档对比）

### 1. 选择模式差距
- **当前**：`relation_select` 选择关系名字符串
- **目标**：`edge_select` 选择完整边（包含src、relation、tgt）
- **影响模块**：`envs/`, `policies/`, `prompts/`, `contracts/`

### 2. 数据结构差距
- **当前**：`relation_set: list[str]` 只包含关系名
- **目标**：`candidate_edges: list[CandidateEdge]` 包含完整边信息
- **影响模块**：`contracts/`, `envs/`

### 3. 噪音过滤差距
- **当前**：无过滤逻辑
- **目标**：Freebase噪音关系黑名单过滤
- **影响模块**：`third_party_integration/freebase_integration/`

### 4. MID处理差距
- **当前**：无MID概念
- **目标**：Freebase MID双轨制（内部MID，外部可读名称）
- **影响模块**：`third_party_integration/freebase_integration/`

### 5. 数据源差距
- **当前**：仅LightRAG单一数据源
- **目标**：支持Freebase外部HTTP服务（localhost:8000/search, localhost:8890/sparql）
- **影响模块**：`providers/`, `config/`, `third_party_integration/`

## 开发纪律

1. **废弃即删除**：不保留旧模式的代码分支
2. **各司其职**：严格遵守模块职责边界
3. **统一日志字段**：使用明确命名如 `agent_prompt`, `agent_raw_response`, `candidate_edges_length`

## 子模块文档

- [envs/AGENTS.md](envs/AGENTS.md) - 环境层详细说明
- [policies/AGENTS.md](policies/AGENTS.md) - 策略层详细说明
- [prompts/AGENTS.md](prompts/AGENTS.md) - 提示词层详细说明
- [providers/AGENTS.md](providers/AGENTS.md) - 提供者层详细说明
- [contracts/AGENTS.md](contracts/AGENTS.md) - 合约层详细说明
- [config/AGENTS.md](config/AGENTS.md) - 配置层详细说明