from __future__ import annotations

import json
import platform
import shutil
import subprocess
from pathlib import Path
from typing import Dict, List, Any


def generate_repo_map(*, workspace_root: Path) -> str:
    """
    生成增强版仓库图谱 (V2)：
    1. 引入权重计算 (Ranking)：根据文件深度和符号数量识别核心模块。
    2. 深度树形结构。
    3. 自动排除非核心符号，防止上下文溢出。
    """
    ctags_exe = shutil.which("ctags")
    if not ctags_exe:
        return "Repo Map: ctags not found."

    # 1. 扫描符号 (增加更多的元数据字段)
    args = [
        ctags_exe,
        "--languages=Python,JavaScript,TypeScript,Go,Rust,C,C++,C#",
        "--output-format=json",
        "--fields=+n+k+K+S",
        "--extras=+q",
        "-R",
        "--exclude=.git", "--exclude=node_modules", "--exclude=venv", "--exclude=.venv",
        "--exclude=__pycache__", "--exclude=build", "--exclude=dist", "--exclude=.clude",
        "--exclude=*.json", "--exclude=*.md", "--exclude=tests", # 排除文档和常规测试目录以聚焦核心
        ".",
    ]

    abs_root = str(workspace_root.resolve())
    try:
        cp = subprocess.run(args, cwd=abs_root, capture_output=True, text=True, encoding="utf-8", shell=(platform.system() == "Windows"))
    except Exception as e:
        return f"Repo Map Error: {e}"

    # 2. 解析并计算文件权重
    # file_stats[path] = {"symbols": [], "weight": float}
    file_stats: Dict[str, Dict[str, Any]] = {}
    
    for line in (cp.stdout or "").splitlines():
        try:
            obj = json.loads(line)
        except: continue
        
        path = obj.get("path")
        kind = obj.get("kind")
        if not (path and kind in ("class", "function", "interface", "struct")): continue
        
        if path not in file_stats:
            # 权重计算逻辑：根目录下的文件权重更高；.py 比 .txt 高
            depth = len(Path(path).parts)
            base_weight = 10.0 / depth
            file_stats[path] = {"symbols": [], "weight": base_weight}
            
        file_stats[path]["symbols"].append({
            "name": obj.get("name"),
            "kind": kind[0].upper(),
            "line": obj.get("line")
        })
        # 每增加一个核心符号，文件权重略微增加
        file_stats[path]["weight"] += 0.5

    # 3. 筛选核心文件（仅展示权重前 50 的文件，防止上下文挤爆）
    top_files = sorted(file_stats.keys(), key=lambda x: file_stats[x]["weight"], reverse=True)[:50]
    
    # 4. 构建渲染树
    tree: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
    for p in top_files:
        p_obj = Path(p)
        d, f = str(p_obj.parent), p_obj.name
        if d not in tree: tree[d] = {}
        tree[d][f] = file_stats[p]["symbols"]

    # 5. 渲染 Markdown
    lines = ["# 核心代码架构图谱 (Core Repo Map)", "提示：已优先展示项目核心逻辑文件及符号。", ""]
    
    for dir_path in sorted(tree.keys()):
        # 简化根目录显示
        display_dir = "Project Root" if dir_path == "." else dir_path
        lines.append(f"📁 {display_dir}/")
        
        for file_name in sorted(tree[dir_path].keys()):
            lines.append(f"  📄 {file_name}")
            syms = tree[dir_path][file_name]
            # 排序：类 -> 函数
            sorted_syms = sorted(syms, key=lambda x: (x["kind"] != "C", x["line"]))
            
            # 单个文件内最多展示 8 个符号
            for s in sorted_syms[:8]:
                lines.append(f"    └─ [{s['kind']}] {s['name']} (L{s['line']})")
            if len(sorted_syms) > 8:
                lines.append(f"    └─ ... (+{len(sorted_syms)-8} more)")
        lines.append("")

    return "\n".join(lines)
