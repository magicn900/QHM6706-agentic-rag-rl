# Faiss 索引优化指南

## 问题背景

原始使用 `IndexFlatL2`（暴力搜索），每次查询需要计算与 **2200 万向量**的距离，耗时约 **10 秒**。

## 解决方案：IVF 索引

IVF (Inverted File Index) 将向量空间划分为多个聚类，查询时只搜索最近的几个聚类，大幅减少计算量。

### 性能预期

| 索引类型 | 检索时间 | 精度 | 内存 |
|---------|---------|------|------|
| Flat (原始) | ~10 秒 | 100% | 33 GB |
| IVF (推荐) | ~0.01-0.1 秒 | 95-99% | 33 GB |
| IVF+PQ | ~0.01 秒 | 90-95% | 3-5 GB |

## 使用步骤

### 1. 构建 IVF 索引（只需运行一次）

```bash
cd /data/liufeifan/project/QHM6706-agentic-rag-rl/third_party_integration/freebase_integration/utils

# 复制原始索引文件（如果还没有）
# cp /data/maochongchong/project/DoM/DoM-main/utils/name_ids.faiss .
# cp /data/maochongchong/project/DoM/DoM-main/utils/name_to_ids.pkl .

# 运行构建脚本（预计 30-60 分钟）
python build_ivf_index.py --input name_ids.faiss --output name_ids_ivf.faiss --nlist 8192 --nprobe 64
```

### 2. 参数说明

- `--nlist`: 聚类数量
  - 建议：`sqrt(向量数)` 或 `4 * sqrt(向量数)`
  - 对于 2200 万向量，建议 **4096-16384**
  - 默认：8192

- `--nprobe`: 查询时探测的聚类数
  - 越大越准确但越慢
  - 建议：**32-128**
  - 默认：64

- `--gpu`: 使用 GPU 加速训练（如果可用）

- `--sample-size`: 训练采样数量
  - 训练不需要全部数据，采样即可
  - 默认：100 万

### 3. 启动服务

```bash
# 服务会自动检测并加载 IVF 索引
python entity_id_search_server.py
```

### 4. 调整 nprobe（可选）

如果需要更高精度或更快速度，可以修改 `entity_id_search_server.py` 中的 `nprobe` 值：

```python
index.nprobe = 64  # 增大提高精度，减小提高速度
```

## 测试效果

构建完成后，可以用以下命令测试：

```bash
curl -X POST http://127.0.0.1:8003/search \
  -H 'Content-Type: application/json' \
  -d '{"query":"Barack Obama","top_k":5}'
```

预期响应时间：**10-100 毫秒**（而非 10 秒）

## 进一步优化

如果需要更好的性能，可以考虑：

1. **IVF+PQ 索引**：压缩向量，减少内存占用
2. **HNSW 索引**：更快的检索速度，但构建更慢
3. **GPU 加速**：使用 `faiss-gpu` 库

如需这些优化方案，请告知。