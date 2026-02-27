"""
入口文件 — 启动 Master Agent Graph

用法:
  # 交互式命令行
  python main.py

  # LangGraph Studio (开发调试)
  langgraph dev
"""

import os
import sys

# 确保 langgraph_vibe_engine 目录在 path 中
_this_dir = os.path.dirname(os.path.abspath(__file__))
if _this_dir not in sys.path:
    sys.path.insert(0, _this_dir)

# 加载 .env 文件（必须在 import agent 之前，因为 import 时会读取环境变量）
from dotenv import load_dotenv
load_dotenv(os.path.join(_this_dir, ".env"))

from langchain_core.messages import HumanMessage, AIMessage
from agent import master_graph


# ── Todo 显示 ──────────────────────────────────────────────

STATUS_ICONS = {
    "pending": "⬜",
    "in_progress": "🔄",
    "completed": "✅",
    "cancelled": "⛔",
}


def _print_todos(todos: list, label: str = ""):
    """美观打印 todo 列表"""
    if not todos:
        return
    if label:
        print(f"\n  {label}")
    for t in todos:
        icon = STATUS_ICONS.get(t.get("status", ""), "⬜")
        content = t.get("content", "")
        print(f"    {icon} {content}")
    print(flush=True)


def _todos_changed(old_todos: list, new_todos: list) -> bool:
    """检查 todos 是否发生了变化"""
    if len(old_todos) != len(new_todos):
        return True
    old_map = {t.get("id"): t for t in old_todos}
    new_map = {t.get("id"): t for t in new_todos}
    return old_map != new_map


# ── 主循环 ──────────────────────────────────────────────────

def run_interactive():
    """交互式命令行运行 Master Agent (streaming 模式, 实时展示 todos)"""
    print("=" * 60)
    print("  Vibe Engine — LangGraph Master Agent (DeepSeek)")
    print("  输入 'quit' 退出")
    print("  支持发送图片: 直接输入图片路径即可 (如 ~/photo.jpg)")
    print("=" * 60)

    # 初始 state
    state = {
        "messages": [],
        "workspace_id": "",
        "current_canvas_id": "",
        "current_canvas_content": "",
        "current_canvas_title": "",
        "canvas_tool": None,
        "url_data": {},
        "todos": [],
    }

    while True:
        try:
            user_input = input("\n🧑 You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n\nBye!")
            break

        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit", "q"):
            print("Bye!")
            break

        # 追加用户消息
        state["messages"].append(HumanMessage(content=user_input))

        # 使用 stream 实时获取中间状态, 监听 todo 变化
        print("\n🤖 Vibe: ", end="", flush=True)

        prev_todos = list(state.get("todos", []))
        last_ai_content = ""

        for chunk in master_graph.stream(state, stream_mode="values"):
            # stream_mode="values" → 每次 yield 完整的 state snapshot
            current_todos = chunk.get("todos", [])
            if _todos_changed(prev_todos, current_todos):
                _print_todos(current_todos, "📋 Task Progress:")
                prev_todos = list(current_todos)

            # 记录最后一条 AI 消息用于最终输出
            for msg in reversed(chunk.get("messages", [])):
                if isinstance(msg, AIMessage) and msg.content:
                    last_ai_content = msg.content
                    break

        # stream 结束 → chunk 就是最终 state
        state = chunk

        # 打印最后一条 AI 消息
        if last_ai_content:
            print(last_ai_content)


# LangGraph Studio 入口 — langgraph.json 中引用此 graph
graph = master_graph
#启动是langgraph dev

if __name__ == "__main__":
    run_interactive()
