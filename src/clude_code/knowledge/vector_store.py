from __future__ import annotations

import os
from pathlib import Path
from typing import Any, List, Optional

try:
    import lancedb
    import pyarrow as pa
except ImportError:
    lancedb = None  # type: ignore
    pa = None  # type: ignore

class VectorStore:
    """
    Wrapper around LanceDB for storing and searching code embeddings.
    """
    def __init__(self, workspace_root: str):
        self.workspace_root = Path(workspace_root)
        self.db_dir = self.workspace_root / ".clude" / "index"
        self.db_dir.mkdir(parents=True, exist_ok=True)
        self.table_name = "code_chunks"
        self._db: Optional[Any] = None
        self._table: Optional[Any] = None

    def _connect(self):
        if lancedb is None:
            raise RuntimeError("lancedb is not installed. Please run `pip install lancedb`.")
        if self._db is None:
            self._db = lancedb.connect(str(self.db_dir))
        
        if self.table_name not in self._db.table_names():
            # Define schema
            schema = pa.schema([
                pa.field("vector", pa.list_(pa.float32(), 384)), # Default for bge-small
                pa.field("text", pa.string()),
                pa.field("path", pa.string()),
                pa.field("start_line", pa.int32()),
                pa.field("end_line", pa.int32()),
                pa.field("file_hash", pa.string()),
            ])
            self._table = self._db.create_table(self.table_name, schema=schema)
        else:
            self._table = self._db.open_table(self.table_name)

    def add_chunks(self, chunks: List[dict[str, Any]]):
        """
        Add a list of code chunks to the vector store.
        Each chunk should have: vector, text, path, start_line, end_line, file_hash
        """
        self._connect()
        if self._table:
            self._table.add(chunks)

    def delete_by_path(self, path: str):
        """
        Remove all chunks associated with a specific file path.
        Useful for incremental updates.
        """
        self._connect()
        if self._table:
            self._table.delete(f'path = "{path}"')

    def search(self, query_vector: List[float], limit: int = 5) -> List[dict[str, Any]]:
        """
        Search for the most similar code chunks.
        """
        self._connect()
        if self._table is None:
            return []
        
        results = self._table.search(query_vector).limit(limit).to_list()
        return results

    def clear_all(self):
        """
        Wipe the entire index.
        """
        self._connect()
        if self._db and self.table_name in self._db.table_names():
            self._db.drop_table(self.table_name)
            self._table = None
            self._db = None

