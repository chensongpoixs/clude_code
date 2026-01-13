import os
import json
from pathlib import Path
from typing import Tuple, Set

# 允许执行的验证命令白名单（前缀匹配）
SAFE_COMMAND_PREFIXES: Set[str] = frozenset([
    "pytest", "python -m pytest", "python -m unittest",
    "npm test", "npm run test", "npx jest", "npx mocha",
    "go test", "cargo test",
    "flake8", "pylint", "mypy", "ruff",
    "eslint", "tsc --noEmit",
])


class ProjectDetector:
    """自动探测项目类型和适用的验证工具。"""
    
    @staticmethod
    def detect(workspace_root: Path) -> Tuple[str, str]:
        """
        返回: (项目语言, 建议验证命令)
        
        探测优先级：
        1. Python (pyproject.toml > pytest.ini > requirements.txt)
        2. Node.js (package.json)
        3. Go (go.mod)
        4. Rust (Cargo.toml)
        """
        # Python - 优先级最高
        if (workspace_root / "pyproject.toml").exists():
            return "python", "pytest --maxfail=3 -q"
        if (workspace_root / "pytest.ini").exists():
            return "python", "pytest --maxfail=3 -q"
        if (workspace_root / "setup.py").exists() or (workspace_root / "requirements.txt").exists():
            return "python", "python -m pytest --maxfail=3 -q"
            
        # Node.js - 检查 package.json 中是否有 test script
        package_json = workspace_root / "package.json"
        if package_json.exists():
            try:
                with open(package_json, "r", encoding="utf-8") as f:
                    pkg = json.load(f)
                    scripts = pkg.get("scripts", {})
                    if "test" in scripts:
                        return "nodejs", "npm test"
                    elif "lint" in scripts:
                        return "nodejs", "npm run lint"
            except (json.JSONDecodeError, IOError):
                pass
            # 默认尝试 npm test
            return "nodejs", "npm test"
            
        # Go
        if (workspace_root / "go.mod").exists():
            return "go", "go test ./... -v"
            
        # Rust
        if (workspace_root / "Cargo.toml").exists():
            return "rust", "cargo test"
            
        return "unknown", ""
    
    @staticmethod
    def is_safe_command(cmd: str) -> bool:
        """
        检查命令是否在白名单中（前缀匹配）。
        
        安全设计：
        - 只允许已知的测试/lint 命令
        - 防止命令注入攻击
        """
        cmd_lower = cmd.strip().lower()
        for prefix in SAFE_COMMAND_PREFIXES:
            if cmd_lower.startswith(prefix.lower()):
                return True
        return False
