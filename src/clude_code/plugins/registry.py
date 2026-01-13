"""
Tool 插件系统 - 注册表与执行器

业界对比：
- Claude Code MCP: JSON Schema + subprocess + 沙箱隔离
- Aider: 简单的 Python 函数注册
- Cursor: 内置工具，不可扩展

本实现：YAML/JSON 插件定义 + 子进程沙箱执行 + Schema 校验
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
import yaml
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Literal, Callable
from enum import Enum

from pydantic import BaseModel, Field, ValidationError


class PluginType(str, Enum):
    """插件类型。"""
    SCRIPT = "script"           # 外部脚本（shell/python/node）
    HTTP = "http"               # HTTP API 调用
    PYTHON = "python"           # 内嵌 Python 代码（沙箱执行）


class PluginParamSchema(BaseModel):
    """插件参数定义。"""
    name: str = Field(..., description="参数名")
    type: Literal["string", "integer", "number", "boolean", "array", "object"] = Field("string", description="参数类型")
    description: str = Field("", description="参数描述")
    required: bool = Field(False, description="是否必需")
    default: Any = Field(None, description="默认值")


class PluginDefinition(BaseModel):
    """
    插件定义（YAML/JSON 格式）。
    
    示例：
    ```yaml
    name: my_tool
    type: script
    description: "自定义工具示例"
    command: ["python", "scripts/my_tool.py"]
    params:
      - name: input
        type: string
        required: true
        description: "输入数据"
    timeout_s: 60
    sandbox: true
    ```
    """
    name: str = Field(..., min_length=1, max_length=64, pattern=r"^[a-z_][a-z0-9_]*$", description="工具名（小写+下划线）")
    type: PluginType = Field(PluginType.SCRIPT, description="插件类型")
    description: str = Field("", max_length=500, description="工具描述")
    
    # Script 类型配置
    command: List[str] = Field(default_factory=list, description="执行命令（仅 script 类型）")
    working_dir: Optional[str] = Field(None, description="工作目录（相对于 workspace）")
    env: Dict[str, str] = Field(default_factory=dict, description="环境变量")
    
    # HTTP 类型配置
    url: Optional[str] = Field(None, description="HTTP URL（仅 http 类型）")
    method: Literal["GET", "POST", "PUT", "DELETE"] = Field("POST", description="HTTP 方法")
    headers: Dict[str, str] = Field(default_factory=dict, description="HTTP 头")
    
    # Python 类型配置
    code: Optional[str] = Field(None, description="Python 代码（仅 python 类型）")
    
    # 通用配置
    params: List[PluginParamSchema] = Field(default_factory=list, description="参数列表")
    timeout_s: int = Field(60, ge=1, le=3600, description="超时时间（秒）")
    sandbox: bool = Field(True, description="是否启用沙箱隔离")
    
    # 元数据
    version: str = Field("1.0.0", description="插件版本")
    author: Optional[str] = Field(None, description="作者")
    tags: List[str] = Field(default_factory=list, description="标签（用于分类）")


@dataclass
class PluginResult:
    """插件执行结果。"""
    ok: bool
    output: str = ""
    error: str = ""
    exit_code: int = 0
    duration_ms: int = 0


class PluginExecutor:
    """
    插件执行器（沙箱隔离）。
    
    安全措施：
    - 工作目录限制
    - 环境变量过滤
    - 超时保护
    - 输出大小限制
    """
    
    # 敏感环境变量（执行时移除）
    SENSITIVE_ENV_VARS = {
        "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN",
        "GITHUB_TOKEN", "GH_TOKEN", "GITLAB_TOKEN",
        "OPENAI_API_KEY", "ANTHROPIC_API_KEY",
        "DATABASE_URL", "DB_PASSWORD", "PASSWORD",
        "SECRET", "API_KEY", "PRIVATE_KEY",
    }
    
    def __init__(
        self,
        workspace_root: Path,
        max_output_bytes: int = 1_000_000,
    ):
        self.workspace_root = workspace_root.resolve()
        self.max_output_bytes = max_output_bytes
    
    def _get_safe_env(self, plugin: PluginDefinition) -> Dict[str, str]:
        """获取安全的环境变量（移除敏感变量）。"""
        env = os.environ.copy()
        
        # 移除敏感变量
        for key in list(env.keys()):
            if any(s in key.upper() for s in self.SENSITIVE_ENV_VARS):
                del env[key]
        
        # 添加插件定义的环境变量
        env.update(plugin.env)
        
        # 注入标准变量
        env["CLUDE_WORKSPACE"] = str(self.workspace_root)
        env["CLUDE_PLUGIN_NAME"] = plugin.name
        
        return env
    
    def _resolve_working_dir(self, plugin: PluginDefinition) -> Path:
        """解析工作目录。"""
        if plugin.working_dir:
            wd = (self.workspace_root / plugin.working_dir).resolve()
            # 安全检查：必须在 workspace 内
            try:
                wd.relative_to(self.workspace_root)
            except ValueError:
                wd = self.workspace_root
        else:
            wd = self.workspace_root
        return wd
    
    def execute_script(
        self,
        plugin: PluginDefinition,
        args: Dict[str, Any],
    ) -> PluginResult:
        """执行脚本类型插件。"""
        import time
        start_time = time.time()
        
        if not plugin.command:
            return PluginResult(ok=False, error="No command specified for script plugin")
        
        # 构建命令（替换参数占位符）
        command = []
        for part in plugin.command:
            for key, value in args.items():
                part = part.replace(f"${{{key}}}", str(value))
                part = part.replace(f"${key}", str(value))
            command.append(part)
        
        # 准备环境
        env = self._get_safe_env(plugin) if plugin.sandbox else os.environ.copy()
        env.update(plugin.env)
        cwd = self._resolve_working_dir(plugin)
        
        # 通过 stdin 传递参数（更安全）
        stdin_data = json.dumps(args, ensure_ascii=False).encode("utf-8")
        
        try:
            result = subprocess.run(
                command,
                input=stdin_data,
                capture_output=True,
                timeout=plugin.timeout_s,
                cwd=cwd,
                env=env,
            )
            
            stdout = result.stdout.decode("utf-8", errors="replace")
            stderr = result.stderr.decode("utf-8", errors="replace")
            
            # 限制输出大小
            if len(stdout) > self.max_output_bytes:
                stdout = stdout[:self.max_output_bytes] + "\n[OUTPUT TRUNCATED]"
            if len(stderr) > self.max_output_bytes:
                stderr = stderr[:self.max_output_bytes] + "\n[OUTPUT TRUNCATED]"
            
            duration_ms = int((time.time() - start_time) * 1000)
            
            return PluginResult(
                ok=result.returncode == 0,
                output=stdout,
                error=stderr if result.returncode != 0 else "",
                exit_code=result.returncode,
                duration_ms=duration_ms,
            )
            
        except subprocess.TimeoutExpired as e:
            duration_ms = int((time.time() - start_time) * 1000)
            return PluginResult(
                ok=False,
                error=f"Plugin execution timed out after {plugin.timeout_s}s",
                exit_code=-1,
                duration_ms=duration_ms,
            )
        except FileNotFoundError as e:
            return PluginResult(
                ok=False,
                error=f"Command not found: {command[0]}",
                exit_code=-1,
            )
        except Exception as e:
            return PluginResult(
                ok=False,
                error=f"Plugin execution failed: {str(e)}",
                exit_code=-1,
            )
    
    def execute_http(
        self,
        plugin: PluginDefinition,
        args: Dict[str, Any],
    ) -> PluginResult:
        """执行 HTTP 类型插件。"""
        import time
        start_time = time.time()
        
        if not plugin.url:
            return PluginResult(ok=False, error="No URL specified for HTTP plugin")
        
        try:
            import httpx
        except ImportError:
            return PluginResult(ok=False, error="httpx not installed (required for HTTP plugins)")
        
        try:
            # 替换 URL 中的参数
            url = plugin.url
            for key, value in args.items():
                url = url.replace(f"${{{key}}}", str(value))
                url = url.replace(f"${key}", str(value))
            
            with httpx.Client(timeout=plugin.timeout_s) as client:
                if plugin.method == "GET":
                    response = client.get(url, headers=plugin.headers, params=args)
                elif plugin.method == "POST":
                    response = client.post(url, headers=plugin.headers, json=args)
                elif plugin.method == "PUT":
                    response = client.put(url, headers=plugin.headers, json=args)
                elif plugin.method == "DELETE":
                    response = client.delete(url, headers=plugin.headers, params=args)
                else:
                    return PluginResult(ok=False, error=f"Unsupported HTTP method: {plugin.method}")
            
            duration_ms = int((time.time() - start_time) * 1000)
            
            return PluginResult(
                ok=response.is_success,
                output=response.text[:self.max_output_bytes],
                error="" if response.is_success else f"HTTP {response.status_code}: {response.text[:500]}",
                exit_code=0 if response.is_success else response.status_code,
                duration_ms=duration_ms,
            )
            
        except httpx.TimeoutException:
            return PluginResult(ok=False, error=f"HTTP request timed out after {plugin.timeout_s}s", exit_code=-1)
        except Exception as e:
            return PluginResult(ok=False, error=f"HTTP request failed: {str(e)}", exit_code=-1)
    
    def execute_python(
        self,
        plugin: PluginDefinition,
        args: Dict[str, Any],
    ) -> PluginResult:
        """执行 Python 类型插件（沙箱隔离）。"""
        import time
        start_time = time.time()
        
        if not plugin.code:
            return PluginResult(ok=False, error="No code specified for Python plugin")
        
        # 创建临时文件执行（隔离）
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            # 注入参数
            wrapper_code = f'''
import json
import sys

# 从 stdin 读取参数
args = json.loads(sys.stdin.read())

# 用户代码
{plugin.code}
'''
            f.write(wrapper_code)
            temp_path = f.name
        
        try:
            env = self._get_safe_env(plugin) if plugin.sandbox else os.environ.copy()
            cwd = self._resolve_working_dir(plugin)
            
            result = subprocess.run(
                [sys.executable, temp_path],
                input=json.dumps(args).encode("utf-8"),
                capture_output=True,
                timeout=plugin.timeout_s,
                cwd=cwd,
                env=env,
            )
            
            stdout = result.stdout.decode("utf-8", errors="replace")
            stderr = result.stderr.decode("utf-8", errors="replace")
            duration_ms = int((time.time() - start_time) * 1000)
            
            return PluginResult(
                ok=result.returncode == 0,
                output=stdout[:self.max_output_bytes],
                error=stderr[:self.max_output_bytes] if result.returncode != 0 else "",
                exit_code=result.returncode,
                duration_ms=duration_ms,
            )
            
        except subprocess.TimeoutExpired:
            return PluginResult(ok=False, error=f"Python plugin timed out after {plugin.timeout_s}s", exit_code=-1)
        except Exception as e:
            return PluginResult(ok=False, error=f"Python plugin failed: {str(e)}", exit_code=-1)
        finally:
            # 清理临时文件
            try:
                os.unlink(temp_path)
            except Exception:
                pass
    
    def execute(
        self,
        plugin: PluginDefinition,
        args: Dict[str, Any],
    ) -> PluginResult:
        """执行插件（自动选择执行器）。"""
        # 参数校验
        validation_error = self._validate_args(plugin, args)
        if validation_error:
            return PluginResult(ok=False, error=validation_error)
        
        if plugin.type == PluginType.SCRIPT:
            return self.execute_script(plugin, args)
        elif plugin.type == PluginType.HTTP:
            return self.execute_http(plugin, args)
        elif plugin.type == PluginType.PYTHON:
            return self.execute_python(plugin, args)
        else:
            return PluginResult(ok=False, error=f"Unknown plugin type: {plugin.type}")
    
    def _validate_args(self, plugin: PluginDefinition, args: Dict[str, Any]) -> str | None:
        """校验插件参数。"""
        for param in plugin.params:
            if param.required and param.name not in args:
                return f"Missing required parameter: {param.name}"
            
            if param.name in args:
                value = args[param.name]
                # 简单类型检查
                if param.type == "string" and not isinstance(value, str):
                    return f"Parameter {param.name} must be string"
                if param.type == "integer" and not isinstance(value, int):
                    return f"Parameter {param.name} must be integer"
                if param.type == "number" and not isinstance(value, (int, float)):
                    return f"Parameter {param.name} must be number"
                if param.type == "boolean" and not isinstance(value, bool):
                    return f"Parameter {param.name} must be boolean"
                if param.type == "array" and not isinstance(value, list):
                    return f"Parameter {param.name} must be array"
                if param.type == "object" and not isinstance(value, dict):
                    return f"Parameter {param.name} must be object"
        
        return None


class PluginRegistry:
    """
    插件注册表。
    
    功能：
    - 从目录加载插件定义
    - 插件增删改查
    - 插件执行分发
    """
    
    def __init__(
        self,
        workspace_root: Path,
        plugins_dir: str = ".clude/plugins",
    ):
        self.workspace_root = workspace_root.resolve()
        self.plugins_dir = self.workspace_root / plugins_dir
        self.executor = PluginExecutor(workspace_root)
        self._plugins: Dict[str, PluginDefinition] = {}
        self._load_from_directory()
    
    def _load_from_directory(self) -> None:
        """从插件目录加载所有插件定义。"""
        if not self.plugins_dir.exists():
            return
        
        for file in self.plugins_dir.glob("*.yaml"):
            self._load_plugin_file(file)
        for file in self.plugins_dir.glob("*.yml"):
            self._load_plugin_file(file)
        for file in self.plugins_dir.glob("*.json"):
            self._load_plugin_file(file)
    
    def _load_plugin_file(self, path: Path) -> bool:
        """加载单个插件定义文件。"""
        try:
            content = path.read_text(encoding="utf-8")
            
            if path.suffix in (".yaml", ".yml"):
                data = yaml.safe_load(content)
            else:
                data = json.loads(content)
            
            if not isinstance(data, dict):
                return False
            
            plugin = PluginDefinition.model_validate(data)
            self._plugins[plugin.name] = plugin
            return True
            
        except (yaml.YAMLError, json.JSONDecodeError, ValidationError) as e:
            # 加载失败：静默跳过（可以在调试时打印）
            return False
    
    def register(self, plugin: PluginDefinition) -> None:
        """注册插件。"""
        self._plugins[plugin.name] = plugin
    
    def unregister(self, name: str) -> bool:
        """注销插件。"""
        if name in self._plugins:
            del self._plugins[name]
            return True
        return False
    
    def get(self, name: str) -> PluginDefinition | None:
        """获取插件定义。"""
        return self._plugins.get(name)
    
    def list_all(self) -> List[PluginDefinition]:
        """列出所有插件。"""
        return list(self._plugins.values())
    
    def list_names(self) -> List[str]:
        """列出所有插件名。"""
        return list(self._plugins.keys())
    
    def execute(self, name: str, args: Dict[str, Any]) -> PluginResult:
        """执行插件。"""
        plugin = self.get(name)
        if not plugin:
            return PluginResult(ok=False, error=f"Plugin not found: {name}")
        
        return self.executor.execute(plugin, args)
    
    def save_plugin(self, plugin: PluginDefinition, format: Literal["yaml", "json"] = "yaml") -> Path:
        """保存插件定义到文件。"""
        self.plugins_dir.mkdir(parents=True, exist_ok=True)
        
        filename = f"{plugin.name}.{format}"
        path = self.plugins_dir / filename
        
        data = plugin.model_dump(exclude_none=True)
        
        if format == "yaml":
            content = yaml.dump(data, default_flow_style=False, allow_unicode=True)
        else:
            content = json.dumps(data, indent=2, ensure_ascii=False)
        
        path.write_text(content, encoding="utf-8")
        self._plugins[plugin.name] = plugin
        
        return path
    
    def generate_tool_description(self, name: str) -> str | None:
        """生成供 LLM 使用的工具描述。"""
        plugin = self.get(name)
        if not plugin:
            return None
        
        desc = f"工具名: {plugin.name}\n描述: {plugin.description}\n"
        
        if plugin.params:
            desc += "参数:\n"
            for p in plugin.params:
                req = " (必需)" if p.required else ""
                default = f" (默认: {p.default})" if p.default is not None else ""
                desc += f"  - {p.name} ({p.type}){req}{default}: {p.description}\n"
        
        return desc
    
    def generate_all_tool_descriptions(self) -> str:
        """生成所有插件工具的描述（用于注入 system prompt）。"""
        if not self._plugins:
            return ""
        
        lines = ["=== 自定义插件工具 ==="]
        for name in sorted(self._plugins.keys()):
            desc = self.generate_tool_description(name)
            if desc:
                lines.append(desc)
        
        return "\n".join(lines)


# 导入 sys 用于 Python 插件执行
import sys

