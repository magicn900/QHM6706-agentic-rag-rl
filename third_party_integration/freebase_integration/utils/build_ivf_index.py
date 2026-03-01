#!/usr/bin/env python3
"""
将 Faiss Flat 索引转换为 IVF 索引以加速检索

IVF (Inverted File Index) 原理：
1. 将向量空间划分为 nlist 个聚类中心
2. 每个向量归属于最近的聚类
3. 查询时只搜索最近的 nprobe 个聚类，而不是全部向量

性能预期：
- Flat 索引：搜索全部 2200 万向量，耗时 10 秒
- IVF 索引：搜索约 1% 的向量，耗时 0.01-0.1 秒
"""

import faiss
import numpy as np
import time
import os
import psutil

def get_memory_usage():
    """获取当前内存使用情况"""
    process = psutil.Process(os.getpid())
    mem = process.memory_info().rss / 1024 / 1024 / 1024  # GB
    return f"{mem:.2f} GB"

def build_ivf_index(
    flat_index_path: str,
    ivf_index_path: str,
    nlist: int = 8192,
    nprobe: int = 64,
    use_gpu: bool = False,
    sample_size: int = 1000000
):
    """
    将 Flat 索引转换为 IVF 索引
    
    参数：
    - flat_index_path: 原 Flat 索引路径
    - ivf_index_path: 新 IVF 索引保存路径
    - nlist: 聚类数量，建议 sqrt(n) 或 4*sqrt(n)
            对于 2200 万向量，建议 4096-16384
    - nprobe: 查询时探测的聚类数量，越大越准确但越慢
             建议 32-128，默认 64
    - use_gpu: 是否使用 GPU 加速训练
    - sample_size: 训练时的采样数量，训练不需要全部数据
    """
    
    print("=" * 60)
    print("Faiss IVF 索引构建工具")
    print("=" * 60)
    
    # 1. 加载原始 Flat 索引
    print(f"\n[1/5] 加载原始索引: {flat_index_path}")
    print(f"      当前内存: {get_memory_usage()}")
    start = time.time()
    
    flat_index = faiss.read_index(flat_index_path)
    n_vectors = flat_index.ntotal
    d = flat_index.d
    
    print(f"      ✓ 加载完成，耗时: {time.time()-start:.2f} 秒")
    print(f"      向量数量: {n_vectors:,}")
    print(f"      向量维度: {d}")
    print(f"      当前内存: {get_memory_usage()}")
    
    # 2. 准备训练数据（采样）
    print(f"\n[2/5] 准备训练数据（采样 {sample_size:,} 个向量）")
    print(f"      当前内存: {get_memory_usage()}")
    start = time.time()
    
    # 随机采样向量用于训练
    sample_size = min(sample_size, n_vectors)
    sample_indices = np.random.choice(n_vectors, sample_size, replace=False)
    sample_indices = np.sort(sample_indices)  # 排序以提高读取效率
    
    # 提取采样向量
    sample_vectors = np.zeros((sample_size, d), dtype='float32')
    for i, idx in enumerate(sample_indices):
        sample_vectors[i] = flat_index.reconstruct(int(idx))
    
    print(f"      ✓ 采样完成，耗时: {time.time()-start:.2f} 秒")
    print(f"      当前内存: {get_memory_usage()}")
    
    # 3. 创建并训练 IVF 索引
    print(f"\n[3/5] 训练 IVF 索引 (nlist={nlist})")
    print(f"      这可能需要几分钟...")
    print(f"      当前内存: {get_memory_usage()}")
    start = time.time()
    
    # 创建量化器（用于聚类）
    quantizer = faiss.IndexFlatL2(d)
    
    # 创建 IVF 索引
    ivf_index = faiss.IndexIVFFlat(quantizer, d, nlist, faiss.METRIC_L2)
    
    # 如果使用 GPU
    if use_gpu and faiss.get_num_gpus() > 0:
        print(f"      使用 GPU 加速训练")
        res = faiss.StandardGpuResources()
        ivf_index = faiss.index_cpu_to_gpu(res, 0, ivf_index)
    
    # 训练聚类中心
    ivf_index.train(sample_vectors)
    
    print(f"      ✓ 训练完成，耗时: {time.time()-start:.2f} 秒")
    print(f"      聚类中心数量: {ivf_index.nlist}")
    print(f"      当前内存: {get_memory_usage()}")
    
    # 如果使用了 GPU，转回 CPU
    if use_gpu and faiss.get_num_gpus() > 0:
        ivf_index = faiss.index_gpu_to_cpu(ivf_index)
    
    # 4. 批量添加向量到 IVF 索引
    print(f"\n[4/5] 添加 {n_vectors:,} 个向量到 IVF 索引")
    print(f"      这可能需要较长时间...")
    print(f"      当前内存: {get_memory_usage()}")
    start = time.time()
    
    batch_size = 100000
    for i in range(0, n_vectors, batch_size):
        end_idx = min(i + batch_size, n_vectors)
        
        # 提取一批向量
        batch_vectors = np.zeros((end_idx - i, d), dtype='float32')
        for j in range(i, end_idx):
            batch_vectors[j - i] = flat_index.reconstruct(j)
        
        # 添加到索引
        ivf_index.add(batch_vectors)
        
        # 进度显示
        progress = (end_idx / n_vectors) * 100
        elapsed = time.time() - start
        eta = elapsed / (end_idx / n_vectors) * (n_vectors - end_idx)
        print(f"      进度: {progress:.1f}% ({end_idx:,}/{n_vectors:,}) | "
              f"耗时: {elapsed:.1f}s | 预计剩余: {eta:.1f}s", end='\r')
    
    print(f"\n      ✓ 添加完成，总耗时: {time.time()-start:.2f} 秒")
    print(f"      当前内存: {get_memory_usage()}")
    
    # 5. 设置 nprobe 并保存
    print(f"\n[5/5] 保存 IVF 索引")
    ivf_index.nprobe = nprobe
    print(f"      nprobe 设置为: {nprobe}")
    
    faiss.write_index(ivf_index, ivf_index_path)
    print(f"      ✓ 已保存到: {ivf_index_path}")
    
    # 显示文件大小
    flat_size = os.path.getsize(flat_index_path) / 1024 / 1024 / 1024
    ivf_size = os.path.getsize(ivf_index_path) / 1024 / 1024 / 1024
    print(f"      原始索引大小: {flat_size:.2f} GB")
    print(f"      IVF 索引大小: {ivf_size:.2f} GB")
    
    print("\n" + "=" * 60)
    print("✓ IVF 索引构建完成！")
    print("=" * 60)
    
    return ivf_index


def test_ivf_index(ivf_index_path: str, test_queries: list, d: int = 384):
    """测试 IVF 索引的检索性能"""
    
    print("\n" + "=" * 60)
    print("测试 IVF 索引性能")
    print("=" * 60)
    
    # 加载索引
    index = faiss.read_index(ivf_index_path)
    print(f"索引向量数量: {index.ntotal:,}")
    print(f"聚类数量 (nlist): {index.nlist}")
    print(f"探测聚类数 (nprobe): {index.nprobe}")
    
    # 测试不同 nprobe 的性能
    for nprobe in [16, 32, 64, 128]:
        index.nprobe = nprobe
        
        times = []
        for query_vec in test_queries:
            q = query_vec.reshape(1, -1).astype('float32')
            
            start = time.time()
            D, I = index.search(q, k=5)
            times.append(time.time() - start)
        
        avg_time = np.mean(times) * 1000  # 毫秒
        print(f"nprobe={nprobe:3d}: 平均耗时 {avg_time:.2f} ms")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="构建 Faiss IVF 索引")
    parser.add_argument("--input", type=str, default="name_ids.faiss",
                        help="输入的 Flat 索引路径")
    parser.add_argument("--output", type=str, default="name_ids_ivf.faiss",
                        help="输出的 IVF 索引路径")
    parser.add_argument("--nlist", type=int, default=8192,
                        help="聚类数量 (默认: 8192)")
    parser.add_argument("--nprobe", type=int, default=64,
                        help="查询时探测的聚类数 (默认: 64)")
    parser.add_argument("--gpu", action="store_true",
                        help="使用 GPU 加速训练")
    parser.add_argument("--sample-size", type=int, default=1000000,
                        help="训练采样数量 (默认: 100万)")
    
    args = parser.parse_args()
    
    # 构建 IVF 索引
    build_ivf_index(
        flat_index_path=args.input,
        ivf_index_path=args.output,
        nlist=args.nlist,
        nprobe=args.nprobe,
        use_gpu=args.gpu,
        sample_size=args.sample_size
    )