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


async def generate_radio_script(payload: RealTimeLocationPayload) -> list:
    """
    调用 DeepSeek 生成电台剧本
    
    Args:
        payload: 实时位置和环境信息
        
    Returns:
        dialogue_list: 对话列表，每个元素为 {"role": "A" or "B", "text": "..."}
        
    Raises:
        Exception: DeepSeek 请求失败
    """
    print("🧠 正在呼叫 DeepSeek 编写剧本...")
    
    # 动态生成用户提示词（随机选取元素、风格、气氛、内容方向）
    user_prompt = build_radio_prompt(payload)
    
    # 构建请求（联网搜索模式：让 DeepSeek 自动查资料减少幻觉）
    request_body = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": DEEPSEEK_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt}
        ],
        "response_format": {"type": "json_object"},
        "enable_search": True
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
            
            print("✅ 剧本生成成功！")
            return dialogue_list
            
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

只返回严格 JSON：{{"index": 数字, "name": "POI名称", "reason": "一句话理由"}}"""

    request_body = {
        "model": "deepseek-chat",
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
        content = resp.json()["choices"][0]["message"]["content"]
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
