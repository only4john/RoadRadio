"""
DeepSeek 剧本生成服务
"""
import json
import re
import httpx
from models import RealTimeLocationPayload
from config import (
    DEEPSEEK_API_KEY,
    DEEPSEEK_API_URL,
    DEEPSEEK_REQUEST_TIMEOUT,
    DEEPSEEK_MODEL,
    DEEPSEEK_SYSTEM_PROMPT,
    build_radio_prompt,
)
from poi_knowledge import get_knowledge, save_knowledge
from query_classifier import classify_needs_search
from tavily_search import search_web


async def generate_radio_script(payload: RealTimeLocationPayload) -> tuple[list, str]:
    """
    调用 DeepSeek 生成电台剧本
    
    流程：
    1. 查 POI 知识库缓存 → 命中则直接用
    2. 未命中 → 搜索判别器判断是否需要联网搜索
    3. 需要搜索 → Bing Search → 结果存入知识库
    4. 将知识注入 prompt → DeepSeek 生成剧本
    
    Returns:
        (dialogue_list, knowledge_source): 对话列表 + 知识来源 ("web"|"cache"|"model")
    """
    print("🧠 正在呼叫 DeepSeek 编写剧本...")

    # ─── 1. 查 POI 知识库 ───
    cached = get_knowledge(
        payload.poi_name,
        province=payload.province,
        city=payload.city,
        lat=payload.lat,
        lon=payload.lon
    )

    knowledge_source = "model"
    bing_results = []

    if cached:
        # ─── 缓存命中 ───
        print(f"📚 命中 POI 知识库缓存！{payload.province}{payload.city} {payload.poi_name} ({len(cached)} 字)")
        knowledge_source = "cache"
    else:
        # ─── 2. 搜索判别器：判断是否需要联网搜索 ───
        need_search = await classify_needs_search(
            payload.poi_name,
            province=payload.province,
            city=payload.city,
        )

        if need_search:
            # ─── 3. Tavily 联网搜索 ───
            location_parts = [p for p in [payload.province, payload.city, payload.district] if p]
            location_str = "".join(location_parts)
            search_query = f"{location_str}{payload.poi_name} 历史 介绍" if location_str else f"{payload.poi_name} 历史 介绍"
            print(f"🌐 Tavily 搜索: {search_query}")
            bing_results = await search_web(search_query)

            if bing_results:
                knowledge_source = "web"
                # 存入知识库缓存
                combined = "\n\n".join([
                    f"[{r['title']}]\n{r['snippet']}"
                    for r in bing_results
                ])
                await save_knowledge(
                    poi_name=payload.poi_name,
                    knowledge_text=combined,
                    province=payload.province,
                    city=payload.city,
                    district=payload.district,
                    latitude=payload.lat,
                    longitude=payload.lon,
                )
                print(f"✅ 已缓存 {len(bing_results)} 条搜索结果到知识库")
            else:
                print("ℹ️ Bing 搜索无结果，回退到模型知识")
                knowledge_source = "model"
        else:
            knowledge_source = "model"

    # ─── 4. 构建知识块 ───
    knowledge_text = cached  # 缓存命中时用缓存内容
    if not knowledge_text and bing_results:
        # 本次搜索结果
        knowledge_text = "\n\n".join([
            f"[{r['title']}]\n{r['snippet']}"
            for r in bing_results
        ])

    # ─── 5. 动态生成 prompt ───
    user_prompt = build_radio_prompt(payload, cached_knowledge=knowledge_text)

    # ─── 6. 调用 DeepSeek 生成剧本 ───
    request_body = {
        "model": DEEPSEEK_MODEL,
        "messages": [
            {"role": "system", "content": DEEPSEEK_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt}
        ],
        "response_format": {"type": "json_object"},
    }

    request_bytes = json.dumps(request_body, ensure_ascii=False).encode('utf-8')

    async with httpx.AsyncClient(timeout=DEEPSEEK_REQUEST_TIMEOUT) as client:
        try:
            response = await client.post(
                DEEPSEEK_API_URL,
                headers={
                    "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                    "Content-Type": "application/json"
                },
                content=request_bytes
            )
            response.raise_for_status()
            response_json = response.json()

            # 提取剧本内容
            script_content = response_json['choices'][0]['message']['content']
            if isinstance(script_content, (dict, list)):
                script_data = script_content
            else:
                try:
                    script_data = json.loads(script_content, strict=False)
                except json.JSONDecodeError:
                    cleaned = script_content
                    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
                    cleaned = re.sub(r"\s*```$", "", cleaned)
                    cleaned = re.sub(r"[\x00-\x1f]", " ", cleaned)
                    print("[⚠️  DeepSeek JSON 修复尝试] 原始输出：", script_content)
                    script_data = json.loads(cleaned, strict=False)

            dialogue_list = script_data.get('dialogue', [])
            print("✅ 剧本生成成功！")
            return dialogue_list, knowledge_source

        except Exception as e:
            print(f"❌ DeepSeek 请求失败: {e}")
            raise


async def select_best_landmark(candidates: list) -> dict:
    """用 DeepSeek 从候选 POI 中选出最有趣的一个"""
    print("🤔 正在咨询 DeepSeek 哪个 POI 最值得播报...")

    candidate_lines = []
    for i, c in enumerate(candidates):
        full_name = c.get("name", "?")
        addr_parts = []
        for key in ("province", "city", "district"):
            v = c.get(key, "")
            if v:
                addr_parts.append(v)
        if addr_parts:
            full_name = "".join(addr_parts) + " " + full_name
        details = f"{full_name}（{c.get('type', '未知')}, 距离{c.get('distance_m', '?')}m, 已播{c.get('introduced_count', 0)}次）"
        candidate_lines.append(f"{i+1}. {details}")

    prompt = f"""以下是从高德地图获取的前方 POI 候选列表：

{chr(10).join(candidate_lines)}

请从中选择最适合做车载电台播报的一个 POI。评判标准：
- 历史文化丰富度
- 知名度和趣味性
- 是否有故事可讲
- 距离适中（太远的不优先）
- 避免商业设施（如加油站、便利店、药店等），除非它们有特别的历史或文化意义。

只返回严格 JSON：{{"index": 数字, "name": "POI名称", "reason": "一句话理由"}}"""

    request_body = {
        "model": DEEPSEEK_MODEL,
        "messages": [
            {"role": "system", "content": "你是一个旅行家，擅长挑选最有故事的地标。只输出 JSON。"},
            {"role": "user", "content": prompt}
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.7,
    }

    request_bytes = json.dumps(request_body, ensure_ascii=False).encode("utf-8")

    async with httpx.AsyncClient(timeout=DEEPSEEK_REQUEST_TIMEOUT) as client:
        resp = await client.post(
            DEEPSEEK_API_URL,
            headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"},
            content=request_bytes,
        )
        resp.raise_for_status()
        data_raw = resp.json()

        content = data_raw["choices"][0]["message"]["content"]
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            cleaned = re.sub(r"[\x00-\x1f]", " ", content)
            data = json.loads(cleaned)

    idx = data.get("index", 1) - 1
    if 0 <= idx < len(candidates):
        chosen = dict(candidates[idx])
        chosen["_selection_reason"] = data.get("reason", "")
        print(f"✅ DeepSeek 选中: {data.get('name')} — {data.get('reason')}")
        return chosen
    print(f"⚠️ DeepSeek 返回无效索引，回退到第一个候选")
    fallback = dict(candidates[0])
    fallback["_selection_reason"] = "（回退选择）"
    return fallback
