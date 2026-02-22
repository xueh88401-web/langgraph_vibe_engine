"""
State 定义 — Master Agent 和各 SubAgent 的状态类型

对应原项目:
- AgentContext + ContextPayload → VibeMasterState
- Research SubAgent context → VibeResearchState
- ImageGeneration SubAgent context → VibeImageGenState
"""

from typing import Any, Optional
from typing_extensions import TypedDict, Annotated
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class VibeMasterState(TypedDict):
    """Master Agent 的 Graph State
    
    对应原项目的 AgentContext + ContextPayload:
    - messages: 对话消息序列 (对应 ctx.llm_req.message_seq)
    - workspace_id: 工作区 ID
    - current_canvas_id: 当前画布 ID
    - current_canvas_content: 当前画布内容
    - current_canvas_title: 当前画布标题
    - canvas_tool: 共享画布工具实例 (SubAgent 共享)
    - url_data: 网页缓存 (对应 ContextPayload.url_data)
    - todos: 任务列表
    """
    messages: Annotated[list[BaseMessage], add_messages]
    workspace_id: str
    current_canvas_id: str
    current_canvas_content: str
    current_canvas_title: str
    canvas_tool: Any            # 共享画布实例，SubAgent 通过此共享画布状态
    url_data: dict              # 网页抓取缓存 {normalized_url: {index, meta, scraping}}
    todos: list                 # todo 列表


class VibeResearchState(TypedDict):
    """Research SubAgent 的 Graph State
    
    对应原项目的 context_init_subagent + ContextPayload.research_scratchpad:
    - messages: 对话消息序列
    - research_mode: "persist" | "scratchpad"
    - research_sub_workspace: persist 模式下的工作区路径
    - scratchpad: scratchpad 模式下的内存存储
    - budget_total: 预算总轮数
    - budget_used: 已用轮数
    - canvas_tool: 从 Master 共享的画布工具
    - url_data: 网页缓存
    - is_terminated: 是否已调用终止型工具 (finish_research_with_report)
    """
    messages: Annotated[list[BaseMessage], add_messages]
    research_mode: str          # "persist" | "scratchpad"
    research_sub_workspace: str # persist 模式下的画布路径
    scratchpad: dict            # scratchpad 内存存储
    budget_total: int           # 预算总轮数
    budget_used: int            # 已用轮数
    canvas_tool: Any            # 从 Master 共享
    url_data: dict              # 网页缓存
    is_terminated: bool         # finish_research_with_report 是否已调用


class VibeImageGenState(TypedDict):
    """ImageGeneration SubAgent 的 Graph State

    标准 ReAct 循环: Seed 2.0 Pro 做推理, 自己决定调 text2img/img2img,
    看到工具返回结果后自己判断满不满意, 不满意就继续调工具改 prompt,
    满意就调 finish_image_generation 结束.

    - messages: 对话消息序列 (ReAct 循环的完整上下文)
    - is_terminated: 是否已调用 finish_image_generation
    """
    messages: Annotated[list[BaseMessage], add_messages]
    is_terminated: bool         # finish_image_generation 是否已调用
