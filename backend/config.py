"""
API 配置和密钥管理
注意：不要将此文件提交到公开的 GitHub 仓库
"""

# ==========================================
# 🔑 API 密钥配置
# ==========================================
DEEPSEEK_API_KEY = "sk-a3664d2ba5864986b65efffc59503bef"
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"
DEEPSEEK_REQUEST_TIMEOUT = 30.0

MINIMAX_API_KEY = "sk-cp-9Xyei5hLBF7dh3dHKZZA1p-YKOYWCHV2NVzns3-_9Frjwx4XGrkdr8wuSXrZtEQCtQBAWR-PcKNJL8_s6hH4rphP2lSS53z08m4p7_wiDSQGmx5YeI95FWM"
MINIMAX_WS_URL = "wss://api.minimax.chat/ws/v1/t2a_v2?GroupId=2025485655798195032"

# ==========================================
# 🎙️ 语音合成配置
# ==========================================
VOICE_SETTINGS = {
    "A": {
        "voice_id": "male-qn-qingse",
        "speed": 1,
        "vol": 2,
        "pitch": 0
    },
    "B": {
        "voice_id": "female-chengshu",
        "speed": 1,
        "vol": 2,
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
DEEPSEEK_SYSTEM_PROMPT = "你是一个王牌车载电台的编剧，只输出 JSON 格式的代码，不要输出任何多余的解释。A是清爽男声，B是成熟女声。"

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
