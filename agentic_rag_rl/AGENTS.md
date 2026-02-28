# AGENTS.md - agentic_rag_rl 核心包

本目录承载 Edge-Select 主链路的核心实现，当前架构已经完成 relation 模式迁移。

## 目录结构

```
agentic_rag_rl/
├── config/        # API配置和环境变量
├── contracts/     # 数据类型定义（Edge-Select 合约）
├── envs/          # RL环境实现（EdgeSelectionEnv）
├── policies/      # 策略/动作决策（OpenAIActionPolicy）
├── prompts/       # 提示词模板（candidate_edges）
├── providers/     # 图数据提供者抽象层与工厂
├── runners/       # 运行脚本和演示
├── temp/          # 临时文件
└── utils/         # 工具函数
```

## 当前实现：Edge-Select 数据流

```
┌────────────────────────────────────────────────────────────────┐
│  EdgeSelectionEnv                                               │
│    - reset/step 维护 active_paths 与 candidate_edges            │
│    - 处理 edge_select（支持分号多选）                           │
│    - 输出标准 termination_reason                                │
└─────────────────────────────────────────────────────────────────┘
                           ↓
┌────────────────────────────────────────────────────────────────┐
│  OpenAIActionPolicy                                             │
│    - 构建 prompt(question + knowledge + candidate_edges)       │
│    - 解析 <edge_select> 或 <answer> 标签                        │
│    - 返回 EdgeEnvAction                                         │
└────────────────────────────────────────────────────────────────┘
                           ↓
┌────────────────────────────────────────────────────────────────┐
│  GraphProvider (LightRAG / Freebase)                           │
│    - get_snapshot() 输出 SeedSnapshot + CandidateEdge           │
│    - ProviderFactory 按 graph_adapter_type 选择图源             │
└────────────────────────────────────────────────────────────────┘
```

## 模块职责边界

| 模块 | 职责 | 禁止事项 |
|-----|------|---------|
| `envs/` | 状态管理、路径扩展、剪枝、终止信息 | 调用LLM、拼装SPARQL |
| `policies/` | 提示词构建、响应解析、回退动作 | 拼装SPARQL、直接访问图服务 |
| `providers/` | 图源抽象、快照组装、工厂接线 | 混入Env/Policy业务逻辑 |
| `prompts/` | 模板常量、候选边文本格式化 | 执行候选边校验/图查询 |
| `contracts/` | 类型合约与数据载体 | 写入外部服务调用逻辑 |
| `config/` | 环境变量加载与校验 | 管理运行时会话状态 |

## 运行与验收入口

- Env 集成验证：`python -m agentic_rag_rl.runners.test_edge_selection_env`
- Mock 策略演示：`python -m agentic_rag_rl.runners.mock_edge_select_test`
- Phase G 烟测：`python -m agentic_rag_rl.runners.edge_env_demo`

## 子模块文档

- [envs/AGENTS.md](envs/AGENTS.md)
- [policies/AGENTS.md](policies/AGENTS.md)
- [prompts/AGENTS.md](prompts/AGENTS.md)
- [providers/AGENTS.md](providers/AGENTS.md)
- [contracts/AGENTS.md](contracts/AGENTS.md)
- [config/AGENTS.md](config/AGENTS.md)