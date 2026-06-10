"""
API 配置和密钥管理
支持 .env 环境变量，优先级：环境变量 > 硬编码默认值
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ==========================================
# 🔑 API 密钥配置
# ==========================================
AMAP_API_KEY = os.getenv("AMAP_API_KEY", "1bf4810688b1f136dd5e5d16ea67b587")

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "sk-a3664d2ba5864986b65efffc59503bef")
DEEPSEEK_API_URL = os.getenv("DEEPSEEK_API_URL", "https://api.deepseek.com/v1/chat/completions")
DEEPSEEK_REQUEST_TIMEOUT = float(os.getenv("DEEPSEEK_TIMEOUT", "30.0"))

MINIMAX_API_KEY = os.getenv("MINIMAX_API_KEY", "sk-cp-9Xyei5hLBF7dh3dHKZZA1p-YKOYWCHV2NVzns3-_9Frjwx4XGrkdr8wuSXrZtEQCtQBAWR-PcKNJL8_s6hH4rphP2lSS53z08m4p7_wiDSQGmx5YeI95FWM")
MINIMAX_WS_URL = os.getenv("MINIMAX_WS_URL", "wss://api.minimax.chat/ws/v1/t2a_v2?GroupId=2025485655798195032")

# ==========================================
# 🎙️ 语音合成配置
# ==========================================
VOICE_SETTINGS = {
    "A": {
        "voice_id": "male-qn-qingse",
        "speed": 1,
        "vol": 5,
        "pitch": 0
    },
    "B": {
        "voice_id": "female-shaonv",  # 少女音，更年轻活泼
        "speed": 1,
        "vol": 5,
        "pitch": 0
    }
}

AUDIO_SETTINGS = {
    "format": "mp3",
    "sample_rate": 32000,
    "channel": 1
}

# ==========================================
# 🎭 DeepSeek 剧本配置
# ==========================================
DEEPSEEK_SYSTEM_PROMPT = "你是一个王牌车载电台的编剧，A叫阿甘（清爽男声），B叫珍妮（活泼女声）。他们是一对默契的电台搭档。你的任务是输出他们之间的对话，只输出严格 JSON 格式，不要任何多余解释。"""

STYLE_POOL = [
    ("两人像老朋友一样轻松聊天，相互应和", "语气舒缓放松，像午后电台"),
    ("两人像损友一样互相抬杠调侃，但氛围友好", "语气开心活泼，充满能量"),
    ("一个正经介绍、一个插科打诨逗哏", "语气温暖治愈，像深夜电台"),
    ("两人一起感叹和共鸣", "语气充满好奇和探索感"),
]

CONTENT_HINTS = [
    "可以聊聊这个地标的历史小故事或典故",
    "可以顺便说说这个地标的现状和游览体验",
    "可以从文化衍生的角度聊聊这里的独特之处",
    "分享一个跟这个地标相关的轶事或八卦",
    "说一个关于这里的冷知识或有趣的细节",
]


def build_radio_prompt(payload) -> str:
    """动态构建电台播报 prompt，随机选取信息元素、对话风格和内容方向"""
    import random

    # ─── 1. 信息元素池 ───
    elements = []
    if payload.time_of_day:
        elements.append(f"当前时间：{payload.time_of_day}")
    if payload.weather or payload.temperature:
        parts = []
        if payload.weather:
            parts.append(f"天气{payload.weather}")
        if payload.temperature:
            parts.append(f"气温{payload.temperature}度")
        elements.append("，".join(parts))
    if payload.month:
        elements.append(f"正值{payload.month}")
    if payload.speed_kmh > 0:
        elements.append(f"正以{payload.speed_kmh} km/h 的车速行驶")
    if payload.current_music and payload.current_music != "无":
        music_str = f"车内正在播放《{payload.current_music}》"
        if payload.artist:
            music_str += f"（{payload.artist}）"
        elements.append(music_str)

    # ─── 2. 随机选几个额外元素 ───
    roll = random.random()
    if roll < 0.25:
        num_extras = 0
    elif roll < 0.75:
        num_extras = 1
    elif roll < 0.95:
        num_extras = 2
    else:
        num_extras = min(3, len(elements))

    selected = random.sample(elements, min(num_extras, len(elements)))

    # ─── 3. 随机风格 + 气氛 + 内容方向 ───
    style, atmosphere = random.choice(STYLE_POOL)
    hint = random.choice(CONTENT_HINTS)

    # ─── 4. 音乐评论提示（小概率） ───
    music_comment = ""
    music_selected = any("播放" in e for e in selected)
    if music_selected and random.random() < 0.3:
        music_comment = ("如果提到了音乐，可以顺便简单评论一下这位歌手/艺术家的风格或近况，"
                         "自然地一带而过，不用太长。")

    # ─── 5. 拼接 prompt ───
    info_block = "\n".join(f"- {e}" for e in selected) if selected else "（仅关注前方地标）"

    return f"""前方即将经过或处于【{payload.poi_name}】。

当前环境信息：
{info_block}

对话风格：{style}
整体气氛：{atmosphere}
内容提示：{hint}
{music_comment}
请生成 2到3 轮自然、有沉浸感的电台双人对话。要求：
1. 必须围绕【{payload.poi_name}】展开，这是最核心的话题。
2. 基于真实信息进行介绍，不要编造不存在的事实、人物、年代或数据。你知道多少就说多少，不知道的宁可不提。
3. 如果提供了环境信息，自然地融入对话中，不要生硬堆砌每一行。
4. 像公路旅行中的朋友聊天，轻松不做作，不要像导游词。
5. 返回强制严格 JSON 格式：{{"dialogue": [{{"role": "A", "text": "内容"}}, {{"role": "B", "text": "内容"}}]}}"""


# 旧模板保留兼容（不再使用，由 build_radio_prompt 替代）
DEEPSEEK_USER_PROMPT_TEMPLATE = """
当前时间是{time_of_day}，天气{weather}，气温{temperature}度。
我们正以 {speed_kmh} km/h 的车速行驶，前方即将经过或处于【{poi_name}】。
车内正在播放音乐《{current_music}》。

请结合当前的环境氛围、天气感受以及前方的具体地标，生成 2到3 轮自然、舒缓的电台双人对话。
要求：
1. 像老朋友在公路旅行一样聊天，带出一种在路上的沉浸感。
2. 有小概率自然地提到车窗外的温度或天气，并对即将到达的地标或正在听的歌表示期待和共鸣。
3. 如果有即将到来的地标，可以简要介绍一下这个地标的特色或历史，最好是相关轶事，不要过于正式，保持轻松的语气。
4. 返回强制严格 JSON 格式：{{"dialogue": [{{"role": "A", "text": "内容"}}, {{"role": "B", "text": "内容"}}]}}
"""
