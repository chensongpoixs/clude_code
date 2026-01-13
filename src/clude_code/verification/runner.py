import subprocess
import re
import logging
from pathlib import Path
from typing import List, Optional
from .models import VerificationResult, VerificationIssue
from .detector import ProjectDetector
from clude_code.observability.logger import get_logger

class Verifier:
    """执行验证并解析输出，同时确保原始输出的可追溯性。"""
    
    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root
        # 延迟初始化日志，确保在调用时获取最新的 log_to_console 配置
        # 但我们强制此日志只写文件
        self._file_only_logger = None
        
    @property
    def file_only_logger(self):
        if self._file_only_logger is None:
            self._file_only_logger = get_logger(
                f"{__name__}.raw_output",
                workspace_root=self.workspace_root,
                log_to_console=False  # 核心隔离点：确保不污染控制台 UI
            )
        return self._file_only_logger
        
    def run_verify(self) -> VerificationResult:
        lang, cmd = ProjectDetector.detect(self.workspace_root)
        
        if lang == "unknown" or not cmd:
            return VerificationResult(
                ok=True, 
                type="unknown", 
                summary="未探测到支持的项目类型，跳过验证。"
            )
            
        try:
            self.file_only_logger.info(f"--- 启动验证任务: {cmd} (语言: {lang}) ---")
            
            # 使用 utf-8 编码读取输出，遇到无法解码字符替换为占位符
            result = subprocess.run(
                cmd,
                shell=True,
                cwd=self.workspace_root,
                capture_output=True,
                text=True,
                timeout=60,
                encoding="utf-8",
                errors="replace"
            )
            
            stdout_stderr = (result.stdout or "") + "\n" + (result.stderr or "")
            
            # 记录到日志文件
            self.file_only_logger.info(f"--- 验证原始输出 (Exit Code: {result.returncode}) ---\n{stdout_stderr}")
            
            if result.returncode == 0:
                return VerificationResult(
                    ok=True,
                    type="test",
                    summary=f"验证通过: {cmd}"
                )
            else:
                return self._parse_errors(lang, cmd, stdout_stderr)
                
        except subprocess.TimeoutExpired as e:
            # 超时情况下，尽量获取已有的输出
            stdout = e.stdout.decode("utf-8", "replace") if e.stdout else ""
            stderr = e.stderr.decode("utf-8", "replace") if e.stderr else ""
            self.file_only_logger.error(f"验证任务超时 (60s):\n{stdout}\n{stderr}")
            return VerificationResult(
                ok=False,
                type="test",
                summary="验证超时 (60s)",
                errors=[VerificationIssue(file="", message="测试运行超时，可能存在死循环或环境问题")]
            )
        except Exception as e:
            self.file_only_logger.exception("验证执行过程中发生严重错误")
            return VerificationResult(
                ok=False,
                type="error",
                summary=f"执行验证工具时出错: {str(e)}"
            )

    def _parse_errors(self, lang: str, cmd: str, output: str) -> VerificationResult:
        """增强版错误解析。"""
        errors = []
        
        if lang == "python":
            # 模式 1: 路径:行号: 错误信息
            # 模式 2: File "路径", line 行号
            regex_list = [
                r'([\w\./\\]+\.py):(\d+): (.*)',
                r'File "([^"]+\.py)", line (\d+)'
            ]
            
            for regex in regex_list:
                for m in re.finditer(regex, output):
                    groups = m.groups()
                    if len(groups) == 3:
                        file, line, msg = groups
                        errors.append(VerificationIssue(file=file, line=int(line), message=msg.strip()))
                    elif len(groups) == 2:
                        file, line = groups
                        errors.append(VerificationIssue(file=file, line=int(line), message="代码逻辑错误 (Traceback)"))

            # 过滤并去重
            seen = set()
            unique_errors = []
            for e in errors:
                # 排除第三方库路径
                if "site-packages" in e.file or "lib/python" in e.file:
                    continue
                key = (e.file, e.line)
                if key not in seen:
                    unique_errors.append(e)
                    seen.add(key)
            errors = unique_errors
            
            summary = f"验证失败，定位到 {len(errors)} 处错误。" if errors else "验证失败，请查看日志。"
        else:
            summary = "验证失败，未适配解析。"
            
        return VerificationResult(
            ok=False,
            type="test",
            summary=summary,
            errors=errors[:10]
        )
