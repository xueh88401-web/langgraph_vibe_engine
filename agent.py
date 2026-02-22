"""
Master Agent Graph — 用 LangGraph StateGraph 实现

对应原项目:
- agent/master_agent_system.py (system prompt)
- agent/master_agent_init.py (context init / kickoff)
- agent/master_agent_context.py (ContextPayload / tool execution)
- vibeagent/agent.py (ReAct loop)

Graph 结构:
  ┌──────────────────┐
  │     __start__     │
  └────────┬─────────┘
           ▼
  ┌──────────────────┐
  │   master_agent   │◄─────────────────────────────┐
  └────────┬─────────┘                               │
           ▼                                         │
  ┌──────────────────┐                               │
  │     route        │                               │
  └──┬───┬───┬───┬───┘                               │
     │   │   │   │                                   │
     ▼   │   │   ▼                                   │
  tools  │   │  __end__                              │
     │   │   │                                       │
     │   ▼   ▼                                       │
     │  research  image_generation                   │
     │  _subgraph  _subgraph                         │
     │   │         │                                 │
     └───┴─────────┴─────────────────────────────────┘

路由逻辑:
- 如果 LLM 没有 tool_calls → __end__
- 如果 tool_calls 中包含 "research" → research_subgraph
- 如果 tool_calls 中包含 "image_generation" → image_subgraph
- 否则 → tools (普通工具执行)
"""

import os
import json
import datetime
from typing import Literal

from langchain_openai import ChatOpenAI
from langchain_core.messages import (
    SystemMessage,
    HumanMessage,
    AIMessage,
    ToolMessage,
)
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode

from state import VibeMasterState, VibeResearchState, VibeImageGenState
from prompts.master import MASTER_SYSTEM_PROMPT
from tools.web_tools import search_web, read_webpage
from tools.canvas_tools import (
    canvas_create,
    canvas_update,
    canvas_insert,
    canvas_delete,
    get_directory,
    read_document,
    search_in_workspace,
)
from tools.image_tools import upload_image
from tools.master_tools import research, image_generation, todo_write, get_all_todos, _TODOS
from research_graph import research_graph
from image_graph import image_graph


# ── 工具集 ──────────────────────────────────────────────────
# Master Agent 可用的全部工具 (包括 research 触发器)
MASTER_TOOLS = [
    # Web 工具
    search_web,
    read_webpage,
    # 画布工具
    canvas_create,
    canvas_update,
    canvas_insert,
    canvas_delete,
    get_directory,
    read_document,
    search_in_workspace,
    # 图片上传
    upload_image,
    # SubAgent 调用
    research,
    image_generation,
    # 辅助工具
    todo_write,
]

# SubAgent 触发器名称 (不由 ToolNode 执行，而是由 SubGraph 节点处理)
SUBAGENT_TOOL_NAMES = {"research", "image_generation"}

# 普通工具 (用于 ToolNode)
REGULAR_TOOLS = [t for t in MASTER_TOOLS if t.name not in SUBAGENT_TOOL_NAMES]


# ── LLM ──────────────────────────────────────────────────
def _get_master_llm():
    """创建 Master Agent 使用的 DeepSeek 模型实例"""
    return ChatOpenAI(
        model="deepseek-chat",
        base_url="https://api.deepseek.com/v1",
        api_key=os.environ.get("DEEPSEEK_API_KEY", ""),
        temperature=0.5,
        max_tokens=16384,
    ).bind_tools(MASTER_TOOLS)


# ── 节点 ──────────────────────────────────────────────────

def _format_todos_for_prompt(todos: list) -> str:
    """将 todos 列表格式化为注入 system prompt 的文本"""
    if not todos:
        return ""
    
    STATUS_ICONS = {
        "pending": "⬜",
        "in_progress": "🔄",
        "completed": "✅",
        "cancelled": "⛔",
    }
    lines = ["# Current Task Progress"]
    for t in todos:
        icon = STATUS_ICONS.get(t.get("status", ""), "⬜")
        lines.append(f"{icon} {t.get('content', '')} [{t.get('status', '')}]")
    return "\n".join(lines)


def master_agent_node(state: VibeMasterState) -> dict:
    """Master Agent 推理节点 — 调用 LLM 决定下一步动作
    
    对应原项目 ReAct loop 中的 LLM 调用:
    - vibeagent/llm/openai.py OpenaiLLM.call()
    - agent/master_agent_init.py context_init() + kickoff_message_generate()
    """
    llm = _get_master_llm()

    messages = list(state["messages"])

    # 构建 system prompt（每轮都刷新，确保 todos 最新）
    current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    current_todos = _format_todos_for_prompt(state.get("todos", []))
    system_prompt = MASTER_SYSTEM_PROMPT.format(
        current_time=current_time,
        current_todos=current_todos,
    )

    # 替换或插入 system prompt
    if messages and isinstance(messages[0], SystemMessage):
        messages[0] = SystemMessage(content=system_prompt)
    else:
        messages.insert(0, SystemMessage(content=system_prompt))

    response = llm.invoke(messages)

    return {"messages": [response]}


def master_tools_node(state: VibeMasterState) -> dict:
    """普通工具执行节点 — 执行除 research 外的所有工具
    
    对应原项目 ContextPayload.process_step() / execute_tools()
    执行后同步全局 _TODOS 到 state["todos"]。
    """
    tool_node = ToolNode(REGULAR_TOOLS)
    result = tool_node.invoke(state)

    # 同步 todos: 工具执行后，全局 _TODOS 可能已更新
    result["todos"] = get_all_todos()

    return result


def research_subgraph_node(state: VibeMasterState) -> dict:
    """Research SubGraph 调用节点
    
    从 Master 的 tool_calls 中提取 research 参数，
    构建 VibeResearchState，调用 research_graph，
    然后将结果作为 ToolMessage 注入回 Master 的消息序列。
    
    对应原项目 tools/research.py 中 Research.research() 的调用逻辑。
    """
    # 找到最后一条 AIMessage 中的 research tool_call
    last_ai_msg = None
    for msg in reversed(state["messages"]):
        if isinstance(msg, AIMessage) and msg.tool_calls:
            last_ai_msg = msg
            break

    if not last_ai_msg:
        return {"messages": []}

    # 处理所有 tool_calls: research 的交给 subgraph, 其他的也要返回 ToolMessage
    result_messages = []

    for tc in last_ai_msg.tool_calls:
        if tc["name"] == "research":
            # 提取 research 参数
            args = tc["args"]
            research_task = args.get("research_task", "")
            mode = args.get("mode", "scratchpad")
            research_sub_workspace = args.get("research_sub_workspace", "")

            # 构建 Research SubAgent 的初始 State
            research_state: VibeResearchState = {
                "messages": [
                    HumanMessage(content=research_task),
                ],
                "research_mode": mode,
                "research_sub_workspace": research_sub_workspace,
                "scratchpad": {},
                "budget_total": 5,
                "budget_used": 0,
                "canvas_tool": state.get("canvas_tool"),
                "url_data": state.get("url_data", {}),
                "is_terminated": False,
            }

            # 自动更新 todo: 标记 research 进行中
            _TODOS[f"subagent_research_{tc['id']}"] = {
                "id": f"subagent_research_{tc['id']}",
                "content": f"Research: {research_task[:50]}",
                "status": "in_progress",
            }

            # 调用 Research SubGraph
            research_result = research_graph.invoke(research_state)

            # 自动更新 todo: 标记 research 完成
            _TODOS[f"subagent_research_{tc['id']}"]["status"] = "completed"

            # 提取 research 最终结果
            research_messages = research_result.get("messages", [])
            # 取最后一条非 ToolMessage 的内容作为报告
            report = "Research completed."
            for msg in reversed(research_messages):
                if isinstance(msg, AIMessage) and msg.content:
                    report = msg.content
                    break
                elif isinstance(msg, ToolMessage) and "<done/>" in (msg.content or ""):
                    report = msg.content
                    break

            result_messages.append(
                ToolMessage(
                    content=report,
                    tool_call_id=tc["id"],
                    name="research",
                )
            )
        else:
            # 非 research 的 tool_call，用 ToolNode 执行
            # (理论上路由保证这里只有 research，但做兜底)
            result_messages.append(
                ToolMessage(
                    content=f"[Error] Unexpected tool '{tc['name']}' in research path.",
                    tool_call_id=tc["id"],
                    name=tc["name"],
                )
            )

    return {"messages": result_messages, "todos": get_all_todos()}


def image_subgraph_node(state: VibeMasterState) -> dict:
    """ImageGeneration SubGraph 调用节点
    
    从 Master 的 tool_calls 中提取 image_generation 参数,
    构建 VibeImageGenState, 调用 image_graph (标准 ReAct 循环),
    然后将结果作为 ToolMessage 注入回 Master 的消息序列.
    
    SubAgent 内部: Seed 2.0 Pro 自己调 text2img/img2img,
    看到结果后自己判断满不满意, 不满意就继续调工具.
    """
    last_ai_msg = None
    for msg in reversed(state["messages"]):
        if isinstance(msg, AIMessage) and msg.tool_calls:
            last_ai_msg = msg
            break

    if not last_ai_msg:
        return {"messages": []}

    result_messages = []

    for tc in last_ai_msg.tool_calls:
        if tc["name"] == "image_generation":
            args = tc["args"]
            instruction = args.get("instruction", "")
            source_image_url = args.get("source_image_url", "")

            # Build kickoff message — 如果有用户图片，构造多模态消息让 SubAgent 看到图
            if source_image_url:
                kickoff_content = [
                    {
                        "type": "text",
                        "text": (
                            f"The user has provided a reference/source image. "
                            f"You MUST carefully analyze this image yourself first "
                            f"(style, composition, colors, mood, subjects, etc.), "
                            f"then decide how to fulfill the user's request.\n\n"
                            f"User's request: {instruction}\n"
                            f"Source image URL: {source_image_url}\n\n"
                            f"IMPORTANT: The instruction above is the user's raw intent, "
                            f"NOT an analysis of the image. You must look at the image "
                            f"yourself and craft your own detailed prompt based on what "
                            f"you actually see in the image combined with the user's request."
                        ),
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": source_image_url},
                    },
                ]
                kickoff_msg = HumanMessage(content=kickoff_content)
            else:
                kickoff_msg = HumanMessage(content=f"Please generate an image: {instruction}")

            image_state: VibeImageGenState = {
                "messages": [kickoff_msg],
                "is_terminated": False,
            }

            task_type = "img2img" if source_image_url else "text2img"

            # 自动更新 todo: 标记 image_generation 进行中
            _TODOS[f"subagent_image_{tc['id']}"] = {
                "id": f"subagent_image_{tc['id']}",
                "content": f"Image ({task_type}): {instruction[:40]}",
                "status": "in_progress",
            }

            print(f"\n--- ImageGeneration SubAgent ({task_type}): {instruction[:60]}... ---")
            image_result = image_graph.invoke(image_state)
            print("--- ImageGeneration SubAgent finished. ---")

            # 自动更新 todo: 标记 image_generation 完成
            _TODOS[f"subagent_image_{tc['id']}"]["status"] = "completed"

            # Extract final report — 确保图片 URL 明确出现在返回中
            image_messages = image_result.get("messages", [])
            report = "Image generation completed."
            final_image_url = ""
            for msg in reversed(image_messages):
                if isinstance(msg, ToolMessage) and msg.name == "finish_image_generation":
                    report = msg.content
                    break
                elif isinstance(msg, AIMessage) and msg.content:
                    report = msg.content
                    break
            
            # 从所有消息中提取最后一个生成的图片 URL
            import re as _re
            for msg in reversed(image_messages):
                if isinstance(msg, ToolMessage) and msg.name in ("text2img", "img2img"):
                    m = _re.search(r'(?:Image URL|Modified image URL): (https?://\S+)', msg.content or "")
                    if m:
                        final_image_url = m.group(1)
                        break

            # 在 report 前加上明确的图片 URL 标记
            # ⚠️ 强调 URL 完整性, 防止 Master Agent 截断签名参数
            if final_image_url and final_image_url not in report:
                report = (
                    f"[Generated Image URL — DO NOT truncate or modify this URL, "
                    f"copy it EXACTLY as-is including all query parameters]: "
                    f"{final_image_url}\n\n{report}"
                )

            result_messages.append(
                ToolMessage(
                    content=report,
                    tool_call_id=tc["id"],
                    name="image_generation",
                )
            )
        else:
            result_messages.append(
                ToolMessage(
                    content=f"[Error] Unexpected tool '{tc['name']}' in image generation path.",
                    tool_call_id=tc["id"],
                    name=tc["name"],
                )
            )

    return {"messages": result_messages, "todos": get_all_todos()}


# ── 路由 ──────────────────────────────────────────────────

def _has_tool_call(ai_msg: AIMessage, tool_name: str) -> bool:
    """检查 AIMessage 是否包含指定 tool_call"""
    if not ai_msg.tool_calls:
        return False
    return any(tc["name"] == tool_name for tc in ai_msg.tool_calls)


def master_route(state: VibeMasterState) -> Literal["tools", "research_subgraph", "image_subgraph", "__end__"]:
    """Master Agent 路由决策
    
    对应原项目中:
    - 如果 LLM 返回纯文本 (无 tool_calls) → 结束
    - 如果 tool_calls 包含 "research" → 走 research_subgraph
    - 如果 tool_calls 包含 "image_generation" → 走 image_subgraph
    - 否则 → 走普通 tools 节点
    """
    messages = state["messages"]
    last_message = messages[-1]

    # 没有 tool_calls → 对话结束
    if not isinstance(last_message, AIMessage) or not last_message.tool_calls:
        return "__end__"

    # 包含 research 调用 → 走 Research SubGraph
    if _has_tool_call(last_message, "research"):
        return "research_subgraph"

    # 包含 image_generation 调用 → 走 ImageGeneration SubGraph
    if _has_tool_call(last_message, "image_generation"):
        return "image_subgraph"

    # 普通工具调用
    return "tools"


# ── 构建 Graph ────────────────────────────────────────────

def build_master_graph() -> StateGraph:
    """构建 Master Agent 的完整 StateGraph"""
    graph = StateGraph(VibeMasterState)

    # ── 添加节点 ──
    graph.add_node("master_agent", master_agent_node)
    graph.add_node("tools", master_tools_node)
    graph.add_node("research_subgraph", research_subgraph_node)
    graph.add_node("image_subgraph", image_subgraph_node)

    # ── 添加边 ──
    # 入口 → master_agent
    graph.add_edge(START, "master_agent")

    # master_agent → 路由
    graph.add_conditional_edges(
        "master_agent",
        master_route,
        {
            "tools": "tools",
            "research_subgraph": "research_subgraph",
            "image_subgraph": "image_subgraph",
            "__end__": END,
        },
    )

    # tools → 回到 master_agent (ReAct 循环)
    graph.add_edge("tools", "master_agent")

    # research_subgraph → 回到 master_agent (SubAgent 完成后继续)
    graph.add_edge("research_subgraph", "master_agent")

    # image_subgraph → 回到 master_agent (SubAgent 完成后继续)
    graph.add_edge("image_subgraph", "master_agent")

    return graph.compile()


# 导出编译后的 graph
master_graph = build_master_graph()
