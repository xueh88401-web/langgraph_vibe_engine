"""
Web 相关工具 — search_web, read_webpage

使用 Tavily API 提供网页搜索和内容提取能力。
需要设置环境变量 TAVILY_API_KEY。
"""

import os
import logging
from langchain_core.tools import tool
from tavily import TavilyClient

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tavily 客户端（懒加载单例）
# ---------------------------------------------------------------------------
_tavily_client: TavilyClient | None = None


def _get_tavily_client() -> TavilyClient:
    global _tavily_client
    if _tavily_client is None:
        api_key = os.environ.get("TAVILY_API_KEY")
        if not api_key:
            raise ValueError(
                "请设置环境变量 TAVILY_API_KEY，可在 https://app.tavily.com 获取。"
            )
        _tavily_client = TavilyClient(api_key=api_key)
    return _tavily_client


# ---------------------------------------------------------------------------
# search_web
# ---------------------------------------------------------------------------
@tool
def search_web(query: str) -> str:
    """Issues a query to a search engine and returns search results.

    Use when the task requires up-to-date facts, niche details,
    or when correctness is critical. Returns titles, URLs, and summaries.

    Args:
        query: The search query to execute.
    """
    client = _get_tavily_client()
    try:
        response = client.search(query, max_results=10)
    except Exception as e:
        logger.error(f"Tavily search failed: {e}")
        return f"搜索失败: {e}"

    results = response.get("results", [])
    if not results:
        return f"未找到与 '{query}' 相关的结果。"

    formatted = []
    for i, r in enumerate(results, 1):
        title = r.get("title", "")
        url = r.get("url", "")
        content = r.get("content", "")
        formatted.append(f"[{i}] {title}\n    URL: {url}\n    {content}")
    return "\n\n".join(formatted)


# ---------------------------------------------------------------------------
# read_webpage
# ---------------------------------------------------------------------------
@tool
def read_webpage(url: str) -> str:
    """Read and extract content from a webpage.

    Fetches the webpage, extracts main text content, and returns it.

    Args:
        url: The URL of the webpage to read.
    """
    client = _get_tavily_client()
    try:
        response = client.extract(urls=[url])
    except Exception as e:
        logger.error(f"Tavily extract failed: {e}")
        return f"读取网页失败: {e}"

    results = response.get("results", [])
    if not results:
        return f"无法提取 '{url}' 的内容。"

    result = results[0]
    raw_content = result.get("raw_content", "") or result.get("content", "")
    if not raw_content:
        return f"网页 '{url}' 内容为空。"

    # 添加行号方便引用
    lines = raw_content.split("\n")
    numbered = [f"{i + 1}| {line}" for i, line in enumerate(lines)]
    return f"URL: {url}\n---\n" + "\n".join(numbered)
