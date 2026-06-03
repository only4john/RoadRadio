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


class LandmarkIntroRecordPayload(BaseModel):
    """记录地标介绍的请求体"""
    poi_id: str
    name: str
    location: str
    address: str = ""
    type: str = ""
