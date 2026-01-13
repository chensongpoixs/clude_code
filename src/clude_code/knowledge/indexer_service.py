from __future__ import annotations

import hashlib
import threading
import time
from pathlib import Path
from typing import List, Optional

from clude_code.config import CludeConfig
from clude_code.knowledge.vector_store import VectorStore
from clude_code.knowledge.embedder import CodeEmbedder

class IndexerService:
    """
    Background service that scans the workspace and updates the vector index.
    """
    def __init__(self, cfg: CludeConfig):
        self.cfg = cfg
        self.workspace_root = Path(cfg.workspace_root)
        self.store = VectorStore(cfg)
        self.embedder = CodeEmbedder()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.status = "idle"
        self.indexed_files = 0
        self.total_files = 0

    def start(self):
        """Start the background indexing thread."""
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self):
        """Stop the background indexing thread."""
        self._stop_event.set()
        if self._thread:
            self._thread.join()

    def _run_loop(self):
        while not self._stop_event.is_set():
            try:
                self.status = "scanning"
                files_to_index = self._scan_files()
                self.total_files = len(files_to_index)
                
                if files_to_index:
                    self.status = "indexing"
                    for i, file_path in enumerate(files_to_index):
                        if self._stop_event.is_set():
                            break
                        self._index_file(file_path)
                        self.indexed_files = i + 1
                
                self.status = "idle"
                # Scan every 60 seconds for changes
                for _ in range(60):
                    if self._stop_event.is_set():
                        break
                    time.sleep(1)
            except Exception as e:
                self.status = f"error: {str(e)}"
                time.sleep(10)

    def _scan_files(self) -> List[Path]:
        """Find all source files that need indexing/re-indexing."""
        # Simple implementation: scan everything and check hashes (MVP logic)
        # In a real app, you'd use mtime or a dedicated tracker.
        valid_extensions = {".py", ".js", ".ts", ".go", ".java", ".c", ".cpp", ".rs"}
        files = []
        for p in self.workspace_root.rglob("*"):
            if p.is_file() and p.suffix in valid_extensions:
                # Exclude common dirs
                if any(part in p.parts for part in {".git", "node_modules", ".venv", "dist", "build"}):
                    continue
                files.append(p)
        return files

    def _get_file_hash(self, path: Path) -> str:
        return hashlib.md5(path.read_bytes()).hexdigest()

    def _index_file(self, path: Path):
        """Chunk a file, embed chunks, and add to VectorStore."""
        rel_path = str(path.relative_to(self.workspace_root))
        file_content = path.read_text(encoding="utf-8", errors="replace")
        file_hash = self._get_file_hash(path)
        
        # Simple line-based chunker (MVP)
        lines = file_content.splitlines()
        chunk_size = 50 # lines
        overlap = 5
        
        chunks_data = []
        for i in range(0, len(lines), chunk_size - overlap):
            chunk_lines = lines[i : i + chunk_size]
            if not chunk_lines:
                break
            
            chunk_text = "\n".join(chunk_lines)
            chunks_data.append({
                "text": chunk_text,
                "start_line": i + 1,
                "end_line": i + len(chunk_lines),
            })

        if not chunks_data:
            return

        # Generate embeddings
        texts = [c["text"] for c in chunks_data]
        vectors = self.embedder.embed_texts(texts)
        
        # Prepare for LanceDB
        final_chunks = []
        for j, v in enumerate(vectors):
            final_chunks.append({
                "vector": v,
                "text": chunks_data[j]["text"],
                "path": rel_path,
                "start_line": chunks_data[j]["start_line"],
                "end_line": chunks_data[j]["end_line"],
                "file_hash": file_hash,
            })
        
        # Update VectorStore (Delete old chunks for this file first)
        self.store.delete_by_path(rel_path)
        self.store.add_chunks(final_chunks)

