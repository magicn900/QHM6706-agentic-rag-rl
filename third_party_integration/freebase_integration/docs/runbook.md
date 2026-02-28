# Freebase Integration 运行手册（最小版）

## 1. 适用范围

本文档用于 `third_party_integration/freebase_integration/` 的最小可运行与排障说明。

- 图源类型：`freebase`
- 主链路模式：`edge_select`
- 目标：外部服务不可用时返回空候选，不中断 episode

## 2. 依赖服务

需要两个 HTTP 服务：

1. 实体搜索服务
   - 方法：`POST`
   - 地址：`http://localhost:8000/search`
   - 请求体：
     ```json
     {"query": "Barack Obama", "top_k": 5}
     ```
   - 响应体（示例）：
     ```json
     {
       "results": [
         {"name": "Barack Obama", "freebase_ids": ["m.02mjmr"]}
       ]
     }
     ```

2. SPARQL 服务
   - 方法：`GET`
   - 地址：`http://localhost:8890/sparql`
   - 参数：
     - `query`：URL 编码 SPARQL 字符串
     - `format`：`application/sparql-results+json`

## 3. 环境变量配置

建议在 `<repo-root>/.env` 或 `<repo-root>/agentic_rag_rl/.env` 中配置：

```env
# 图源切换
GRAPH_ADAPTER_TYPE=freebase

# Freebase 服务
FREEBASE_ENTITY_API_URL=http://localhost:8000
FREEBASE_SPARQL_API_URL=http://localhost:8890
FREEBASE_ENTITY_API_KEY=
FREEBASE_SPARQL_API_KEY=
```

说明：
- `FREEBASE_ENTITY_API_URL` 与 `FREEBASE_SPARQL_API_URL` 配置的是基础地址；客户端会自动拼接 `/search` 和 `/sparql`。
- 若不设置，默认值分别为 `http://localhost:8000` 和 `http://localhost:8890`。

## 4. 验证命令

在仓库根目录执行：

```bash
python -m third_party_integration.freebase_integration.scripts.test_freebase_integration
python -m agentic_rag_rl.runners.edge_env_demo
```

期望现象：
- 服务可用时，能看到实体召回与候选边扩展日志。
- 服务不可用时，不抛出未处理异常，候选边可能为 0，但流程仍可结束。

## 5. 回退与故障行为

当前实现中的回退策略：

1. `EntitySearchClient.search()`：请求失败重试后返回空列表。
2. `SPARQLClient.query()`：请求失败重试后返回空 `bindings`。
3. `FreebaseAdapter.search_entities()/expand_edges()`：内部异常捕获后返回空结果。
4. `EdgeSelectionEnv`：若候选边为空，可通过 `answer` 动作或达到步数上限终止。

## 6. 常见问题

1. 候选边始终为 0
   - 检查 `/search` 是否返回 `freebase_ids`。
   - 检查 `/sparql` 是否可访问。

2. 能召回实体但无法扩展
   - 检查 SPARQL 服务是否支持输入 MID 查询。
   - 检查关系是否被噪音过滤器过滤（当前默认过滤规则为空，通常不会过滤）。

3. 模型调用错误
   - `edge_env_demo` 为 smoke 脚本，不依赖在线 LLM；如运行其他 runner 需要额外配置 Action 模型密钥。
