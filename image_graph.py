"""
ImageGeneration SubAgent Graph — 标准 ReAct 循环

推理 LLM: Seed 2.0 Pro (多模态, 支持 function calling)
生图工具: Seedream 3.0 (text2img / img2img)

Graph 结构:
  __start__ --> image_agent --> route
                    ^            |
                    |            v
                    +-- tools ---+
                    |            |
                    |            v
                    +------  __end__

- image_agent: 调用 Seed 2.0 Pro, 它自己决定调什么工具
- tools: 执行 text2img / img2img / finish_image_generation
- route: 检查是否有 tool_calls → 有则走 tools, 无或已终止则 __end__

Seed 2.0 Pro 自己看图判断满不满意, 不满意就改 prompt 继续调工具.
"""

import os
import re
import datetime
from typing import Literal

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode

from state import VibeImageGenState
from prompts.imagegeneration import IMAGEGENERATION_SYSTEM_PROMPT
from tools.image_tools import text2img, img2img, finish_image_generation


# ── 工具集 ──────────────────────────────────────────────────
IMAGE_TOOLS = [text2img, img2img, finish_image_generation]
TERMINATING_TOOLS = {"finish_image_generation"}


# ── LLM ──────────────────────────────────────────────────
def _get_image_llm():
    """创建 Seed 2.0 Pro 模型实例 (支持多模态 + function calling)"""
    return ChatOpenAI(
        model="doubao-seed-2-0-pro-260215",
        base_url="https://ark.cn-beijing.volces.com/api/v3",
        api_key=os.environ.get("DOUBAO_API_KEY", ""),
        temperature=0.7,
        max_tokens=4096,
    ).bind_tools(IMAGE_TOOLS)


# ── 节点 ──────────────────────────────────────────────────

def image_agent_node(state: VibeImageGenState) -> dict:
    """Seed 2.0 Pro 推理节点 — 决定下一步动作

    第一轮: 根据用户需求, 构造 prompt, 调 text2img/img2img
    后续轮: 看到工具返回的图片结果, 自己判断满不满意, 决定继续还是 finish
    """
    llm = _get_image_llm()
    messages = list(state["messages"])

    # 注入 system prompt (如果还没有)
    if not messages or not isinstance(messages[0], SystemMessage):
        current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        system_prompt = IMAGEGENERATION_SYSTEM_PROMPT.format(current_time=current_time)
        messages.insert(0, SystemMessage(content=system_prompt))

    response = llm.invoke(messages)
    return {"messages": [response]}


# ── 路由 ──────────────────────────────────────────────────

def image_route(state: VibeImageGenState) -> Literal["tools", "__end__"]:
    """路由决策:
    - 如果 LLM 返回了 tool_calls → 走 tools 节点执行
    - 如果没有 tool_calls → 结束 (LLM 认为任务完成)
    - 如果已调用 finish_image_generation → 结束
    """
    if state.get("is_terminated", False):
        return "__end__"

    messages = state["messages"]
    last_message = messages[-1]

    if isinstance(last_message, AIMessage) and last_message.tool_calls:
        # 检查是否调用了终止工具
        for tc in last_message.tool_calls:
            if tc["name"] in TERMINATING_TOOLS:
                return "tools"  # 先执行 finish 工具, 下一轮再 __end__
        return "tools"

    return "__end__"


def check_termination(state: VibeImageGenState) -> dict:
    """检查工具执行结果:
    - 如果执行了 finish_image_generation → 标记终止
    - 如果执行了 text2img/img2img → 提取图片 URL, 注入多模态消息让 Seed 2.0 Pro 真正看到图片
    
    关键: Seed 2.0 Pro 只看到 ToolMessage 里的文字 (Image URL: ...),
    它并不会自动去加载图片. 必须通过 image_url 类型的 content 把图片传给它,
    它才能真正看到图, 做出有意义的质量判断.
    """
    messages = state["messages"]
    
    # 检查最近的 ToolMessage 组
    for msg in reversed(messages):
        if isinstance(msg, ToolMessage) and msg.name == "finish_image_generation":
            return {"is_terminated": True}
        if not isinstance(msg, ToolMessage):
            break

    # 未终止 → 找到生成的图片 URL, 注入多模态消息让 LLM 看到图
    image_url = None
    for msg in reversed(messages):
        if isinstance(msg, ToolMessage) and msg.name in ("text2img", "img2img"):
            # 从工具返回内容中提取图片 URL
            content = msg.content or ""
            m = re.search(r'(?:Image URL|Modified image URL): (https?://\S+)', content)
            if m:
                image_url = m.group(1)
            break
        if not isinstance(msg, ToolMessage):
            break

    if image_url:
        # 注入一条多模态 HumanMessage, 让 Seed 2.0 Pro 真正看到生成的图片
        review_msg = HumanMessage(
            content=[
                {
                    "type": "text",
                    "text": (
                        "Above is the generated image. Please carefully review it:\n"
                        "1. Does the style match the requirements?\n"
                        "2. Are all requested elements present?\n"
                        "3. Are details correct (faces, text, composition)?\n\n"
                        "If satisfied, call finish_image_generation with the image URL.\n"
                        "If not satisfied, explain what's wrong and call text2img/img2img again with an improved prompt."
                    ),
                },
                {
                    "type": "image_url",
                    "image_url": {"url": image_url},
                },
            ]
        )
        return {"messages": [review_msg]}

    return {}


# ── 构建 Graph ────────────────────────────────────────────

def build_image_graph():
    """构建 ImageGeneration SubAgent 的标准 ReAct 循环"""
    graph = StateGraph(VibeImageGenState)

    # 节点
    graph.add_node("image_agent", image_agent_node)
    graph.add_node("tools", ToolNode(IMAGE_TOOLS))
    graph.add_node("check_termination", check_termination)

    # 边
    graph.add_edge(START, "image_agent")

    # image_agent → 路由
    graph.add_conditional_edges(
        "image_agent",
        image_route,
        {"tools": "tools", "__end__": END},
    )

    # tools → check_termination → image_agent (ReAct 循环)
    graph.add_edge("tools", "check_termination")

    # check_termination → 如果已终止则 __end__, 否则回到 image_agent
    graph.add_conditional_edges(
        "check_termination",
        lambda state: "__end__" if state.get("is_terminated", False) else "image_agent",
        {"__end__": END, "image_agent": "image_agent"},
    )

    return graph.compile()


image_graph = build_image_graph()
