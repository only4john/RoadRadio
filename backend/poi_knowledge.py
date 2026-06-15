"""
POI 知识库缓存 — 为每个地标存储搜索结果，避免重复联网搜索
"""
import sqlite3
import os
from datetime import datetime
from config import POI_KNOWLEDGE_DB

DB_PATH = POI_KNOWLEDGE_DB


def _ensure_db():
    conn = sqlite3.connect(DB_PATH)
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
    conn.close()


def get_knowledge(poi_name: str, province: str = "", city: str = "",
                  lat: float = 0, lon: float = 0) -> str | None:
    """查询 POI 知识库，先按名+省市+粗坐标匹配，再模糊回退"""
    _ensure_db()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    lat_int = int(round(lat * 10)) if lat else 0    # 保留1位小数, ±0.05° ≈ 5.5km
    lon_int = int(round(lon * 10)) if lon else 0
    
    # 精确匹配：名字 + 省市 + 粗坐标 ±1（约 100m 范围）
    cursor.execute(
        """SELECT knowledge_text FROM poi_knowledge 
           WHERE poi_name = ? AND province = ? AND city = ?
           AND ABS(lat_int - ?) <= 1 AND ABS(lon_int - ?) <= 1""",
        (poi_name, province, city, lat_int, lon_int)
    )
    row = cursor.fetchone()
    if row and row[0]:
        conn.close()
        return row[0]
    
    # 回退1：名字 + 城市（不含区）
    cursor.execute(
        "SELECT knowledge_text FROM poi_knowledge WHERE poi_name = ? AND city = ? ORDER BY created_at DESC LIMIT 1",
        (poi_name, city)
    )
    row = cursor.fetchone()
    if row and row[0]:
        conn.close()
        return row[0]
    
    # 回退2：只按名字
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
    lat_int = int(round(latitude * 10)) if latitude else 0
    lon_int = int(round(longitude * 10)) if longitude else 0
    conn.execute(
        """INSERT OR REPLACE INTO poi_knowledge 
           (poi_name, province, city, district, lat_int, lon_int, knowledge_text, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (poi_name, province, city, district, lat_int, lon_int, knowledge_text, now)
    )
    conn.commit()
    conn.close()
    print(f"📚 POI 知识已缓存: {province}{city} {poi_name} ({len(knowledge_text)} 字)")
