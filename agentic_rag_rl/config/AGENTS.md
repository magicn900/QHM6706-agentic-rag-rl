# AGENTS.md - 配置层 (config/)

本目录包含API配置和环境变量管理。

## 当前实现

### 文件：`api_config.py`

**类**：`CoreAPIConfig`

**配置项**：
```python
@dataclass(slots=True)
class CoreAPIConfig:
    llm_model: str = "gpt-4o-mini"
    llm_base_url: str | None = None
    llm_api_key: str | None = None
    embed_model: str = "text-embedding-3-small"
    embed_dim: int = 1536
    embed_base_url: str | None = None
    embed_api_key: str | None = None
    action_model: str = "gpt-4o-mini"
    action_base_url: str | None = None
    action_api_key: str | None = None
    env_source: str = ""
```

**支持的环境变量**：

| 环境变量 | 用途 | 优先级 |
|---------|------|-------|
| `LIGHTRAG_BASE_URL` | 统一API基础URL | 低 |
| `LIGHTRAG_API_KEY` | 统一API密钥 | 低 |
| `LIGHTRAG_LLM_BASE_URL` | LLM服务URL | 中 |
| `LIGHTRAG_LLM_API_KEY` | LLM API密钥 | 中 |
| `LIGHTRAG_EMBED_BASE_URL` | Embedding服务URL | 中 |
| `LIGHTRAG_EMBED_API_KEY` | Embedding API密钥 | 中 |
| `ACTION_LLM_BASE_URL` | Agent动作模型URL | 中 |
| `ACTION_LLM_API_KEY` | Agent动作模型密钥 | 中 |
| `AGENTIC_RAG_*` | 项目专属配置 | 高 |

**配置加载逻辑**：
```python
@classmethod
def from_env(cls) -> "CoreAPIConfig":
    env_source = _load_project_envs()  # 自动加载.env文件
    
    # 级联优先级
    llm_base_url = (
        os.getenv("AGENTIC_RAG_LLM_BASE_URL")      # 最高优先级
        or os.getenv("LIGHTRAG_LLM_BASE_URL")
        or os.getenv("LIGHTRAG_BASE_URL")          # 最低优先级
    )
    ...
```

**.env文件加载**：
```python
def _load_project_envs() -> str:
    repo_root = Path(__file__).resolve().parents[2]
    candidates = [
        repo_root / "agentic_rag_rl" / ".env",
        repo_root / ".env",
    ]
    # 自动加载第一个存在的.env文件
```

## 差距分析（与rebuild文档对比）

### 1. 数据源配置差距
| 当前实现 | 目标架构 | 说明 |
|---------|---------|------|
| 仅LightRAG配置 | 支持多数据源切换 | 需新增配置项 |
| 无Freebase配置 | Freebase服务URL | 需新增环境变量 |

**缺失的配置项**：
```python
# 目标配置
graph_adapter_type: str = "lightrag"  # 或 "freebase"
freebase_entity_search_url: str = "http://localhost:8000/search"
freebase_sparql_url: str = "http://localhost:8890/sparql"
freebase_request_timeout: int = 30
freebase_max_retries: int = 3
```

### 2. 环境变量差距
**当前支持**：LLM、Embedding、Action模型配置

**缺失的环境变量**：
| 环境变量 | 用途 | 默认值 |
|---------|------|-------|
| `GRAPH_ADAPTER_TYPE` | 数据源类型 | `lightrag` |
| `FREEBASE_ENTITY_SEARCH_URL` | 实体向量服务 | `http://localhost:8000/search` |
| `FREEBASE_SPARQL_URL` | SPARQL服务 | `http://localhost:8890/sparql` |
| `FREEBASE_REQUEST_TIMEOUT` | 请求超时(秒) | `30` |
| `FREEBASE_MAX_RETRIES` | 最大重试次数 | `3` |

### 3. 配置验证差距
**当前**：无配置验证逻辑

**目标**：
- 验证数据源类型是否有效（`lightrag` | `freebase`）
- 验证URL格式是否正确
- 验证超时和重试参数范围

### 4. 配置文档差距
**当前**：无独立的配置文档

**目标**：需要在 `__init__.py` 或单独文档中列出所有支持的环境变量

## 依赖关系

```
config/
  └── 无外部依赖
```

## 待重构清单

1. **新增配置项**：
   - `graph_adapter_type` - 数据源类型
   - `freebase_entity_search_url` - Freebase实体搜索URL
   - `freebase_sparql_url` - Freebase SPARQL URL
   - `freebase_request_timeout` - 请求超时
   - `freebase_max_retries` - 重试次数

2. **新增环境变量解析**：
   - `GRAPH_ADAPTER_TYPE`
   - `FREEBASE_ENTITY_SEARCH_URL`
   - `FREEBASE_SPARQL_URL`
   - `FREEBASE_REQUEST_TIMEOUT`
   - `FREEBASE_MAX_RETRIES`

3. **配置验证**：
   - 添加 `validate()` 方法验证配置有效性

4. **配置类重构**：
   - 考虑拆分为 `LLMConfig`、`GraphAdapterConfig` 等子配置
   - 或保持单一配置类但添加分组

5. **配置文档**：
   - 在 `__init__.py` 中添加完整的配置说明

## 环境变量示例

```bash
# .env 示例

# === LLM配置 ===
LIGHTRAG_BASE_URL=https://api.openai.com/v1
LIGHTRAG_API_KEY=sk-xxx
LIGHTRAG_LLM_MODEL=gpt-4o-mini
LIGHTRAG_EMBED_MODEL=text-embedding-3-small

# === Agent动作模型配置 ===
ACTION_LLM_BASE_URL=https://api.openai.com/v1
ACTION_LLM_API_KEY=sk-xxx
ACTION_LLM_MODEL=gpt-4o-mini

# === 数据源配置（目标架构）===
GRAPH_ADAPTER_TYPE=lightrag  # 或 freebase
FREEBASE_ENTITY_SEARCH_URL=http://localhost:8000/search
FREEBASE_SPARQL_URL=http://localhost:8890/sparql
FREEBASE_REQUEST_TIMEOUT=30
FREEBASE_MAX_RETRIES=3
```

## 相关文档

- [../AGENTS.md](../AGENTS.md) - 核心包总览
- [../providers/AGENTS.md](../providers/AGENTS.md) - 提供者层（使用配置）
- [../../third_party_integration/AGENTS.md](../../third_party_integration/AGENTS.md) - 集成层
- [../../docs/freebase_rebuild_guide.md](../../docs/freebase_rebuild_guide.md) - 重构指南