"""Freebase MID 映射器

维护 Freebase 实体 MID 与可读名称之间的映射关系。
MID 仅在内部使用，不暴露给 Agent。
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class MidMapper:
    """Freebase MID 映射器
    
    维护 MID -> display_name 的映射，用于：
    1. 内部处理时使用 MID
    2. 对外（Agent）展示时使用可读名称
    """

    def __init__(self, storage_path: Path | None = None):
        """初始化 MID 映射器
        
        Args:
            storage_path: 持久化存储路径（可选）
        """
        self._mid_to_name: dict[str, str] = {}
        self._name_to_mids: dict[str, list[str]] = {}  # 一个名称可能对应多个 MID
        self._storage_path = storage_path

        if storage_path and storage_path.exists():
            self._load()

    def add_mapping(self, mid: str, name: str) -> None:
        """添加 MID 到名称的映射
        
        Args:
            mid: Freebase MID
            name: 可读名称
        """
        if not mid or not name:
            return

        mid = mid.strip()
        name = name.strip()

        self._mid_to_name[mid] = name

        if name not in self._name_to_mids:
            self._name_to_mids[name] = []
        if mid not in self._name_to_mids[name]:
            self._name_to_mids[name].append(mid)

        logger.debug(f"Added mapping: {mid} -> {name}")

    def get_name(self, mid: str) -> str | None:
        """获取 MID 对应的可读名称
        
        Args:
            mid: Freebase MID
            
        Returns:
            可读名称，如果不存在则返回 None
        """
        return self._mid_to_name.get(mid)

    def get_mids(self, name: str) -> list[str]:
        """获取名称对应的所有 MID
        
        Args:
            name: 可读名称
            
        Returns:
            MID 列表
        """
        return self._name_to_mids.get(name, [])

    def has_mid(self, mid: str) -> bool:
        """检查 MID 是否已映射
        
        Args:
            mid: Freebase MID
            
        Returns:
            True 表示已存在
        """
        return mid in self._mid_to_name

    def has_name(self, name: str) -> bool:
        """检查名称是否已映射
        
        Args:
            name: 可读名称
            
        Returns:
            True 表示已存在
        """
        return name in self._name_to_mids

    def remove_mapping(self, mid: str) -> None:
        """移除指定 MID 的映射
        
        Args:
            mid: Freebase MID
        """
        name = self._mid_to_name.pop(mid, None)
        if name and name in self._name_to_mids:
            mids = self._name_to_mids[name]
            mids.remove(mid)
            if not mids:
                del self._name_to_mids[name]

    def clear(self) -> None:
        """清空所有映射"""
        self._mid_to_name.clear()
        self._name_to_mids.clear()

    def size(self) -> int:
        """获取映射数量
        
        Returns:
            MID 映射数量
        """
        return len(self._mid_to_name)

    def save(self, path: Path | None = None) -> None:
        """保存映射到文件
        
        Args:
            path: 存储路径，默认使用初始化时的路径
        """
        target_path = path or self._storage_path
        if not target_path:
            logger.warning("No storage path specified, skipping save")
            return

        data = {
            "mid_to_name": self._mid_to_name,
            "name_to_mids": self._name_to_mids,
        }

        target_path.parent.mkdir(parents=True, exist_ok=True)
        with open(target_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        logger.info(f"MID mappings saved to {target_path}")

    def _load(self) -> None:
        """从文件加载映射"""
        if not self._storage_path or not self._storage_path.exists():
            return

        try:
            with open(self._storage_path, encoding="utf-8") as f:
                data = json.load(f)

            self._mid_to_name = data.get("mid_to_name", {})
            self._name_to_mids = data.get("name_to_mids", {})
            logger.info(
                f"Loaded {len(self._mid_to_name)} MID mappings from {self._storage_path}"
            )
        except Exception as e:
            logger.error(f"Failed to load MID mappings: {e}")

    def get_all_mids(self) -> list[str]:
        """获取所有已映射的 MID
        
        Returns:
            MID 列表
        """
        return list(self._mid_to_name.keys())

    def get_all_names(self) -> list[str]:
        """获取所有已映射的名称
        
        Returns:
            名称列表
        """
        return list(self._name_to_mids.keys())

    def batch_add(
        self,
        mappings: list[dict[str, str]],
    ) -> None:
        """批量添加映射
        
        Args:
            mappings: 映射列表，每项包含 mid 和 name 字段
        """
        for item in mappings:
            mid = item.get("mid")
            name = item.get("name")
            if mid and name:
                self.add_mapping(mid, name)


# ========== 便捷函数 ==========

def create_mapper(storage_path: Path | None = None) -> MidMapper:
    """创建 MID 映射器
    
    Args:
        storage_path: 持久化路径
        
    Returns:
        MidMapper 实例
    """
    return MidMapper(storage_path=storage_path)


# ========== 单元测试 ==========

if __name__ == "__main__":
    # 简单自测
    mapper = MidMapper()
    
    print("=== MidMapper Test ===")
    
    # 测试添加映射
    mapper.add_mapping("m.06n7_", "Barack Obama")
    mapper.add_mapping("m.0d5w2", "Obama")
    mapper.add_mapping("m.0cnt", "United States")
    
    print(f"Size: {mapper.size()}")
    print(f"Get name for m.06n7_: {mapper.get_name('m.06n7_')}")
    print(f"Get mids for Obama: {mapper.get_mids('Obama')}")
    print(f"All mids: {mapper.get_all_mids()}")
    print(f"All names: {mapper.get_all_names()}")
    
    # 测试批量添加
    mapper.batch_add([
        {"mid": "m.07s0", "name": "France"},
    ])
    print(f"Size after batch: {mapper.size()}")