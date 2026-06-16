"""
Tavily Search API 客户端 — 为 POI 搜索背景知识
"""
import httpx
from config import TAVILY_API_KEY, TAVILY_SEARCH_ENDPOINT, TAVILY_SEARCH_TIMEOUT

TAVILY_COUNT = 5


async def search_web(query: str, count: int = TAVILY_COUNT) -> list[dict]:
    """
    调用 Tavily Search API 搜索信息
    
    Args:
        query: 搜索关键词
        count: 返回结果数量（1-20）
        
    Returns:
        list[dict]: 搜索结果列表，每项包含 title, snippet, url
    """
    if not TAVILY_API_KEY:
        print("⚠️ TAVILY_API_KEY 未设置，跳过联网搜索")
        return []

    payload = {
        "api_key": TAVILY_API_KEY,
        "query": query,
        "max_results": min(count, 20),
        "search_depth": "basic",
        "include_answer": False,
    }

    try:
        async with httpx.AsyncClient(timeout=TAVILY_SEARCH_TIMEOUT) as client:
            resp = await client.post(TAVILY_SEARCH_ENDPOINT, json=payload)
            resp.raise_for_status()
            data = resp.json()

        results = []
        for item in data.get("results", []):
            results.append({
                "title": item.get("title", ""),
                "snippet": item.get("content", ""),
                "url": item.get("url", ""),
            })
        return results

    except Exception as e:
        print(f"❌ Tavily 搜索失败: {e}")
        return []
