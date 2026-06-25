import httpx
from math import inf, sin, cos, sqrt, pi

from config import AMAP_API_KEY, logger

AMAP_PLACE_AROUND_URL = "https://restapi.amap.com/v3/place/around"
AMAP_SEARCH_KEYWORDS = "历史建筑|文化地标|旅游景点|博物馆|纪念馆|公园|大学|名人故居|寺庙|教堂|古塔|古桥|老街|古镇|广场|故居|遗址"

# ==========================================
# ⚖️  POI 选择权重配置
# ==========================================
# 距离相关：100m 以内不算播报目标（可能已路过 / GPS 抖动）
MIN_DISTANCE_CONSIDERED = 100
# 提前多久开始考虑这个 POI（用于 preview_start_seconds）
PREVIEW_LEAD_MINUTES = 2

# POI 类型权重表（高德 typecode 前缀 -> 权重）
# 数值越高代表"越值得做电台介绍"
# weight=0 → 直接排除，不进入候选
POI_TYPE_WEIGHTS = {
    # ⭐ 绝对值得播
    "110200": 1.5,  # 风景名胜
    "110000": 1.5,  # 博物馆 / 知名景点
    "110100": 1.4,  # 公园广场
    "150200": 1.4,  # 美术馆 / 展览馆
    "110300": 1.3,  # 城市广场
    "150300": 1.3,  # 科技馆
    "140000": 1.2,  # 政府机构 / 知名建筑
    "150100": 1.1,  # 学校 / 高校（有历史感的）
    # ⚠️ 勉强可以
    "060000": 0.6,  # 购物（仅限有历史/文化价值的商场老街）
    "050000": 0.5,  # 餐饮（仅限老字号/名店）
    "080000": 0.4,  # 住宿（仅限有特色的宾馆/民宿）
    "100000": 0.3,  # 体育场馆
    # ❌ 商业/生活服务——直接排除
    "170000": 0.0,  # 公司企业（旅行社、打字复印社等）
    "160000": 0.0,  # 商业零售
    "180000": 0.0,  # 生活服务
    "190000": 0.0,  # 加油站 / 汽车服务
    "200000": 0.0,  # 公共设施
    "010000": 0.0,  # 地铁站 / 公交站
    "020000": 0.0,  # 道路附属
}
DEFAULT_POI_TYPE_WEIGHT = 0.0  # 未知类型也排除

# WGS84 → GCJ-02 火星坐标系转换常量
_EARTH_A = 6378245.0  # 长半轴
_EARTH_EE = 0.00669342162296594323  # 扁率


def _out_of_china(lat: float, lon: float) -> bool:
    """判断坐标是否在中国境外（境外不需要转换）"""
    return lon < 72.004 or lon > 137.8347 or lat < 0.8293 or lat > 55.8271


def _transform_lat(x: float, y: float) -> float:
    ret = -100.0 + 2.0 * x + 3.0 * y + 0.2 * y * y + 0.1 * x * y + 0.2 * sqrt(abs(x))
    ret += (20.0 * sin(6.0 * x * pi) + 20.0 * sin(2.0 * x * pi)) * 2.0 / 3.0
    ret += (20.0 * sin(y * pi) + 40.0 * sin(y / 3.0 * pi)) * 2.0 / 3.0
    ret += (160.0 * sin(y / 12.0 * pi) + 320.0 * sin(y * pi / 30.0)) * 2.0 / 3.0
    return ret


def _transform_lon(x: float, y: float) -> float:
    ret = 300.0 + x + 2.0 * y + 0.1 * x * x + 0.1 * x * y + 0.1 * sqrt(abs(x))
    ret += (20.0 * sin(6.0 * x * pi) + 20.0 * sin(2.0 * x * pi)) * 2.0 / 3.0
    ret += (20.0 * sin(x * pi) + 40.0 * sin(x / 3.0 * pi)) * 2.0 / 3.0
    ret += (150.0 * sin(x / 12.0 * pi) + 300.0 * sin(x / 30.0 * pi)) * 2.0 / 3.0
    return ret


def wgs84_to_gcj02(lat: float, lon: float) -> tuple[float, float]:
    """WGS84 → GCJ-02 火星坐标系"""
    if _out_of_china(lat, lon):
        return lat, lon  # 境外不转换
    dlat = _transform_lat(lon - 105.0, lat - 35.0)
    dlon = _transform_lon(lon - 105.0, lat - 35.0)
    radlat = lat / 180.0 * pi
    magic = 1 - _EARTH_EE * sin(radlat) * sin(radlat)
    sqrtmagic = sqrt(magic)
    dlat = (dlat * 180.0) / ((_EARTH_A * (1 - _EARTH_EE)) / (magic * sqrtmagic) * pi)
    dlon = (dlon * 180.0) / (_EARTH_A / sqrtmagic * cos(radlat) * pi)
    return lat + dlat, lon + dlon


def normalize_search_radius(speed_kmh: float) -> int:
    if speed_kmh <= 0:
        return 200  # 静止时 200m
    elif speed_kmh <= 30:
        return 300
    elif speed_kmh <= 70:
        return 500
    elif speed_kmh <= 100:
        return 800
    else:
        return 1000


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


def _rating_to_popularity(rating: float) -> float:
    """将高德评分 (0-5) 映射为热度权重 (0.4-1.0)"""
    if rating <= 0:
        return 0.5  # 无评分用默认值
    return max(0.4, min(1.0, rating / 5.0))


def compute_selection_weight(introduced_count: int, distance_m: int, is_ahead: bool = True,
                              typecode: str = "", rating: float = 0.0) -> float:
    """
    计算 POI 的选择权重（0.0 - 1.5 范围，实际受所有因子压制）
    
    公式：weight = type_weight × popularity_weight × frequency_weight × proximity_weight
    
    硬性返回 0.0 的情况：
    - introduced_count >= 5（已经讲烂了）
    - distance_m < MIN_DISTANCE_CONSIDERED（太近，可能已路过）
    - distance_m > MAX_SEARCH_RADIUS_METERS（太远，超出本次搜索范围）
    - 不在前进方向（is_ahead == False）
    """
    # 介绍次数 >= 5 次：直接排除
    if introduced_count >= 5:
        return 0.0
    
    # 太近（可能已路过）或不在前进方向：排除
    if distance_m < MIN_DISTANCE_CONSIDERED or not is_ahead:
        return 0.0
    
    # 权重 = 类型权重 × 热度评分 × 熟悉度 × 距离衰减
    type_weight = _get_type_weight(typecode)
    # 商业/生活服务类直接排除
    if type_weight <= 0:
        return 0.0
    popularity_weight = _rating_to_popularity(rating)
    # 介绍过 1 次 → 0.67，2 次 → 0.5，3 次 → 0.4，4 次 → 0.33
    frequency_weight = 1.0 / (1.0 + introduced_count * 0.5)
    # 距离越近权重越高，最小不低于 0.2；3000m 以外衰减到 0.2
    proximity_weight = max(0.2, 1.0 - distance_m / 3000.0)
    
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
    Otherwise use a ±90° tolerance (front 180°).
    """
    # 只有速度极低（几乎静止）且 heading 噪声大时才放宽
    if speed_kmh < 2.0:
        return True

    heading_tolerance = 30  # ±30°，即前方 60° 扇形

    poi_pos = _parse_location(poi_location_str)
    if not poi_pos:
        return False  # 无法解析坐标时，保守返回不在前方
    
    poi_lon, poi_lat = poi_pos
    bearing_to_poi = _bearing_between_points(car_lat, car_lon, poi_lat, poi_lon)
    angle_diff = _normalize_angle_diff(car_heading, bearing_to_poi)
    
    return angle_diff <= heading_tolerance


async def get_upcoming_landmarks(lat: float, lon: float, speed_kmh: float, heading: int = 0,
                                  max_results: int = 5, introduced_poi_ids: dict = None):
    """
    查询前方 POI，并为每个 POI 计算选择权重

    Args:
        lat, lon:         GPS 位置
        speed_kmh:        车速（用于动态搜索半径 & 方向判断）
        heading:          车头方向 (0-360)
        max_results:      返回候选数量上限
        introduced_poi_ids: iOS 本地历史 {poi_id: 播报次数}（用于算 frequency_weight）

    Returns:
        按 selection_weight 降序的 POI 列表，每个包含:
        - 原始高德字段 (poi_id, name, type, typecode, address, distance_m, location, rating, province, city, district)
        - selection_weight: float  选择权重（0 表示应排除）
        - is_ahead:        bool   是否在前进方向
        - introduced_count: int   本 POI 在 iOS 历史中的播报次数
    """
    if introduced_poi_ids is None:
        introduced_poi_ids = {}

    # WGS84 → GCJ-02 火星坐标转换
    gcj_lat, gcj_lon = wgs84_to_gcj02(lat, lon)
    radius = normalize_search_radius(speed_kmh)
    params = {
        "key": AMAP_API_KEY,
        "location": format_location(gcj_lat, gcj_lon),
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
        logger.warning(f"高德返回空结果 | lat={lat} lon={lon} radius={radius} keywords={AMAP_SEARCH_KEYWORDS}")
        if not _is_coordinate_in_china(lat, lon):
            logger.info("坐标不在中国范围内，使用模拟地标候选")
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

        # 计算方向（需用 GCJ-02 坐标调高德，同坐标系）
        is_ahead = is_poi_ahead_in_direction(
            car_lat=gcj_lat, car_lon=gcj_lon,
            car_heading=heading,
            poi_location_str=poi_location,
            speed_kmh=speed_kmh,
        )

        # 从 iOS 历史中取已播报次数
        introduced_count = introduced_poi_ids.get(poi_id, 0)

        # 计算选择权重
        typecode = poi.get("typecode", "")
        weight = compute_selection_weight(
            introduced_count=introduced_count,
            distance_m=distance,
            is_ahead=is_ahead,
            typecode=typecode,
            rating=rating,
        )

        landmarks.append({
            "poi_id": poi_id,
            "name": poi.get("name", "未知地点"),
            "type": poi.get("type", "未知类型"),
            "typecode": typecode,
            "address": poi.get("address", ""),
            "distance_m": distance,
            "location": poi_location,
            "rating": rating,
            "province": poi.get("pname", ""),
            "city": poi.get("cityname", ""),
            "district": poi.get("adname", ""),
            "is_ahead": is_ahead,
            "introduced_count": introduced_count,
            "selection_weight": round(weight, 4),
        })

    # 按选择权重降序，剔除 weight=0 的（不在前方/太近/已播太多次）
    landmarks.sort(key=lambda x: x["selection_weight"], reverse=True)
    landmarks = [lm for lm in landmarks if lm["selection_weight"] > 0]
    return landmarks[:max_results]
