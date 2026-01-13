import os
from pathlib import Path
from typing import Optional, Tuple

class ProjectDetector:
    """自动探测项目类型和适用的验证工具。"""
    
    @staticmethod
    def detect(workspace_root: Path) -> Tuple[str, str]:
        """
        返回: (项目语言, 建议验证命令)
        """
        # Python
        if (workspace_root / "pyproject.toml").exists() or (workspace_root / "pytest.ini").exists():
            return "python", "pytest --maxfail=3"
        if (workspace_root / "requirements.txt").exists():
            return "python", "python -m pytest"
            
        # Node.js
        if (workspace_root / "package.json").exists():
            # 简单逻辑：如果是 Node，优先尝试 npm test
            return "nodejs", "npm test"
            
        # Go
        if (workspace_root / "go.mod").exists():
            return "go", "go test ./..."
            
        return "unknown", ""

