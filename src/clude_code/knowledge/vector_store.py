from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, List, Optional

try:
    import lancedb
    import pyarrow as pa
except ImportError:
    lancedb = None  # type: ignore
    pa = None  # type: ignore

from clude_code.config import CludeConfig

# P1-1: 模块级 logger，用于调试 RAG 向量存储问题
_logger = logging.getLogger(__name__)


class VectorStore:
    """
    围绕 LanceDB 和 fastembed 的包装器，用于存储和搜索代码嵌入向量。
    大文件治理说明：支持从 CludeConfig 动态配置计算设备和模型路径。
    """
    def __init__(self, cfg: CludeConfig):
        self.cfg = cfg
        self.workspace_root = Path(cfg.workspace_root)
        # 使用配置中的 db_path
        self.db_dir = Path(cfg.rag.db_path) if os.path.isabs(cfg.rag.db_path) else self.workspace_root / cfg.rag.db_path
        self.db_dir.parent.mkdir(parents=True, exist_ok=True)
        
        self.table_name = str(getattr(cfg.rag, "table_name", "") or "code_chunks")
        self._db: Optional[Any] = None
        self._table: Optional[Any] = None

    def _connect(self):
        if lancedb is None or pa is None:
            raise RuntimeError("lancedb/pyarrow is not installed. Please run `pip install lancedb pyarrow`.")
        
        if self._db is None:
            self._db = lancedb.connect(str(self.db_dir))
        
        if self.table_name not in self._db.table_names():
            # 业界做法：向量维度可能随 embedding_model 变化，避免固定尺寸以提升兼容性。
            schema = pa.schema([
                pa.field("vector", pa.list_(pa.float32())),
                pa.field("text", pa.string()),
                pa.field("path", pa.string()),
                pa.field("start_line", pa.int32()),
                pa.field("end_line", pa.int32()),
                pa.field("file_hash", pa.string()),
                # AST-aware 元数据（可选）：用于更可解释的召回与后续 rerank
                pa.field("language", pa.string()),
                pa.field("symbol", pa.string()),
                pa.field("node_type", pa.string()),
                pa.field("scope", pa.string()),
                pa.field("chunk_id", pa.string()),
            ])
            self._table = self._db.create_table(self.table_name, schema=schema)
        else:
            self._table = self._db.open_table(self.table_name)

    def add_chunks(self, chunks: List[dict[str, Any]]):
        """添加分块到向量数据库。"""
        self._connect()
        if self._table:
            self._table.add(chunks)

    def search(self, query_vector: List[float], limit: int = 5) -> List[dict[str, Any]]:
        """根据向量进行语义搜索。"""
        self._connect()
        if self._table is None:
            return []

        results = self._table.search(query_vector).limit(limit).to_list()
        # LanceDB 通常会附带 `_distance`；这里统一补一个可用的 `score`（越大越相似）
        out: list[dict[str, Any]] = []
        for r in results or []:
            if not isinstance(r, dict):
                continue
            dist = r.get("_distance")
            try:
                d = float(dist) if dist is not None else None
            except Exception as e:
                # P1-1: distance 类型转换失败，DEBUG 级别（不影响结果召回）
                _logger.debug(f"_distance 转换失败: {e} [value={dist}]")
                d = None
            if d is not None:
                r["score"] = 1.0 / (1.0 + max(0.0, d))
            out.append(r)
        return out

    def delete_by_path(self, path: str):
        """删除特定路径的所有分块。"""
        self._connect()
        if self._table:
            self._table.delete(f'path = "{path}"')

    def clear_all(self):
        """清空索引。"""
        self._connect()
        if self._db and self.table_name in self._db.table_names():
            self._db.drop_table(self.table_name)
            self._table = None
            self._db = None
