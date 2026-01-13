import subprocess
import re
import os
from pathlib import Path
from typing import List, Dict
from clude_code.config import CludeConfig
from .models import VerificationResult, VerificationIssue
from .detector import ProjectDetector
from clude_code.observability.logger import get_logger

# 需要从子进程环境中移除的敏感变量
SENSITIVE_ENV_KEYS = frozenset([
    "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN",
    "GITHUB_TOKEN", "GH_TOKEN", "GITLAB_TOKEN",
    "DATABASE_PASSWORD", "DB_PASSWORD",
    "SECRET_KEY", "API_KEY", "PRIVATE_KEY",
])


class Verifier:
    """执行验证并解析输出，同时确保原始输出的可追溯性。"""
    
    def __init__(self, cfg: CludeConfig):
        self.workspace_root = Path(cfg.workspace_root)
        # 如果需要，这里可以从 cfg 中读取具体的验证超时时间
        self.timeout_s = 60 
        self._file_only_logger = None
        
    @property
    def file_only_logger(self):
        if self._file_only_logger is None:
            self._file_only_logger = get_logger(
                f"{__name__}.raw_output",
                workspace_root=self.workspace_root,
                log_to_console=False
            )
        return self._file_only_logger
    
    def _get_safe_env(self) -> Dict[str, str]:
        """返回移除敏感变量后的环境副本。"""
        env = os.environ.copy()
        for key in SENSITIVE_ENV_KEYS:
            env.pop(key, None)
        # 额外移除所有以 _SECRET 或 _TOKEN 结尾的变量
        for key in list(env.keys()):
            if key.endswith("_SECRET") or key.endswith("_TOKEN") or key.endswith("_PASSWORD"):
                env.pop(key, None)
        return env
        
    def run_verify(self, modified_paths: List[Path] | None = None) -> VerificationResult:
        lang, cmd = ProjectDetector.detect(self.workspace_root)
        
        # 尝试精炼命令（选择性测试）
        if modified_paths:
            refined_cmd = ProjectDetector.refine_command(lang, cmd, modified_paths)
            if refined_cmd != cmd:
                self.file_only_logger.info(f"精炼验证范围: {cmd} -> {refined_cmd}")
                cmd = refined_cmd

        if lang == "unknown" or not cmd:
            return VerificationResult(
                ok=True, 
                type="unknown", 
                summary="未探测到支持的项目类型，跳过验证。"
            )
        
        # 安全校验：确保命令在白名单内
        if not ProjectDetector.is_safe_command(cmd):
            self.file_only_logger.warning(f"命令未通过白名单校验，拒绝执行: {cmd}")
            return VerificationResult(
                ok=False,
                type="policy",
                summary=f"命令被安全策略拒绝: {cmd}"
            )
            
        try:
            self.file_only_logger.info(f"--- 启动验证任务: {cmd} (语言: {lang}, 超时: {self.timeout_s}s) ---")
            
            result = subprocess.run(
                cmd,
                shell=True,
                cwd=self.workspace_root,
                capture_output=True,
                text=True,
                timeout=self.timeout_s,
                encoding="utf-8",
                errors="replace",
                env=self._get_safe_env()  # 隔离敏感环境变量
            )
            
            stdout_stderr = (result.stdout or "") + "\n" + (result.stderr or "")
            
            self.file_only_logger.info(f"--- 验证原始输出 (Exit Code: {result.returncode}) ---\n{stdout_stderr}")

            # 在 shell=True 下，命令不存在通常不会抛 FileNotFoundError，而是返回码 127(POSIX)/9009(Windows)。
            # 这里做一个启发式识别，给出更友好的建议，避免误进入“测试失败解析器”。
            stderr_lower = (result.stderr or "").lower()
            stdout_lower = (result.stdout or "").lower()
            combined_lower = stdout_lower + "\n" + stderr_lower
            if result.returncode in (127, 9009) or ("not recognized" in combined_lower) or ("not found" in combined_lower):
                return VerificationResult(
                    ok=False,
                    type="error",
                    summary=f"验证命令不可用或未安装: {cmd}",
                    errors=[VerificationIssue(file="", message=(result.stderr or result.stdout or "command not found").strip())],
                    suggestion="请安装对应工具并确保在 PATH 中（如 `pip install pytest` / `npm i` / `go install`）。"
                )
            
            if result.returncode == 0:
                return VerificationResult(
                    ok=True,
                    type="test",
                    summary=f"验证通过: {cmd}"
                )
            else:
                return self._parse_errors(lang, cmd, stdout_stderr)
                
        except subprocess.TimeoutExpired as e:
            # 注意：在 text=True 时，TimeoutExpired.stdout/stderr 可能已经是 str；否则才是 bytes。
            if isinstance(e.stdout, bytes):
                stdout = e.stdout.decode("utf-8", "replace")
            else:
                stdout = e.stdout or ""
            if isinstance(e.stderr, bytes):
                stderr = e.stderr.decode("utf-8", "replace")
            else:
                stderr = e.stderr or ""
            self.file_only_logger.error(f"验证任务超时 ({self.timeout_s}s):\n{stdout}\n{stderr}")
            return VerificationResult(
                ok=False,
                type="test",
                summary=f"验证超时 ({self.timeout_s}s)",
                errors=[VerificationIssue(file="", message="测试运行超时，可能存在死循环或环境问题")],
                suggestion="尝试缩小测试范围或增加超时时间"
            )
        except FileNotFoundError as e:
            self.file_only_logger.error(f"验证工具未找到: {e}")
            return VerificationResult(
                ok=False,
                type="error",
                summary=f"验证工具未安装或不在 PATH 中: {cmd.split()[0]}",
                suggestion="请确保已安装对应的测试框架（如 pytest, npm 等）"
            )
        except Exception as e:
            self.file_only_logger.exception("验证执行过程中发生严重错误")
            return VerificationResult(
                ok=False,
                type="error",
                summary=f"执行验证工具时出错: {str(e)}"
            )

    def _parse_errors(self, lang: str, cmd: str, output: str) -> VerificationResult:
        """多语言错误解析器。"""
        errors = []
        
        if lang == "python":
            errors = self._parse_python_errors(output)
        elif lang == "nodejs":
            errors = self._parse_nodejs_errors(output)
        elif lang == "go":
            errors = self._parse_go_errors(output)
        elif lang == "rust":
            errors = self._parse_rust_errors(output)
        else:
            errors = self._parse_generic_errors(output)
        
        # 去重并限制数量
        errors = self._dedupe_errors(errors)[:10]
        
        summary = f"验证失败，定位到 {len(errors)} 处错误。" if errors else "验证失败，请查看日志详情。"
        
        return VerificationResult(
            ok=False,
            type="test",
            summary=summary,
            errors=errors
        )
    
    def _parse_python_errors(self, output: str) -> List[VerificationIssue]:
        """Python 错误解析（pytest/flake8/traceback）。"""
        errors = []
        patterns = [
            (r'([\w\./\\]+\.py):(\d+): (.+)', 3),           # pytest/flake8
            (r'File "([^"]+\.py)", line (\d+)', 2),          # Traceback
            (r'([\w\./\\]+\.py):(\d+):(\d+): (.+)', 4),      # flake8 with column
        ]
        
        for pattern, group_count in patterns:
            for m in re.finditer(pattern, output):
                groups = m.groups()
                if group_count == 3 and len(groups) >= 3:
                    file, line, msg = groups[0], groups[1], groups[2]
                    errors.append(VerificationIssue(file=file, line=int(line), message=msg.strip()))
                elif group_count == 2 and len(groups) >= 2:
                    file, line = groups[0], groups[1]
                    errors.append(VerificationIssue(file=file, line=int(line), message="Traceback 异常"))
                elif group_count == 4 and len(groups) >= 4:
                    file, line, col, msg = groups[0], groups[1], groups[2], groups[3]
                    errors.append(VerificationIssue(file=file, line=int(line), message=f"[col:{col}] {msg.strip()}"))
        
        return errors
    
    def _parse_nodejs_errors(self, output: str) -> List[VerificationIssue]:
        """Node.js 错误解析（Jest/Mocha/ESLint）。"""
        errors = []
        patterns = [
            r'([\w\./\\]+\.[jt]sx?):(\d+):(\d+)',              # ESLint/TypeScript
            r'at .+ \(([\w\./\\]+\.[jt]sx?):(\d+):(\d+)\)',    # Stack trace
            r'FAIL ([\w\./\\]+\.[jt]sx?)',                     # Jest FAIL
        ]
        
        for pattern in patterns:
            for m in re.finditer(pattern, output):
                groups = m.groups()
                if len(groups) >= 2:
                    file = groups[0]
                    line = int(groups[1]) if groups[1].isdigit() else 1
                    errors.append(VerificationIssue(file=file, line=line, message="测试/Lint 失败"))
                elif len(groups) == 1:
                    errors.append(VerificationIssue(file=groups[0], line=1, message="测试失败"))
        
        return errors
    
    def _parse_go_errors(self, output: str) -> List[VerificationIssue]:
        """Go 错误解析。"""
        errors = []
        patterns = [
            r'([\w\./\\]+\.go):(\d+):(\d+): (.+)',   # 编译错误
            r'([\w\./\\]+\.go):(\d+): (.+)',          # go vet
            r'--- FAIL: (\w+)',                       # 测试函数名
        ]
        
        for pattern in patterns:
            for m in re.finditer(pattern, output):
                groups = m.groups()
                if len(groups) == 4:
                    file, line, col, msg = groups
                    errors.append(VerificationIssue(file=file, line=int(line), message=f"[col:{col}] {msg.strip()}"))
                elif len(groups) == 3:
                    file, line, msg = groups
                    errors.append(VerificationIssue(file=file, line=int(line), message=msg.strip()))
                elif len(groups) == 1:
                    errors.append(VerificationIssue(file="", message=f"测试函数失败: {groups[0]}"))
        
        return errors
    
    def _parse_rust_errors(self, output: str) -> List[VerificationIssue]:
        """Rust 错误解析。"""
        errors = []
        patterns = [
            r'--> ([\w\./\\]+\.rs):(\d+):(\d+)',    # Rust 编译器错误
            r'error\[E\d+\]: (.+)',                  # 错误代码
        ]
        
        for pattern in patterns:
            for m in re.finditer(pattern, output):
                groups = m.groups()
                if len(groups) == 3:
                    file, line, col = groups
                    errors.append(VerificationIssue(file=file, line=int(line), message=f"编译错误 (col:{col})"))
                elif len(groups) == 1:
                    errors.append(VerificationIssue(file="", message=groups[0].strip()))
        
        return errors
    
    def _parse_generic_errors(self, output: str) -> List[VerificationIssue]:
        """通用 file:line 格式解析。"""
        errors = []
        pattern = r'([\w\./\\]+\.\w+):(\d+)'
        for m in re.finditer(pattern, output):
            file, line = m.groups()
            errors.append(VerificationIssue(file=file, line=int(line), message="错误"))
        return errors
    
    def _dedupe_errors(self, errors: List[VerificationIssue]) -> List[VerificationIssue]:
        """去重并过滤第三方库。"""
        seen = set()
        unique = []
        skip_patterns = ["site-packages", "lib/python", "node_modules", ".venv", "venv"]
        for e in errors:
            if any(p in e.file for p in skip_patterns):
                continue
            key = (e.file, e.line)
            if key not in seen:
                unique.append(e)
                seen.add(key)
        return unique
