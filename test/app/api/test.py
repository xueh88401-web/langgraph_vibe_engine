"""
画布操作工具 — 纯内存模拟版

用一个全局 dict 模拟 workspace，所有画布存在内存里。
先跑通 Graph 流程，后续可替换为:
  方案A: 接原项目的 workspace 服务 (tools/workspace_tool.py)
  方案B: 接第三方文档 API
"""

import json
from typing import Optional
from langchain_core.tools import tool


# ── 内存 Workspace ──────────────────────────────────────
# 结构: { "/path/to/canvas": { "title": str, "content": [line1, line2, ...] } }
_WORKSPACE: dict[str, dict] = {"/": {"title": "root", "content": []}, "/test": {"title": "test", "content": ["hello", "world"]}}


def _normalize_path(path: str) -> str:
    """统一路径格式: 确保 / 开头，去掉尾部 /"""
    path = path.strip()
    if not path.startswith("/"):
        path = "/" + path
    path = path.rstrip("/")
    return path or "/"


def _get_canvas(path: str) -> Optional[dict]:
    return _WORKSPACE.get(_normalize_path(path))


def _list_children(parent: str) -> list[str]:
    """列出某个路径下的直接子画布"""
    parent = _normalize_path(parent)
    prefix = parent if parent == "/" else parent + "/"
    children = []
    for p in _WORKSPACE:
        if p == parent:
            continue
        if p.startswith(prefix):
            # 只取直接子级 (prefix 之后不再有 /)
            remainder = p[len(prefix):]
            if "/" not in remainder:
                children.append(p)
    return sorted(children)


# ── LangChain Tools ─────────────────────────────────────

@tool
def canvas_create(title: str, content: str, parent_canvas_path: str = "/") -> str:
    """Create a new canvas (document) in the workspace.

    Args:
        title: Title of the new canvas.
        content: Full Markdown content to write.
        parent_canvas_path: Parent path in workspace tree. Default is root "/".
    """
    parent = _normalize_path(parent_canvas_path)
    full_path = parent + "/" + title.strip() if parent != "/" else "/" + title.strip()
    full_path = _normalize_path(full_path)

    if full_path in _WORKSPACE:
        return f"Error: Canvas already exists at '{full_path}'"

    lines = content.split("\n") if content else []
    _WORKSPACE[full_path] = {"title": title.strip(), "content": lines}
    return f"Canvas created at '{full_path}' ({len(lines)} lines)"


@tool
def canvas_update(target_canvas_path: str, operations: str) -> str:
    """Update an existing canvas by replacing specific line ranges.

    Args:
        target_canvas_path: Path of the canvas to update.
        operations: JSON array of operations, each with 'start_line', 'end_line', 'new_str'.
                    Example: '[{"start_line": 1, "end_line": 3, "new_str": "replaced text"}]'
    """
    path = _normalize_path(target_canvas_path)
    canvas = _get_canvas(path)
    if not canvas:
        return f"Error: Canvas not found at '{path}'"

    try:
        ops = json.loads(operations)
    except json.JSONDecodeError as e:
        return f"Error: Invalid JSON in operations: {e}"

    lines = list(canvas["content"])
    # 按 start_line 降序排列，从后往前替换避免行号偏移
    ops_sorted = sorted(ops, key=lambda o: o.get("start_line", 0), reverse=True)
    for op in ops_sorted:
        start = int(op.get("start_line", 1)) - 1  # 转 0-based
        end = int(op.get("end_line", start + 1))    # 1-based inclusive
        new_lines = op.get("new_str", "").split("\n")
        lines[start:end] = new_lines

    canvas["content"] = lines
    return f"Canvas updated at '{path}' (now {len(lines)} lines, {len(ops)} operations applied)"


@tool
def canvas_insert(target_canvas_path: str, insert_line: int, content: str) -> str:
    """Insert new content at a specific line in the canvas.

    Args:
        target_canvas_path: Path of the canvas.
        insert_line: Line number to insert after (0 = before first line, 1-based).
        content: Content to insert.
    """
    path = _normalize_path(target_canvas_path)
    canvas = _get_canvas(path)
    if not canvas:
        return f"Error: Canvas not found at '{path}'"

    new_lines = content.split("\n") if content else [""]
    pos = max(0, min(insert_line, len(canvas["content"])))
    canvas["content"][pos:pos] = new_lines
    return f"Inserted {len(new_lines)} lines after line {insert_line} in '{path}' (now {len(canvas['content'])} lines)"


@tool
def canvas_delete(target_canvas_path: str) -> str:
    """Delete a canvas from the workspace.

    Args:
        target_canvas_path: Path of the canvas to delete.
    """
    path = _normalize_path(target_canvas_path)
    if path not in _WORKSPACE:
        return f"Error: Canvas not found at '{path}'"
    del _WORKSPACE[path]
    return f"Canvas deleted: '{path}'"


@tool
def get_directory(path: str = "/") -> str:
    """Get the workspace directory tree at the given path.

    Args:
        path: Directory path to list. Default is root "/" for full tree.
    """
    if not _WORKSPACE:
        return "Workspace is empty. No canvases exist yet."

    path = _normalize_path(path)

    def _build_tree(parent: str, indent: str = "") -> str:
        children = _list_children(parent)
        result = ""
        for i, child_path in enumerate(children):
            is_last = (i == len(children) - 1)
            connector = "└── " if is_last else "├── "
            title = _WORKSPACE[child_path]["title"]
            line_count = len(_WORKSPACE[child_path]["content"])
            grandchildren = _list_children(child_path)
            suffix = "/" if grandchildren else ""
            result += f"{indent}{connector}{title}{suffix} ({line_count} lines)\n"
            if grandchildren:
                next_indent = indent + ("    " if is_last else "│   ")
                result += _build_tree(child_path, next_indent)
        return result

    # 根路径
    if path == "/":
        header = "Workspace directory:\n"
        tree = _build_tree("/")
        # 也列出根级画布
        root_canvases = _list_children("/")
        if not root_canvases and not tree:
            return "Workspace is empty."
        return header + tree
    else:
        canvas = _get_canvas(path)
        if not canvas:
            return f"Error: Path '{path}' not found"
        title = canvas["title"]
        header = f"Subtree at '{path}':\n"
        tree = _build_tree(path)
        return header + tree if tree else f"'{path}' has no children."


@tool
def read_document(target_canvas_path: str) -> str:
    """Read the full content of a canvas with line numbers.

    Args:
        target_canvas_path: Path of the canvas to read.
    """
    path = _normalize_path(target_canvas_path)
    canvas = _get_canvas(path)
    if not canvas:
        return f"Error: Canvas not found at '{path}'"

    lines = canvas["content"]
    if not lines:
        return f"Canvas '{path}' exists but is empty."

    numbered = [f"{i+1:3d}| {line}" for i, line in enumerate(lines)]
    return f"Content of {path} (entire document, {len(lines)} lines):\n" + "\n".join(numbered)


@tool
def search_in_workspace(query: str) -> str:
    """Search across all canvases in the workspace by keyword.

    Args:
        query: Search keyword.
    """
    query_lower = query.lower()
    results = []
    for path, canvas in _WORKSPACE.items():
        content_text = "\n".join(canvas["content"])
        if query_lower in content_text.lower() or query_lower in canvas["title"].lower():
            # 找到包含关键词的行
            highlights = []
            for i, line in enumerate(canvas["content"]):
                if query_lower in line.lower():
                    highlights.append(f"  L{i+1}: {line.strip()[:100]}")
            results.append(f"<path>{path}</path>\n<title>{canvas['title']}</title>\n" +
                         "\n".join(highlights[:3]))  # 最多 3 行高亮

    if not results:
        return f"No results found for '{query}'"
    return f"Found {len(results)} canvas(es) matching '{query}':\n\n" + "\n\n".join(results)

@tool
def get_directory_tree(path: str = "/") -> str:
    """Return structured JSON tree for frontend file explorer."""
    path = _normalize_path(path)

    def build(parent: str):
        nodes = []
        children = _list_children(parent)
        for child in children:
            canvas = _WORKSPACE[child]
            grandchildren = _list_children(child)

            nodes.append({
                "name": canvas["title"],
                "path": child,
                "type": "folder" if grandchildren else "file",
                "line_count": len(canvas["content"]),
                "children": build(child) if grandchildren else []
            })
        return nodes

    tree = build(path)
    return json.dumps(tree, ensure_ascii=False)