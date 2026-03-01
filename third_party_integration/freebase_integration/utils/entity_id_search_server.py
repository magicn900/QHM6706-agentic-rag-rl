# api_server.py

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import torch
import numpy as np
import faiss
import pickle
import os
from transformers import AutoTokenizer, AutoModel
import time
from sklearn.metrics.pairwise import cosine_similarity

app = FastAPI()

# 初始化设备、模型和tokenizer
device = 'cuda' if torch.cuda.is_available() else 'cpu'
model_name = "/data/maochongchong/project/LLMs/BAAI/bge-small-en-v1.5"
tokenizer = AutoTokenizer.from_pretrained(model_name)
model = AutoModel.from_pretrained(model_name).to(device)

# 优先加载 IVF 索引（更快），如果不存在则加载原始索引
ivf_index_path = "name_ids_ivf.faiss"
flat_index_path = "name_ids.faiss"

if os.path.exists(ivf_index_path):
    print(f"加载 IVF 索引: {ivf_index_path}")
    index = faiss.read_index(ivf_index_path)
    # 设置探测聚类数（nprobe 越大越准确但越慢）
    if hasattr(index, 'nprobe'):
        index.nprobe = 64  # 可根据精度需求调整：16-128
    print(f"索引类型: IVF, nprobe={getattr(index, 'nprobe', 'N/A')}")
else:
    print(f"加载 Flat 索引: {flat_index_path}")
    print("提示: 运行 python build_ivf_index.py 构建 IVF 索引可提速 100-1000 倍")
    index = faiss.read_index(flat_index_path)
    print(f"索引类型: Flat (暴力搜索)")

print(f"索引向量数量: {index.ntotal:,}")

# 加载 name_to_ids 映射
with open("name_to_ids.pkl", "rb") as f:
    name_to_ids = pickle.load(f)

# 将 name_to_ids 转换为列表
names = list(name_to_ids.keys())

class QueryRequest(BaseModel):
    query: str
    top_k: int = 5  # 默认返回 top 5 个结果

def get_embedding(text):
    inputs = tokenizer(text, return_tensors="pt", truncation=True, max_length=64).to(device)
    with torch.no_grad():
        outputs = model(**inputs)
        emb = outputs.last_hidden_state[:, 0, :]  # 使用 [CLS]
        return emb[0].cpu().numpy()

@app.post("/search")
async def search(query_request: QueryRequest):
    query = query_request.query
    top_k = query_request.top_k

    
    print(f"Query:{query}-开始处理")
    start_time = time.time()
    # 获取查询的 embedding
    q_vec = get_embedding(query).reshape(1, -1).astype('float32')
    print(f"Query:{query}-Embedding耗时: {time.time() - start_time:.2f} 秒")
    
    start_time = time.time()
    # 在 Faiss 索引中进行检索
    D, I = index.search(q_vec, k=top_k)
    print(f"Query:{query}-检索耗时: {time.time() - start_time:.2f} 秒")

    start_time = time.time()
    # 返回检索结果
    results = []
    for idx in I[0]:
        matched_name = names[idx]
        results.append({
            "name": matched_name,
            "freebase_ids": name_to_ids[matched_name]
        })
    print(f"Query:{query}-结果处理耗时: {time.time() - start_time:.2f} 秒")

    if not results:
        raise HTTPException(status_code=404, detail="No matches found")

    return {"query": query, "top_k": top_k, "results": results}

if __name__ == "__main__":
    import uvicorn
    
    # 配置 Uvicorn 运行参数
    uvicorn.run(
        app,
        host="0.0.0.0",  # 允许所有IP访问
        port=8003,       # 端口号
        workers=1,       # 工作进程数，根据你的服务器配置调整
        log_level="info" # 日志级别
    )