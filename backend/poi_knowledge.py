"""
POI 知识库缓存 — 为每个地标存储搜索结果，避免重复联网搜索
"""
import sqlite3
import os
from datetime import datetime

DB_PATH = os.environ.get("POI_KNOWLEDGE_DB", os.path.join(os.path.dirname(__file__), "poi_knowledge.db"))


def _ensure_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS poi_knowledge (
            poi_name TEXT NOT NULL,
            province TEXT DEFAULT '',
            city TEXT DEFAULT '',
            district TEXT DEFAULT '',
            latitude REAL DEFAULT 0,
            longitude REAL DEFAULT 0,
            knowledge_text TEXT DEFAULT '',
            created_at TEXT DEFAULT '',
            PRIMARY KEY (poi_name, province, city)
        )
        """
    )
    conn.commit()
    conn.close()


def get_knowledge(poi_name: str, province: str = "", city: str = "") -> str | None:
    """查询 POI 知识库，返回缓存的文本，没有则返回 None"""
    _ensure_db()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # 先精确匹配
    cursor.execute(
        "SELECT knowledge_text FROM poi_knowledge WHERE poi_name = ? AND province = ? AND city = ?",
        (poi_name, province, city)
    )
    row = cursor.fetchone()
    if row and row[0]:
        conn.close()
        return row[0]
    # 回退：只按 poi_name 查
    cursor.execute(
        "SELECT knowledge_text FROM poi_knowledge WHERE poi_name = ? ORDER BY created_at DESC LIMIT 1",
        (poi_name,)
    )
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None


def save_knowledge(poi_name: str, knowledge_text: str,
                   province: str = "", city: str = "", district: str = "",
                   latitude: float = 0, longitude: float = 0):
    """存储 POI 知识到缓存"""
    _ensure_db()
    now = datetime.utcnow().isoformat()
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """INSERT OR REPLACE INTO poi_knowledge 
           (poi_name, province, city, district, latitude, longitude, knowledge_text, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (poi_name, province, city, district, latitude, longitude, knowledge_text, now)
    )
    conn.commit()
    conn.close()
    print(f"📚 POI 知识已缓存: {province}{city} {poi_name} ({len(knowledge_text)} 字)")
