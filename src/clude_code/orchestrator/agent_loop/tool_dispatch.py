from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Callable, Iterable, TYPE_CHECKING
from dataclasses import dataclass

from pydantic import TypeAdapter, ValidationError

from clude_code.tooling.local_tools import ToolResult

if TYPE_CHECKING:
    from .agent_loop import AgentLoop

logger = logging.getLogger(__name__)


def _obj_schema(*, properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": required or [],
        "additionalProperties": False,
    }


ToolHandler = Callable[["AgentLoop", dict[str, Any]], ToolResult]


@dataclass(frozen=True)
class ToolSpec:
    """
    工具规范（参考Claude Code：同一份"工具事实"驱动所有相关功能）。
    """

    # 核心必需字段
    name: str
    summary: str
    args_schema: dict[str, Any]
    example_args: dict[str, Any]
    side_effects: set[str]
    external_bins_required: set[str]
    external_bins_optional: set[str]
    visible_in_prompt: bool
    callable_by_model: bool
    exec_command_key: str | None
    handler: ToolHandler

    # 扩展可选字段
    description: str = ""
    category: str = "general"
    priority: int = 0
    cacheable: bool = False
    timeout_seconds: int = 30
    requires_confirmation: bool = False
    version: str = "1.0.0"
    deprecated: bool = False

    def validate_args(self, args: dict[str, Any]) -> tuple[bool, dict[str, Any] | str]:
        """
        使用 Pydantic 运行时强校验参数是否符合 args_schema。
        返回: (是否通过, 转换后的参数或错误消息)
        """
        from pydantic import ConfigDict, create_model
        
        # 1. 解析 properties
        props = self.args_schema.get("properties", {})
        required = self.args_schema.get("required", [])
        
        # 2. 映射 JSON Schema 类型到 Python 类型（基础版）
        type_mapping = {
            "string": str,
            "integer": int,
            "boolean": bool,
            "number": float,
            "array": list,
            "object": dict
        }
        
        def _pick_type(fi: dict[str, Any]) -> tuple[str, bool]:
            """
            兼容 JSON Schema:
            - type: "string"
            - type: ["integer","null"]
            - anyOf/oneOf: [{type: ...}, ...]（MVP 取第一个可识别 type）
            返回: (基础类型名, 是否允许 null)
            """
            allow_null = False
            t = fi.get("type")
            if isinstance(t, list):
                allow_null = "null" in t
                non_null = [x for x in t if x != "null"]
                if non_null and isinstance(non_null[0], str):
                    return non_null[0], allow_null
                return "string", allow_null
            if isinstance(t, str):
                return t, False

            # Fallback: anyOf/oneOf
            for k in ("anyOf", "oneOf"):
                opts = fi.get(k)
                if isinstance(opts, list):
                    for opt in opts:
                        if isinstance(opt, dict) and isinstance(opt.get("type"), (str, list)):
                            return _pick_type(opt)
            return "string", False

        field_definitions: dict[str, Any] = {}
        for field_name, field_info in props.items():
            # 兼容 type 为 list 的情况（例如 ["integer","null"]）
            js_type, allow_null = _pick_type(field_info if isinstance(field_info, dict) else {})
            py_type: Any = type_mapping.get(js_type, Any)
            if allow_null:
                py_type = py_type | None
            
            # 处理默认值（业界做法：schema 的 default 应真正生效，避免 handler 里散落默认值逻辑）
            default_val: Any = None
            if isinstance(field_info, dict) and "default" in field_info:
                default_val = field_info.get("default")

            # 处理可选参数
            if field_name in required:
                field_definitions[field_name] = (py_type, ...)
            else:
                # 非 required：允许缺省；缺省时用 schema default（否则 None）
                optional_type = (py_type | None) if allow_null is False else py_type
                field_definitions[field_name] = (optional_type, default_val)
        
        try:
            # 3. 动态创建 Pydantic 模型
            # 业界做法：禁止额外参数，避免模型乱传参被静默忽略
            DynamicModel = create_model(
                f"Args_{self.name}",
                __config__=ConfigDict(extra="forbid"),
                **field_definitions,
            )
            # 4. 执行校验与转换
            validated = DynamicModel(**args)
            out = validated.model_dump(exclude_none=False)

            # 5. enum 约束（MVP 轻量实现）：如果 schema 声明了 enum，则严格检查
            for field_name, field_info in props.items():
                if not isinstance(field_info, dict):
                    continue
                enums = field_info.get("enum")
                if not isinstance(enums, list) or not enums:
                    continue
                val = out.get(field_name)
                if val is None:
                    continue
                if val not in enums:
                    return False, f"参数 '{field_name}': 必须为 {enums} 之一"

            return True, out
        except ValidationError as e:
            # 5. 格式化友好的错误回喂
            errors = []
            for err in e.errors():
                loc = ".".join(str(x) for x in err["loc"])
                msg = err["msg"]
                errors.append(f"参数 '{loc}': {msg}")
            return False, "; ".join(errors)
        except Exception as ex:
            return False, f"校验逻辑异常: {ex}"


def _h_list_dir(loop: "AgentLoop", args: dict[str, Any]) -> ToolResult:
    return loop.tools.list_dir(path=args.get("path", "."))


def _h_read_file(loop: "AgentLoop", args: dict[str, Any]) -> ToolResult:
    return loop.tools.read_file(path=args["path"], offset=args.get("offset"), limit=args.get("limit"))


def _h_glob_file_search(loop: "AgentLoop", args: dict[str, Any]) -> ToolResult:
    return loop.tools.glob_file_search(
        glob_pattern=args["glob_pattern"],
        target_directory=args.get("target_directory", "."),
    )


def _h_grep(loop: "AgentLoop", args: dict[str, Any]) -> ToolResult:
    return loop.tools.grep(
        pattern=args["pattern"],
        path=args.get("path", "."),
        ignore_case=bool(args.get("ignore_case", False)),
        max_hits=int(args.get("max_hits", 200)),
    )


def _h_apply_patch(loop: "AgentLoop", args: dict[str, Any]) -> ToolResult:
    return loop.tools.apply_patch(
        path=args["path"],
        old=args["old"],
        new=args["new"],
        expected_replacements=int(args.get("expected_replacements", 1)),
        fuzzy=bool(args.get("fuzzy", False)),
        min_similarity=float(args.get("min_similarity", 0.92)),
    )


def _h_undo_patch(loop: "AgentLoop", args: dict[str, Any]) -> ToolResult:
    return loop.tools.undo_patch(
        undo_id=args["undo_id"],
        force=bool(args.get("force", False)),
    )

# --- IGNORE ---
# ... Other tool handlers ...
def _h_write_file(loop: "AgentLoop", args: dict[str, Any]) -> ToolResult:
    return loop.tools.write_file(
        path=args["path"],
        text=args.get("text", ""),
        content_based=bool(args.get("content_based", False)),
        insert_at_line=args.get("insert_at_line")
    );


def _h_run_cmd(loop: "AgentLoop", args: dict[str, Any]) -> ToolResult:
    return loop.tools.run_cmd(
        command=args["command"],
        cwd=args.get("cwd", "."),
        timeout_s=args.get("timeout_s"),
    )


def _h_search_semantic(loop: "AgentLoop", args: dict[str, Any]) -> ToolResult:
    # 语义检索属于 AgentLoop 的能力（依赖 embedder/vector_store），不直接放在 LocalTools
    return loop._semantic_search(query=args["query"])


def _h_display(loop: "AgentLoop", args: dict[str, Any]) -> ToolResult:
    """
    向用户输出信息（进度、分析结果、说明等）。

    实现原理：
    1. 从 AgentLoop 获取当前的 _ev 回调和 trace_id
    2. 调用 tooling/tools/display.py 中的 display 函数
    3. 通过事件机制广播到 UI（--live 模式）
    """
    from clude_code.tooling.tools.display import display

    # 兼容旧字段：message -> content
    content = args.get("content")
    if not isinstance(content, str) or not content.strip():
        content = args.get("message", "")
    level = args.get("level", "info")
    title = args.get("title")
    # 思考/解释（可选）：用于把“为什么/怎么想的”展示给用户（对标 Claude Code 的 message_user）
    thought = args.get("thought")
    explanation = args.get("explanation")
    evidence = args.get("evidence")

    _ev = getattr(loop, "_current_ev", None)
    trace_id = getattr(loop, "_current_trace_id", None)

    return display(
        loop=loop,
        content=str(content),
        level=str(level) if isinstance(level, str) else "info",
        title=str(title) if isinstance(title, str) else None,
        thought=str(thought) if isinstance(thought, str) else None,
        explanation=str(explanation) if isinstance(explanation, str) else None,
        evidence=evidence if isinstance(evidence, list) else None,
        _ev=_ev,
        trace_id=trace_id,
    )


def _h_internal_repo_map(loop: "AgentLoop", args: dict[str, Any]) -> ToolResult:
    repo_map = loop.tools.generate_repo_map()
    return ToolResult(ok=True, payload={"repo_map": repo_map})


def _run_local_tool(name: str, args: dict[str, Any]) -> ToolResult:
    """Legacy helper - should not be used in new code."""
    raise NotImplementedError(f"_run_local_tool is deprecated. Use proper tool handlers instead.")


def _spec_list_dir() -> ToolSpec:
    """ToolSpec：list_dir（只读）。"""
    return ToolSpec(
        name="list_dir",
        summary="列出目录内容（只读）。",
        description=(
            "用于查看某个目录下有哪些文件/子目录（List Directory）。\n"
            "- 适合：先 list_dir 再决定 read_file/grep/glob_file_search。\n"
            "- 注意：path 必须是工作区内的相对路径。"
        ),
        args_schema=_obj_schema(
            properties={"path": {"type": "string", "default": ".", "description": "相对工作区的目录路径"}},
            required=[],
        ),
        example_args={"path": "."},
        side_effects={"read"},
        external_bins_required=set(),
        external_bins_optional=set(),
        visible_in_prompt=True,
        callable_by_model=True,
        exec_command_key=None,
        handler=_h_list_dir,
    )


def _spec_read_file() -> ToolSpec:
    """ToolSpec：read_file（只读）。"""
    return ToolSpec(
        name="read_file",
        summary="读取文件内容（只读，支持 offset/limit 分段）。",
        description=(
            "用于读取工作区内文件内容（Read File）。\n"
            "- 大文件建议用 offset/limit 分段读取，避免上下文刷屏。\n"
            "- 如需搜索再定位：优先用 grep/search_semantic 再 read_file 精读。"
        ),
        args_schema=_obj_schema(
            properties={
                "path": {"type": "string", "description": "相对工作区的文件路径"},
                "offset": {"type": ["integer", "null"], "minimum": 1, "description": "起始行号（1-based）"},
                "limit": {"type": ["integer", "null"], "minimum": 1, "description": "读取行数上限"},
            },
            required=["path"],
        ),
        example_args={"path": "README.md", "offset": 1, "limit": 200},
        side_effects={"read"},
        external_bins_required=set(),
        external_bins_optional=set(),
        visible_in_prompt=True,
        callable_by_model=True,
        exec_command_key=None,
        handler=_h_read_file,
    )


def _spec_glob_file_search() -> ToolSpec:
    """ToolSpec：glob_file_search（只读）。"""
    return ToolSpec(
        name="glob_file_search",
        summary="按文件名模式查找文件（只读，支持 ** 递归）。",
        description=(
            "用于按文件名模式快速定位文件（Glob File Search）。\n"
            "- 适合：找某类文件（例如 **/*.md、**/*config*.py）。\n"
            "- 注意：这是文件名匹配，不是内容搜索；内容搜索请用 grep。"
        ),
        args_schema=_obj_schema(
            properties={
                "glob_pattern": {"type": "string", "description": "glob 模式，例如 **/*.md, **/*.py, **/*.cpp, **/*.c, **/*.h, **/*.cc, **/*.java, **/*.js, **/*.ts, **/*.html, **/*.css, **/*.json, **/*.xml"},
                "target_directory": {"type": "string", "default": ".", "description": "搜索根目录（相对工作区）"},
            },
            required=["glob_pattern"],
        ),
        example_args={"glob_pattern": "**/test.md", "target_directory": "."},
        side_effects={"read"},
        external_bins_required=set(),
        external_bins_optional=set(),
        visible_in_prompt=True,
        callable_by_model=True,
        exec_command_key=None,
        handler=_h_glob_file_search,
    )


def _spec_grep() -> ToolSpec:
    """ToolSpec：grep（只读；优先 rg）。"""
    return ToolSpec(
        name="grep",
        summary="代码搜索（优先 rg，fallback Python）。",
        description=(
            "用于在工作区内按正则搜索文本内容（Grep / Ripgrep）。\n"
            "- 适合：定位函数名/类名/错误字符串/配置键。\n"
            "- 建议：pattern 尽量具体；返回太多时用 path 限定目录或降低 max_hits。"
        ),
        args_schema=_obj_schema(
            properties={
                "pattern": {"type": "string", "description": "正则表达式 列如： class\\s+(?i)， 表示匹配 class 后跟空白符再跟任意字符，且忽略大小写"},
                "path": {"type": "string", "default": ".", "description": "搜索路径（相对工作区）"},
                "ignore_case": {"type": "boolean", "default": False, "description": "是否忽略大小写"},
                "max_hits": {"type": "integer", "default": 200, "minimum": 1, "description": "最多返回条数"},
            },
            required=["pattern"],
        ),
        example_args={"pattern": "class\\s+(?i)", "path": "src", "ignore_case": False, "max_hits": 200},
        side_effects={"read"},
        external_bins_required=set(),
        external_bins_optional={"rg"},
        visible_in_prompt=True,
        callable_by_model=True,
        exec_command_key=None,
        handler=_h_grep,
    )


def _spec_apply_patch() -> ToolSpec:
    """ToolSpec：apply_patch（写文件）。"""
    return ToolSpec(
        name="apply_patch",
        summary="补丁式编辑（写文件，支持 fuzzy）。",
        description=(
            "用于对文件进行“基于上下文的补丁替换”（Apply Patch）。\n"
            "- 建议：old/new 块带足够上下文（前后至少 3-5 行）以保证唯一匹配。\n"
            "- fuzzy=true 仅建议在单点替换且文本略有漂移时使用。\n"
            "- 重要：该工具会写文件，必须遵守 policy 的确认机制。"
        ),
        args_schema=_obj_schema(
            properties={
                "path": {"type": "string", "description": "目标文件路径（相对工作区）"},
                "old": {"type": "string", "description": "要被替换的旧代码块（建议带上下文）"},
                "new": {"type": "string", "description": "新代码块"},
                "expected_replacements": {"type": "integer", "default": 1, "minimum": 0, "description": "期望替换次数（0=全替换）"},
                "fuzzy": {"type": "boolean", "default": False, "description": "是否启用模糊匹配（仅支持单处替换）"},
                "min_similarity": {"type": "number", "default": 0.92, "minimum": 0.0, "maximum": 1.0, "description": "模糊匹配最小相似度"},
            },
            required=["path", "old", "new"],
        ),
        example_args={
            "path": "src/*.*",
            "old": "x = 1",
            "new": "x = 2",
            "expected_replacements": 1,
            "fuzzy": False,
            "min_similarity": 0.92,
        },
        side_effects={"write"},
        external_bins_required=set(),
        external_bins_optional=set(),
        visible_in_prompt=True,
        callable_by_model=True,
        exec_command_key=None,
        handler=_h_apply_patch,
    )


def _spec_undo_patch() -> ToolSpec:
    """ToolSpec：undo_patch（写文件）。"""
    return ToolSpec(
        name="undo_patch",
        summary="回滚补丁（写文件，基于 undo_id）。",
        description=(
            "用于回滚 apply_patch 产生的变更（Undo Patch）。\n"
            "- 适合：补丁应用错误/需要撤销。\n"
            "- 注意：force=true 会忽略 hash 冲突检查，可能覆盖你后续手动修改。"
        ),
        args_schema=_obj_schema(
            properties={
                "undo_id": {"type": "string", "description": "apply_patch 返回的 undo_id"},
                "force": {"type": "boolean", "default": False, "description": "强制回滚（忽略 hash 冲突检查）"},
            },
            required=["undo_id"],
        ),
        example_args={"undo_id": "undo_123", "force": False},
        side_effects={"write"},
        external_bins_required=set(),
        external_bins_optional=set(),
        visible_in_prompt=True,
        callable_by_model=True,
        exec_command_key=None,
        handler=_h_undo_patch,
    )


def _spec_write_file() -> ToolSpec:
    """ToolSpec：write_file（写文件）。"""
    return ToolSpec(
        name="write_file",
        summary="写入文件（写文件）。",
        description=(
            "用于创建/覆盖/追加写入文件（Write File）。\n"
            "- 默认：覆盖写入（wrote）。\n"
            "- content_based=true：文件非空则追加（appended）。\n"
            "- insert_at_line：按行插入（注意行号是 0-based）。\n"
            "重要：该工具会写文件，必须遵守 policy 的确认机制。"
        ),
         args_schema=_obj_schema(
            properties={
                "path": {"type": "string", "description": "目标文件路径（相对工作区）"},
                "text": {"type": "string", "default": "", "description": "写入内容"},
                "content_based": {"type": "boolean", "default": False, "description": "是否根据现有内容智能决定写入行为：空文件则写入，有内容则追加"},
                "insert_at_line": {"type": "integer", "default": 0, "description": "在指定行号插入内容（从0开始）。如果指定此参数，将忽略content_based设置"},
            },
            required=["path"],
        ),
        example_args={"path": "notes.md", "text": "hello world\n", "content_based": True},
        side_effects={"write"},
        external_bins_required=set(),
        external_bins_optional=set(),
        visible_in_prompt=True,
        callable_by_model=True,
        exec_command_key=None,
        handler=_h_write_file,
    )


def _spec_run_cmd() -> ToolSpec:
    """ToolSpec：run_cmd（exec）。"""
    return ToolSpec(
        name="run_cmd",
        summary="执行命令（可能有副作用，受策略约束）。",
        description=(
            "用于在工作区内执行命令（Execute Command）。\n"
            "- 适合：运行测试/格式化/构建/一次性诊断命令。\n"
            "- 注意：该工具可能产生副作用（写文件/联网/安装依赖），必须遵守 policy 的确认与限制。\n"
            "- 建议：命令尽量幂等；输出可能会被 max_output_bytes 截断。"
        ),
        args_schema=_obj_schema(
            properties={
                "command": {"type": "string", "description": "要执行的命令字符串"},
                "cwd": {"type": "string", "default": ".", "description": "工作目录（相对工作区）"},
                "timeout_s": {"type": "integer", "default": 30, "minimum": 1, "description": "超时时间（秒），默认取配置 command.timeout_s"},
            },
            required=["command"],
        ),
        example_args={"command": "python -m pytest -q", "cwd": ".", "timeout_s": 60},
        side_effects={"exec"},
        external_bins_required=set(),
        external_bins_optional=set(),
        visible_in_prompt=True,
        callable_by_model=True,
        exec_command_key="command",
        handler=_h_run_cmd,
    )


def _spec_search_semantic() -> ToolSpec:
    """ToolSpec：search_semantic（只读 + search）。"""
    return ToolSpec(
        name="search_semantic",
        summary="语义检索（向量 RAG，只读）。",
        args_schema=_obj_schema(
            properties={
                "query": {"type": "string", "description": "自然语言查询"},
                "max_results": {"type": "integer", "default": 10, "minimum": 1, "description": "最多返回条数"},
            },
            required=["query"],
        ),
        example_args={"query": "用户认证逻辑", "max_results": 10},
        side_effects={"read"},
        external_bins_required=set(),
        external_bins_optional=set(),
        visible_in_prompt=True,
        callable_by_model=True,
        exec_command_key=None,
        handler=_h_search_semantic,
    )


def _spec_display() -> ToolSpec:
    """ToolSpec：display（只读）。"""
    return ToolSpec(
        name="display",
        summary="向用户输出信息（进度、分析结果、说明等，只读）。",
        args_schema=_obj_schema(
            properties={
                "content": {"type": "string", "description": "要显示的内容（支持 Markdown）"},
                "level": {
                    "type": "string",
                    "enum": ["info", "success", "warning", "error", "progress"],
                    "default": "info",
                    "description": "消息级别",
                },
                "title": {"type": ["string", "null"], "description": "可选标题"},
                "thought": {"type": ["string", "null"], "description": "可选：思考过程（对齐 UI 的 Why/Decision 区域）"},
                "explanation": {"type": ["string", "null"], "description": "可选：解释/理由（与 thought 语义接近，兼容不同 prompt 习惯）"},
                "evidence": {
                    "type": ["array", "null"],
                    "items": {"type": "string"},
                    "description": "可选：证据/要点列表（用于 UI Evidence 区域）",
                },

                # 兼容字段：历史上曾使用 message（保留以避免旧 prompt/脚本失效）
                "message": {"type": ["string", "null"], "description": "兼容字段：等价于 content（后续将废弃）"},
            },
            required=["content"],
        ),
        example_args={"content": "正在分析文件...", "level": "progress"},
        side_effects=set(),  # 无副作用（只读展示）
        external_bins_required=set(),
        external_bins_optional=set(),
        visible_in_prompt=True,
        callable_by_model=True,
        exec_command_key=None,
        handler=_h_display,
    )


def _spec_internal_repo_map() -> ToolSpec:
    """ToolSpec：internal_repo_map（只读）。"""
    return ToolSpec(
        name="internal_repo_map",
        summary="生成代码仓库结构图（只读）。",
        args_schema=_obj_schema(properties={}, required=[]),
        example_args={},
        side_effects={"read"},
        external_bins_required={"ctags"},
        external_bins_optional=set(),
        visible_in_prompt=False,
        callable_by_model=False,
        exec_command_key=None,
        handler=_h_internal_repo_map,
    )


def _spec_preview_multi_edit() -> ToolSpec:
    return ToolSpec(
        name="preview_multi_edit",
        summary="预览多文件批量编辑的影响和风险",
        description="在应用多文件编辑前预览所有变化，分析潜在风险和依赖关系。帮助用户做出明智的编辑决策。",
        args_schema={
            "type": "object",
            "properties": {
                "edits": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string", "description": "文件路径"},
                            "old_string": {"type": "string", "description": "要替换的旧内容"},
                            "new_string": {"type": "string", "description": "替换成的新内容"}
                        },
                        "required": ["path", "old_string", "new_string"]
                    },
                    "description": "编辑任务列表"
                }
            },
            "required": ["edits"]
        },
        example_args={
            "edits": [
                {
                    "path": "src/main.py",
                    "old_string": "def old_func():",
                    "new_string": "def new_func():"
                }
            ]
        },
        side_effects={"read"},  # 只读操作，分析影响
        external_bins_required=set(),
        external_bins_optional=set(),
        visible_in_prompt=True,
        callable_by_model=True,
        category="file",
        priority=2,
        cacheable=False,  # 预览不缓存
        timeout_seconds=30,
        exec_command_key=None,
        requires_confirmation=False,  # 预览不需要确认
        version="1.0.0",
        handler=_h_preview_multi_edit,
    )


def _h_preview_multi_edit(loop: "AgentLoop", args: dict[str, Any]) -> ToolResult:
    """处理多文件编辑预览"""
    try:
        import asyncio
        from clude_code.tooling.advanced_editing import get_advanced_code_editor

        edits = args.get("edits", [])
        if not edits:
            return ToolResult(False, error={"code": "E_NO_EDITS", "message": "没有提供编辑任务"})

        # 获取编辑器
        editor = get_advanced_code_editor(Path(loop.cfg.workspace_root))

        # 运行预览（同步方式调用异步函数）
        async def run_preview():
            return await editor.preview_multi_file_edit(edits)

        previews = asyncio.run(run_preview())

        # 生成摘要
        summary = editor.generate_edit_summary(previews)

        return ToolResult(
            True,
            payload={
                "preview_count": len(previews),
                "summary": summary,
                "previews": [
                    {
                        "file": str(p.file_path),
                        "confidence": p.confidence,
                        "impact_level": p.impact_level,
                        "changes": len(p.line_changes)
                    }
                    for p in previews
                ]
            }
        )

    except Exception as e:
        return ToolResult(False, error={"code": "E_PREVIEW_FAILED", "message": f"预览失败: {e}"})


def _h_question(loop: "AgentLoop", args: dict[str, Any]) -> ToolResult:
    """处理器：question（向用户提问）。"""
    question = args.get("question", "")
    options = args.get("options")
    multiple = args.get("multiple", False)
    header = args.get("header")

    return loop.tools.ask_question(question=question, options=options, multiple=multiple, header=header)


def _spec_question() -> ToolSpec:
    """ToolSpec：question（向用户提问）。"""
    return ToolSpec(
        name="question",
        summary="向用户提问并获取回答。",
        args_schema=_obj_schema(
            properties={
                "question": {"type": "string", "description": "问题文本"},
                "options": {"type": "array", "items": {"type": "string"}, "description": "可选的选项列表"},
                "multiple": {"type": "boolean", "default": False, "description": "是否允许多选"},
                "header": {"type": "string", "description": "问题标题"}
            },
            required=["question"],
        ),
        example_args={"question": "您想要如何处理这个文件？", "options": ["删除", "重命名", "保留"]},
        side_effects={"read"},  # 实际上不修改文件，但需要用户交互
        external_bins_required=set(),
        external_bins_optional=set(),
        visible_in_prompt=True,
        callable_by_model=True,
        exec_command_key=None,
        handler=_h_question,
    )


def _h_webfetch(loop: "AgentLoop", args: dict[str, Any]) -> ToolResult:
    """处理器：webfetch（获取网页内容）。"""
    url = args.get("url", "")
    format = args.get("format", "markdown")
    timeout = args.get("timeout", 30)

    return loop.tools.fetch_web_content(url=url, format=format, timeout=timeout)


def _spec_webfetch() -> ToolSpec:
    """ToolSpec：webfetch（获取网页内容）。"""
    return ToolSpec(
        name="webfetch",
        summary="抓取网页内容（支持 markdown/text/html）。",
        description=(
            "用于把指定 URL 的网页内容抓取为可读文本（Web Fetch）。\n"
            "- 适合：抓官网文档/博客/FAQ，然后结合内容回答或写代码。\n"
            "- 注意：只支持 http/https；内容会按配置的 max_content_length 截断。\n"
            "- 提示：如果只是需要“找资料”，先用 websearch 再 webfetch 关键页面。"
        ),
        args_schema=_obj_schema(
            properties={
                "url": {"type": "string", "description": "要获取的URL"},
                # "format": {"type": "string", "enum": ["markdown", "text", "html"], "default": "markdown", "description": "返回格式"},
                "format": {"type": "string", "enum": ["markdown", "text"], "default": "markdown", "description": "返回格式"},
                "timeout": {"type": "integer", "default": 30, "minimum": 1, "description": "请求超时时间（秒）"}
            },
            required=["url"],
        ),
        example_args={"url": "https://httpx.readthedocs.io/en/latest/", "format": "markdown", "timeout": 30},
        side_effects={"network"},  # 网络访问
        external_bins_required=set(),
        external_bins_optional={"curl", "wget"},  # 可选的外部工具
        visible_in_prompt=True,
        callable_by_model=True,
        exec_command_key=None,
        handler=_h_webfetch,
    )


def _h_load_skill(loop: "AgentLoop", args: dict[str, Any]) -> ToolResult:
    """处理器：load_skill（加载技能）。"""
    skill_name = args.get("skill_name", "")

    return loop.tools.load_skill(skill_name)


def _spec_load_skill() -> ToolSpec:
    """ToolSpec：load_skill（加载技能）。"""
    return ToolSpec(
        name="load_skill",
        summary="加载和执行预定义的技能。",
        args_schema=_obj_schema(
            properties={
                "skill_name": {"type": "string", "description": "技能名称（文件名，不含扩展名）"}
            },
            required=["skill_name"],
        ),
        example_args={"skill_name": "refactor"},
        side_effects={"read"},
        external_bins_required=set(),
        external_bins_optional=set(),
        visible_in_prompt=True,
        callable_by_model=True,
        exec_command_key=None,
        handler=_h_load_skill,
    )


def _h_todowrite(loop: "AgentLoop", args: dict[str, Any]) -> ToolResult:
    """处理器：todowrite（创建任务）。"""
    content = args.get("content", "")
    priority = args.get("priority", "medium")
    status = args.get("status", "pending")

    return loop.tools.todowrite(content=content, priority=priority, status=status)


def _spec_todowrite() -> ToolSpec:
    """ToolSpec：todowrite（创建任务）。"""
    return ToolSpec(
        name="todowrite",
        summary="创建或更新任务列表。",
        args_schema=_obj_schema(
            properties={
                "content": {"type": "string", "description": "任务内容"},
                "priority": {"type": "string", "enum": ["high", "medium", "low"], "default": "medium", "description": "优先级"},
                "status": {"type": "string", "enum": ["pending", "in_progress", "completed", "cancelled"], "default": "pending", "description": "状态"}
            },
            required=["content"],
        ),
        example_args={"content": "修复登录bug", "priority": "high", "status": "pending"},
        side_effects={"write"},  # 可能写入任务文件
        external_bins_required=set(),
        external_bins_optional=set(),
        visible_in_prompt=True,
        callable_by_model=True,
        exec_command_key=None,
        handler=_h_todowrite,
    )


def _h_todoread(loop: "AgentLoop", args: dict[str, Any]) -> ToolResult:
    """处理器：todoread（读取任务）。"""
    status = args.get("status")
    todo_id = args.get("todo_id")

    return loop.tools.todoread(status=status, todo_id=todo_id)


def _spec_todoread() -> ToolSpec:
    """ToolSpec：todoread（读取任务）。"""
    return ToolSpec(
        name="todoread",
        summary="读取任务列表。",
        args_schema=_obj_schema(
            properties={
                "status": {"type": "string", "enum": ["pending", "in_progress", "completed", "cancelled"], "description": "过滤状态"},
                "todo_id": {"type": "string", "description": "特定任务ID"}
            },
            required=[],
        ),
        example_args={"status": "pending"},
        side_effects={"read"},
        external_bins_required=set(),
        external_bins_optional=set(),
        visible_in_prompt=True,
        callable_by_model=True,
        exec_command_key=None,
        handler=_h_todoread,
    )


def _h_websearch(loop: "AgentLoop", args: dict[str, Any]) -> ToolResult:
    """处理器：websearch（网页搜索）。"""
    query = args.get("query", "")
    num_results = args.get("num_results", 8)
    livecrawl = args.get("livecrawl", "fallback")
    search_type = args.get("search_type", "auto")
    context_max_chars = args.get("context_max_chars", 10000)

    return loop.tools.websearch(query=query, num_results=num_results, livecrawl=livecrawl, search_type=search_type, context_max_chars=context_max_chars)


def _spec_websearch() -> ToolSpec:
    """ToolSpec：websearch（网页搜索）。"""
    return ToolSpec(
        name="websearch",
        summary="执行实时网页搜索（返回标题/链接/摘要）。",
        description=(
            "用于“找资料/找页面”，返回搜索结果列表（title/url/snippet）。\n"
            "- 如需阅读全文：拿 websearch 的 url 再用 webfetch 抓取页面内容。\n"
            "- 搜索源由配置决定（Open-WebSearch MCP / Serper）。"
        ),
        args_schema=_obj_schema(
            properties={
                "query": {"type": "string", "description": "搜索查询"},
                "num_results": {"type": "integer", "default": 8, "minimum": 1, "description": "返回结果数量"},
                "livecrawl": {"type": "string", "enum": ["fallback", "preferred"], "default": "fallback", "description": "实时爬取模式"},
                "search_type": {"type": "string", "enum": ["auto", "fast", "deep"], "default": "auto", "description": "搜索类型"},
                "context_max_chars": {"type": "integer", "default": 10000, "minimum": 1000, "description": "上下文最大字符数"}
            },
            required=["query"],
        ),
        example_args={"query": "httpx timeout best practices", "num_results": 5},
        side_effects={"network"},
        external_bins_required=set(),
        external_bins_optional=set(),
        visible_in_prompt=True,
        callable_by_model=True,
        exec_command_key=None,
        handler=_h_websearch,
    )


def _h_codesearch(loop: "AgentLoop", args: dict[str, Any]) -> ToolResult:
    """处理器：codesearch（代码搜索）。"""
    query = args.get("query", "")
    tokens_num = args.get("tokens_num", 5000)

    return loop.tools.codesearch(query=query, tokens_num=tokens_num)


def _spec_codesearch() -> ToolSpec:
    """ToolSpec：codesearch（网络代码搜索）。"""
    return ToolSpec(
        name="codesearch",
        summary="网络搜索开源代码片段（网络）。",
        description=(
            "用于编程任务的代码片段检索（Network Code Search）。\n"
            "- 适合：查找某库/某框架的典型用法、报错修复示例、实现模式（会返回代码片段）。\n"
            "- 不适合：读取当前仓库源码（请优先用 read_file/grep/search_semantic）。\n"
            "注意：返回的是开源匹配片段，可能需要根据项目上下文改造与验证（tests/lint）。"
        ),
        args_schema=_obj_schema(
            properties={
                "query": {
                    "type": "string",
                    "description": "代码搜索查询（建议包含库名/函数名/关键字/语言，例如 'python httpx timeout Client'）",
                },
                "tokens_num": {
                    "type": "integer",
                    "default": 5000,
                    "minimum": 500,
                    "maximum": 50000,
                    "description": "输出预算（越大返回越多；工具会做上限与截断，避免刷屏）。",
                }
            },
            required=["query"],
        ),
        example_args={"query": "python httpx Client timeout usage", "tokens_num": 2500},
        side_effects={"network"},  # 可能需要外部API
        external_bins_required=set(),
        external_bins_optional=set(),
        visible_in_prompt=True,
        callable_by_model=True,
        exec_command_key=None,
        handler=_h_codesearch,
    )


def _h_run_task(loop: "AgentLoop", args: dict[str, Any]) -> ToolResult:
    """处理器：run_task（运行子代理任务）。"""
    description = args.get("description", "")
    prompt = args.get("prompt", "")
    subagent_type = args.get("subagent_type", "general")
    session_id = args.get("session_id")

    return loop.tools.run_task(description=description, prompt=prompt, subagent_type=subagent_type, session_id=session_id)


def _spec_run_task() -> ToolSpec:
    """ToolSpec：run_task（运行子代理任务）。"""
    return ToolSpec(
        name="run_task",
        summary="启动和管理系统中的子代理。",
        args_schema=_obj_schema(
            properties={
                "description": {"type": "string", "description": "任务描述"},
                "prompt": {"type": "string", "description": "代理提示"},
                "subagent_type": {"type": "string", "enum": ["general", "explore"], "default": "general", "description": "代理类型"},
                "session_id": {"type": "string", "description": "会话ID"}
            },
            required=["description", "prompt"],
        ),
        example_args={"description": "分析代码库结构", "prompt": "请分析这个项目的架构", "subagent_type": "explore"},
        side_effects={"exec"},  # 可能执行子代理
        external_bins_required=set(),
        external_bins_optional=set(),
        visible_in_prompt=True,
        callable_by_model=True,
        exec_command_key=None,
        handler=_h_run_task,
    )


def _h_get_task_status(loop: "AgentLoop", args: dict[str, Any]) -> ToolResult:
    """处理器：get_task_status（获取任务状态）。"""
    task_id = args.get("task_id", "")

    return loop.tools.get_task_status(task_id)


def _spec_get_task_status() -> ToolSpec:
    """ToolSpec：get_task_status（获取任务状态）。"""
    return ToolSpec(
        name="get_task_status",
        summary="获取子代理任务的状态。",
        args_schema=_obj_schema(
            properties={
                "task_id": {"type": "string", "description": "任务ID"}
            },
            required=["task_id"],
        ),
        example_args={"task_id": "task_123"},
        side_effects={"read"},
        external_bins_required=set(),
        external_bins_optional=set(),
        visible_in_prompt=True,
        callable_by_model=True,
        exec_command_key=None,
        handler=_h_get_task_status,
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 天气工具（OpenWeatherMap API）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _h_get_weather(loop: "AgentLoop", args: dict[str, Any]) -> ToolResult:
    """处理器：get_weather（获取实时天气）。"""
    city = args.get("city")
    lat = args.get("lat")
    lon = args.get("lon")
    units = args.get("units", "metric")
    lang = args.get("lang", "zh_cn")
    timeout = args.get("timeout", 10)

    return loop.tools.get_weather(
        city=city, lat=lat, lon=lon, units=units, lang=lang, timeout=timeout
    )


def _spec_get_weather() -> ToolSpec:
    """
    ToolSpec：get_weather（获取实时天气）
    
    使用 OpenWeatherMap API 获取全球任意城市的实时天气信息。
    支持城市名查询和经纬度查询两种方式。
    
    环境变量配置：
    - OPENWEATHERMAP_API_KEY: OpenWeatherMap API Key（必需）
    
    获取免费 API Key: https://openweathermap.org/api
    """
    return ToolSpec(
        name="get_weather",
        summary="获取实时天气信息（OpenWeatherMap）",
        description="使用 OpenWeatherMap API 获取全球城市的实时天气，支持城市名或经纬度查询，返回温度、湿度、风速等详细信息。",
        args_schema=_obj_schema(
            properties={
                "city": {
                    "type": "string",
                    "description": "城市名称（支持中文、英文），如 'Beijing', '北京', 'London'"
                },
                "lat": {
                    "type": "number",
                    "description": "纬度（-90 到 90），与 lon 配合使用",
                    "minimum": -90,
                    "maximum": 90
                },
                "lon": {
                    "type": "number",
                    "description": "经度（-180 到 180），与 lat 配合使用",
                    "minimum": -180,
                    "maximum": 180
                },
                "units": {
                    "type": "string",
                    "enum": ["metric", "imperial", "standard"],
                    "default": "metric",
                    "description": "温度单位：metric=摄氏度（默认），imperial=华氏度，standard=开尔文"
                },
                "lang": {
                    "type": "string",
                    "default": "zh_cn",
                    "description": "返回语言（默认中文 zh_cn）"
                },
                "timeout": {
                    "type": "integer",
                    "default": 10,
                    "minimum": 1,
                    "maximum": 60,
                    "description": "请求超时时间（秒）"
                }
            },
            required=[],  # city 或 lat+lon 二选一
        ),
        example_args={"city": "Beijing", "units": "metric"},
        side_effects={"network"},
        external_bins_required=set(),
        external_bins_optional=set(),
        visible_in_prompt=True,
        callable_by_model=True,
        exec_command_key=None,
        handler=_h_get_weather,
        category="external_api",
        timeout_seconds=15,
        version="1.0.0",
    )


def _h_get_weather_forecast(loop: "AgentLoop", args: dict[str, Any]) -> ToolResult:
    """处理器：get_weather_forecast（获取天气预报）。"""
    city = args.get("city")
    lat = args.get("lat")
    lon = args.get("lon")
    units = args.get("units", "metric")
    lang = args.get("lang", "zh_cn")
    days = args.get("days", 5)
    timeout = args.get("timeout", 10)

    return loop.tools.get_weather_forecast(
        city=city, lat=lat, lon=lon, units=units, lang=lang, days=days, timeout=timeout
    )


def _spec_get_weather_forecast() -> ToolSpec:
    """
    ToolSpec：get_weather_forecast（获取天气预报）
    
    使用 OpenWeatherMap API 获取最多5天的天气预报。
    每3小时提供一个数据点，包含温度、湿度、降水概率等信息。
    """
    return ToolSpec(
        name="get_weather_forecast",
        summary="获取天气预报（最多5天）",
        description="使用 OpenWeatherMap API 获取未来5天的天气预报，每3小时一个数据点，包含温度、湿度、降水概率等。",
        args_schema=_obj_schema(
            properties={
                "city": {
                    "type": "string",
                    "description": "城市名称（支持中文、英文）"
                },
                "lat": {
                    "type": "number",
                    "description": "纬度（-90 到 90）",
                    "minimum": -90,
                    "maximum": 90
                },
                "lon": {
                    "type": "number",
                    "description": "经度（-180 到 180）",
                    "minimum": -180,
                    "maximum": 180
                },
                "units": {
                    "type": "string",
                    "enum": ["metric", "imperial", "standard"],
                    "default": "metric",
                    "description": "温度单位"
                },
                "lang": {
                    "type": "string",
                    "default": "zh_cn",
                    "description": "返回语言"
                },
                "days": {
                    "type": "integer",
                    "default": 5,
                    "minimum": 1,
                    "maximum": 5,
                    "description": "预报天数（最多5天）"
                },
                "timeout": {
                    "type": "integer",
                    "default": 10,
                    "minimum": 1,
                    "maximum": 60,
                    "description": "请求超时时间（秒）"
                }
            },
            required=[],
        ),
        example_args={"city": "Shanghai", "days": 3},
        side_effects={"network"},
        external_bins_required=set(),
        external_bins_optional=set(),
        visible_in_prompt=True,
        callable_by_model=True,
        exec_command_key=None,
        handler=_h_get_weather_forecast,
        category="external_api",
        timeout_seconds=15,
        version="1.0.0",
    )


def iter_tool_specs() -> Iterable[ToolSpec]:
    """
    返回所有工具规范（保持稳定顺序）。
    """
    yield _spec_list_dir()
    yield _spec_read_file()
    yield _spec_glob_file_search()
    yield _spec_grep()
    yield _spec_apply_patch()
    yield _spec_undo_patch()
    yield _spec_write_file()
    yield _spec_run_cmd()
    yield _spec_search_semantic()
    yield _spec_display()
    yield _spec_preview_multi_edit()
    yield _spec_internal_repo_map()
    yield _spec_question()
    yield _spec_webfetch()
    yield _spec_load_skill()
    yield _spec_todowrite()
    yield _spec_todoread()
    yield _spec_websearch()
    yield _spec_codesearch()
    yield _spec_run_task()
    yield _spec_get_task_status()
    yield _spec_get_weather()
    yield _spec_get_weather_forecast()


# 注册表驱动（业界版）：同一份注册表 = tool dispatch + tool prompt/help 的来源
TOOL_REGISTRY: dict[str, ToolSpec] = {s.name: s for s in iter_tool_specs()}

# 新增：集成工具注册表管理器
def get_tool_registry():
    """获取工具注册表管理器"""
    from clude_code.tooling.tool_registry import get_tool_registry as _get_registry
    registry = _get_registry()

    # 确保所有工具都已注册
    for tool_spec in iter_tool_specs():
        if not registry.get_tool(tool_spec.name):
            registry.register_tool(tool_spec)

    return registry


def render_tools_for_system_prompt(*, include_schema: bool = False) -> str:
    """
    为 SYSTEM_PROMPT 生成“可用工具清单”片段。
    - 默认只输出简洁示例（避免 system prompt 过长导致上下文挤压）
    - include_schema=True 时额外输出 JSON Schema（更适合写入 docs 或 debug）
    """
    lines: list[str] = []
    for spec in iter_tool_specs():
        if not spec.visible_in_prompt:
            continue
        ex = json.dumps(spec.example_args, ensure_ascii=False)
        lines.append(f"  - {spec.name}: {ex}")
        if include_schema:
            schema = json.dumps(spec.args_schema, ensure_ascii=False)
            lines.append(f"    - schema: {schema}")
            lines.append(f"    - summary: {spec.summary}")
    return "\n".join(lines)


def dispatch_tool(loop: "AgentLoop", name: str, args: dict[str, Any]) -> ToolResult:
    """
    工具分发（注册表驱动 + Pydantic 运行时强校验）。

    大文件治理说明：
    - 实现了阶段 B 运行时契约加固：在执行 handler 前拦截非法参数。
    """
    try:
        spec = TOOL_REGISTRY.get(name)
        if spec is None:
            return ToolResult(False, error={"code": "E_NO_TOOL", "message": f"unknown tool: {name}"})
        if not spec.callable_by_model:
            return ToolResult(False, error={"code": "E_NO_TOOL", "message": f"tool not callable: {name}"})

        # --- 运行时强校验拦截 (Phase B) ---
        # 真正分发前执行 Pydantic 强校验（包含自动转换）
        ok, validated_or_msg = spec.validate_args(args)
        if not ok:
            logger.warning(f"[yellow]⚠ 工具 {name} 参数校验失败: {validated_or_msg}[/yellow]")
            return ToolResult(ok=False, error={"code": "E_INVALID_ARGS", "message": f"参数校验失败: {validated_or_msg}"})
        
        # 校验通过，执行处理器（使用校验/转换后的参数，例如 "1" -> 1）
        return spec.handler(loop, validated_or_msg)  # type: ignore

    except KeyError as e:
        logger.error(f"[red]✗ 参数缺失: {e}[/red]", exc_info=True)
        return ToolResult(ok=False, error={"code": "E_INVALID_ARGS", "message": f"missing arg: {e}"})
    except Exception as e:
        logger.error(f"[red]✗ 工具执行异常: {e}[/red]", exc_info=True)
        return ToolResult(ok=False, error={"code": "E_TOOL", "message": str(e)})





