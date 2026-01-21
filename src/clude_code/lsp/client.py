"""
LSP (Language Server Protocol) 客户端适配器

业界对比：
- Cursor: 内置多语言 LSP 支持
- Continue.dev: 通过 IDE 代理 LSP
- Aider: 不支持 LSP（纯文本分析）

本实现：通用 LSP 客户端，支持多语言服务器
"""
from __future__ import annotations

import json
import subprocess
import threading
import queue
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Literal
from enum import Enum

from pydantic import BaseModel, Field

"""LSP 服务器配置。"""
class LSPServerConfig(BaseModel):
    
    language: str = Field(..., description="语言标识（python/typescript/go/rust）")
    command: List[str] = Field(..., description="启动命令（如 ['pylsp'] 或 ['typescript-language-server', '--stdio']）")
    root_uri: Optional[str] = Field(None, description="工作区根目录 URI")
    initialization_options: Dict[str, Any] = Field(default_factory=dict, description="初始化选项")

"""LSP 能力枚举。"""
class LSPCapability(str, Enum):
    
    GO_TO_DEFINITION = "textDocument/definition"
    FIND_REFERENCES = "textDocument/references"
    HOVER = "textDocument/hover"
    COMPLETION = "textDocument/completion"
    DOCUMENT_SYMBOLS = "textDocument/documentSymbol"
    WORKSPACE_SYMBOLS = "workspace/symbol"
    RENAME = "textDocument/rename"
    DIAGNOSTICS = "textDocument/publishDiagnostics"

"""LSP 位置信息。"""
@dataclass
class LSPLocation:
    uri: str
    start_line: int
    start_char: int
    end_line: int
    end_char: int
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "uri": self.uri,
            "range": {
                "start": {"line": self.start_line, "character": self.start_char},
                "end": {"line": self.end_line, "character": self.end_char}
            }
        }


@dataclass
class LSPSymbol:
    """LSP 符号信息。"""
    name: str
    kind: int  # SymbolKind
    location: LSPLocation
    container_name: Optional[str] = None


@dataclass
class LSPDiagnostic:
    """LSP 诊断信息（错误/警告）。"""
    uri: str
    line: int
    character: int
    message: str
    severity: int = 1  # 1=Error, 2=Warning, 3=Info, 4=Hint
    source: Optional[str] = None
    code: Optional[str] = None


"""
通用 LSP 客户端。

支持的操作：
- go_to_definition: 跳转到定义
- find_references: 查找引用
- get_document_symbols: 获取文档符号
- get_workspace_symbols: 搜索工作区符号
- get_hover: 获取悬停信息
- get_diagnostics: 获取诊断信息

业界最佳实践：
- 使用 stdio 通信（最稳定）
- 异步消息处理（防阻塞）
- 超时保护（防止服务器卡死）
"""
class LSPClient:

    
    # 常用语言服务器命令映射
    DEFAULT_SERVERS: Dict[str, List[str]] = {
        "python": ["pylsp"],
        "typescript": ["typescript-language-server", "--stdio"],
        "javascript": ["typescript-language-server", "--stdio"],
        "go": ["gopls", "serve"],
        "rust": ["rust-analyzer"],
        "c": ["clangd"],
        "cpp": ["clangd"],
    }
    
    def __init__(
        self,
        workspace_root: Path,
        language: str,
        command: List[str] | None = None,
        timeout_s: int = 30,
    ):
        self.workspace_root = workspace_root.resolve()
        self.language = language.lower()
        self.command = command or self.DEFAULT_SERVERS.get(self.language, [])
        self.timeout_s = timeout_s
        
        self._process: subprocess.Popen | None = None
        self._request_id = 0
        self._response_queue: queue.Queue[Dict[str, Any]] = queue.Queue()
        self._notification_queue: queue.Queue[Dict[str, Any]] = queue.Queue()
        self._reader_thread: threading.Thread | None = None
        self._initialized = False
        self._server_capabilities: Dict[str, Any] = {}
        self._diagnostics: Dict[str, List[LSPDiagnostic]] = {}  # uri -> diagnostics
        
    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id
    
    def _send(self, message: Dict[str, Any]) -> None:
        """发送 LSP 消息（JSON-RPC over stdio）。"""
        if self._process is None or self._process.stdin is None:
            raise RuntimeError("LSP server not started")
        
        content = json.dumps(message)
        header = f"Content-Length: {len(content)}\r\n\r\n"
        self._process.stdin.write(header.encode("utf-8"))
        self._process.stdin.write(content.encode("utf-8"))
        self._process.stdin.flush()
    """读取一条 LSP 消息。"""
    def _read_message(self) -> Dict[str, Any] | None:
        
        if self._process is None or self._process.stdout is None:
            return None
        
        # Read headers
        headers: Dict[str, str] = {}
        while True:
            line = self._process.stdout.readline()
            if not line:
                return None
            line_str = line.decode("utf-8").strip()
            if not line_str:
                break
            if ":" in line_str:
                key, value = line_str.split(":", 1)
                headers[key.strip()] = value.strip()
        
        content_length = int(headers.get("Content-Length", 0))
        if content_length == 0:
            return None
        
        content = self._process.stdout.read(content_length)
        return json.loads(content.decode("utf-8"))
    
    def _reader_loop(self) -> None:
        """后台线程：持续读取服务器消息。"""
        while self._process is not None and self._process.poll() is None:
            try:
                msg = self._read_message()
                if msg is None:
                    continue
                
                # 区分响应和通知
                if "id" in msg:
                    self._response_queue.put(msg)
                else:
                    # 处理服务器通知（如诊断信息）
                    method = msg.get("method", "")
                    if method == "textDocument/publishDiagnostics":
                        self._handle_diagnostics(msg.get("params", {}))
                    self._notification_queue.put(msg)
            except Exception:
                continue
    
    def _handle_diagnostics(self, params: Dict[str, Any]) -> None:
        """处理诊断信息推送。"""
        uri = params.get("uri", "")
        diagnostics = params.get("diagnostics", [])
        self._diagnostics[uri] = [
            LSPDiagnostic(
                uri=uri,
                line=d.get("range", {}).get("start", {}).get("line", 0),
                character=d.get("range", {}).get("start", {}).get("character", 0),
                message=d.get("message", ""),
                severity=d.get("severity", 1),
                source=d.get("source"),
                code=str(d.get("code")) if d.get("code") else None,
            )
            for d in diagnostics
        ]
    
    def _wait_response(self, request_id: int) -> Dict[str, Any]:
        """等待指定 ID 的响应。"""
        try:
            while True:
                msg = self._response_queue.get(timeout=self.timeout_s)
                if msg.get("id") == request_id:
                    return msg
                # 其他响应放回队列（不太可能发生）
        except queue.Empty:
            raise TimeoutError(f"LSP request {request_id} timed out after {self.timeout_s}s")
    
    def _request(self, method: str, params: Dict[str, Any]) -> Any:
        """发送请求并等待响应。"""
        request_id = self._next_id()
        message = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params,
        }
        self._send(message)
        response = self._wait_response(request_id)
        
        if "error" in response:
            error = response["error"]
            raise RuntimeError(f"LSP error [{error.get('code')}]: {error.get('message')}")
        
        return response.get("result")
    """发送通知（无需响应）。"""
    def _notify(self, method: str, params: Dict[str, Any]) -> None:
        
        message = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
        }
        self._send(message)
    """启动 LSP 服务器。"""
    def start(self) -> bool:
        
        if not self.command:
            return False
        
        try:
            self._process = subprocess.Popen(
                self.command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=self.workspace_root,
            )
            
            # 启动读取线程
            self._reader_thread = threading.Thread(target=self._reader_loop, daemon=True)
            self._reader_thread.start()
            
            # 发送 initialize 请求
            init_result = self._request("initialize", {
                "processId": os.getpid(),
                "rootUri": self.workspace_root.as_uri(),
                "rootPath": str(self.workspace_root),
                "capabilities": {
                    "textDocument": {
                        "definition": {"dynamicRegistration": False},
                        "references": {"dynamicRegistration": False},
                        "hover": {"contentFormat": ["markdown", "plaintext"]},
                        "documentSymbol": {"dynamicRegistration": False},
                        "publishDiagnostics": {"relatedInformation": True},
                    },
                    "workspace": {
                        "symbol": {"dynamicRegistration": False},
                    },
                },
                "initializationOptions": {},
            })
            
            self._server_capabilities = init_result.get("capabilities", {})
            
            # 发送 initialized 通知
            self._notify("initialized", {})
            
            self._initialized = True
            return True
            
        except FileNotFoundError:
            return False
        except Exception:
            self.stop()
            return False
    """停止 LSP 服务器。"""
    def stop(self) -> None:
        
        if self._process is not None:
            try:
                self._request("shutdown", {})
                self._notify("exit", {})
            except Exception:
                pass
            finally:
                self._process.terminate()
                self._process = None
                self._initialized = False

    """检查服务器是否就绪。"""
    def is_ready(self) -> bool:
        
        return self._initialized and self._process is not None and self._process.poll() is None
    """将文件路径转换为 URI。"""
    def _uri_for_path(self, path: str) -> str:
        
        p = (self.workspace_root / path).resolve()
        return p.as_uri()
    """通知服务器打开文档。"""
    def open_document(self, path: str, text: str, language_id: str | None = None) -> None:
        
        self._notify("textDocument/didOpen", {
            "textDocument": {
                "uri": self._uri_for_path(path),
                "languageId": language_id or self.language,
                "version": 1,
                "text": text,
            }
        })
    """通知服务器关闭文档。"""
    def close_document(self, path: str) -> None:
        
        self._notify("textDocument/didClose", {
            "textDocument": {"uri": self._uri_for_path(path)}
        })
    
    def go_to_definition(self, path: str, line: int, character: int) -> List[LSPLocation]:
        """跳转到定义（核心功能）。"""
        result = self._request("textDocument/definition", {
            "textDocument": {"uri": self._uri_for_path(path)},
            "position": {"line": line, "character": character},
        })
        
        if result is None:
            return []
        
        # 结果可能是单个 Location 或 Location[]
        locations = result if isinstance(result, list) else [result]
        return [
            LSPLocation(
                uri=loc.get("uri", ""),
                start_line=loc.get("range", {}).get("start", {}).get("line", 0),
                start_char=loc.get("range", {}).get("start", {}).get("character", 0),
                end_line=loc.get("range", {}).get("end", {}).get("line", 0),
                end_char=loc.get("range", {}).get("end", {}).get("character", 0),
            )
            for loc in locations if loc
        ]
    
    def find_references(self, path: str, line: int, character: int, include_declaration: bool = True) -> List[LSPLocation]:
        """查找所有引用。"""
        result = self._request("textDocument/references", {
            "textDocument": {"uri": self._uri_for_path(path)},
            "position": {"line": line, "character": character},
            "context": {"includeDeclaration": include_declaration},
        })
        
        if result is None:
            return []
        
        return [
            LSPLocation(
                uri=loc.get("uri", ""),
                start_line=loc.get("range", {}).get("start", {}).get("line", 0),
                start_char=loc.get("range", {}).get("start", {}).get("character", 0),
                end_line=loc.get("range", {}).get("end", {}).get("line", 0),
                end_char=loc.get("range", {}).get("end", {}).get("character", 0),
            )
            for loc in result if loc
        ]
    """
    获取文档中的所有符号。
    """
    def get_document_symbols(self, path: str) -> List[LSPSymbol]:
        
        result = self._request("textDocument/documentSymbol", {
            "textDocument": {"uri": self._uri_for_path(path)},
        })
        
        if result is None:
            return []
        
        symbols = []
        uri = self._uri_for_path(path)
        
        def extract_symbols(items: List[Dict], container: str | None = None) -> None:
            for item in items:
                # 处理 DocumentSymbol 格式
                if "range" in item:
                    symbols.append(LSPSymbol(
                        name=item.get("name", ""),
                        kind=item.get("kind", 0),
                        location=LSPLocation(
                            uri=uri,
                            start_line=item["range"]["start"]["line"],
                            start_char=item["range"]["start"]["character"],
                            end_line=item["range"]["end"]["line"],
                            end_char=item["range"]["end"]["character"],
                        ),
                        container_name=container,
                    ))
                    # 递归处理子符号
                    if "children" in item:
                        extract_symbols(item["children"], item.get("name"))
                # 处理 SymbolInformation 格式
                elif "location" in item:
                    loc = item["location"]
                    symbols.append(LSPSymbol(
                        name=item.get("name", ""),
                        kind=item.get("kind", 0),
                        location=LSPLocation(
                            uri=loc.get("uri", uri),
                            start_line=loc.get("range", {}).get("start", {}).get("line", 0),
                            start_char=loc.get("range", {}).get("start", {}).get("character", 0),
                            end_line=loc.get("range", {}).get("end", {}).get("line", 0),
                            end_char=loc.get("range", {}).get("end", {}).get("character", 0),
                        ),
                        container_name=item.get("containerName"),
                    ))
        
        extract_symbols(result)
        return symbols
    
    def get_workspace_symbols(self, query: str) -> List[LSPSymbol]:
        """搜索工作区符号。"""
        result = self._request("workspace/symbol", {"query": query})
        
        if result is None:
            return []
        
        return [
            LSPSymbol(
                name=item.get("name", ""),
                kind=item.get("kind", 0),
                location=LSPLocation(
                    uri=item.get("location", {}).get("uri", ""),
                    start_line=item.get("location", {}).get("range", {}).get("start", {}).get("line", 0),
                    start_char=item.get("location", {}).get("range", {}).get("start", {}).get("character", 0),
                    end_line=item.get("location", {}).get("range", {}).get("end", {}).get("line", 0),
                    end_char=item.get("location", {}).get("range", {}).get("end", {}).get("character", 0),
                ),
                container_name=item.get("containerName"),
            )
            for item in result
        ]
    
    def get_hover(self, path: str, line: int, character: int) -> str | None:
        """获取悬停信息（类型、文档等）。"""
        result = self._request("textDocument/hover", {
            "textDocument": {"uri": self._uri_for_path(path)},
            "position": {"line": line, "character": character},
        })
        
        if result is None:
            return None
        
        contents = result.get("contents")
        if isinstance(contents, str):
            return contents
        if isinstance(contents, dict):
            return contents.get("value", "")
        if isinstance(contents, list):
            return "\n".join(
                c.get("value", c) if isinstance(c, dict) else str(c)
                for c in contents
            )
        return None
    
    def get_diagnostics(self, path: str) -> List[LSPDiagnostic]:
        """获取文件的诊断信息。"""
        uri = self._uri_for_path(path)
        return self._diagnostics.get(uri, [])

"""
LSP 服务器管理器。

负责：
- 根据文件类型自动选择/启动 LSP 服务器
- 管理多个语言服务器的生命周期
- 提供统一的符号查询接口
"""
class LSPManager:

    
    # 文件扩展名到语言的映射
    EXTENSION_MAP: Dict[str, str] = {
        ".py": "python",
        ".pyw": "python",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".js": "javascript",
        ".jsx": "javascript",
        ".go": "go",
        ".rs": "rust",
        ".c": "c",
        ".h": "c",
        ".cpp": "cpp",
        ".hpp": "cpp",
        ".cc": "cpp",
    }
    
    def __init__(self, workspace_root: Path, timeout_s: int = 30):
        self.workspace_root = workspace_root
        self.timeout_s = timeout_s
        self._clients: Dict[str, LSPClient] = {}
    
    def _get_language(self, path: str) -> str | None:
        """根据文件路径推断语言。"""
        suffix = Path(path).suffix.lower()
        return self.EXTENSION_MAP.get(suffix)
    
    def _get_or_create_client(self, language: str) -> LSPClient | None:
        """获取或创建指定语言的 LSP 客户端。"""
        if language in self._clients:
            client = self._clients[language]
            if client.is_ready():
                return client
            # 服务器已死，重新创建
            client.stop()
        
        client = LSPClient(self.workspace_root, language, timeout_s=self.timeout_s)
        if client.start():
            self._clients[language] = client
            return client
        return None
    
    def go_to_definition(self, path: str, line: int, character: int) -> List[LSPLocation]:
        """跳转到定义。"""
        language = self._get_language(path)
        if not language:
            return []
        
        client = self._get_or_create_client(language)
        if not client:
            return []
        
        return client.go_to_definition(path, line, character)
    
    def find_references(self, path: str, line: int, character: int) -> List[LSPLocation]:
        """查找引用。"""
        language = self._get_language(path)
        if not language:
            return []
        
        client = self._get_or_create_client(language)
        if not client:
            return []
        
        return client.find_references(path, line, character)
    
    def get_symbols(self, path: str) -> List[LSPSymbol]:
        """获取文档符号。"""
        language = self._get_language(path)
        if not language:
            return []
        
        client = self._get_or_create_client(language)
        if not client:
            return []
        
        return client.get_document_symbols(path)
    
    def search_symbols(self, query: str, language: str | None = None) -> List[LSPSymbol]:
        """搜索工作区符号。"""
        if language:
            client = self._get_or_create_client(language)
            if client:
                return client.get_workspace_symbols(query)
            return []
        
        # 搜索所有已启动的语言服务器
        results = []
        for client in self._clients.values():
            if client.is_ready():
                results.extend(client.get_workspace_symbols(query))
        return results
    
    def stop_all(self) -> None:
        """停止所有 LSP 服务器。"""
        for client in self._clients.values():
            client.stop()
        self._clients.clear()

