from __future__ import annotations

import hashlib
import json
import re
import subprocess
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from difflib import SequenceMatcher


import platform # 修正：导入平台信息用于 generate_repo_map 中的系统判断


class ToolError(RuntimeError):
    """工具执行中的基础异常类"""
    pass


def _resolve_in_workspace(workspace_root: Path, user_path: str) -> Path:
    """
    安全地将用户提供的路径解析为工作区内的绝对路径。
    防止目录遍历攻击（Path Traversal）。
    """
    root = workspace_root.resolve()
    p = (root / user_path).resolve()
    try:
        p.relative_to(root)
    except ValueError as e:
        raise ToolError(f"路径超出了工作区范围: {user_path}") from e
    return p


@dataclass(frozen=True)
class ToolResult:
    """
    标准化的工具执行结果。
    ok: 是否成功
    payload: 成功时的载荷数据
    error: 失败时的错误信息（包含 code 和 message）
    """
    ok: bool
    payload: dict[str, Any] | None = None
    error: dict[str, Any] | None = None


class LocalTools:
    """本地工程工具箱：提供文件读写、搜索、补丁应用及命令执行等核心功能。"""
    def __init__(self, workspace_root: str, *, max_file_read_bytes: int, max_output_bytes: int) -> None:
        self.workspace_root = Path(workspace_root)
        self.max_file_read_bytes = max_file_read_bytes # 最大文件读取字节限制，防止 OOM
        self.max_output_bytes = max_output_bytes # 命令输出截断限制

    def list_dir(self, path: str = ".") -> ToolResult:
        """列出目录下的文件和子目录。"""
        p = _resolve_in_workspace(self.workspace_root, path)
        if not p.exists() or not p.is_dir():
            return ToolResult(False, error={"code": "E_NOT_DIR", "message": f"不是一个有效的目录: {path}"})
        items = []
        for child in sorted(p.iterdir(), key=lambda x: x.name.lower()):
            items.append(
                {
                    "name": child.name,
                    "is_dir": child.is_dir(),
                    "size_bytes": child.stat().st_size if child.is_file() else None,
                }
            )
        return ToolResult(True, payload={"path": path, "items": items})

    def read_file(self, path: str, offset: int | None = None, limit: int | None = None) -> ToolResult:
        """
        读取文件内容。
        - 自动处理非 UTF-8 编码。
        - 支持按行进行分页读取（offset 和 limit）。
        - 超大文件会自动截断。
        """
        try:
            p = _resolve_in_workspace(self.workspace_root, path)
            if not p.exists() or not p.is_file():
                return ToolResult(False, error={"code": "E_NOT_FILE", "message": f"文件不存在: {path}"})
            
            file_size = p.stat().st_size
            data = p.read_bytes()
            
            truncated = False
            if len(data) > self.max_file_read_bytes:
                data = data[: self.max_file_read_bytes]
                truncated = True
            
            # 使用 errors="replace" 优雅处理乱码
            text = data.decode("utf-8", errors="replace")
            lines = text.splitlines()
            
            res_payload: dict[str, Any] = {
                "path": path,
                "total_size": file_size,
                "read_size": len(data),
                "truncated": truncated
            }
            if truncated:
                res_payload["warning"] = f"文件过大 ({file_size} 字节). 已截断至 {self.max_file_read_bytes} 字节。"

            if offset is None and limit is None:
                res_payload["text"] = text
                return ToolResult(True, payload=res_payload)
            
            # 索引安全计算
            start = max((offset or 1) - 1, 0)
            count = limit or 200
            end = min(start + count, len(lines))
            
            sliced = "\n".join(lines[start:end])
            res_payload["text"] = sliced
            res_payload["offset"] = offset
            res_payload["limit"] = limit
            return ToolResult(True, payload=res_payload)
        except Exception as e:
            return ToolResult(False, error={"code": "E_READ", "message": str(e)})

    def write_file(self, path: str, text: str) -> ToolResult:
        """全量写入文件。注意：仅在确认文件较小时使用。"""
        p = _resolve_in_workspace(self.workspace_root, path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        return ToolResult(True, payload={"path": path, "bytes_written": len(text.encode("utf-8"))})

    def apply_patch(
        self,
        path: str,
        old: str,
        new: str,
        expected_replacements: int = 1,
        fuzzy: bool = False,
        min_similarity: float = 0.92,
    ) -> ToolResult:
        """
        核心补丁应用引擎：
        - 支持精确匹配替换。
        - 支持 expected_replacements 校验，防止意外的全局替换或定位错误。
        - 支持模糊匹配（fuzzy），当 old 块由于缩进或微小差异不匹配时，尝试寻找最相似的块。
        - 自动生成备份并记录 undo_id，支持通过 undo_patch 完美回滚。
        """
        p = _resolve_in_workspace(self.workspace_root, path)
        if not p.exists() or not p.is_file():
            return ToolResult(False, error={"code": "E_NOT_FILE", "message": f"文件不存在: {path}"})
        before_text = p.read_text(encoding="utf-8", errors="replace")
        before_hash = hashlib.sha256(before_text.encode("utf-8", errors="ignore")).hexdigest()

        replacements = 0
        updated_text = before_text
        mode = "exact"
        matched_similarity: float | None = None

        if old in before_text:
            count = before_text.count(old)
            if expected_replacements > 0 and count != expected_replacements:
                return ToolResult(
                    False,
                    error={
                        "code": "E_NOT_UNIQUE",
                        "message": f"旧代码块匹配到 {count} 处，预期为 {expected_replacements} 处。请增加上下文以保证唯一性。",
                    },
                )
            if expected_replacements == 0:
                replacements = count
                updated_text = before_text.replace(old, new)
            else:
                replacements = expected_replacements
                updated_text = before_text.replace(old, new, expected_replacements)
        else:
            if not fuzzy:
                return ToolResult(False, error={"code": "E_NOT_FOUND", "message": "未在文件中找到指定的旧代码块。"})
            if expected_replacements != 1:
                return ToolResult(
                    False,
                    error={"code": "E_UNSUPPORTED", "message": "模糊匹配目前仅支持单次替换 (expected_replacements=1)。"},
                )
            # 模糊匹配算法：基于锚行搜索和相似度打分
            old_lines = old.splitlines()
            file_lines = before_text.splitlines()
            n = max(len(old_lines), 1)

            # 选择最长的行作为锚点进行初步过滤
            anchor = ""
            for ln in sorted((l.strip() for l in old_lines), key=len, reverse=True):
                if ln:
                    anchor = ln[:120]
                    break

            candidate_starts: list[int] = []
            if anchor:
                for i, ln in enumerate(file_lines):
                    if anchor in ln:
                        candidate_starts.append(max(i - n // 2, 0))
            else:
                candidate_starts = list(range(0, max(len(file_lines) - n + 1, 1)))

            best = None
            best_ratio = 0.0
            candidate_starts = candidate_starts[:200]
            for start in candidate_starts:
                for span in (n, max(n - 1, 1), n + 1):
                    if start + span > len(file_lines):
                        continue
                    cand = "\n".join(file_lines[start : start + span])
                    r = SequenceMatcher(None, old, cand).ratio()
                    if r > best_ratio:
                        best_ratio = r
                        best = (start, cand)
            
            if best is None or best_ratio < float(min_similarity):
                return ToolResult(
                    False,
                    error={
                        "code": "E_FUZZY_NO_MATCH",
                        "message": f"模糊匹配失败：最高相似度为 {best_ratio:.3f}，低于阈值 {min_similarity}。",
                    },
                )

            mode = "fuzzy"
            matched_similarity = best_ratio
            start, cand = best
            updated_text = before_text.replace(cand, new, 1)
            replacements = 1

        # 备份机制：记录修改前的状态，支持回滚
        after_hash = hashlib.sha256(updated_text.encode("utf-8", errors="ignore")).hexdigest()
        undo_dir = self.workspace_root / ".clude" / "undo"
        undo_dir.mkdir(parents=True, exist_ok=True)
        undo_id = f"undo_{time.time_ns()}"
        bak_path = undo_dir / f"{undo_id}.bak"
        meta_path = undo_dir / f"{undo_id}.json"
        bak_path.write_text(before_text, encoding="utf-8")
        meta_path.write_text(
            json.dumps(
                {
                    "undo_id": undo_id,
                    "path": path,
                    "created_at_ns": time.time_ns(),
                    "before_hash": before_hash,
                    "after_hash": after_hash,
                    "backup_file": str(bak_path),
                    "mode": mode,
                    "replacements": replacements,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        p.write_text(updated_text, encoding="utf-8")
        return ToolResult(
            True,
            payload={
                "path": path,
                "mode": mode,
                "replacements": replacements,
                "undo_id": undo_id,
                "before_hash": before_hash,
                "after_hash": after_hash,
            },
        )

    def undo_patch(self, undo_id: str, force: bool = False) -> ToolResult:
        """根据 undo_id 恢复文件。会自动校验当前哈希值以确保安全性。"""
        undo_dir = self.workspace_root / ".clude" / "undo"
        meta_path = undo_dir / f"{undo_id}.json"
        if not meta_path.exists():
            return ToolResult(False, error={"code": "E_UNDO_NOT_FOUND", "message": f"未找到该回滚 ID: {undo_id}"})
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        path = str(meta["path"])
        p = _resolve_in_workspace(self.workspace_root, path)
        
        current_text = p.read_text(encoding="utf-8", errors="replace")
        current_hash = hashlib.sha256(current_text.encode("utf-8", errors="ignore")).hexdigest()
        expected_after = str(meta.get("after_hash", ""))
        
        if (not force) and expected_after and current_hash != expected_after:
            return ToolResult(
                False,
                error={
                    "code": "E_UNDO_CONFLICT",
                    "message": "文件在 Patch 后已被手动修改，为了安全禁止回滚。请使用 force=true 强制覆盖。",
                },
            )

        bak_path = Path(str(meta["backup_file"]))
        if not bak_path.exists():
            return ToolResult(False, error={"code": "E_UNDO_BAK_MISSING", "message": "备份文件已丢失。"})
        
        before_text = bak_path.read_text(encoding="utf-8", errors="replace")
        p.write_text(before_text, encoding="utf-8")
        return ToolResult(True, payload={"path": path, "undo_id": undo_id, "status": "restored"})

    def glob_file_search(self, glob_pattern: str, target_directory: str = ".") -> ToolResult:
        """使用 glob 模式查找文件（支持 ** 递归）。"""
        root = _resolve_in_workspace(self.workspace_root, target_directory)
        matches = []
        try:
            for p in root.glob(glob_pattern):
                if p.is_file():
                    rel = str(p.resolve().relative_to(self.workspace_root.resolve()))
                    # 自动排除常见的干扰目录
                    if any(part in p.parts for part in {".git", ".clude", "node_modules", ".venv", "dist", "build"}):
                        continue
                    matches.append(rel)
        except Exception as e:
            return ToolResult(False, error={"code": "E_GLOB", "message": str(e)})
        return ToolResult(True, payload={"pattern": glob_pattern, "matches": sorted(matches)})

    def grep(self, pattern: str, path: str = ".", ignore_case: bool = False, max_hits: int = 200) -> ToolResult:
        """
        高性能代码搜索：优先调用系统中的 ripgrep (rg)，若不存在则回退至 Python 原生正则搜索。
        """
        if shutil.which("rg"):
            tr = self._rg_grep(pattern=pattern, path=path, ignore_case=ignore_case, max_hits=max_hits)
            if tr.ok:
                return tr
        return self._python_grep(pattern=pattern, path=path, ignore_case=ignore_case, max_hits=max_hits)

    def _rg_grep(self, *, pattern: str, path: str, ignore_case: bool, max_hits: int) -> ToolResult:
        """调用系统 ripgrep 实现的高速搜索。"""
        root = _resolve_in_workspace(self.workspace_root, path)
        args = ["rg", "--json"]
        if ignore_case: args.append("-i")
        # 排除噪音
        args.extend(["-g", "!.clude/*", "-g", "!.git/*", "-g", "!node_modules/*"])
        args.extend([pattern, path])

        try:
            cp = subprocess.run(args, cwd=str(self.workspace_root.resolve()), capture_output=True, text=True, encoding="utf-8")
            if cp.returncode not in (0, 1):
                return ToolResult(False, error={"code": "E_RG", "message": "rg 执行失败"})
            
            hits = []
            for line in cp.stdout.splitlines():
                obj = json.loads(line)
                if obj.get("type") == "match":
                    data = obj.get("data", {})
                    p = data.get("path", {}).get("text", "")
                    ln = data.get("line_number")
                    txt = data.get("lines", {}).get("text", "")
                    hits.append({"path": p, "line": ln, "preview": txt[:300]})
            
            truncated = len(hits) > max_hits
            return ToolResult(True, payload={"pattern": pattern, "engine": "rg", "hits": hits[:max_hits], "truncated": truncated})
        except Exception as e:
            return ToolResult(False, error={"code": "E_RG_EXEC", "message": str(e)})

    def _python_grep(self, *, pattern: str, path: str, ignore_case: bool, max_hits: int) -> ToolResult:
        """Python 原生实现的 Grep 退避方案。"""
        root = _resolve_in_workspace(self.workspace_root, path)
        flags = re.IGNORECASE if ignore_case else 0
        rx = re.compile(pattern, flags)
        hits = []
        for fp in root.rglob("*"):
            if fp.is_dir() or fp.stat().st_size > 1_000_000: continue
            if any(part in fp.parts for part in {".git", ".clude", "node_modules"}): continue
            
            try:
                content = fp.read_text(encoding="utf-8", errors="ignore")
                for i, line in enumerate(content.splitlines(), start=1):
                    if rx.search(line):
                        rel = str(fp.resolve().relative_to(self.workspace_root.resolve()))
                        hits.append({"path": rel, "line": i, "preview": line[:300]})
                        if len(hits) >= max_hits: return ToolResult(True, payload={"hits": hits, "truncated": True})
            except: continue
        return ToolResult(True, payload={"pattern": pattern, "engine": "python", "hits": hits, "truncated": False})

    def generate_repo_map(self) -> str:
        """
        利用 ctags 生成仓库符号地图。这对于 LLM 理解大型项目的全局结构至关重要。
        """
        ctags_exe = shutil.which("ctags")
        if not ctags_exe:
            return "仓库地图：未找到 ctags。全局上下文不可用。"
        
        args = [ctags_exe, "--languages=Python,JavaScript,TypeScript", "--output-format=json", "--fields=+n", "-R", "."]
        try:
            cp = subprocess.run(args, cwd=str(self.workspace_root.resolve()), capture_output=True, text=True, encoding="utf-8", shell=(platform.system() == "Windows"))
            if cp.returncode != 0: return "仓库地图生成失败。"
            
            symbols_by_file: dict[str, list[str]] = {}
            for line in cp.stdout.splitlines():
                try:
                    obj = json.loads(line)
                    path, name, kind, ln = obj.get("path"), obj.get("name"), obj.get("kind"), obj.get("line")
                    if kind not in ("class", "function", "method"): continue
                    if path not in symbols_by_file: symbols_by_file[path] = []
                    symbols_by_file[path].append(f"{kind[0].upper()}| {name} (L{ln})")
                except: continue
            
            res = ["# 仓库符号概览 (Repo Map)"]
            for f in sorted(symbols_by_file.keys())[:50]:
                res.append(f"## {f}")
                res.extend([f"  - {s}" for s in symbols_by_file[f][:10]])
            return "\n".join(res)
        except: return "仓库地图生成过程中发生异常。"

    def run_cmd(self, command: str, cwd: str = ".") -> ToolResult:
        """
        在安全隔离的环境中执行 shell 命令。
        - 清理环境变量，防止泄露敏感 Token。
        - 限制输出长度，防止 Token 溢出。
        """
        import os
        wd = _resolve_in_workspace(self.workspace_root, cwd)
        safe_keys = {"PATH", "HOME", "USER", "LANG", "SHELL"}
        scrubbed_env = {k: v for k, v in os.environ.items() if k.upper() in safe_keys or k.startswith("PYTHON")}

        try:
            cp = subprocess.run(command, cwd=str(wd), shell=True, capture_output=True, text=True, encoding="utf-8", env=scrubbed_env)
            out = (cp.stdout or "") + (cp.stderr or "")
            if len(out) > self.max_output_bytes: out = "..." + out[-self.max_output_bytes:]
            return ToolResult(True, payload={"exit_code": cp.returncode, "output": out})
        except Exception as e:
            return ToolResult(False, error={"code": "E_EXEC", "message": str(e)})


