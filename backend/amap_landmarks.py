import os
import random
import sqlite3
import httpx
from math import inf
from datetime import datetime
from pydantic import BaseModel

AMAP_API_KEY = "1bf4810688b1f136dd5e5d16ea67b587"
AMAP_PLACE_AROUND_URL = "https://restapi.amap.com/v3/place/around"
AMAP_SEARCH_KEYWORDS = "历史建筑|文化标志|文化地标|旅游景点|博物馆|纪念馆"
MIN_SEARCH_RADIUS_METERS = 500
MAX_SEARCH_RADIUS_METERS = 5000
PREVIEW_LEAD_MINUTES = 3
MIN_DISTANCE_CONSIDERED = 150
HISTORY_DB_PATH = os.path.join(os.path.dirname(__file__), "landmark_history.db")


class LandmarkSearchPayload(BaseModel):
    lat: float
    lon: float
    speed_kmh: float = 40.0
    heading: int = 0  # 0-360, compass bearing (0=North, 90=East, 180=South, 270=West)
    max_results: int = 5
    frequency_level: int = 50  # 0-100, controls how frequently to include less-famous POIs


class LandmarkInfo(BaseModel):
    poi_id: str
    name: str
    type: str
    address: str
    distance_m: int
    location: str
    estimated_arrival_min: float
    preview_start_seconds: int
    introduced_count: int = 0
    selection_weight: float = 0.0


class LandmarkRecordPayload(BaseModel):
    poi_id: str
    name: str
    location: str
    address: str = ""
    type: str = ""


def _ensure_history_db():
    conn = sqlite3.connect(HISTORY_DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS landmark_history (
            poi_id TEXT PRIMARY KEY,
            name TEXT,
            location TEXT,
            address TEXT,
            type TEXT,
            introduced_count INTEGER DEFAULT 0,
            last_introduced TEXT
        )
        """
    )
    conn.commit()
    conn.close()


def _get_history_record(poi_id: str):
    conn = sqlite3.connect(HISTORY_DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT poi_id, name, location, address, type, introduced_count, last_introduced FROM landmark_history WHERE poi_id = ?",
        (poi_id,)
    )
    row = cursor.fetchone()
    conn.close()
    if row:
        return {
            "poi_id": row[0],
            "name": row[1],
            "location": row[2],
            "address": row[3],
            "type": row[4],
            "introduced_count": row[5],
            "last_introduced": row[6],
        }
    return None


def record_landmark_introduction(poi_id: str, name: str, location: str, address: str = "", type: str = ""):
    _ensure_history_db()
    now = datetime.utcnow().isoformat()
    conn = sqlite3.connect(HISTORY_DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT introduced_count FROM landmark_history WHERE poi_id = ?",
        (poi_id,)
    )
    row = cursor.fetchone()
    if row:
        cursor.execute(
            "UPDATE landmark_history SET introduced_count = introduced_count + 1, last_introduced = ?, name = ?, location = ?, address = ?, type = ? WHERE poi_id = ?",
            (now, name, location, address, type, poi_id)
        )
    else:
        cursor.execute(
            "INSERT INTO landmark_history (poi_id, name, location, address, type, introduced_count, last_introduced) VALUES (?, ?, ?, ?, ?, 1, ?)",
            (poi_id, name, location, address, type, now)
        )
    conn.commit()
    conn.close()


def normalize_search_radius(speed_kmh: float) -> int:
    if speed_kmh <= 0:
        return 1000
    radius = int(speed_kmh * 1000.0 / 20.0)
    return max(MIN_SEARCH_RADIUS_METERS, min(radius, MAX_SEARCH_RADIUS_METERS))


def format_location(lat: float, lon: float) -> str:
    return f"{lon},{lat}"


def compute_estimated_arrival_min(distance_m: int, speed_kmh: float) -> float:
    if speed_kmh <= 0:
        return float(inf)
    speed_m_per_s = speed_kmh * 1000.0 / 3600.0
    return distance_m / speed_m_per_s / 60.0


def compute_preview_start_seconds(distance_m: int, speed_kmh: float) -> int:
    arrival_sec = compute_estimated_arrival_min(distance_m, speed_kmh) * 60.0
    return max(0, int(arrival_sec - PREVIEW_LEAD_MINUTES * 60))


def compute_selection_weight(introduced_count: int, distance_m: int, is_ahead: bool = True) -> float:
    # 介绍次数 >= 5 次：直接排除
    if introduced_count >= 5:
        return 0.0
    
    # 太近（可能已路过）或不在前进方向：排除
    if distance_m < MIN_DISTANCE_CONSIDERED or not is_ahead:
        return 0.0
    
    # 权重 = 已介绍次数倒数 × 距离衰减
    # 未介绍过时权重最高，介绍过1-4次时权重递减
    frequency_weight = 1.0 / (1.0 + introduced_count * 0.5)
    proximity_weight = max(0.2, 1.0 - min(distance_m, MAX_SEARCH_RADIUS_METERS) / MAX_SEARCH_RADIUS_METERS)
    
    return frequency_weight * proximity_weight


def _normalize_poi_id(poi):
    return poi.get("id") or poi.get("location") or f"{poi.get('name','')}_{poi.get('location','')}"


def _parse_location(location_str: str):
    """Parse Amap location string 'lon,lat' to tuple (lon, lat)"""
    parts = location_str.split(",")
    if len(parts) >= 2:
        try:
            return (float(parts[0]), float(parts[1]))
        except:
            return None
    return None


def _bearing_between_points(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate bearing (compass angle 0-360) from point1 to point2.
    0 = North, 90 = East, 180 = South, 270 = West
    """
    from math import atan2, degrees, radians
    
    lat1_rad = radians(lat1)
    lat2_rad = radians(lat2)
    dlon = radians(lon2 - lon1)
    
    x = atan2(dlon, (lat1_rad - lat2_rad))
    bearing = (degrees(x) + 90) % 360
    return bearing


def _normalize_angle_diff(angle1: float, angle2: float) -> float:
    """Calculate smallest angle difference between two bearings (0-180)"""
    diff = abs(angle1 - angle2)
    if diff > 180:
        diff = 360 - diff
    return diff


def _is_coordinate_in_china(lat: float, lon: float) -> bool:
    # 高德地图主要覆盖中国国内范围，外部坐标常常返回空结果
    return 18.0 <= lat <= 54.0 and 73.0 <= lon <= 135.0


def _create_simulated_landmark(lat: float, lon: float, speed_kmh: float):
    distance = 1200
    return {
        "poi_id": f"simulated_{lat:.5f}_{lon:.5f}",
        "name": "模拟地标",
        "type": "模拟测试",
        "address": "模拟地点",
        "distance_m": distance,
        "location": f"{lon},{lat}",
        "estimated_arrival_min": round(compute_estimated_arrival_min(distance, speed_kmh), 1),
        "preview_start_seconds": compute_preview_start_seconds(distance, speed_kmh),
        "introduced_count": 0,
        "selection_weight": 0.5,
    }


def is_poi_ahead_in_direction(car_lat: float, car_lon: float, car_heading: int,
                               poi_location_str: str, heading_tolerance: int = 90) -> bool:
    """
    Check if POI is in front of the car within heading_tolerance degrees.
    heading_tolerance: acceptable angle deviation from car_heading (0-180, default 90 means ±90°)
    """
    poi_pos = _parse_location(poi_location_str)
    if not poi_pos:
        return False
    
    poi_lon, poi_lat = poi_pos
    bearing_to_poi = _bearing_between_points(car_lat, car_lon, poi_lat, poi_lon)
    angle_diff = _normalize_angle_diff(car_heading, bearing_to_poi)
    
    # If angle difference is <= tolerance, POI is ahead
    return angle_diff <= heading_tolerance


async def get_upcoming_landmarks(lat: float, lon: float, speed_kmh: float, heading: int = 0, max_results: int = 5, frequency_level: int = 50):
    radius = normalize_search_radius(speed_kmh)
    params = {
        "key": AMAP_API_KEY,
        "location": format_location(lat, lon),
        "keywords": AMAP_SEARCH_KEYWORDS,
        "radius": radius,
        "offset": max_results,
        "extensions": "base",
        "sortrule": "distance"
    }

    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(AMAP_PLACE_AROUND_URL, params=params)
        response.raise_for_status()
        data = response.json()

    pois = data.get("pois", [])
    if not pois:
        print(f"[⚠️  高德返回空结果] lat={lat} lon={lon} radius={radius} keywords={AMAP_SEARCH_KEYWORDS}")
        if not _is_coordinate_in_china(lat, lon):
            print(f"[ℹ️  坐标不在中国范围内，使用模拟地标候选]")
            return [_create_simulated_landmark(lat, lon, speed_kmh)]

    landmarks = []
    for poi in pois:
        distance = int(poi.get("distance", 0))
        estimated_arrival_min = compute_estimated_arrival_min(distance, speed_kmh)
        preview_seconds = compute_preview_start_seconds(distance, speed_kmh)
        poi_id = _normalize_poi_id(poi)
        poi_location = poi.get("location", "")
        
        # Check if POI is in front of the car within ±90° heading tolerance
        is_ahead = is_poi_ahead_in_direction(lat, lon, heading, poi_location, heading_tolerance=90)
        
        # 计算到 POI 的方向
        poi_pos = _parse_location(poi_location)
        if poi_pos:
            poi_lon, poi_lat = poi_pos
            bearing_to_poi = _bearing_between_points(lat, lon, poi_lat, poi_lon)
            angle_diff = _normalize_angle_diff(heading, bearing_to_poi)
        else:
            bearing_to_poi = -1
            angle_diff = 180
        
        history = _get_history_record(poi_id) or {}

        landmarks.append(LandmarkInfo(
            poi_id=poi_id,
            name=poi.get("name", "未知地点"),
            type=poi.get("type", "未知类型"),
            address=poi.get("address", ""),
            distance_m=distance,
            location=poi_location,
            estimated_arrival_min=round(estimated_arrival_min, 1),
            preview_start_seconds=preview_seconds,
            introduced_count=history.get("introduced_count", 0),
            selection_weight=compute_selection_weight(history.get("introduced_count", 0), distance, is_ahead)
        ).dict())
        
        print(f"  📍 {poi.get('name', '?')} | 距离 {distance}m | 方向 {bearing_to_poi:.0f}° (车头 {heading}° | 差异 {angle_diff:.0f}°) | 前方: {is_ahead} | 权重: {landmarks[-1]['selection_weight']:.3f}")

    sorted_landmarks = sorted(landmarks, key=lambda x: (-x["selection_weight"], x["distance_m"]))
    # Apply frequency_level filtering to control how permissive selection is
    # Map frequency_level to a minimum selection_weight threshold
    if frequency_level < 20:
        min_weight = 0.5
    elif frequency_level < 50:
        min_weight = 0.25
    elif frequency_level < 80:
        min_weight = 0.05
    else:
        min_weight = 0.0

    filtered = [l for l in sorted_landmarks if l["selection_weight"] >= min_weight]

    # If filtering is too strict and returns nothing, relax the filter gradually
    if not filtered:
        if frequency_level < 20:
            # fallback: allow introduced_count==0
            filtered = [l for l in sorted_landmarks if l.get("introduced_count", 0) == 0 and l.get("selection_weight", 0) > 0]
        if not filtered:
            filtered = sorted_landmarks

    return filtered[:max_results]


def select_landmark_for_session(candidates):
    if not candidates:
        return None

    # 优先选择有正权重的候选项，否则在所有候选中挑一个最合适的
    weighted = [c for c in candidates if c.get("selection_weight", 0.0) > 0.0]
    available = weighted if weighted else candidates

    weights = [c.get("selection_weight", 0.0) for c in available]
    total = sum(weights)
    if total > 0:
        return random.choices(available, weights=weights, k=1)[0]

    # 所有权重均为 0 时，选择最少介绍且距离最近的 POI
    return min(available, key=lambda x: (x.get("introduced_count", 0), x.get("distance_m", inf)))


# Load or initialize the database immediately when the module is imported.
_ensure_history_db()
