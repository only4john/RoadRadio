import os
import random
import httpx
from math import inf
from config import AMAP_API_KEY

AMAP_PLACE_AROUND_URL = "https://restapi.amap.com/v3/place/around"
AMAP_SEARCH_KEYWORDS = "历史建筑|文化地标|旅游景点|博物馆|纪念馆|公园"
MAX_SEARCH_RADIUS_METERS = 2000


def normalize_search_radius(speed_kmh: float) -> int:
    if speed_kmh <= 0:
        return 100
    elif speed_kmh <= 30:
        return 100
    elif speed_kmh <= 70:
        return 200
    elif speed_kmh <= 100:
        return 500
    else:
        return 2000


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


def _get_type_weight(typecode: str) -> float:
    """根据高德 typecode 返回类型权重"""
    for prefix, weight in POI_TYPE_WEIGHTS.items():
        if typecode.startswith(prefix):
            return weight
    return DEFAULT_POI_TYPE_WEIGHT


def compute_selection_weight(introduced_count: int, distance_m: int, is_ahead: bool = True,
                              typecode: str = "", popularity_weight: float = 0.5) -> float:
    # 介绍次数 >= 5 次：直接排除
    if introduced_count >= 5:
        return 0.0
    
    # 太近（可能已路过）或不在前进方向：排除
    if distance_m < MIN_DISTANCE_CONSIDERED or not is_ahead:
        return 0.0
    
    # 距离超过搜索半径：排除（防止远处不相关景点混入）
    if distance_m > MAX_SEARCH_RADIUS_METERS:
        return 0.0
    
    # 权重 = 类型权重 × 热度评分 × 熟悉度 × 距离衰减
    type_weight = _get_type_weight(typecode)
    frequency_weight = 1.0 / (1.0 + introduced_count * 0.5)
    proximity_weight = max(0.2, 1.0 - min(distance_m, MAX_SEARCH_RADIUS_METERS) / MAX_SEARCH_RADIUS_METERS)
    
    return type_weight * popularity_weight * frequency_weight * proximity_weight


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
    dlat = lat2_rad - lat1_rad  # North is positive
    
    x = atan2(dlon, dlat)  # atan2(east_component, north_component)
    bearing = (degrees(x) + 360) % 360
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
                               poi_location_str: str, speed_kmh: float = 0.0) -> bool:
    """
    Check if POI is in front of the car.
    When speed is very low, heading is unreliable — treat all POIs as 'ahead'.
    Otherwise use a ±60° tolerance (front 120°).
    """
    # heading 在静止/低速时不可靠，此时不按方向过滤
    if speed_kmh < 5.0:
        return True

    heading_tolerance = 30  # ±30°，即前方 60° 扇形

    poi_pos = _parse_location(poi_location_str)
    if not poi_pos:
        return False
    
    poi_lon, poi_lat = poi_pos
    bearing_to_poi = _bearing_between_points(car_lat, car_lon, poi_lat, poi_lon)
    angle_diff = _normalize_angle_diff(car_heading, bearing_to_poi)
    
    return angle_diff <= heading_tolerance


async def get_upcoming_landmarks(lat: float, lon: float, speed_kmh: float, heading: int = 0, max_results: int = 5):
    """查询前方 POI（仅查高德 API，不做任何过滤，不过滤历史）"""
    radius = normalize_search_radius(speed_kmh)
    params = {
        "key": AMAP_API_KEY,
        "location": format_location(lat, lon),
        "keywords": AMAP_SEARCH_KEYWORDS,
        "radius": radius,
        "offset": max_results,
        "extensions": "all",
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
        poi_id = _normalize_poi_id(poi)
        poi_location = poi.get("location", "")

        # 提取高德评分
        biz_ext = poi.get("biz_ext", {}) or {}
        rating_str = biz_ext.get("rating", "")
        try:
            rating = float(rating_str) if rating_str else 0.0
        except (ValueError, TypeError):
            rating = 0.0

        landmarks.append({
            "poi_id": poi_id,
            "name": poi.get("name", "未知地点"),
            "type": poi.get("type", "未知类型"),
            "typecode": poi.get("typecode", ""),
            "address": poi.get("address", ""),
            "distance_m": distance,
            "location": poi_location,
            "rating": rating,
            "province": poi.get("pname", ""),
            "city": poi.get("cityname", ""),
            "district": poi.get("adname", ""),
        })

    # 只按距离排序，不做任何过滤
    landmarks.sort(key=lambda x: x["distance_m"])
    return landmarks[:max_results]
