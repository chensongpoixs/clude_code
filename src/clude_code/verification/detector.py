import os
import json
from pathlib import Path
from typing import Tuple, Set, List


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
        """
        cmd_lower = cmd.strip().lower()
        for prefix in SAFE_COMMAND_PREFIXES:
            if cmd_lower.startswith(prefix.lower()):
                return True
        return False

    @staticmethod
    def refine_command(lang: str, base_cmd: str, modified_paths: List[Path]) -> str:
        """
        根据修改过的文件路径，精炼验证命令，实现选择性测试 (Selective Testing)。
        """
        if not modified_paths:
            return base_cmd

        # 只处理存在的文件
        existing_paths = [p for p in modified_paths if p.exists()]
        if not existing_paths:
            return base_cmd

        if lang == "python":
            # 策略：如果修改了 test_*.py，直接跑该文件；如果修改了其他 .py，跑同目录下或子目录下的相关测试
            # 为简化逻辑，目前直接针对修改的 Python 文件列表运行 pytest
            paths_str = " ".join(str(p) for p in existing_paths if p.suffix == ".py")
            if paths_str:
                return f"pytest {paths_str} --maxfail=3 -q"
        
        elif lang == "nodejs":
            # Jest 等支持直接跟路径
            paths_str = " ".join(str(p) for p in existing_paths if p.suffix in {".js", ".ts", ".tsx", ".jsx"})
            if paths_str:
                # 针对 npm test，通常无法直接追加路径，需要模型适配或通过参数传递
                # 这里假设如果是 jest，可以直接跟路径
                if "jest" in base_cmd or "mocha" in base_cmd:
                    return f"{base_cmd} {paths_str}"
        
        elif lang == "go":
            # Go test 支持包路径或文件路径
            dirs = {str(p.parent) for p in existing_paths if p.suffix == ".go"}
            if dirs:
                dirs_str = " ".join(f"./{d}" for d in dirs)
                return f"go test {dirs_str} -v"

        return base_cmd
