"""
配置向导，帮助用户快速配置 clude-code
"""
from __future__ import annotations

import os
import platform
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

import typer
from rich.console import Console
from rich.prompt import Confirm, Prompt
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich import print as rprint

from ..config import CludeConfig, LLMConfig, RAGConfig, LimitsConfig
from ..observability.logger import get_logger

console = Console()


class ConfigWizard:
    """配置向导，帮助用户快速配置 clude-code"""
    
    def __init__(self, workspace_root: str = "."):
        self.workspace_root = workspace_root
        # 配置向导属于交互式流程：默认只输出到控制台，避免占用文件句柄影响临时目录清理
        self.logger = get_logger(__name__, log_to_console=True, workspace_root=None)
        self.config = self._load_user_config()
        self.detected_env = {}
        self.presets = {
            "本地开发": {
                "description": "适合本地开发环境，注重隐私保护",
                "config": {
                    "llm.provider": "llama_cpp_http",
                    "llm.base_url": "http://127.0.0.1:8899",
                    "llm.api_mode": "openai_compat",
                    "policy.allow_network": False,
                    "policy.confirm_write": True,
                    "policy.confirm_exec": True,
                    "rag.enabled": True,
                    "rag.device": "cpu",
                }
            },
            "高性能": {
                "description": "适合高性能环境，最大化处理能力",
                "config": {
                    # 与 LLMConfig.max_tokens 上限保持一致，避免触发配置校验失败
                    "llm.max_tokens": 409600,
                    "rag.device": "cuda" if platform.system() != "Darwin" else "mps",
                    "rag.embed_batch_size": 128,
                    "limits.max_file_read_bytes": 2_000_000,
                    "limits.max_output_bytes": 2_000_000,
                }
            },
            "资源受限": {
                "description": "适合资源受限环境，最小化资源使用",
                "config": {
                    "llm.max_tokens": 204800,
                    "rag.device": "cpu",
                    "rag.embed_batch_size": 32,
                    "rag.chunk_size": 300,
                    "limits.max_file_read_bytes": 500_000,
                    "limits.max_output_bytes": 500_000,
                }
            },
            "云端API": {
                "description": "使用云端API服务，适合没有本地GPU的环境",
                "config": {
                    "llm.provider": "openai",
                    "llm.base_url": "https://api.openai.com/v1",
                    "llm.api_mode": "openai_compat",
                    "policy.allow_network": True,
                    "policy.confirm_write": True,
                    "policy.confirm_exec": True,
                    "rag.enabled": True,
                    "rag.device": "cpu",
                }
            }
        }

    def _get_user_config_file(self) -> Path:
        """主配置文件位置：~/.clude/.clude.yaml"""
        return Path.home() / ".clude" / ".clude.yaml"

    def _load_user_config(self) -> CludeConfig:
        """从用户目录 ~/.clude/.clude.yaml 加载配置；不存在则返回默认配置。"""
        cfg_file = self._get_user_config_file()
        if cfg_file.exists():
            try:
                import yaml

                with open(cfg_file, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                # 确保工作区根目录一致（用户级配置也允许保存 workspace_root）
                if isinstance(data, dict) and self.workspace_root:
                    data.setdefault("workspace_root", str(Path(self.workspace_root)))
                return CludeConfig(**(data if isinstance(data, dict) else {}))
            except Exception as e:
                self.logger.warning("加载用户配置失败，将使用默认配置: %s", e, exc_info=True)
                return CludeConfig(workspace_root=self.workspace_root)

        # 纯代码默认值，不受 env / file 影响
        return CludeConfig.model_construct(workspace_root=self.workspace_root)
    
    def run_wizard(self) -> CludeConfig:
        """运行配置向导"""
        console.print("[bold blue]欢迎使用 clude-code 配置向导![/bold blue]")
        console.print("本向导将帮助您快速配置 clude-code，确保最佳使用体验。\n")
        
        # 检测系统环境
        self._detect_environment()
        
        # 选择预设
        preset = self._select_preset()
        
        # 应用预设
        self._apply_preset(preset)
        
        # 配置 LLM
        self._configure_llm()
        
        # 配置工作区
        self._configure_workspace()
        
        # 高级配置
        if Confirm.ask("是否进行高级配置?", default=False):
            self._configure_advanced()
        
        # 验证配置
        self._validate_config()
        
        # 保存配置
        self._save_config()
        
        console.print("\n[bold green]配置完成![/bold green]")
        console.print("您现在可以开始使用 clude-code 了。")
        
        return self.config
    
    def _detect_environment(self) -> None:
        """检测系统环境"""
        console.print("[bold]检测系统环境...[/bold]")
        
        # 系统信息
        system = platform.system()
        machine = platform.machine()
        python_version = platform.python_version()
        
        # 内存信息
        mem_gb = self._get_memory_info()
        
        # GPU 检测
        has_gpu, gpu_type, gpu_memory = self._detect_gpu()
        
        # 存储空间
        storage_info = self._get_storage_info()
        
        # 网络连接
        network_available = self._check_network_connectivity()
        
        # 保存检测结果
        self.detected_env = {
            "system": system,
            "machine": machine,
            "python_version": python_version,
            "memory_gb": mem_gb,
            "has_gpu": has_gpu,
            "gpu_type": gpu_type,
            "gpu_memory_gb": gpu_memory,
            "storage_info": storage_info,
            "network_available": network_available
        }
        
        # 显示检测结果
        env_table = Table(show_header=True, box=None)
        env_table.add_column("项目", style="bold")
        env_table.add_column("值")
        
        env_table.add_row("操作系统", f"{system} ({machine})")
        env_table.add_row("Python版本", python_version)
        env_table.add_row("内存", f"{mem_gb:.1f} GB")
        env_table.add_row("GPU", "是" if has_gpu else "否")
        if has_gpu and gpu_type:
            env_table.add_row("GPU 类型", gpu_type)
            if gpu_memory:
                env_table.add_row("GPU 内存", f"{gpu_memory:.1f} GB")
        env_table.add_row("存储空间", f"{storage_info['free']:.1f} GB 可用 / {storage_info['total']:.1f} GB 总计")
        env_table.add_row("网络连接", "是" if network_available else "否")
        
        console.print(Panel(env_table, title="环境检测结果"))
        
        # 根据环境调整默认配置
        if mem_gb < 8:
            console.print("[yellow]检测到内存较小，将使用资源受限配置。[/yellow]")
            self.config.limits.max_file_read_bytes = 500_000
            self.config.limits.max_output_bytes = 500_000
            self.config.rag.embed_batch_size = 32
        
        if has_gpu:
            console.print(f"[green]检测到 {gpu_type} GPU，将启用 GPU 加速。[/green]")
            self.config.rag.device = gpu_type
        
        if not network_available:
            console.print("[yellow]检测到无网络连接，将使用本地模式。[/yellow]")
            self.config.policy.allow_network = False
    
    def _get_memory_info(self) -> float:
        """获取内存信息（GB）"""
        try:
            if platform.system() == "Linux":
                with open('/proc/meminfo', 'r') as f:
                    for line in f:
                        if line.startswith('MemTotal:'):
                            mem_kb = int(line.split()[1])
                            return mem_kb / (1024 * 1024)
            elif platform.system() == "Darwin":  # macOS
                result = subprocess.run(['sysctl', 'hw.memsize'], capture_output=True, text=True)
                if result.returncode == 0:
                    mem_bytes = int(result.stdout.split()[1])
                    return mem_bytes / (1024 * 1024 * 1024)
            elif platform.system() == "Windows":
                import psutil
                mem_bytes = psutil.virtual_memory().total
                return mem_bytes / (1024 * 1024 * 1024)
            else:
                return 8.0  # 默认值
        except:
            return 8.0  # 默认值
    
    def _detect_gpu(self) -> Tuple[bool, Optional[str], Optional[float]]:
        """检测GPU信息"""
        has_gpu = False
        gpu_type = None
        gpu_memory = None
        
        try:
            if platform.system() == "Linux":
                # 检测NVIDIA GPU
                result = subprocess.run(['nvidia-smi', '--query-gpu=name,memory.total', '--format=csv,noheader,nounits'], 
                                      capture_output=True, text=True)
                if result.returncode == 0:
                    has_gpu = True
                    gpu_type = "cuda"
                    lines = result.stdout.strip().split('\n')
                    if lines and len(lines[0].split(',')) >= 2:
                        memory_mb = float(lines[0].split(',')[1].strip())
                        gpu_memory = memory_mb / 1024  # 转换为GB
            elif platform.system() == "Darwin":
                # macOS Apple Silicon
                machine = platform.machine()
                if machine in ("arm64", "arm64e"):
                    has_gpu = True
                    gpu_type = "mps"
                    # 尝试获取GPU内存
                    try:
                        result = subprocess.run(['system_profiler', 'SPHardwareDataType'], capture_output=True, text=True)
                        if result.returncode == 0:
                            for line in result.stdout.split('\n'):
                                if 'Memory:' in line:
                                    # 这是一个粗略估计，实际GPU内存可能不同
                                    gpu_memory = float(line.split(':')[1].strip().split()[0])
                                    break
                    except:
                        pass
            elif platform.system() == "Windows":
                # Windows GPU检测
                try:
                    import GPUtil
                    gpus = GPUtil.getGPUs()
                    if gpus:
                        has_gpu = True
                        gpu_type = "cuda"
                        gpu_memory = gpus[0].memoryTotal / 1024  # 转换为GB
                except ImportError:
                    # 如果没有GPUtil，尝试使用nvidia-smi
                    try:
                        result = subprocess.run(['nvidia-smi', '--query-gpu=name,memory.total', '--format=csv,noheader,nounits'], 
                                              capture_output=True, text=True)
                        if result.returncode == 0:
                            has_gpu = True
                            gpu_type = "cuda"
                            lines = result.stdout.strip().split('\n')
                            if lines and len(lines[0].split(',')) >= 2:
                                memory_mb = float(lines[0].split(',')[1].strip())
                                gpu_memory = memory_mb / 1024
                    except:
                        pass
        except:
            pass
        
        return has_gpu, gpu_type, gpu_memory
    
    def _get_storage_info(self) -> Dict[str, float]:
        """获取存储空间信息"""
        try:
            current_path = Path.cwd()
            stat = os.statvfs(current_path)
            total = stat.f_frsize * stat.f_blocks / (1024**3)  # GB
            free = stat.f_frsize * stat.f_bavail / (1024**3)  # GB
            return {"total": total, "free": free}
        except:
            return {"total": 0.0, "free": 0.0}
    
    def _check_network_connectivity(self) -> bool:
        """检查网络连接"""
        try:
            import socket
            socket.create_connection(("8.8.8.8", 53), timeout=3)
            return True
        except:
            return False
    
    def _select_preset(self) -> str:
        """选择配置预设"""
        console.print("\n[bold]选择配置预设:[/bold]")
        
        # 显示预设选项
        preset_table = Table(show_header=True, box=None)
        preset_table.add_column("序号", style="bold")
        preset_table.add_column("预设", style="bold")
        preset_table.add_column("描述")
        preset_table.add_column("推荐")
        
        for i, (name, info) in enumerate(self.presets.items(), 1):
            recommended = ""
            if name == "本地开发" and not self.detected_env.get("network_available", False):
                recommended = "[green]推荐[/green]"
            elif name == "云端API" and self.detected_env.get("network_available", False):
                recommended = "[green]推荐[/green]"
            elif name == "高性能" and self.detected_env.get("memory_gb", 0) > 16:
                recommended = "[green]推荐[/green]"
            elif name == "资源受限" and self.detected_env.get("memory_gb", 0) < 8:
                recommended = "[green]推荐[/green]"
            
            preset_table.add_row(str(i), name, info["description"], recommended)
        
        console.print(preset_table)
        
        while True:
            choice = Prompt.ask("请选择预设 (1-4)", default="1")
            if choice in ("1", "2", "3", "4"):
                preset_names = list(self.presets.keys())
                return preset_names[int(choice) - 1]
            console.print("[red]无效选择，请输入 1-4。[/red]")
    
    def _apply_preset(self, preset_name: str) -> None:
        """应用配置预设"""
        preset = self.presets[preset_name]
        console.print(f"\n[bold]应用预设: {preset_name}[/bold]")
        
        for key, value in preset["config"].items():
            # 解析嵌套键，如 "llm.provider" -> config.llm.provider
            parts = key.split('.')
            obj = self.config
            for part in parts[:-1]:
                obj = getattr(obj, part)
            setattr(obj, parts[-1], value)
        
        console.print(f"[green]已应用预设: {preset_name}[/green]")
    
    def _configure_llm(self) -> None:
        """配置 LLM"""
        console.print("\n[bold]配置 LLM:[/bold]")
        
        # 选择提供商
        providers = ["llama_cpp_http", "openai", "anthropic", "ollama"]
        console.print("可用 LLM 提供商:")
        for i, provider in enumerate(providers, 1):
            console.print(f"{i}. {provider}")
        
        while True:
            choice = Prompt.ask("选择 LLM 提供商 (1-4)", default="1")
            if choice in ("1", "2", "3", "4"):
                self.config.llm.provider = providers[int(choice) - 1]
                break
            console.print("[red]无效选择，请输入 1-4。[/red]")
        
        # 根据提供商配置不同参数
        if self.config.llm.provider == "llama_cpp_http":
            self._configure_llama_cpp()
        elif self.config.llm.provider == "openai":
            self._configure_openai()
        elif self.config.llm.provider == "anthropic":
            self._configure_anthropic()
        elif self.config.llm.provider == "ollama":
            self._configure_ollama()
        
        # 测试连接
        if Confirm.ask("测试 LLM 连接?", default=True):
            self._test_llm_connection()
    
    def _configure_llama_cpp(self) -> None:
        """配置 llama.cpp"""
        # 基础 URL
        current_url = self.config.llm.base_url
        new_url = Prompt.ask("llama.cpp 基础 URL", default=current_url)
        self.config.llm.base_url = new_url
        
        # 模型
        current_model = self.config.llm.model
        new_model = Prompt.ask("模型名称", default=current_model)
        self.config.llm.model = new_model
        
        # API 模式
        api_modes = ["openai_compat", "completion"]
        console.print("可用 API 模式:")
        for i, mode in enumerate(api_modes, 1):
            console.print(f"{i}. {mode}")
        
        while True:
            choice = Prompt.ask("选择 API 模式 (1-2)", default="1")
            if choice in ("1", "2"):
                self.config.llm.api_mode = api_modes[int(choice) - 1]
                break
            console.print("[red]无效选择，请输入 1-2。[/red]")
    
    def _configure_openai(self) -> None:
        """配置 OpenAI"""
        # API 密钥
        api_key = Prompt.ask("OpenAI API 密钥", password=True)
        os.environ["OPENAI_API_KEY"] = api_key
        
        # 基础 URL
        current_url = self.config.llm.base_url
        new_url = Prompt.ask("OpenAI API 基础 URL", default=current_url)
        self.config.llm.base_url = new_url
        
        # 模型
        models = ["gpt-4", "gpt-4-turbo", "gpt-3.5-turbo"]
        console.print("可用模型:")
        for i, model in enumerate(models, 1):
            console.print(f"{i}. {model}")
        
        while True:
            choice = Prompt.ask("选择模型 (1-3)", default="1")
            if choice in ("1", "2", "3"):
                self.config.llm.model = models[int(choice) - 1]
                break
            console.print("[red]无效选择，请输入 1-3。[/red]")
    
    def _configure_anthropic(self) -> None:
        """配置 Anthropic"""
        # API 密钥
        api_key = Prompt.ask("Anthropic API 密钥", password=True)
        os.environ["ANTHROPIC_API_KEY"] = api_key
        
        # 基础 URL
        current_url = self.config.llm.base_url
        new_url = Prompt.ask("Anthropic API 基础 URL", default=current_url)
        self.config.llm.base_url = new_url
        
        # 模型
        models = ["claude-3-opus-20240229", "claude-3-sonnet-20240229", "claude-3-haiku-20240307"]
        console.print("可用模型:")
        for i, model in enumerate(models, 1):
            console.print(f"{i}. {model}")
        
        while True:
            choice = Prompt.ask("选择模型 (1-3)", default="2")
            if choice in ("1", "2", "3"):
                self.config.llm.model = models[int(choice) - 1]
                break
            console.print("[red]无效选择，请输入 1-3。[/red]")
    
    def _configure_ollama(self) -> None:
        """配置 Ollama"""
        # 基础 URL
        current_url = self.config.llm.base_url
        new_url = Prompt.ask("Ollama 基础 URL", default=current_url)
        self.config.llm.base_url = new_url
        
        # 模型
        models = ["llama2", "codellama", "mistral", "vicuna"]
        console.print("可用模型:")
        for i, model in enumerate(models, 1):
            console.print(f"{i}. {model}")
        
        while True:
            choice = Prompt.ask("选择模型 (1-4)", default="1")
            if choice in ("1", "2", "3", "4"):
                self.config.llm.model = models[int(choice) - 1]
                break
            console.print("[red]无效选择，请输入 1-4。[/red]")
    
    def _configure_workspace(self) -> None:
        """配置工作区"""
        console.print("\n[bold]配置工作区:[/bold]")
        
        # 工作区路径
        current_path = self.config.workspace_root
        new_path = Prompt.ask("工作区路径", default=current_path)
        self.config.workspace_root = new_path
        
        # 确认工作区可访问
        workspace_path = Path(new_path)
        if not workspace_path.exists():
            console.print(f"[red]路径不存在: {new_path}[/red]")
            if Confirm.ask("创建工作区目录?", default=True):
                workspace_path.mkdir(parents=True, exist_ok=True)
                console.print(f"[green]已创建: {new_path}[/green]")
            else:
                console.print("[yellow]请确保工作区路径存在。[/yellow]")
    
    def _configure_advanced(self) -> None:
        """高级配置"""
        console.print("\n[bold]高级配置:[/bold]")
        
        # RAG 配置
        if Confirm.ask("配置 RAG (检索增强生成)?", default=True):
            self._configure_rag()
        
        # 策略配置
        if Confirm.ask("配置安全策略?", default=True):
            self._configure_policy()
        
        # 性能配置
        if Confirm.ask("配置性能限制?", default=True):
            self._configure_limits()
    
    def _configure_rag(self) -> None:
        """配置 RAG"""
        console.print("\n[bold]RAG 配置:[/bold]")
        
        # 启用/禁用
        enabled = Confirm.ask("启用 RAG?", default=self.config.rag.enabled)
        self.config.rag.enabled = enabled
        
        if enabled:
            # 设备
            devices = ["cpu", "cuda", "mps"]
            console.print("可用设备:")
            for i, device in enumerate(devices, 1):
                console.print(f"{i}. {device}")
            
            while True:
                choice = Prompt.ask("选择设备 (1-3)", default="1")
                if choice in ("1", "2", "3"):
                    self.config.rag.device = devices[int(choice) - 1]
                    break
                console.print("[red]无效选择，请输入 1-3。[/red]")
            
            # 嵌入模型
            models = ["BAAI/bge-small-zh-v1.5", "BAAI/bge-base-zh-v1.5", "BAAI/bge-large-zh-v1.5"]
            console.print("可用嵌入模型:")
            for i, model in enumerate(models, 1):
                console.print(f"{i}. {model}")
            
            while True:
                choice = Prompt.ask("选择嵌入模型 (1-3)", default="1")
                if choice in ("1", "2", "3"):
                    self.config.rag.embedding_model = models[int(choice) - 1]
                    break
                console.print("[red]无效选择，请输入 1-3。[/red]")
            
            # 分块大小
            chunk_size = Prompt.ask("代码分块大小 (字符)", default=str(self.config.rag.chunk_size))
            self.config.rag.chunk_size = int(chunk_size)
    
    def _configure_policy(self) -> None:
        """配置安全策略"""
        console.print("\n[bold]安全策略配置:[/bold]")
        
        # 网络访问
        allow_network = Confirm.ask("允许网络访问?", default=self.config.policy.allow_network)
        self.config.policy.allow_network = allow_network
        
        # 写入确认
        confirm_write = Confirm.ask("写入文件前确认?", default=self.config.policy.confirm_write)
        self.config.policy.confirm_write = confirm_write
        
        # 执行确认
        confirm_exec = Confirm.ask("执行命令前确认?", default=self.config.policy.confirm_exec)
        self.config.policy.confirm_exec = confirm_exec
    
    def _configure_limits(self) -> None:
        """配置性能限制"""
        console.print("\n[bold]性能限制配置:[/bold]")
        
        # 最大文件读取大小
        max_file_read = Prompt.ask(
            "最大文件读取大小 (字节)", 
            default=str(self.config.limits.max_file_read_bytes)
        )
        self.config.limits.max_file_read_bytes = int(max_file_read)
        
        # 最大输出大小
        max_output = Prompt.ask(
            "最大输出大小 (字节)", 
            default=str(self.config.limits.max_output_bytes)
        )
        self.config.limits.max_output_bytes = int(max_output)
        
        # 最大 token 数
        max_tokens = Prompt.ask(
            "LLM 最大 token 数", 
            default=str(self.config.llm.max_tokens)
        )
        self.config.llm.max_tokens = int(max_tokens)
    
    def _validate_config(self) -> None:
        """验证配置"""
        console.print("\n[bold]验证配置...[/bold]")
        
        errors = []
        warnings = []
        
        # 验证工作区
        workspace_path = Path(self.config.workspace_root)
        if not workspace_path.exists():
            errors.append("工作区路径不存在")
        elif not workspace_path.is_dir():
            errors.append("工作区路径不是目录")
        
        # 验证 LLM 配置
        if not self.config.llm.base_url:
            errors.append("LLM 基础 URL 未设置")
        
        if not self.config.llm.model:
            errors.append("LLM 模型未设置")
        
        # 验证 RAG 配置
        if self.config.rag.enabled:
            rag_db_path = Path(self.config.rag.db_path)
            if not rag_db_path.parent.exists():
                try:
                    rag_db_path.parent.mkdir(parents=True, exist_ok=True)
                except Exception as e:
                    errors.append(f"无法创建 RAG 数据库目录: {e}")
            
            # 检查设备兼容性
            if self.config.rag.device == "cuda" and not self.detected_env.get("has_gpu", False):
                warnings.append("选择了 CUDA 设备但未检测到 GPU")
            
            if self.config.rag.device == "mps" and platform.system() != "Darwin":
                warnings.append("MPS 设备仅在 macOS 上可用")
        
        # 显示验证结果
        if errors:
            console.print("[red]配置验证失败:[/red]")
            for error in errors:
                console.print(f"- {error}")
            
            if not Confirm.ask("是否继续保存配置?", default=False):
                raise typer.Abort()
        
        if warnings:
            console.print("[yellow]配置警告:[/yellow]")
            for warning in warnings:
                console.print(f"- {warning}")
        
        if not errors and not warnings:
            console.print("[green]配置验证通过![/green]")
    
    def _save_config(self, generate_shell_config: bool = True) -> None:
        """保存配置

        Args:
            generate_shell_config: 是否生成shell配置脚本（用于自动化时设为False）
        """
        console.print("\n[bold]保存配置...[/bold]")

        # 创建配置目录（用户目录）
        config_dir = Path.home() / ".clude"
        config_dir.mkdir(parents=True, exist_ok=True)

        # 保存配置文件
        config_file = config_dir / ".clude.yaml"

        # 转换为字典并保存
        from .config import _render_commented_yaml
        config_dict = self.config.model_dump()

        # 统一 YAML 保存（项目规范：不再使用 JSON 配置）
        import yaml

        # 保留中文注释：使用模板渲染输出
        config_file.write_text(_render_commented_yaml(config_dict), encoding="utf-8")
        console.print(f"[green]配置已保存到: {config_file}[/green]")

        # 显示环境变量设置提示
        console.print("\n[bold]环境变量设置:[/bold]")
        console.print("您也可以通过以下环境变量覆盖配置:")
        console.print("- CLUDE_WORKSPACE_ROOT: 工作区路径")
        console.print("- CLUDE_LLM__BASE_URL: LLM 基础 URL")
        console.print("- CLUDE_LLM__MODEL: LLM 模型")
        console.print("- CLUDE_LLM__API_MODE: LLM API 模式")
        console.print("- CLUDE_POLICY__ALLOW_NETWORK: 允许网络访问")
        console.print("- CLUDE_RAG__ENABLED: 启用 RAG")
        console.print("- CLUDE_RAG__DEVICE: RAG 设备")

        # 生成 shell 配置（如果启用且是交互式环境）
        if generate_shell_config:
            try:
                if Confirm.ask("生成 shell 配置脚本?", default=True):
                    self._generate_shell_config(config_dir)
            except EOFError:
                # 非交互式环境，跳过shell配置生成
                console.print("[dim]跳过shell配置生成（非交互式环境）[/dim]")
    
    def _generate_shell_config(self, config_dir: Path) -> None:
        """生成 shell 配置脚本"""
        # 生成 bash 配置
        bash_config = config_dir / "clude_env.sh"
        with open(bash_config, 'w') as f:
            f.write(f"# clude-code 环境配置\n")
            f.write(f"export CLUDE_WORKSPACE_ROOT=\"{self.config.workspace_root}\"\n")
            f.write(f"export CLUDE_LLM__BASE_URL=\"{self.config.llm.base_url}\"\n")
            f.write(f"export CLUDE_LLM__MODEL=\"{self.config.llm.model}\"\n")
            f.write(f"export CLUDE_LLM__API_MODE=\"{self.config.llm.api_mode}\"\n")
            f.write(f"export CLUDE_POLICY__ALLOW_NETWORK=\"{self.config.policy.allow_network}\"\n")
            f.write(f"export CLUDE_RAG__ENABLED=\"{self.config.rag.enabled}\"\n")
            f.write(f"export CLUDE_RAG__DEVICE=\"{self.config.rag.device}\"\n")
        
        # 生成 PowerShell 配置
        ps_config = config_dir / "clude_env.ps1"
        with open(ps_config, 'w') as f:
            f.write(f"# clude-code 环境配置\n")
            f.write(f"$env:CLUDE_WORKSPACE_ROOT=\"{self.config.workspace_root}\"\n")
            f.write(f"$env:CLUDE_LLM__BASE_URL=\"{self.config.llm.base_url}\"\n")
            f.write(f"$env:CLUDE_LLM__MODEL=\"{self.config.llm.model}\"\n")
            f.write(f"$env:CLUDE_LLM__API_MODE=\"{self.config.llm.api_mode}\"\n")
            f.write(f"$env:CLUDE_POLICY__ALLOW_NETWORK=\"{self.config.policy.allow_network}\"\n")
            f.write(f"$env:CLUDE_RAG__ENABLED=\"{self.config.rag.enabled}\"\n")
            f.write(f"$env:CLUDE_RAG__DEVICE=\"{self.config.rag.device}\"\n")
        
        console.print(f"[green]已生成 shell 配置脚本:[/green]")
        console.print(f"- Bash: {bash_config}")
        console.print(f"- PowerShell: {ps_config}")
        console.print("\n使用方法:")
        console.print("- Bash: source ~/.clude/clude_env.sh")
        console.print("- PowerShell: . ~/.clude/clude_env.ps1")
    
    def _test_llm_connection(self) -> None:
        """测试 LLM 连接"""
        console.print("[bold]测试 LLM 连接...[/bold]")
        
        try:
            # 根据不同的提供商使用不同的测试方法
            if self.config.llm.provider == "llama_cpp_http":
                self._test_llama_cpp_connection()
            elif self.config.llm.provider == "openai":
                self._test_openai_connection()
            elif self.config.llm.provider == "anthropic":
                self._test_anthropic_connection()
            elif self.config.llm.provider == "ollama":
                self._test_ollama_connection()
        except Exception as e:
            console.print(f"[red]LLM 连接测试失败: {e}[/red]")
            console.print("[yellow]请检查 LLM 服务是否正在运行，以及配置是否正确。[/yellow]")
    
    def _test_llama_cpp_connection(self) -> None:
        """测试 llama.cpp 连接"""
        from clude_code.llm.llama_cpp_http import LlamaCppHttpClient, ChatMessage
        
        client = LlamaCppHttpClient(
            base_url=self.config.llm.base_url,
            api_mode=self.config.llm.api_mode,
            model=self.config.llm.model,
            temperature=0.0,
            max_tokens=10,
            timeout_s=10,
        )
        
        response = client.chat([
            ChatMessage(role="system", content="你是测试助手，只回复 OK。"),
            ChatMessage(role="user", content="测试"),
        ])
        
        console.print(f"[green]llama.cpp 连接成功! 响应: {response}[/green]")
    
    def _test_openai_connection(self) -> None:
        """测试 OpenAI 连接"""
        import openai
        
        client = openai.OpenAI(
            base_url=self.config.llm.base_url,
            api_key=os.environ.get("OPENAI_API_KEY", "sk-HWtp4KMBc3NNFt9WMOLEIKCSeMB1sEsXBZxc9TzqPdX1uUOy")
        )
        
        response = client.chat.completions.create(
            model=self.config.llm.model,
            messages=[
                {"role": "system", "content": "你是测试助手，只回复 OK。"},
                {"role": "user", "content": "测试"}
            ],
            max_tokens=10,
            temperature=0.0
        )
        
        console.print(f"[green]OpenAI 连接成功! 响应: {response.choices[0].message.content}[/green]")
    
    def _test_anthropic_connection(self) -> None:
        """测试 Anthropic 连接"""
        import anthropic
        
        client = anthropic.Anthropic(
            api_key=os.environ.get("ANTHROPIC_API_KEY"),
            base_url=self.config.llm.base_url
        )
        
        response = client.messages.create(
            model=self.config.llm.model,
            max_tokens=10,
            temperature=0.0,
            messages=[
                {"role": "user", "content": "你是测试助手，只回复 OK。测试"}
            ]
        )
        
        console.print(f"[green]Anthropic 连接成功! 响应: {response.content[0].text}[/green]")
    
    def _test_ollama_connection(self) -> None:
        """测试 Ollama 连接"""
        import requests
        
        response = requests.post(
            f"{self.config.llm.base_url}/api/generate",
            json={
                "model": self.config.llm.model,
                "prompt": "你是测试助手，只回复 OK。测试",
                "stream": False
            },
            timeout=10
        )
        
        if response.status_code == 200:
            result = response.json()
            console.print(f"[green]Ollama 连接成功! 响应: {result.get('response', '')}[/green]")
        else:
            raise Exception(f"HTTP {response.status_code}: {response.text}")


def run_config_wizard(workspace_root: str = ".") -> CludeConfig:
    """运行配置向导"""
    wizard = ConfigWizard(workspace_root)
    return wizard.run_wizard()