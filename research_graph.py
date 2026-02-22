"""
Research SubAgent Graph — 用 LangGraph StateGraph 实现

对应原项目:
- tools/research.py 中的 Research 类
- agent/research_agent_system.py 中的 SYSTEM_PROMPT
- agent/agent_defs.py 中的 RESEARCH_AGENT 定义

Graph 结构:
  ┌─────────────┐
  │  __start__   │
  └──────┬──────┘
         ▼
  ┌─────────────┐
  │  research_   │◄────────────┐
  │   agent      │             │
  └──────┬──────┘             │
         ▼                    │
  ┌─────────────┐    yes      │
  │ should_     ├────────►────┘
  │ continue?   │   (has tool_calls & not terminated & budget ok)
  └──────┬──────┘
         │ no (terminated or budget exhausted)
         ▼
  ┌─────────────┐
  │   __end__    │
  └─────────────┘
"""

import os
import json
import datetime
from typing import Literal

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode

from state import VibeResearchState
from prompts.research import RESEARCH_SYSTEM_PROMPT
from tools.web_tools import search_web, read_webpage
from tools.research_tools import archive_source_into_scratchpad, finish_research_with_report


# ── 工具集 ──────────────────────────────────────────────
RESEARCH_TOOLS = [
    search_web,
    read_webpage,
    archive_source_into_scratchpad,
    finish_research_with_report,
]

# 终止型工具名称
TERMINATING_TOOL_NAMES = {"finish_research_with_report"}


# ── LLM ──────────────────────────────────────────────────
def _get_research_llm():
    """创建 Research SubAgent 使用的 DeepSeek 模型实例"""
    return ChatOpenAI(
        model="deepseek-chat",
        base_url="https://api.deepseek.com/v1",
        api_key=os.environ.get("DEEPSEEK_API_KEY", ""),
        temperature=0.3,
        max_tokens=8192,
    ).bind_tools(RESEARCH_TOOLS)


# ── 节点 ──────────────────────────────────────────────────

def research_agent_node(state: VibeResearchState) -> dict:
    """Research Agent 推理节点 — 调用 LLM 生成下一步动作
    
    对应原项目 ReAct loop 中的 LLM 调用阶段:
    - vibeagent/llm/openai.py 中的 OpenaiLLM.call()
    """
    llm = _get_research_llm()

    # 如果 messages 中没有 system prompt，注入之
    messages = list(state["messages"])
    if not messages or not isinstance(messages[0], SystemMessage):
        current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        system_prompt = RESEARCH_SYSTEM_PROMPT.format(current_time=current_time)
        # 追加 mode 信息
        mode = state.get("research_mode", "scratchpad")
        system_prompt += f"\n\nRESEARCH MODE: You are working in `{mode}` mode."
        if mode == "persist":
            ws = state.get("research_sub_workspace", "")
            system_prompt += f"\nresearch_sub_workspace: {ws}"
        messages.insert(0, SystemMessage(content=system_prompt))

    response = llm.invoke(messages)
    
    # 更新 budget
    budget_used = state.get("budget_used", 0) + 1

    return {
        "messages": [response],
        "budget_used": budget_used,
    }


def research_tools_node(state: VibeResearchState) -> dict:
    """Research 工具执行节点 — 执行 LLM 请求的工具调用
    
    对应原项目 ContextPayload.process_step() 中的工具执行阶段。
    使用 LangGraph 的 ToolNode 自动执行。
    """
    # 使用 ToolNode 执行工具
    tool_node = ToolNode(RESEARCH_TOOLS)
    result = tool_node.invoke(state)
    
    # 检查是否调用了终止型工具
    last_ai_msg = None
    for msg in reversed(state["messages"]):
        if isinstance(msg, AIMessage) and msg.tool_calls:
            last_ai_msg = msg
            break
    
    is_terminated = False
    if last_ai_msg:
        for tc in last_ai_msg.tool_calls:
            if tc["name"] in TERMINATING_TOOL_NAMES:
                is_terminated = True
                break

    return {
        **result,
        "is_terminated": is_terminated,
    }


# ── 路由 ──────────────────────────────────────────────────

def should_continue(state: VibeResearchState) -> Literal["tools", "__end__"]:
    """路由决策 — 决定 Research Agent 是否继续循环
    
    对应原项目 vibeagent/agent.py 中 ReAct loop 的终止判断:
    1. LLM 没有返回 tool_calls → 结束
    2. 已调用终止型工具 → 结束
    3. budget 用尽 → 结束
    4. 否则 → 继续执行工具
    """
    messages = state["messages"]
    last_message = messages[-1]
    
    # 没有 tool_calls → 结束
    if not isinstance(last_message, AIMessage) or not last_message.tool_calls:
        return "__end__"
    
    # 已终止 → 结束
    if state.get("is_terminated", False):
        return "__end__"
    
    # 预算用尽 → 结束
    budget_total = state.get("budget_total", 10)
    budget_used = state.get("budget_used", 0)
    if budget_used >= budget_total:
        return "__end__"
    
    return "tools"


# ── 构建 Graph ────────────────────────────────────────────

def build_research_graph() -> StateGraph:
    """构建 Research SubAgent 的 StateGraph
    
    返回 compiled graph，可以作为 Master Graph 的 subgraph 使用。
    """
    graph = StateGraph(VibeResearchState)

    # 添加节点
    graph.add_node("research_agent", research_agent_node)
    graph.add_node("tools", research_tools_node)

    # 添加边
    graph.add_edge(START, "research_agent")
    graph.add_conditional_edges(
        "research_agent",
        should_continue,
        {
            "tools": "tools",
            "__end__": END,
        },
    )
    graph.add_edge("tools", "research_agent")  # 工具执行完回到 agent

    return graph.compile()


# 导出编译后的 graph
research_graph = build_research_graph()
