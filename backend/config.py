"""
API 配置和密钥管理
支持 .env 环境变量，优先级：环境变量 > 无默认值（请用 .env 配置）
"""

import os
import logging
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

# ==========================================
# 📋 统一日志配置（带时间戳）
# ==========================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s.%(msecs)03d [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("laniakea")

# ==========================================
# 🔑 API 密钥配置（请通过 .env 文件设置，勿硬编码）
# ==========================================
AMAP_API_KEY = os.getenv("AMAP_API_KEY", "")
if not AMAP_API_KEY:
    print("⚠️  警告: AMAP_API_KEY 未设置，请配置 .env 文件")

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
if not DEEPSEEK_API_KEY:
    print("⚠️  警告: DEEPSEEK_API_KEY 未设置，请配置 .env 文件")
DEEPSEEK_API_URL = os.getenv("DEEPSEEK_API_URL", "https://api.deepseek.com/chat/completions")
DEEPSEEK_REQUEST_TIMEOUT = float(os.getenv("DEEPSEEK_TIMEOUT", "30.0"))
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")

MINIMAX_API_KEY = os.getenv("MINIMAX_API_KEY", "")
if not MINIMAX_API_KEY:
    print("⚠️  警告: MINIMAX_API_KEY 未设置，请配置 .env 文件")
MINIMAX_GROUP_ID = os.getenv("MINIMAX_GROUP_ID", "")
if not MINIMAX_GROUP_ID:
    print("⚠️  警告: MINIMAX_GROUP_ID 未设置，请配置 .env 文件")
MINIMAX_WS_URL = os.getenv("MINIMAX_WS_URL", f"wss://api.minimax.chat/ws/v1/t2a_v2?GroupId={MINIMAX_GROUP_ID}" if MINIMAX_GROUP_ID else "")

TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")
if not TAVILY_API_KEY:
    print("⚠️  警告: TAVILY_API_KEY 未设置，联网搜索功能不可用")
TAVILY_SEARCH_ENDPOINT = os.getenv("TAVILY_SEARCH_ENDPOINT", "https://api.tavily.com/search")
TAVILY_SEARCH_TIMEOUT = float(os.getenv("TAVILY_SEARCH_TIMEOUT", "10.0"))

# ==========================================
# 📂 数据持久化路径
# ==========================================
DATA_DIR = os.getenv("DATA_DIR", os.path.join(os.path.dirname(__file__), "data"))
os.makedirs(DATA_DIR, exist_ok=True)
POI_KNOWLEDGE_DB = os.getenv("POI_KNOWLEDGE_DB", os.path.join(DATA_DIR, "poi_knowledge.db"))

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
DEEPSEEK_SYSTEM_PROMPT = "你是一个王牌车载电台的编剧，A（清爽男声），B（活泼女声）。他们是一对默契的电台搭档，A有点喜欢B，B是否喜欢A则有点捉摸不透。你的任务是输出他们之间的对话，只输出严格 JSON 格式，不要任何多余解释。\n\n⚠️ 重要：对话文本是给 TTS 语音合成用的，所以请直接写口语化的台词即可，禁止在文本中使用任何括号内的表情/动作/语气提示词，例如（轻笑）、（感叹）、（惊讶）、（摇头）等一律不要出现。"

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
    "总结一下网上搜索到的关于这里的评论",
]


def build_radio_prompt(payload, cached_knowledge: str = "") -> str:
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
    elif roll < 0.90:
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
        music_comment = ("如果提到了音乐，可以顺便简单评论一下这位歌手/艺术家的风格,历史轶事，或近况，"
                         "以及粉丝们对这位艺术家的公论，历史地位等等。")

    # ─── 5. 拼接 prompt ───
    info_block = "\n".join(f"- {e}" for e in selected) if selected else "（仅关注前方地标）"
    
    # 如果有缓存的知识文本，直接注入 prompt，无需联网搜索
    knowledge_block = ""
    if cached_knowledge:
        knowledge_block = f"\n\n📚 已知资料（基于此进行介绍，不要编造）：\n{cached_knowledge}"

    return f"""前方即将经过或处于【{payload.poi_name}】。{knowledge_block}

当前环境信息：
{info_block}

对话风格：{style}
整体气氛：{atmosphere}
内容提示：{hint}
{music_comment}
请生成 1到3 轮自然、有沉浸感的电台双人对话。要求：
1. 必须围绕【{payload.poi_name}】展开，这是最核心的话题。**在回答前必须通过联网搜索获取关于该地标的最新信息。**
2. 基于真实信息进行介绍，不要编造不存在的事实、人物、年代或数据。你知道多少就说多少，不知道的宁可不提。
3. 如果提供了环境信息，自然地融入对话中，不要生硬堆砌每一行。
4. 像公路旅行中的朋友聊天，轻松不做作，不要像导游词。话题可以开放和发散，但要有回归地标的意识，保持对话的相关性和连贯性。
5. 返回强制严格 JSON 格式：{{"dialogue": [{{"role": "A", "text": "内容"}}, {{"role": "B", "text": "内容"}}]}}"""
