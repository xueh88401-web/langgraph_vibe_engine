"""
Research SubAgent 专用工具 — archive_source, finish_research

对应原项目:
- agent/research_tools.py 中的 archive_source_into_scratchpad, finish_research_with_report
"""

from langchain_core.tools import tool


@tool
def archive_source_into_scratchpad(url: str, annotation: str, excerpted_line_ranges: str = "[]") -> str:
    """Archive a research source into the in-memory scratchpad (scratchpad mode only).

    Records the URL, annotation, and key excerpts for later synthesis into the final report.

    Args:
        url: Canonical URL of the source.
        annotation: Free-form annotation for this source.
        excerpted_line_ranges: JSON string of inclusive line ranges, e.g. [[1,1],[3,10]].
    """
    # TODO: 实现 scratchpad 存储逻辑
    # 原项目中写入 ctx.payload.research_scratchpad 和 research_scratchpad_store
    # 在 LangGraph 中可以通过 State 的 scratchpad 字段实现
    #
    # 简化实现思路:
    # 1. 从 tool 的 config 中获取 state 引用 (或用 RunnableConfig)
    # 2. 将 {url, annotation, excerpts} 追加到 state["scratchpad"]

    return f"Recorded into scratchpad: {url}"


@tool
def finish_research_with_report(report: str, command: str = "create", canvas_path: str = "") -> str:
    """Finalize the research report and signal task completion.

    This is a TERMINATING tool — calling it ends the Research SubAgent's execution.
    
    Under scratchpad mode: the report is returned directly to the MasterAgent.
    Under persist mode: the report is saved to the specified canvas_path.

    Args:
        report: The final synthesized research report text.
        command: Must be "create".
        canvas_path: Canvas path for persist mode (optional for scratchpad).
    """
    # 这个工具的返回值会被 Research Graph 的 should_continue 检测
    # 检测到此工具被调用后，graph 路由到 END

    return f"<done/>\nResearch report finalized ({len(report)} chars)."
