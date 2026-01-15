from __future__ import annotations

import json
import logging
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


def _h_write_file(loop: "AgentLoop", args: dict[str, Any]) -> ToolResult:
    return loop.tools.write_file(path=args["path"], text=args.get("text", ""))


def _h_run_cmd(loop: "AgentLoop", args: dict[str, Any]) -> ToolResult:
    return loop.tools.run_cmd(command=args["command"], cwd=args.get("cwd", "."))


def _h_search_semantic(loop: "AgentLoop", args: dict[str, Any]) -> ToolResult:
    # 语义检索属于 AgentLoop 的能力（依赖 embedder/vector_store），不直接放在 LocalTools
    return loop._semantic_search(query=args["query"])


def _h_display(loop: "AgentLoop", args: dict[str, Any]) -> ToolResult:
    """
    向用户输出信息（进度、分析结果、说明等）。

    实现原理：
    1. 从 AgentLoop 获取当前的 _ev 回调和 trace_id
    2. 通过 _ev("display", {...}) 触发界面更新
    3. 返回 ToolResult 给模型（payload 包含显示内容）
    """
    content = args.get("content", "")
    level = args.get("level", "info")
    title = args.get("title")

    # 触发界面显示事件
    loop._ev("display", {
        "content": content,
        "level": level,
        "title": title,
        "timestamp": time.time(),
    })

    return ToolResult(True, payload={"displayed": True, "content": content})


def _h_internal_repo_map(loop: "AgentLoop", args: dict[str, Any]) -> ToolResult:
    return loop.tools.internal_repo_map()


def _run_local_tool(name: str, args: dict[str, Any]) -> ToolResult:
    """Legacy helper - should not be used in new code."""
    raise NotImplementedError(f"_run_local_tool is deprecated. Use proper tool handlers instead.")


def _spec_list_dir() -> ToolSpec:
    """ToolSpec：list_dir（只读）。"""
    return ToolSpec(
        name="list_dir",
        summary="列出目录内容（只读）。",
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
        args_schema=_obj_schema(
            properties={
                "glob_pattern": {"type": "string", "description": "glob 模式，例如 **/*.md, **/*.py, **/*.cpp, **/*.c, **/*.h, **/*.cc, **/*.java, **/*.js, **/*.ts, **/*.html, **/*.css, **/*.json, **/*.xml"},
                "target_directory": {"type": "string", "default": ".", "description": "搜索根目录（相对工作区）"},
            },
            required=["glob_pattern"],
        ),
        example_args={"glob_pattern": "**/*.*", "target_directory": "."},
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
        args_schema=_obj_schema(
            properties={
                "path": {"type": "string", "description": "目标文件路径（相对工作区）"},
                "text": {"type": "string", "default": "", "description": "写入内容"},
            },
            required=["path"],
        ),
        example_args={"path": "notes.txt", "text": "hello"},
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
        args_schema=_obj_schema(
            properties={
                "command": {"type": "string", "description": "要执行的命令字符串"},
                "cwd": {"type": "string", "default": ".", "description": "工作目录（相对工作区）"},
            },
            required=["command"],
        ),
        example_args={"command": "python -m pytest -q", "cwd": "."},
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
        summary="显示消息给用户（只读）。",
        args_schema=_obj_schema(
            properties={
                "message": {"type": "string", "description": "要显示的消息"},
            },
            required=["message"],
        ),
        example_args={"message": "操作已完成"},
        side_effects={"read"},
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
        editor = get_advanced_code_editor(loop.workspace_root)

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
            return ToolResult(False, error={"code": "E_INVALID_ARGS", "message": f"参数校验失败: {validated_or_msg}"})
        
        # 校验通过，执行处理器（使用校验/转换后的参数，例如 "1" -> 1）
        return spec.handler(loop, validated_or_msg)  # type: ignore

    except KeyError as e:
        logger.error(f"[red]✗ 参数缺失: {e}[/red]", exc_info=True)
        return ToolResult(False, error={"code": "E_INVALID_ARGS", "message": f"missing arg: {e}"})
    except Exception as e:
        logger.error(f"[red]✗ 工具执行异常: {e}[/red]", exc_info=True)
        return ToolResult(False, error={"code": "E_TOOL", "message": str(e)})


