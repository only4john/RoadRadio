"""
搜索判别器 — 用轻量 DeepSeek 调用判断某个 POI 是否需要联网搜索
"""
import json
import re
import httpx
from config import (
    DEEPSEEK_API_KEY,
    DEEPSEEK_API_URL,
    DEEPSEEK_LIGHT_MODEL,
)

CLASSIFIER_PROMPT = """你是一个搜索判别器。判断以下地标/景点是否需要联网搜索来获取更丰富的介绍信息。

判断标准（满足任一即需要搜索）：
- 该地标的知名度不高，可能是小众景点
- 该地标可能有近期变化（如翻新、改名、活动）
- 该地标的历史/文化背景可能超出常识范围
- 地名可能有歧义（如"武汉大学"vs"某个叫武汉大学的地方"）

不需要搜索的情况：
- 非常著名的地标（如故宫、长城、天安门），模型世界知识足够
- 纯自然地理标志（如某座山、某条河），常识足够描述

只返回严格 JSON：{"need_search": true/false, "reason": "一句话理由"}"""

MAX_RETRIES = 2


def _parse_result(content: str) -> dict | None:
    """解析 DeepSeek 返回的 JSON，带容错"""
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass
    # 尝试从 Markdown 代码块中提取
    m = re.search(r"\{[^{}]*\"need_search\"[^{}]*\}", content)
    if m:
        try:
            return json.loads(m.group())
        except json.JSONDecodeError:
            pass
    return None


async def classify_needs_search(poi_name: str, province: str = "", city: str = "") -> bool:
    """
    判断一个 POI 是否需要联网搜索
    
    Args:
        poi_name: POI 名称
        province: 省份
        city: 城市
        
    Returns:
        True 表示需要搜索，False 表示模型知识足够
    """
    location_hint = f"{province}{city}" if province or city else ""
    query = f"{location_hint}{poi_name}" if location_hint else poi_name

    request_body = {
        "model": DEEPSEEK_LIGHT_MODEL,
        "messages": [
            {"role": "system", "content": CLASSIFIER_PROMPT},
            {"role": "user", "content": f"地标：{query}"}
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.1,
        "max_tokens": 150,
    }

    request_bytes = json.dumps(request_body, ensure_ascii=False).encode("utf-8")

    for attempt in range(MAX_RETRIES):
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    DEEPSEEK_API_URL,
                    headers={
                        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    content=request_bytes,
                )
                resp.raise_for_status()
                data = resp.json()

            content = data["choices"][0]["message"]["content"]
            result = _parse_result(content)
            if result is None:
                raise ValueError(f"JSON 解析失败: {content[:100]}")

            need = result.get("need_search", False)
            reason = result.get("reason", "")
            label = "🔍 需要搜索" if need else "🧠 模型知识足够"
            print(f"📋 搜索判别: {poi_name} → {label} ({reason})")
            return need

        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                print(f"⚠️ 搜索判别第 {attempt+1} 次失败，重试中: {e}")
            else:
                print(f"⚠️ 搜索判别失败（已重试 {MAX_RETRIES} 次），默认不搜索: {e}")
                return False
