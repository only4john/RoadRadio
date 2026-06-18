"""
POI 知识库缓存 — 为每个地标存储搜索结果，避免重复联网搜索
"""
import sqlite3
import json
import httpx
from datetime import datetime, timezone
from config import POI_KNOWLEDGE_DB, DEEPSEEK_API_KEY, DEEPSEEK_API_URL, DEEPSEEK_MODEL

DB_PATH = POI_KNOWLEDGE_DB

SUMMARIZE_PROMPT = """请将以下景点搜索资料总结为 {max_chars} 字左右的精炼摘要。
保留：名称、位置、历史背景、文化意义、主要特色、趣闻轶事。
去除：广告信息、网站 URL、重复内容、无关信息。

原始资料：
{text}

精炼摘要："""


async def _summarize_knowledge(text: str, max_chars: int = 1000) -> str:
    """用 DeepSeek 将搜索资料总结为精炼摘要"""
    if len(text) <= max_chars:
        return text

    prompt = SUMMARIZE_PROMPT.format(max_chars=max_chars, text=text)
    request_body = {
        "model": DEEPSEEK_MODEL,
        "messages": [
            {"role": "system", "content": "你是一个知识管理员，擅长提炼和总结景点信息。"},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.3,
        "max_tokens": max_chars * 2,  # 中文一个字约 2 token
    }
    request_bytes = json.dumps(request_body, ensure_ascii=False).encode('utf-8')

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                DEEPSEEK_API_URL,
                headers={
                    "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                    "Content-Type": "application/json"
                },
                content=request_bytes
            )
            resp.raise_for_status()
            data = resp.json()
            summary = data['choices'][0]['message']['content'].strip()
            print(f"📝 DeepSeek 已将 {len(text)} 字总结为 {len(summary)} 字")
            return summary
    except Exception as e:
        print(f"⚠️  总结失败，回退到硬截断: {e}")
        return text[:max_chars]


def _ensure_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS poi_knowledge (
                poi_name TEXT NOT NULL,
                province TEXT DEFAULT '',
                city TEXT DEFAULT '',
                district TEXT DEFAULT '',
                lat_int INTEGER DEFAULT 0,
                lon_int INTEGER DEFAULT 0,
                knowledge_text TEXT DEFAULT '',
                created_at TEXT DEFAULT '',
                PRIMARY KEY (poi_name, province, city, lat_int, lon_int)
            )
            """
        )
        conn.commit()


_ensure_db()


def get_knowledge(poi_name: str, province: str = "", city: str = "",
                  lat: float = 0, lon: float = 0) -> str | None:
    """查询 POI 知识库，先按名+省市+粗坐标匹配，再模糊回退"""
    lat_int = int(round(lat * 10)) if lat else 0
    lon_int = int(round(lon * 10)) if lon else 0

    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()

        cursor.execute(
            """SELECT knowledge_text FROM poi_knowledge 
               WHERE poi_name = ? AND province = ? AND city = ?
               AND ABS(lat_int - ?) <= 1 AND ABS(lon_int - ?) <= 1""",
            (poi_name, province, city, lat_int, lon_int)
        )
        row = cursor.fetchone()
        if row and row[0]:
            return row[0]

        cursor.execute(
            "SELECT knowledge_text FROM poi_knowledge WHERE poi_name = ? AND city = ? ORDER BY created_at DESC LIMIT 1",
            (poi_name, city)
        )
        row = cursor.fetchone()
        if row and row[0]:
            return row[0]

        cursor.execute(
            "SELECT knowledge_text FROM poi_knowledge WHERE poi_name = ? ORDER BY created_at DESC LIMIT 1",
            (poi_name,)
        )
        row = cursor.fetchone()
        return row[0] if row else None


async def save_knowledge(poi_name: str, knowledge_text: str,
                   province: str = "", city: str = "", district: str = "",
                   latitude: float = 0, longitude: float = 0,
                   max_chars: int = 1000):
    """存储 POI 知识到缓存，超过 max_chars 用 DeepSeek 智能总结"""
    now = datetime.now(timezone.utc).isoformat()
    lat_int = int(round(latitude * 10)) if latitude else 0
    lon_int = int(round(longitude * 10)) if longitude else 0

    # 超过上限 → DeepSeek 智能总结
    if len(knowledge_text) > max_chars:
        knowledge_text = await _summarize_knowledge(knowledge_text, max_chars)

    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """INSERT OR REPLACE INTO poi_knowledge
               (poi_name, province, city, district, lat_int, lon_int, knowledge_text, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (poi_name, province, city, district, lat_int, lon_int, knowledge_text, now)
        )
        conn.commit()
    print(f"📚 POI 知识已缓存: {province}{city} {poi_name} ({len(knowledge_text)} 字)")
