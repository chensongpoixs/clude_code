from __future__ import annotations

import json
import hashlib
import logging
import threading
import time
from pathlib import Path
from typing import Any, List, Optional, Dict

from clude_code.config import CludeConfig
from clude_code.knowledge.vector_store import VectorStore
from clude_code.knowledge.embedder import CodeEmbedder
from clude_code.knowledge.chunking import build_chunker, detect_language_from_path


class IndexerService:
    """
    后台索引服务：支持增量扫描与深度调优。
    大文件治理说明：引入 mtime 校验与语义化分块。
    """
    def __init__(self, cfg: CludeConfig):
        self.cfg = cfg
        self.workspace_root = Path(cfg.workspace_root)
        self.store = VectorStore(cfg)
        self.embedder = CodeEmbedder(cfg)
        self.chunker = build_chunker(cfg)
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._logger = logging.getLogger(__name__)
        
        self.status = "idle"
        self.indexed_files = 0
        self.total_files = 0

        # 索引状态持久化（业界标配：可恢复的增量索引）
        # 版本隔离：table_name/chunker 变化时触发重新索引（避免“state 认为已索引，但表为空/策略不同”）
        table_name = str(getattr(cfg.rag, "table_name", "") or "code_chunks")
        chunker_name = str(getattr(cfg.rag, "chunker", "") or "heuristic").lower()
        self._state_path = self.workspace_root / ".clude" / f"index_state_{table_name}_{chunker_name}.json"
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        self._state: Dict[str, Dict[str, Any]] = {}  # rel_path -> {"mtime": float, "hash": str, "skipped": bool}
        self._load_state()

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """停止后台索引线程（用于干净退出/测试）。"""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)

    def _run_loop(self):
        while not self._stop_event.is_set():
            try:
                self.status = "scanning"
                # 1. 扫描出真正变化的文件
                files_to_index = self._scan_modified_files()
                self.total_files = len(files_to_index)
                
                if files_to_index:
                    self.status = "indexing"
                    for i, file_path in enumerate(files_to_index):
                        if self._stop_event.is_set(): break
                        self._index_file(file_path)
                        self.indexed_files = i + 1
                    self._save_state()
                
                self.status = "idle"
                # 休眠间隔（可配置）
                sleep_s = int(getattr(self.cfg.rag, "scan_interval_s", 30) or 30)
                for _ in range(sleep_s):
                    if self._stop_event.is_set(): break
                    time.sleep(1)
            except Exception as e:
                self.status = f"error: {str(e)}"
                self._logger.exception("IndexerService 后台索引异常", exc_info=True)
                time.sleep(10)

    def _scan_modified_files(self) -> List[Path]:
        """增量扫描：仅返回自上次扫描以来修改过或新增加的文件。"""
        valid_exts = {".py", ".js", ".ts", ".go", ".rs", ".c", ".cpp", ".java"}
        exclude_dirs = {".git", "node_modules", ".venv", "venv", "dist", "build", ".clude"}
        
        modified = []
        current_paths: set[str] = set()

        for p in self.workspace_root.rglob("*"):
            if not p.is_file() or p.suffix not in valid_exts:
                continue
            if any(part in p.parts for part in exclude_dirs):
                continue
            
            rel_path = str(p.relative_to(self.workspace_root))
            current_paths.add(rel_path)
            
            mtime = p.stat().st_mtime
            # 如果是新文件，或者 mtime 变了（注意：这里只“发现”，不提前写入 state，避免索引失败后被错误跳过）
            st = self._state.get(rel_path)
            prev_mtime = float(st.get("mtime", 0.0)) if isinstance(st, dict) else 0.0
            if prev_mtime < mtime:
                modified.append(p)
        
        # 清理已删除的文件（可选：同步删除向量库中的记录）
        deleted_paths = set(self._state.keys()) - current_paths
        for dp in deleted_paths:
            self.store.delete_by_path(dp)
            del self._state[dp]

        # 扫描阶段仅在发生删除时持久化（删除需要落盘；mtime 更新应在索引成功后落盘）
        if deleted_paths:
            self._save_state()

        return modified

    def _index_file(self, path: Path):
        """语义化分块并写入向量库。"""
        rel_path = str(path.relative_to(self.workspace_root))
        try:
            # 护栏 1：超大文件跳过
            max_bytes = int(getattr(self.cfg.rag, "max_file_bytes", 2_000_000) or 2_000_000)
            if path.stat().st_size > max_bytes:
                self._state.setdefault(rel_path, {})["skipped"] = True
                return
            # 护栏 2：二进制文件跳过（避免把乱码写入向量库）
            if self._is_probably_binary(path):
                self._state.setdefault(rel_path, {})["skipped"] = True
                return
            content = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return

        mtime = path.stat().st_mtime
        file_hash = hashlib.md5(content.encode()).hexdigest()

        # 如果内容 hash 没变，则跳过（解决某些平台 mtime 抖动/拷贝导致的重复索引）
        prev = self._state.get(rel_path, {})
        if isinstance(prev, dict) and prev.get("hash") == file_hash:
            self._state.setdefault(rel_path, {})["skipped"] = False
            return
        
        # --- 深度调优：基于逻辑块的分块 ---
        chunks = []
        try:
            # tree-sitter 模式缺依赖/解析失败时会返回空；自动降级到启发式（业界常见“可用优先”策略）
            chunks = list(self.chunker.chunk(text=content, path=rel_path))  # type: ignore[attr-defined]
        except Exception:
            chunks = []
        if not chunks:
            chunks = self._smart_chunking(content)
        
        final_chunks = []
        if not chunks:
            return

        # 批量获取向量（更高效 + 节流）
        # 兼容两类结构：dict（历史）与 CodeChunk（新）
        texts: list[str] = []
        for c in chunks:
            if isinstance(c, dict):
                texts.append(str(c.get("text") or ""))
            else:
                texts.append(str(getattr(c, "text", "") or ""))
        vectors: list[list[float]] = []
        batch_size = int(getattr(self.cfg.rag, "embed_batch_size", 64) or 64)
        for i in range(0, len(texts), max(1, batch_size)):
            vectors.extend(self.embedder.embed_texts(texts[i : i + batch_size]))
        
        for i, vec in enumerate(vectors):
            c = chunks[i]
            if isinstance(c, dict):
                c_text = str(c.get("text") or "")
                c_start = int(c.get("start") or 1)
                c_end = int(c.get("end") or c_start)
                lang = detect_language_from_path(rel_path)
                symbol = None
                node_type = None
                scope = None
            else:
                c_text = str(getattr(c, "text", "") or "")
                c_start = int(getattr(c, "start_line", 1) or 1)
                c_end = int(getattr(c, "end_line", c_start) or c_start)
                lang = getattr(c, "language", None)
                symbol = getattr(c, "symbol", None)
                node_type = getattr(c, "node_type", None)
                scope = getattr(c, "scope", None)
            chunk_id = f"{rel_path}:{c_start}-{c_end}:{symbol or node_type or 'chunk'}"
            final_chunks.append({
                "vector": vec,
                "text": c_text,
                "path": rel_path,
                "start_line": c_start,
                "end_line": c_end,
                "file_hash": file_hash,
                "language": lang,
                "symbol": symbol,
                "node_type": node_type,
                "scope": scope,
                "chunk_id": chunk_id,
            })
        
        # 向量库依赖缺失时，索引应“降级停用”而不是持续报错占用资源
        try:
            self.store.delete_by_path(rel_path)
            self.store.add_chunks(final_chunks)
        except Exception as e:
            self.status = f"disabled: vector_store_unavailable ({e})"
            self._logger.error("VectorStore 不可用，已降级停用后台索引。", exc_info=True)
            self._stop_event.set()
            return

        # 只有在索引成功后才更新 state（避免失败后 mtime 被提前写入导致漏索引）
        st = self._state.setdefault(rel_path, {})
        st["hash"] = file_hash
        st["mtime"] = mtime
        st["skipped"] = False

    def _smart_chunking(self, text: str) -> List[Dict[str, Any]]:
        """
        启发式分块：尝试在函数/类定义处切分，而不是固定行数。
        """
        lines = text.splitlines()
        chunks = []
        current_lines = []
        start_line = 1
        
        # 配置参数
        target_lines = int(getattr(self.cfg.rag, "chunk_target_lines", 40) or 40)
        max_lines = int(getattr(self.cfg.rag, "chunk_max_lines", 60) or 60)
        overlap_lines = int(getattr(self.cfg.rag, "chunk_overlap_lines", 5) or 5)
        
        for i, line in enumerate(lines):
            current_lines.append(line)
            
            # 切分触发条件：
            # 1. 达到目标行数且遇到空行
            # 2. 达到硬性上限
            # 3. 遇到新的顶层定义（简易识别）
            is_new_def = line.startswith(("def ", "class ", "export ", "func ", "fn "))
            
            should_split = False
            if len(current_lines) >= target_lines and not line.strip():
                should_split = True
            elif len(current_lines) >= max_lines:
                should_split = True
            elif len(current_lines) > 10 and is_new_def:
                should_split = True
                
            if should_split:
                chunks.append({
                    "text": "\n".join(current_lines),
                    "start": start_line,
                    "end": i + 1
                })
                # 业界做法：保留少量 overlap，提升跨块检索一致性
                if overlap_lines > 0:
                    current_lines = current_lines[-overlap_lines:]
                    start_line = (i + 2) - len(current_lines)
                else:
                    current_lines = []
                    start_line = i + 2
        
        # 处理剩余行
        if current_lines:
            chunks.append({
                "text": "\n".join(current_lines),
                "start": start_line,
                "end": len(lines)
            })
            
        return chunks

    def _is_probably_binary(self, path: Path) -> bool:
        try:
            with path.open("rb") as f:
                head = f.read(4096)
            return b"\x00" in head
        except Exception:
            return False

    def _load_state(self) -> None:
        try:
            if self._state_path.exists():
                obj = json.loads(self._state_path.read_text(encoding="utf-8"))
                if isinstance(obj, dict):
                    self._state = obj  # type: ignore[assignment]
        except Exception:
            self._state = {}

    def _save_state(self) -> None:
        try:
            tmp = self._state_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self._state, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(self._state_path)
        except Exception:
            # 状态文件失败不应阻塞索引
            pass
