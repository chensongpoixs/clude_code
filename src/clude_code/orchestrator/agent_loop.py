import json
import re
from dataclasses import dataclass
from typing import Any, Callable, List, Dict, Optional

from clude_code.config import CludeConfig
from clude_code.llm.llama_cpp_http import ChatMessage, LlamaCppHttpClient
from clude_code.observability.audit import AuditLogger
from clude_code.observability.trace import TraceLogger
from clude_code.policy.command_policy import evaluate_command
from clude_code.tooling.feedback import format_feedback_message
from clude_code.tooling.local_tools import LocalTools, ToolResult
from clude_code.knowledge.indexer_service import IndexerService
from clude_code.knowledge.embedder import CodeEmbedder
from clude_code.knowledge.vector_store import VectorStore


SYSTEM_PROMPT = """\
你是一个本地代码仓库的编程助手（纯 CLI 代理）。
你可以通过“工具调用”来读取/搜索/写入文件以及执行命令。

重要规则：
- 当你需要使用工具时，你必须输出且只输出一个 JSON 对象，格式如下：
  {"tool":"<name>","args":{...}}
- 不需要工具时，输出正常中文解释与步骤（不要输出 JSON）。
- 可用工具：
  - list_dir: {"path":"."}
  - read_file: {"path":"README.md","offset":1,"limit":200}  (offset/limit 可省略)
  - grep: {"pattern":"...","path":"."} (ignore_case/max_hits 可选)
   - apply_patch: {"path":"a/b.py","old":"<旧代码块>","new":"<新代码块>","expected_replacements":1,"fuzzy":false,"min_similarity":0.92}
   - undo_patch: {"undo_id":"undo_...","force":false}
   - write_file: {"path":"a/b.txt","text":"..."}
   - run_cmd: {"command":"...","cwd":"."} (cwd 可省略)
   - search_semantic: {"query":"..."} (基于向量库搜索最相关的代码片段)
 """


@dataclass
class AgentTurn:
    assistant_text: str
    tool_used: bool
    trace_id: str
    events: list[dict[str, Any]]


def _try_parse_tool_call(text: str) -> dict[str, Any] | None:
    text = text.strip()
    # Allow the model to include explanations; try to extract JSON object from:
    # 1) raw text that is a JSON object
    # 2) fenced ```json ... ``` block
    # 3) first {...} object in the text (best-effort)
    candidates: list[str] = []
    if text.startswith("{") and text.endswith("}"):
        candidates.append(text)
    if "```" in text:
        for fence in ("```json", "```JSON", "```"):
            if fence in text:
                parts = text.split(fence, 1)
                if len(parts) == 2:
                    body = parts[1]
                    body = body.split("```", 1)[0]
                    body = body.strip()
                    if body.startswith("{") and body.endswith("}"):
                        candidates.append(body)
    # best-effort: find first JSON-ish object
    if "{" in text and "}" in text:
        start = text.find("{")
        end = text.rfind("}")
        if 0 <= start < end:
            candidates.append(text[start : end + 1].strip())

    obj = None
    for c in candidates:
        try:
            parsed = json.loads(c)
            if isinstance(parsed, dict):
                obj = parsed
                break
        except json.JSONDecodeError:
            continue
    if obj is None:
        return None
    if not isinstance(obj, dict):
        return None
    if "tool" not in obj or "args" not in obj:
        return None
    if not isinstance(obj["tool"], str) or not isinstance(obj["args"], dict):
        return None
    return obj


def _tool_result_to_message(name: str, tr: ToolResult, keywords: set[str] | None = None) -> str:
    # Centralized structured feedback (industry-grade stability):
    # keep decision-critical fields + references, avoid dumping full payload.
    return format_feedback_message(name, tr, keywords=keywords)


class AgentLoop:
    def __init__(self, cfg: CludeConfig) -> None:
        self.cfg = cfg
        # keep it simple & stable enough for MVP; later replace with uuid4
        self.session_id = f"sess_{id(self)}"
        self.llm = LlamaCppHttpClient(
            base_url=cfg.llm.base_url,
            api_mode=cfg.llm.api_mode,  # type: ignore[arg-type]
            model=cfg.llm.model,
            temperature=cfg.llm.temperature,
            max_tokens=cfg.llm.max_tokens,
            timeout_s=cfg.llm.timeout_s,
        )
        self.tools = LocalTools(
            cfg.workspace_root,
            max_file_read_bytes=cfg.limits.max_file_read_bytes,
            max_output_bytes=cfg.limits.max_output_bytes,
        )
        self.audit = AuditLogger(cfg.workspace_root, self.session_id)
        self.trace = TraceLogger(cfg.workspace_root, self.session_id)
        
        # Knowledge / RAG systems
        self.indexer = IndexerService(cfg.workspace_root)
        self.indexer.start() # Start background indexing
        self.embedder = CodeEmbedder()
        self.vector_store = VectorStore(cfg.workspace_root)

        # Initialize with Repo Map for better global context (Aider-style)
        repo_map = self.tools.generate_repo_map()
        self.messages: list[ChatMessage] = [
            ChatMessage(role="system", content=SYSTEM_PROMPT),
            ChatMessage(role="system", content=f"当前代码仓库符号概览：\n\n{repo_map}"),
        ]

    def run_turn(self, user_text: str, *, confirm: Callable[[str], bool], debug: bool = False) -> AgentTurn:
        trace_id = f"trace_{abs(hash((self.session_id, user_text)))}"
        
        # Extract intent keywords for semantic windowing (MVP: simple regex)
        keywords = set(re.findall(r'\w{4,}', user_text.lower()))
        # Filter common non-useful words
        keywords -= {"please", "help", "find", "where", "change", "file", "code", "repo", "make"}
        
        events: list[dict[str, Any]] = []
        step_idx = 0

        def _ev(event: str, data: dict[str, Any]) -> None:
            nonlocal step_idx
            step_idx += 1
            e = {"step": step_idx, "event": event, "data": data}
            events.append(e)
            if debug:
                # keep trace log verbose, but trim huge fields
                self.trace.write(trace_id=trace_id, step=step_idx, event=event, data=data)

        self.audit.write(trace_id=trace_id, event="user_message", data={"text": user_text})
        _ev("user_message", {"text": user_text})
        self.messages.append(ChatMessage(role="user", content=user_text))
        # Keep history bounded to reduce context size
        self._trim_history(max_messages=30)

        tool_used = False
        for _ in range(20):  # hard stop to avoid infinite loops
            _ev("llm_request", {"messages": len(self.messages)})
            assistant = self.llm.chat(self.messages)
            _ev("llm_response", {"text": assistant[:4000], "truncated": len(assistant) > 4000})
            tool_call = _try_parse_tool_call(assistant)
            if tool_call is None:
                self.messages.append(ChatMessage(role="assistant", content=assistant))
                self.audit.write(trace_id=trace_id, event="assistant_text", data={"text": assistant})
                _ev("final_text", {"text": assistant[:4000], "truncated": len(assistant) > 4000})
                self._trim_history(max_messages=30)
                return AgentTurn(assistant_text=assistant, tool_used=tool_used, trace_id=trace_id, events=events)

            name = tool_call["tool"]
            args = tool_call["args"]
            _ev("tool_call_parsed", {"tool": name, "args": args})

            # IMPORTANT: llama.cpp chat templates often require strict alternation:
            # user/assistant/user/assistant...
            # Always record the assistant message before sending a user tool result.
            self.messages.append(ChatMessage(role="assistant", content=assistant))
            _ev("assistant_tool_call_recorded", {"tool": name})
            self._trim_history(max_messages=30)

            # policy confirmations (MVP): only guard write/exec
            if name in {"write_file", "apply_patch", "undo_patch"} and self.cfg.policy.confirm_write:
                decision = confirm(f"确认写文件？tool={name} args={args}")
                self.audit.write(trace_id=trace_id, event="confirm_write", data={"tool": name, "args": args, "allow": decision})
                _ev("confirm_write", {"tool": name, "allow": decision})
                if not decision:
                    msg = _tool_result_to_message(name, ToolResult(False, error={"code": "E_DENIED", "message": "user denied"}), keywords=keywords)
                    self.messages.append(ChatMessage(role="user", content=msg))
                    _ev("denied_by_user", {"tool": name})
                    self._trim_history(max_messages=30)
                    continue
            if name in {"run_cmd"} and self.cfg.policy.confirm_exec:
                decision = confirm(f"确认执行命令？tool={name} args={args}")
                self.audit.write(trace_id=trace_id, event="confirm_exec", data={"tool": name, "args": args, "allow": decision})
                _ev("confirm_exec", {"tool": name, "allow": decision})
                if not decision:
                    msg = _tool_result_to_message(name, ToolResult(False, error={"code": "E_DENIED", "message": "user denied"}), keywords=keywords)
                    self.messages.append(ChatMessage(role="user", content=msg))
                    _ev("denied_by_user", {"tool": name})
                    self._trim_history(max_messages=30)
                    continue

            # minimal command policy (denylist)
            if name == "run_cmd":
                cmd = str(args.get("command", ""))
                dec = evaluate_command(cmd, allow_network=self.cfg.policy.allow_network)
                if not dec.ok:
                    self.audit.write(trace_id=trace_id, event="policy_deny_cmd", data={"command": cmd, "reason": dec.reason})
                    _ev("policy_deny_cmd", {"command": cmd, "reason": dec.reason})
                    msg = _tool_result_to_message(name, ToolResult(False, error={"code": "E_POLICY_DENIED", "message": dec.reason}), keywords=keywords)
                    self.messages.append(ChatMessage(role="user", content=msg))
                    self._trim_history(max_messages=30)
                    continue

            tool_used = True
            result = self._dispatch_tool(name, args)
            _ev("tool_result", {"tool": name, "ok": result.ok, "error": result.error, "payload": result.payload})
            # feed tool result back to model as user message (works with most chat templates)
            self.messages.append(ChatMessage(role="user", content=_tool_result_to_message(name, result, keywords=keywords)))
            _ev("tool_result_fed_back", {"tool": name})
            self._trim_history(max_messages=30)
            audit_data: dict[str, Any] = {"tool": name, "args": args, "ok": result.ok, "error": result.error}
            if name in {"apply_patch", "undo_patch"} and result.ok and result.payload:
                # record hashes/undo_id for traceability
                audit_data["payload"] = result.payload
            self.audit.write(trace_id=trace_id, event="tool_call", data=audit_data)

        _ev("stop_reason", {"reason": "max_tool_calls_reached", "limit": 20})
        return AgentTurn(
            assistant_text="达到本轮最大工具调用次数（20），已停止以避免死循环。请缩小任务或提供更多约束/入口文件。",
            tool_used=tool_used,
            trace_id=trace_id,
            events=events,
        )

    def _trim_history(self, *, max_messages: int) -> None:
        """
        Keep chat history bounded to reduce context size.
        We always keep the first system message, and the most recent (max_messages-1) others.
        """
        if len(self.messages) <= max_messages:
            return
        if not self.messages:
            return
        system = self.messages[0]
        tail = self.messages[-(max_messages - 1) :]
        self.messages = [system, *tail]

    def _dispatch_tool(self, name: str, args: dict[str, Any]) -> ToolResult:
        try:
            if name == "list_dir":
                return self.tools.list_dir(path=args.get("path", "."))
            if name == "read_file":
                return self.tools.read_file(path=args["path"], offset=args.get("offset"), limit=args.get("limit"))
            if name == "grep":
                return self.tools.grep(
                    pattern=args["pattern"],
                    path=args.get("path", "."),
                    ignore_case=bool(args.get("ignore_case", False)),
                    max_hits=int(args.get("max_hits", 200)),
                )
            if name == "apply_patch":
                return self.tools.apply_patch(
                    path=args["path"],
                    old=args["old"],
                    new=args["new"],
                    expected_replacements=int(args.get("expected_replacements", 1)),
                    fuzzy=bool(args.get("fuzzy", False)),
                    min_similarity=float(args.get("min_similarity", 0.92)),
                )
            if name == "undo_patch":
                return self.tools.undo_patch(
                    undo_id=args["undo_id"],
                    force=bool(args.get("force", False)),
                )
            if name == "write_file":
                return self.tools.write_file(path=args["path"], text=args.get("text", ""))
            if name == "run_cmd":
                return self.tools.run_cmd(command=args["command"], cwd=args.get("cwd", "."))
            if name == "search_semantic":
                return self._semantic_search(query=args["query"])
            return ToolResult(False, error={"code": "E_NO_TOOL", "message": f"unknown tool: {name}"})
        except KeyError as e:
            return ToolResult(False, error={"code": "E_INVALID_ARGS", "message": f"missing arg: {e}"})
        except Exception as e:
            return ToolResult(False, error={"code": "E_TOOL", "message": str(e)})

    def _semantic_search(self, query: str) -> ToolResult:
        """Execute vector search and return chunks as ToolResult."""
        try:
            q_vector = self.embedder.embed_query(query)
            hits = self.vector_store.search(q_vector, limit=5)
            
            payload_hits = []
            for h in hits:
                payload_hits.append({
                    "path": h.get("path"),
                    "start_line": h.get("start_line"),
                    "end_line": h.get("end_line"),
                    "text": h.get("text")
                })
            
            return ToolResult(True, payload={"query": query, "hits": payload_hits})
        except Exception as e:
            return ToolResult(False, error={"code": "E_SEMANTIC_SEARCH", "message": str(e)})


