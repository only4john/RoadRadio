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
    DEEPSEEK_USER_PROMPT_TEMPLATE,
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
    
    # 生成用户提示词
    user_prompt = DEEPSEEK_USER_PROMPT_TEMPLATE.format(
        time_of_day=payload.time_of_day,
        weather=payload.weather,
        temperature=payload.temperature,
        speed_kmh=payload.speed_kmh,
        poi_name=payload.poi_name,
        current_music=payload.current_music,
    )
    
    # 构建请求
    request_body = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": DEEPSEEK_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt}
        ],
        "response_format": {"type": "json_object"}
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
