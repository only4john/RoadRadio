from pydantic import BaseModel


class RealTimeLocationPayload(BaseModel):
    """实时位置和环境信息"""
    lat: float = 0.0
    lon: float = 0.0
    speed_kmh: int = 0
    heading: int = 0
    familiarity_level: int = 0
    current_music: str = "无"
    
    # 💡 留空的扩展字段，默认值为空/0，保证前端漏传时不报错
    poi_name: str = ""        
    weather: str = ""         
    temperature: int = 0      
    time_of_day: str = ""
    artist: str = ""          # 当前播放音乐的歌手/艺术家
    month: str = ""           # 当前月份，如 "6月"
    province: str = ""        # POI 所在省
    city: str = ""            # POI 所在市
    district: str = ""        # POI 所在区/县     


class LandmarkIntroRecordPayload(BaseModel):
    """记录地标介绍的请求体"""
    poi_id: str
    name: str
    location: str
    address: str = ""
    type: str = ""


class LandmarkSearchPayload(BaseModel):
    """地标查询请求 — 只查高德，不过滤"""
    lat: float
    lon: float
    speed_kmh: float = 40.0
    heading: int = 0
    max_results: int = 5


class LandmarkCandidate(BaseModel):
    """单个 POI 候选"""
    poi_id: str
    name: str
    type: str = ""
    typecode: str = ""
    address: str = ""
    distance_m: int = 0
    location: str = ""
    rating: float = 0.0
    province: str = ""
    city: str = ""
    district: str = ""


class SelectBestLandmarkPayload(BaseModel):
    """iOS 过滤后传给 DeepSeek 选最佳的请求"""
    candidates: list[LandmarkCandidate]
    user_context: dict = {}  # 可选的额外上下文
