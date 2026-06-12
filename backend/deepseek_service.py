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
    DEEPSEEK_SYSTEM_PROMPT,
    build_radio_prompt,
)
from poi_knowledge import get_knowledge, save_knowledge


async def generate_radio_script(payload: RealTimeLocationPayload) -> tuple[list, bool]:
    """
    调用 DeepSeek 生成电台剧本，优先使用 POI 知识库缓存
    
    Returns:
        (dialogue_list, used_search): 对话列表 + 是否使用了联网搜索
    """
    print("🧠 正在呼叫 DeepSeek 编写剧本...")

    # ─── 🚀 查 POI 知识库 ───
    cached = get_knowledge(
        payload.poi_name,
        province=payload.province,
        city=payload.city
    )
    
    if cached:
        print(f"📚 命中 POI 知识库缓存！{payload.province}{payload.city} {payload.poi_name} ({len(cached)} 字)")
        used_search = False
        enable_search = False
    else:
        print(f"🆕 首次查询 {payload.poi_name}，启用联网搜索")
        used_search = True
        enable_search = True

    # 动态生成用户提示词（随机选取元素、风格、气氛、内容方向）
    user_prompt = build_radio_prompt(payload, cached_knowledge=cached)
    
    # 构建请求（联网搜索模式：让 DeepSeek 自动查资料减少幻觉）
    request_body = {
        "model": "deepseek-v4-flash",
        "messages": [
            {"role": "system", "content": DEEPSEEK_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt}
        ],
        "response_format": {"type": "json_object"},
        "enable_search": enable_search
    }
    
    # 💡 绝对防御：直接将中文字典转为纯 UTF-8 字节流，杜绝系统 ASCII 隐式转码崩溃
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
            
            # 🔍 打印联网搜索返回（如果有的话）
            if "choices" in response_json:
                choice = response_json["choices"][0]
                message = choice.get("message", {})
                search_results = message.get("search_results", [])
                if not search_results:
                    search_results = response_json.get("search_results", [])
                if search_results:
                    print(f"🌐 DeepSeek 联网搜索到 {len(search_results)} 条资料：")
                    for i, sr in enumerate(search_results[:5]):
                        title = sr.get("title", sr.get("name", "?"))
                        snippet = sr.get("snippet", sr.get("content", ""))[:150]
                        print(f"  [{i+1}] {title}")
                        if snippet:
                            print(f"      {snippet}...")
                else:
                    print("🌐 本轮未触发联网搜索（可能是热点知识）")
            
            # 提取剧本内容
            script_content = response_json['choices'][0]['message']['content']
            if isinstance(script_content, (dict, list)):
                script_data = script_content
            else:
                try:
                    script_data = json.loads(script_content, strict=False)
                except json.JSONDecodeError as first_error:
                    cleaned = script_content
                    # 去掉 Markdown 代码块封装
                    cleaned = re.sub(r"^```(?:json)?\\s*", "", cleaned)
                    cleaned = re.sub(r"\s*```$", "", cleaned)
                    # 清除非法控制字符
                    cleaned = re.sub(r"[\x00-\x1f]", " ", cleaned)
                    print("[⚠️  DeepSeek JSON 修复尝试] 原始输出：", script_content)
                    script_data = json.loads(cleaned, strict=False)

            dialogue_list = script_data.get('dialogue', [])
            
            # 💾 把搜索结果存入 POI 知识库（下次不重复搜索）
            if enable_search and search_results:
                combined = "\n\n".join([
                    f"[{sr.get('title', '?')}]\n{sr.get('snippet', sr.get('content', ''))}"
                    for sr in search_results
                ])
                if combined.strip():
                    save_knowledge(
                        poi_name=payload.poi_name,
                        knowledge_text=combined,
                        province=payload.province,
                        city=payload.city,
                        district=payload.district,
                        latitude=payload.lat,
                        longitude=payload.lon
                    )
            
            print("✅ 剧本生成成功！")
            return dialogue_list, used_search
            
        except Exception as e:
            print(f"❌ DeepSeek 请求失败: {e}")
            raise


async def select_best_landmark(candidates: list) -> dict:
    """用 DeepSeek 从候选 POI 中选出最有趣的一个"""
    print("🤔 正在咨询 DeepSeek 哪个 POI 最值得播报...")

    # 构建候选列表（含地名全称）
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
        "model": "deepseek-v4-flash",
        "messages": [
            {"role": "system", "content": "你是一个旅行家，擅长挑选最有故事的地标。只输出 JSON。"},
            {"role": "user", "content": prompt}
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.7,
        "enable_search": True,
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
        
        # 🔍 打印联网搜索结果
        if "choices" in data_raw:
            msg = data_raw["choices"][0].get("message", {})
            sr = msg.get("search_results", [])
            if sr:
                print(f"🌐 DeepSeek 搜索到 {len(sr)} 条资料：")
                for i, s in enumerate(sr[:3]):
                    print(f"  [{i+1}] {s.get('title','?')}")
        
        content = data_raw["choices"][0]["message"]["content"]
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            cleaned = re.sub(r"[\x00-\x1f]", " ", content)
            data = json.loads(cleaned)

    idx = data.get("index", 1) - 1
    if 0 <= idx < len(candidates):
        chosen = dict(candidates[idx])  # copy
        chosen["_selection_reason"] = data.get("reason", "")
        print(f"✅ DeepSeek 选中: {data.get('name')} — {data.get('reason')}")
        return chosen
    print(f"⚠️ DeepSeek 返回无效索引，回退到第一个候选")
    fallback = dict(candidates[0])
    fallback["_selection_reason"] = "（回退选择）"
    return fallback


async def _search_and_cache(payload: RealTimeLocationPayload) -> str:
    """单独做一次联网搜索，把结果存入知识库，返回知识文本"""
    import asyncio
    print(f"🔍 正在为 {payload.poi_name} 执行独立联网搜索...")
    
    search_prompt = f"""请联网搜索关于「{payload.poi_name}」的信息（位于{payload.province}{payload.city}{payload.district}），
整理 3-5 条关键资料，每条包含标题和内容摘要。输出纯 JSON：{{"results": [{{"title": "...", "snippet": "..."}}]}}"""
    
    request_body = {
        "model": "deepseek-v4-flash",
        "messages": [
            {"role": "system", "content": "你是一个旅行资料收集助手，只输出 JSON。"},
            {"role": "user", "content": search_prompt}
        ],
        "response_format": {"type": "json_object"},
        "enable_search": True
    }
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp = await client.post(
                DEEPSEEK_API_URL,
                headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"},
                content=json.dumps(request_body, ensure_ascii=False).encode('utf-8')
            )
            resp.raise_for_status()
            data = resp.json()
            
            # 提取搜索结果
            msg = data["choices"][0].get("message", {})
            search_results = msg.get("search_results", [])
            content = data["choices"][0]["message"]["content"]
            
            if search_results:
                print(f"🌐 搜索到 {len(search_results)} 条资料")
                combined = "\n\n".join([
                    f"[{s.get('title', '?')}]\n{s.get('snippet', s.get('content', ''))}"
                    for s in search_results
                ])
            else:
                # 没触发搜索，用模型自己的回答作为资料
                try:
                    parsed = json.loads(content)
                    results = parsed.get("results", [])
                    if results:
                        combined = "\n\n".join([
                            f"[{r.get('title', '?')}]\n{r.get('snippet', '')}"
                            for r in results
                        ])
                    else:
                        combined = content
                except:
                    combined = content
                print(f"⚠️ 未触发联网搜索，用模型知识替代")
            
            if combined.strip():
                save_knowledge(
                    poi_name=payload.poi_name,
                    knowledge_text=combined,
                    province=payload.province,
                    city=payload.city,
                    district=payload.district,
                    latitude=payload.lat,
                    longitude=payload.lon
                )
            
            return combined
            
        except Exception as e:
            print(f"❌ 独立搜索失败: {e}")
            return ""
