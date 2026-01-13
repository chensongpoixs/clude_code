from __future__ import annotations

import os
from pathlib import Path
from typing import Any, List, Optional

try:
    import lancedb
    import pyarrow as pa
    from fastembed import TextEmbedding
except ImportError:
    lancedb = None  # type: ignore
    pa = None  # type: ignore
    TextEmbedding = None  # type: ignore

from clude_code.config import CludeConfig


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
        
        self.table_name = "code_chunks"
        self._db: Optional[Any] = None
        self._table: Optional[Any] = None
        self._model: Optional[Any] = None

    def _get_model(self):
        """延迟初始化 Embedding 模型。"""
        if TextEmbedding is None:
            raise RuntimeError("fastembed is not installed. Please run `pip install fastembed`.")
        
        if self._model is None:
            # 从配置中读取模型名称、设备和缓存路径
            self._model = TextEmbedding(
                model_name=self.cfg.rag.embedding_model,
                cache_dir=self.cfg.rag.model_cache_dir,
                providers=[self._get_onnx_provider()] # 适配设备驱动
            )
        return self._model

    def _get_onnx_provider(self) -> str:
        """根据配置映射 ONNX Runtime 提供者。"""
        d = self.cfg.rag.device.lower()
        if d == "cuda": return "CUDAExecutionProvider"
        if d == "mps": return "CoreMLExecutionProvider"
        return "CPUExecutionProvider"

    def _connect(self):
        if lancedb is None or pa is None:
            raise RuntimeError("lancedb/pyarrow is not installed. Please run `pip install lancedb pyarrow`.")
        
        if self._db is None:
            self._db = lancedb.connect(str(self.db_dir))
        
        if self.table_name not in self._db.table_names():
            # 获取模型维度（通常 bge-small 是 384）
            dim = 384 # 默认
            schema = pa.schema([
                pa.field("vector", pa.list_(pa.float32(), dim)),
                pa.field("text", pa.string()),
                pa.field("path", pa.string()),
                pa.field("start_line", pa.int32()),
                pa.field("end_line", pa.int32()),
                pa.field("file_hash", pa.string()),
            ])
            self._table = self._db.create_table(self.table_name, schema=schema)
        else:
            self._table = self._db.open_table(self.table_name)

    def embed_text(self, text_list: List[str]) -> List[List[float]]:
        """生成文本向量。"""
        model = self._get_model()
        # model.embed 返回迭代器
        return [list(v) for v in model.embed(text_list)]

    def add_chunks(self, chunks: List[dict[str, Any]]):
        """添加分块到向量数据库。"""
        self._connect()
        if self._table:
            self._table.add(chunks)

    def search(self, query_text: str, limit: int = 5) -> List[dict[str, Any]]:
        """根据文本进行语义搜索。"""
        self._connect()
        if self._table is None:
            return []
        
        # 1. 编码查询
        query_vector = self.embed_text([query_text])[0]
        
        # 2. 向量搜索
        results = self._table.search(query_vector).limit(limit).to_list()
        return results

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
