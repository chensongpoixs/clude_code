"""
扩展工具集 - 集成 LSP 和插件能力

将 LSP 符号查询和插件执行封装为标准 ToolResult 格式，
供 AgentLoop 统一调度。
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from clude_code.tooling.local_tools import ToolResult
from clude_code.lsp.client import LSPManager, LSPLocation, LSPSymbol
from clude_code.plugins.registry import PluginRegistry, PluginResult


class ExtendedTools:
    """
    扩展工具集，封装 LSP 和插件能力。
    
    提供的工具：
    - lsp_go_to_definition: 跳转到定义
    - lsp_find_references: 查找引用
    - lsp_get_symbols: 获取文档符号
    - lsp_search_symbols: 搜索工作区符号
    - plugin_execute: 执行插件
    - plugin_list: 列出可用插件
    """
    
    def __init__(self, workspace_root: Path, lsp_timeout_s: int = 30):
        self.workspace_root = workspace_root.resolve()
        self._lsp_manager: LSPManager | None = None
        self._plugin_registry: PluginRegistry | None = None
        self._lsp_timeout_s = lsp_timeout_s
    
    @property
    def lsp(self) -> LSPManager:
        """懒加载 LSP 管理器。"""
        if self._lsp_manager is None:
            self._lsp_manager = LSPManager(self.workspace_root, timeout_s=self._lsp_timeout_s)
        return self._lsp_manager
    
    @property
    def plugins(self) -> PluginRegistry:
        """懒加载插件注册表。"""
        if self._plugin_registry is None:
            self._plugin_registry = PluginRegistry(self.workspace_root)
        return self._plugin_registry
    
    def _location_to_dict(self, loc: LSPLocation) -> Dict[str, Any]:
        """将 LSPLocation 转换为字典。"""
        # 从 URI 提取相对路径
        uri = loc.uri
        if uri.startswith("file://"):
            path = uri[7:]
            # Windows 路径处理
            if path.startswith("/") and len(path) > 2 and path[2] == ":":
                path = path[1:]
            try:
                rel_path = str(Path(path).relative_to(self.workspace_root))
            except ValueError:
                rel_path = path
        else:
            rel_path = uri
        
        return {
            "path": rel_path,
            "start_line": loc.start_line + 1,  # 转为 1-based
            "start_char": loc.start_char,
            "end_line": loc.end_line + 1,
            "end_char": loc.end_char,
        }
    
    def _symbol_to_dict(self, sym: LSPSymbol) -> Dict[str, Any]:
        """将 LSPSymbol 转换为字典。"""
        return {
            "name": sym.name,
            "kind": self._symbol_kind_name(sym.kind),
            "location": self._location_to_dict(sym.location),
            "container": sym.container_name,
        }
    
    def _symbol_kind_name(self, kind: int) -> str:
        """将 SymbolKind 数字转换为名称。"""
        kinds = {
            1: "File", 2: "Module", 3: "Namespace", 4: "Package",
            5: "Class", 6: "Method", 7: "Property", 8: "Field",
            9: "Constructor", 10: "Enum", 11: "Interface", 12: "Function",
            13: "Variable", 14: "Constant", 15: "String", 16: "Number",
            17: "Boolean", 18: "Array", 19: "Object", 20: "Key",
            21: "Null", 22: "EnumMember", 23: "Struct", 24: "Event",
            25: "Operator", 26: "TypeParameter",
        }
        return kinds.get(kind, f"Unknown({kind})")
    
    # ==================== LSP 工具 ====================
    
    def lsp_go_to_definition(
        self,
        path: str,
        line: int,
        character: int,
    ) -> ToolResult:
        """
        跳转到定义。
        
        参数：
            path: 文件路径（相对于 workspace）
            line: 行号（1-based）
            character: 列号（0-based）
        
        返回：
            定义位置列表
        """
        try:
            locations = self.lsp.go_to_definition(path, line - 1, character)
            
            if not locations:
                return ToolResult(
                    ok=True,
                    payload={"path": path, "line": line, "character": character, "definitions": [], "message": "未找到定义"},
                )
            
            return ToolResult(
                ok=True,
                payload={
                    "path": path,
                    "line": line,
                    "character": character,
                    "definitions": [self._location_to_dict(loc) for loc in locations],
                },
            )
            
        except Exception as e:
            return ToolResult(
                ok=False,
                error={"code": "E_LSP", "message": f"LSP 错误: {str(e)}"},
            )
    
    def lsp_find_references(
        self,
        path: str,
        line: int,
        character: int,
        include_declaration: bool = True,
    ) -> ToolResult:
        """
        查找所有引用。
        
        参数：
            path: 文件路径（相对于 workspace）
            line: 行号（1-based）
            character: 列号（0-based）
            include_declaration: 是否包含声明
        
        返回：
            引用位置列表
        """
        try:
            locations = self.lsp.find_references(path, line - 1, character)
            
            return ToolResult(
                ok=True,
                payload={
                    "path": path,
                    "line": line,
                    "character": character,
                    "references": [self._location_to_dict(loc) for loc in locations],
                    "count": len(locations),
                },
            )
            
        except Exception as e:
            return ToolResult(
                ok=False,
                error={"code": "E_LSP", "message": f"LSP 错误: {str(e)}"},
            )
    
    def lsp_get_symbols(self, path: str) -> ToolResult:
        """
        获取文档中的所有符号。
        
        参数：
            path: 文件路径（相对于 workspace）
        
        返回：
            符号列表（函数、类、变量等）
        """
        try:
            symbols = self.lsp.get_symbols(path)
            
            return ToolResult(
                ok=True,
                payload={
                    "path": path,
                    "symbols": [self._symbol_to_dict(sym) for sym in symbols],
                    "count": len(symbols),
                },
            )
            
        except Exception as e:
            return ToolResult(
                ok=False,
                error={"code": "E_LSP", "message": f"LSP 错误: {str(e)}"},
            )
    
    def lsp_search_symbols(self, query: str, language: str | None = None) -> ToolResult:
        """
        搜索工作区符号。
        
        参数：
            query: 搜索关键词
            language: 限制语言（可选）
        
        返回：
            匹配的符号列表
        """
        try:
            symbols = self.lsp.search_symbols(query, language)
            
            return ToolResult(
                ok=True,
                payload={
                    "query": query,
                    "language": language,
                    "symbols": [self._symbol_to_dict(sym) for sym in symbols],
                    "count": len(symbols),
                },
            )
            
        except Exception as e:
            return ToolResult(
                ok=False,
                error={"code": "E_LSP", "message": f"LSP 错误: {str(e)}"},
            )
    
    # ==================== 插件工具 ====================
    
    def plugin_list(self) -> ToolResult:
        """列出所有可用插件。"""
        plugins = self.plugins.list_all()
        
        return ToolResult(
            ok=True,
            payload={
                "plugins": [
                    {
                        "name": p.name,
                        "type": p.type.value,
                        "description": p.description,
                        "version": p.version,
                        "params": [
                            {
                                "name": param.name,
                                "type": param.type,
                                "required": param.required,
                                "description": param.description,
                            }
                            for param in p.params
                        ],
                    }
                    for p in plugins
                ],
                "count": len(plugins),
            },
        )
    
    def plugin_execute(self, name: str, args: Dict[str, Any] | None = None) -> ToolResult:
        """
        执行插件。
        
        参数：
            name: 插件名
            args: 插件参数
        
        返回：
            插件执行结果
        """
        result = self.plugins.execute(name, args or {})
        
        if result.ok:
            return ToolResult(
                ok=True,
                payload={
                    "plugin": name,
                    "output": result.output,
                    "exit_code": result.exit_code,
                    "duration_ms": result.duration_ms,
                },
            )
        else:
            return ToolResult(
                ok=False,
                error={
                    "code": "E_PLUGIN",
                    "message": result.error,
                    "plugin": name,
                    "exit_code": result.exit_code,
                },
            )
    
    def cleanup(self) -> None:
        """清理资源（停止 LSP 服务器等）。"""
        if self._lsp_manager:
            self._lsp_manager.stop_all()


# 工具描述（供 System Prompt 使用）
EXTENDED_TOOLS_DESCRIPTION = """
=== 扩展工具（LSP + 插件）===

LSP 工具（需要对应语言服务器）：
- lsp_go_to_definition: {"path": "...", "line": 10, "character": 5}
  跳转到符号定义位置
  
- lsp_find_references: {"path": "...", "line": 10, "character": 5}
  查找符号的所有引用
  
- lsp_get_symbols: {"path": "..."}
  获取文件中的所有符号（函数、类、变量等）
  
- lsp_search_symbols: {"query": "MyClass"}
  在整个工作区搜索符号

插件工具：
- plugin_list: {}
  列出所有可用插件
  
- plugin_execute: {"name": "plugin_name", "args": {...}}
  执行指定插件
"""

