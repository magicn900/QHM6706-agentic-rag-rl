# Edge-Select 逐层接口草案（Draft v1）

> 目的：为后续“上下文有限模型”提供低歧义接口目标。
>
> 范围：仅定义接口、类型、输入输出语义、职责边界；不包含实现细节。
>
> 上位文档：
> - `docs/freebase_rebuild_guide.md`
> - `docs/edge_select_refactor_spec_v1.md`

---

## 0. 全局约束（所有层必须遵守）

1. 旧模式废弃：`relation_select` / `relation_set` 不再作为目标接口。
2. Agent 侧不可见 MID：任何 Prompt/Policy 输出不得出现 `m.xxx`。
3. Env 不调用 LLM；Policy 不拼 SPARQL；Integration 不做 Env 状态机。
4. 主流程单一：Provider/Env/Policy 不按图源复制两套逻辑。
5. Freebase 差异下沉到 Integration。

---

## 1. Contracts 层接口草案

目标文件：`agentic_rag_rl/contracts/types.py`

## 1.1 数据类型

```python
from dataclasses import dataclass, field
from typing import Any, Literal

@dataclass(slots=True)
class CandidateEdge:
    """候选边的统一语义结构。

    对 Agent 只暴露可读字段（src_name/relation/tgt_name），
    对系统保留 internal_*_ref 作为内部追踪引用（如 Freebase MID）。
    """

    edge_id: str
    src_name: str
    relation: str
    tgt_name: str
    internal_src_ref: str | None = None
    internal_tgt_ref: str | None = None
    direction: Literal["outgoing", "incoming", "unknown"] = "unknown"
    weight: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def display_text(self) -> str:
        """返回给 Agent 的可读边文本，格式: src_name -relation-> tgt_name。"""
        ...


@dataclass(slots=True)
class PathTrace:
    """环境中的单条路径轨迹。"""

    nodes: list[str]
    relations: list[str]
    score: float = 0.0

    @property
    def tail_entity(self) -> str:
        """返回路径当前末端实体名称；空路径返回空字符串。"""
        ...

    def extend(self, relation: str, next_entity: str | None, score_delta: float = 0.0) -> "PathTrace":
        """基于当前路径扩展一跳，返回新 PathTrace，不原地修改。"""
        ...

    def to_text(self) -> str:
        """将路径渲染为可读文本，便于日志与 knowledge 展示。"""
        ...


@dataclass(slots=True)
class SeedSnapshot:
    """Provider 返回的图快照。

    代表某一步可用于环境决策的候选实体边集合及原始处理信息。
    """

    question: str
    keywords: dict[str, list[str]]
    entity_edges: dict[str, list[CandidateEdge]]
    processing_info: dict[str, Any] = field(default_factory=dict)
    raw_data: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class EdgeEnvState:
    """Env 暴露给 Policy 的状态载体。"""

    question: str
    knowledge: str
    candidate_edges: list[CandidateEdge]
    active_paths: list[PathTrace]
    history: list[dict[str, str]]
    step_index: int
    done: bool = False


@dataclass(slots=True)
class EdgeSelection:
    """边选择动作负载。

    保存一组被 Agent 选中的 edge_id。
    """

    edge_ids: list[str]


@dataclass(slots=True)
class EdgeEnvAction:
    """环境动作。

    与 answer 互斥：要么继续选边探索，要么直接回答终止。
    """

    edge_select: EdgeSelection | None = None
    answer: str | None = None

    @classmethod
    def select_edges(cls, edge_ids: list[str]) -> "EdgeEnvAction":
        """构造“继续探索”动作。"""
        ...

    @classmethod
    def answer_now(cls, answer: str) -> "EdgeEnvAction":
        """构造“直接回答并终止”动作。"""
        ...


@dataclass(slots=True)
class StepResult:
    """Env 单步执行结果。"""

    state: EdgeEnvState
    reward: float
    done: bool
    info: dict[str, Any] = field(default_factory=dict)
```

## 1.2 强约束

- `CandidateEdge` 必须兼容多图源：Freebase 填 `internal_*_ref=MID`，LightRAG 可为空。
- `display_text` 只能用可读文本（`src_name -relation-> tgt_name`）。
- `EdgeEnvAction` 与 `answer` 互斥：同一动作只允许其一生效。

---

## 2. Prompts 层接口草案

目标文件：`agentic_rag_rl/prompts/templates.py`

## 2.1 常量与正则

```python
EDGE_SELECT_REGEX = r"<edge_select>(.*?)</edge_select>"
ANSWER_REGEX = r"<answer>(.*?)</answer>"
THINK_REGEX = r"<think>(.*?)</think>"

CANDIDATE_EDGES_TEMPLATE = "<candidate_edges>\n{edges}\n</candidate_edges>"
KNOWLEDGE_BLOCK_TEMPLATE = "<knowledge>\n{body}\n</knowledge>"
```

## 2.2 格式化函数

```python
from agentic_rag_rl.contracts import CandidateEdge

def format_candidate_edges(candidate_edges: list[CandidateEdge]) -> str:
    """将候选边渲染为<candidate_edges>内部列表文本。"""
    ...

def format_knowledge_body(lines: list[str]) -> str:
    """将knowledge行列表拼装为<knowledge>块。"""
    ...

def build_action_prompt(*, question: str, knowledge: str, candidate_edges: list[CandidateEdge]) -> str:
    """构造给 Agent 的完整提示词。

    输入仅包含语义化信息，不包含 MID/底层内部字段。
    """
    ...
```

## 2.3 输入输出语义

- `format_candidate_edges` 输出行级列表，每行完整边，支持 Agent 精确选择。
- `build_action_prompt` 强制声明可用动作：`<edge_select>...</edge_select>` 或 `<answer>...</answer>`。
- Prompt 不允许包含内部引用字段（MID、raw id、sparql token）。

---

## 3. Policy 层接口草案

目标文件：`agentic_rag_rl/policies/openai_action_policy.py`

## 3.1 对外方法

```python
from agentic_rag_rl.contracts import EdgeEnvAction, EdgeEnvState

class OpenAIActionPolicy:
    """LLM 动作策略。

    负责将 Env 状态转为 prompt，并将 LLM 输出解析为 EdgeEnvAction。
    """

    async def decide(self, state: EdgeEnvState) -> tuple[EdgeEnvAction, str]:
        """返回动作与原始模型输出文本。"""
        ...

    async def decide_with_trace(
        self, state: EdgeEnvState
    ) -> tuple[EdgeEnvAction, str, dict[str, str]]:
        """返回动作、模型输出和可观测 trace 字段。"""
        ...
```

## 3.2 解析规则

- 优先解析 `<edge_select>`。
- 支持多选格式：`A -r1-> B ; C -r2-> D`（或等价 edge_id 引用，最终由 Env 校验）。
- 若解析到 `<answer>`，返回 `answer_now`。
- 解析失败时只能走“可解释回退”，并在 trace 标明 `action_type=*_fallback`。

## 3.3 trace 字段最小集

```python
{
  "agent_prompt": str,
  "agent_raw_response": str,
  "agent_action_type": str,
  "agent_action_value": str,
}
```

## 3.4 禁区

- 不允许构造 SPARQL。
- 不允许访问 Freebase HTTP 客户端。

---

## 4. Env 层接口草案

目标文件：`agentic_rag_rl/envs/edge_selection_env.py`

## 4.1 对外方法

```python
from agentic_rag_rl.contracts import EdgeEnvAction, EdgeEnvState, StepResult

class EdgeSelectionEnv:
    """基于边选择的环境状态机。"""

    async def reset(self, question: str) -> EdgeEnvState:
        """初始化 episode，构建首个状态。"""
        ...

    async def step(self, action: EdgeEnvAction) -> StepResult:
        """执行单步动作并返回奖励、状态与终止标记。"""
        ...
```

## 4.2 内部最小方法（建议）

```python
def _build_state(self, *, done_override: bool | None = None) -> EdgeEnvState:
    """汇总当前内部运行态，生成可对外暴露的 EdgeEnvState。"""
    ...

def _collect_candidate_edges(self) -> list[CandidateEdge]:
    """从快照和活跃路径收集本步候选边。"""
    ...

def _format_knowledge(self) -> str:
    """将活跃路径渲染为<knowledge>可读文本。"""
    ...

async def _prune_paths(self, paths: list[PathTrace]) -> list[PathTrace]:
    """按 beam 策略剪枝路径集合，控制分支规模。"""
    ...
```

## 4.3 行为语义

- `reset`：拉取种子快照，初始化活跃路径与候选边。
- `step(edge_select)`：按选中边扩展路径，去重、去环、剪枝，更新状态。
- `step(answer)`：直接终止。
- 达到 `max_steps` 时触发 Env 终止逻辑（是否调用 provider.answer 由实现决定，但需保持层级边界）。

## 4.4 终止与奖励（接口层约束）

- `StepResult.done=True` 时，`state.done` 也必须为 `True`。
- `info` 必须包含 `termination_reason`（如 `agent_answer`、`max_steps`、`no_candidate_edges`）。

---

## 5. Provider 层接口草案

目标文件：
- `agentic_rag_rl/providers/base.py`
- `agentic_rag_rl/providers/factory.py`（新增）

## 5.1 Provider 接口

```python
from abc import ABC, abstractmethod
from agentic_rag_rl.contracts import SeedSnapshot

class GraphProvider(ABC):
    """图数据提供者抽象。

    向 Env 提供统一快照与问答入口，屏蔽底层图源差异。
    """

    @abstractmethod
    async def initialize(self) -> None:
        """初始化 provider 依赖资源（连接、客户端、缓存等）。"""
        ...

    @abstractmethod
    async def finalize(self) -> None:
        """释放 provider 资源。"""
        ...

    @abstractmethod
    async def insert_texts(self, texts: list[str]) -> None:
        """向底层图源写入文本知识（可选能力）。"""
        ...

    @abstractmethod
    async def get_snapshot(
        self,
        question: str,
        *,
        top_k: int,
        hl_keywords: list[str] | None = None,
        ll_keywords: list[str] | None = None,
    ) -> SeedSnapshot:
        """获取当前问题上下文下的图快照。"""
        ...

    @abstractmethod
    async def answer(self, question: str, *, mode: str = "hybrid") -> str:
        """直接问答接口，通常用于 Env 终止兜底。"""
        ...
```

## 5.2 Provider 工厂接口

```python
from agentic_rag_rl.config import CoreAPIConfig

async def create_graph_provider_from_env(*, working_dir: str) -> GraphProvider:
    """按环境配置构造 GraphProvider。

    根据 graph_adapter_type 路由到 lightrag/freebase 实现。
    """
    ...
```

工厂行为语义：

- `graph_adapter_type=lightrag` -> 创建 LightRAG provider。
- `graph_adapter_type=freebase` -> 创建 Freebase provider。
- 未知类型 -> 抛出可读配置错误。

---

## 6. Integration 层接口草案

目标文件：
- `third_party_integration/lightrag_integration/...`（适配）
- `third_party_integration/freebase_integration/...`（新增）

## 6.1 统一适配协议

建议新增：`agentic_rag_rl/contracts/graph_adapter.py`

```python
from typing import Protocol
from agentic_rag_rl.contracts import CandidateEdge

class GraphAdapterProtocol(Protocol):
    """Integration 层统一适配协议。"""

    async def initialize(self) -> None:
        """初始化外部服务客户端资源。"""
        ...

    async def finalize(self) -> None:
        """释放外部服务客户端资源。"""
        ...

    async def search_entities(self, query: str, top_k: int) -> list[dict]:
        """按 query 做实体召回，返回标准化实体候选。"""
        ...

    async def expand_entity_edges(
        self,
        *,
        entity_ref: str,
        question: str,
        hl_keywords: list[str] | None = None,
        ll_keywords: list[str] | None = None,
        top_k: int = 20,
    ) -> list[CandidateEdge]:
        """扩展指定实体的一跳边并返回 CandidateEdge 列表。"""
        ...

    async def answer(self, question: str, *, mode: str = "hybrid") -> str:
        """可选直接问答接口。"""
        ...
```

## 6.2 Freebase 子接口草案

目标文件（新增建议）：
- `third_party_integration/freebase_integration/clients/entity_search_client.py`
- `third_party_integration/freebase_integration/clients/sparql_client.py`
- `third_party_integration/freebase_integration/adapters/freebase_adapter.py`
- `third_party_integration/freebase_integration/utils/noise_filter.py`
- `third_party_integration/freebase_integration/utils/mid_mapper.py`

```python
class FreebaseEntitySearchClient:
    """封装 Freebase 实体向量召回接口（/search）。"""

    async def search(self, *, query: str, top_k: int) -> list[dict]:
        """返回标准化实体候选列表；失败时可降级为空列表。"""
        ...

class FreebaseSparqlClient:
    """封装 SPARQL 查询接口（/sparql）。"""

    async def query(self, sparql: str) -> dict:
        """执行 SPARQL 并返回原始 JSON 结构。"""
        ...

class FreebaseNoiseFilter:
    """Freebase 关系噪音过滤器。"""

    def is_allowed_relation(self, relation: str) -> bool:
        """判断关系是否允许进入 candidate_edges。"""
        ...

class MidMapper:
    """MID 与可读名称映射工具。"""

    def to_display_name(self, mid: str) -> str | None:
        """将 MID 转为可读名称；不存在时返回 None。"""
        ...

    def save_mapping(self, *, mid: str, name: str) -> None:
        """保存或更新 MID -> 名称映射。"""
        ...
```

强约束：

- 网络失败不得抛穿全链路，需可降级为空结果。但是必须print出错误提示，并记录日志。
- 噪音过滤必须发生在 candidate_edges 输出前。

---

## 7. Config 层接口草案

目标文件：`agentic_rag_rl/config/api_config.py`

## 7.1 配置字段草案

```python
@dataclass(slots=True)
class CoreAPIConfig:
    # existing llm/embed/action fields ...
    graph_adapter_type: str = "lightrag"  # lightrag | freebase

    freebase_entity_search_url: str = "http://localhost:8000/search"
    freebase_sparql_url: str = "http://localhost:8890/sparql"
    freebase_request_timeout: int = 30
    freebase_max_retries: int = 3
```

## 7.2 对外方法

```python
@classmethod
def from_env(cls) -> "CoreAPIConfig":
    """从环境变量加载配置并构建 CoreAPIConfig。"""
    ...

def validate(self) -> None:
    """校验配置合法性；不合法时抛出可读错误。"""
    ...
```

`validate()` 最小检查：

- `graph_adapter_type` 在允许枚举内。
- URL 非空且具备 `http/https` 前缀。
- timeout/retry 为正整数。

---

## 8. Runner 层接口草案（最小改动）

目标文件：`agentic_rag_rl/runners/` 下现有脚本

约束：

- runner 只负责装配 `provider + env + policy`，不嵌入业务逻辑。
- runner 输出日志字段应使用统一语义命名。

建议新增（可选）：

```python
async def run_episode(question: str, *, max_steps: int, beam_width: int) -> dict:
    """装配 provider/env/policy 并执行完整 episode，返回结构化运行结果。"""
    ...
```

---

## 9. 导出与兼容策略（迁移期）

目标文件：各层 `__init__.py`

- 导出新对象：`EdgeSelectionEnv`, `EdgeEnvAction`, `EdgeEnvState`, `CandidateEdge`。
- 不新增 legacy 别名；若短期保留旧名，必须加明确“即将移除”注释并限定一版内删除。

---

## 10. 文档驱动验收（接口阶段）

当以下条件满足，即判定“接口草案阶段完成”：

1. 各层接口文档中不存在 `relation_set/relation_select` 作为目标定义。
2. 所有层都给出“必须负责/禁止负责”的边界描述。
3. Provider 与 Integration 的协议边界明确，且 Freebase 职责位于 Integration。
4. 配置项覆盖多图源切换与 Freebase 基础参数。
5. 日志字段最小集在 Policy/Runner/Env 文档中可追溯。
