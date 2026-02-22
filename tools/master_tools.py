"""
Master Agent 专用工具 — research, image_generation (调用 SubAgent), todo_write

对应原项目 agent/tools.py 中 Master 独有的工具。
research / image_generation 在原项目中是 "调用 SubAgent" 的工具。
在 LangGraph 中，这些调用会被 Master Graph 的路由逻辑检测到，
然后路由到对应的 SubGraph 节点。
"""

import json
from langchain_core.tools import tool


# ── 内存 Todo 存储 ─────────────────────────────────────────
# 结构: { "id": { "id": str, "content": str, "status": str } }
_TODOS: dict[str, dict] = {}


def get_all_todos() -> list[dict]:
    """返回当前所有 todo 项（供 agent.py 同步 state 使用）"""
    return list(_TODOS.values())


@tool
def research(research_task: str, mode: str = "scratchpad", research_sub_workspace: str = "") -> str:
    """Invoke the Research SubAgent to conduct web research.

    This tool dispatches a research task to the Research SubAgent.
    In the LangGraph implementation, calling this tool triggers the Research SubGraph.

    Args:
        research_task: Detailed research instructions for the SubAgent.
        mode: "persist" (save to canvas) or "scratchpad" (in-memory). Default "scratchpad".
        research_sub_workspace: Canvas path for persist mode. Required when mode="persist".
    """
    return f"Research task dispatched: mode={mode}, workspace={research_sub_workspace}"


@tool
def image_generation(instruction: str, source_image_url: str = "") -> str:
    """Invoke the ImageGeneration SubAgent to create or modify images.

    This tool dispatches an image generation/editing task to the ImageGeneration SubAgent.
    - For text-to-image: provide only the instruction (source_image_url should be empty)
    - For image-to-image: provide both the instruction and the source_image_url

    Capabilities:
    - Text-to-Image: Create original images from detailed text descriptions
    - Image-to-Image: Modify existing images with style transfers, edits, enhancements

    Uses Doubao Seed 2.0 model for high-quality image generation.

    Args:
        instruction: Detailed instructions for image generation or editing.
                    Include subject, composition, style, colors, mood, etc.
        source_image_url: URL of the source image for img2img tasks.
                         Leave empty for text-to-image generation.
    """
    task_type = "img2img" if source_image_url else "text2img"
    return f"Image generation task dispatched: type={task_type}"


@tool
def todo_write(todos: str, merge: bool = True) -> str:
    """Create or update a structured task list for workflow tracking.

    Args:
        todos: JSON array of todo items, each with 'id', 'content', 'status'.
              status can be: "pending", "in_progress", "completed", "cancelled".
              Example: [{"id": "1", "content": "Research topic X", "status": "in_progress"}]
        merge: If true, merge into existing todos (update by id). If false, replace all todos.
    """
    VALID_STATUSES = {"pending", "in_progress", "completed", "cancelled"}

    try:
        items = json.loads(todos)
    except json.JSONDecodeError as e:
        return f"Error: Invalid JSON — {e}"

    if not isinstance(items, list):
        return "Error: 'todos' must be a JSON array."

    # 校验每个 item
    for item in items:
        if not isinstance(item, dict):
            return f"Error: Each todo item must be an object, got {type(item).__name__}."
        if "id" not in item or "content" not in item or "status" not in item:
            return "Error: Each todo item must have 'id', 'content', and 'status' fields."
        if item["status"] not in VALID_STATUSES:
            return f"Error: Invalid status '{item['status']}'. Must be one of {VALID_STATUSES}."

    if not merge:
        _TODOS.clear()

    # 写入/更新
    for item in items:
        tid = str(item["id"])
        _TODOS[tid] = {
            "id": tid,
            "content": item["content"],
            "status": item["status"],
        }

    # 生成摘要
    total = len(_TODOS)
    by_status = {}
    for t in _TODOS.values():
        by_status[t["status"]] = by_status.get(t["status"], 0) + 1
    status_summary = ", ".join(f"{s}: {c}" for s, c in sorted(by_status.items()))

    return f"Todos updated ({total} total — {status_summary})."
