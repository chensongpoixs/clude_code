from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, Iterable, TYPE_CHECKING

from clude_code.tooling.local_tools import ToolResult

if TYPE_CHECKING:
    from .agent_loop import AgentLoop


ToolHandler = Callable[["AgentLoop", dict[str, Any]], ToolResult]


@dataclass(frozen=True)
class ToolSpec:
    """
    工具规范（业界做法：同一份“工具事实”驱动 dispatch、prompt、help、policy/doctor）。
    """

    name: str
    summary: str
    args_schema: dict[str, Any]
    example_args: dict[str, Any]
    side_effects: set[str]  # {"read","write","exec","search"}（可扩展）
    handler: ToolHandler


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


def _obj_schema(*, properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": required or [],
        "additionalProperties": False,
    }


def iter_tool_specs() -> Iterable[ToolSpec]:
    """
    返回所有工具规范（保持稳定顺序）。
    """
    yield ToolSpec(
        name="list_dir",
        summary="列出目录内容（只读）。",
        args_schema=_obj_schema(
            properties={"path": {"type": "string", "default": ".", "description": "相对工作区的目录路径"}},
            required=[],
        ),
        example_args={"path": "."},
        side_effects={"read"},
        handler=_h_list_dir,
    )
    yield ToolSpec(
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
        handler=_h_read_file,
    )
    yield ToolSpec(
        name="glob_file_search",
        summary="按文件名模式查找文件（只读，支持 ** 递归）。",
        args_schema=_obj_schema(
            properties={
                "glob_pattern": {"type": "string", "description": "glob 模式，例如 **/*.py"},
                "target_directory": {"type": "string", "default": ".", "description": "搜索根目录（相对工作区）"},
            },
            required=["glob_pattern"],
        ),
        example_args={"glob_pattern": "**/*.py", "target_directory": "."},
        side_effects={"read"},
        handler=_h_glob_file_search,
    )
    yield ToolSpec(
        name="grep",
        summary="代码搜索（优先 rg，fallback Python）。",
        args_schema=_obj_schema(
            properties={
                "pattern": {"type": "string", "description": "正则表达式"},
                "path": {"type": "string", "default": ".", "description": "搜索路径（相对工作区）"},
                "ignore_case": {"type": "boolean", "default": False, "description": "是否忽略大小写"},
                "max_hits": {"type": "integer", "default": 200, "minimum": 1, "description": "最多返回条数"},
            },
            required=["pattern"],
        ),
        example_args={"pattern": "class\\s+AgentLoop", "path": "src", "ignore_case": False, "max_hits": 200},
        side_effects={"read"},
        handler=_h_grep,
    )
    yield ToolSpec(
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
        example_args={"path": "src/a.py", "old": "x = 1", "new": "x = 2", "expected_replacements": 1, "fuzzy": False, "min_similarity": 0.92},
        side_effects={"write"},
        handler=_h_apply_patch,
    )
    yield ToolSpec(
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
        handler=_h_undo_patch,
    )
    yield ToolSpec(
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
        handler=_h_write_file,
    )
    yield ToolSpec(
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
        handler=_h_run_cmd,
    )
    yield ToolSpec(
        name="search_semantic",
        summary="语义检索（向量 RAG，只读）。",
        args_schema=_obj_schema(
            properties={"query": {"type": "string", "description": "查询文本"}},
            required=["query"],
        ),
        example_args={"query": "向量索引在哪里实现？"},
        side_effects={"search", "read"},
        handler=_h_search_semantic,
    )


# 注册表驱动（业界版）：同一份注册表 = tool dispatch + tool prompt/help 的来源
TOOL_REGISTRY: dict[str, ToolSpec] = {s.name: s for s in iter_tool_specs()}


def render_tools_for_system_prompt(*, include_schema: bool = False) -> str:
    """
    为 SYSTEM_PROMPT 生成“可用工具清单”片段。
    - 默认只输出简洁示例（避免 system prompt 过长导致上下文挤压）
    - include_schema=True 时额外输出 JSON Schema（更适合写入 docs 或 debug）
    """
    lines: list[str] = []
    for spec in iter_tool_specs():
        ex = json.dumps(spec.example_args, ensure_ascii=False)
        lines.append(f"  - {spec.name}: {ex}")
        if include_schema:
            schema = json.dumps(spec.args_schema, ensure_ascii=False)
            lines.append(f"    - schema: {schema}")
            lines.append(f"    - summary: {spec.summary}")
    return "\n".join(lines)


def dispatch_tool(loop: "AgentLoop", name: str, args: dict[str, Any]) -> ToolResult:
    """
    工具分发（注册表驱动）。

    大文件治理说明：
    - Tooling 常随项目增长而膨胀，把分发逻辑拆出便于维护/测试。
    """
    try:
        spec = TOOL_REGISTRY.get(name)
        if spec is None:
            return ToolResult(False, error={"code": "E_NO_TOOL", "message": f"unknown tool: {name}"})
        return spec.handler(loop, args)
    except KeyError as e:
        return ToolResult(False, error={"code": "E_INVALID_ARGS", "message": f"missing arg: {e}"})
    except Exception as e:
        return ToolResult(False, error={"code": "E_TOOL", "message": str(e)})


