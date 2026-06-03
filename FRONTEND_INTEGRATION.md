"""
前端集成 API 规范

此文件定义了前端需要收集的数据，以及与后端交互的接口。
前端可以复制这些 TypeScript/Swift 数据模型到自己的项目中。
"""

# ==========================================
# 📍 数据模型（可复制到前端使用）
# ==========================================

# 【请求】实时位置和环境信息
# 用途：调用 /generate-radio 接口生成电台内容
RealTimeLocationPayload = {
    "lat": 39.905,              # float: 纬度 (必需)
    "lon": 116.391,             # float: 经度 (必需)
    "speed_kmh": 60,            # int: 当前车速 (单位：km/h) (必需)
    "heading": 180,             # int: 当前方向 (0-360°, 0=北 90=东 180=南 270=西) (必需)
    "familiarity_level": 0,     # int: 熟悉度 (0-10，保留字段，可不用)
    "current_music": "《打上花火》",  # str: 当前播放歌曲名
    "poi_name": "中山公园-唐花坞",      # str: 即将到达的景点名称 (重要!)
    "weather": "晴天",          # str: 天气情况
    "temperature": 28,          # int: 温度 (℃)
    "time_of_day": "下午3点",   # str: 当前时段描述 (e.g. "上午10点", "晚上8点")
}

# 【请求】地标查询
# 用途：调用 /upcoming-landmarks 接口获取前方候选景点
LandmarkSearchPayload = {
    "lat": 39.905,              # float: 纬度
    "lon": 116.391,             # float: 经度
    "speed_kmh": 60,            # float: 当前车速
    "heading": 180,             # int: 当前方向 (0-360°)
    "max_results": 5,           # int: 最多返回多少个候选 POI (默认5)
}

# 【响应】地标查询结果
LandmarkSearchResponse = {
    "preview_lead_minutes": 3,   # int: 提前介绍时间 (3分钟)
    "speed_kmh": 60,             # float: 当前车速
    "heading": 180,              # int: 当前方向
    "search_radius_m": 1000,     # int: 搜索半径 (根据速度计算)
    "heading_filter": "±90°",    # str: 方向过滤范围说明
    "selection_strategy": "...",  # str: 选择策略说明
    "candidates": [              # list: 候选 POI 列表
        {
            "poi_id": "B0FFGXMJIA",           # str: 高德 POI ID (用于记录)
            "name": "北京中山公园园史展",      # str: POI 名称
            "type": "风景名胜;旅游景点",       # str: POI 类型
            "address": "故宫内",               # str: 地址
            "distance_m": 492,                # int: 距离 (米)
            "location": "116.394101,39.908731",  # str: 经纬度 "lon,lat"
            "estimated_arrival_min": 0.5,    # float: 预计到达时间 (分钟)
            "preview_start_seconds": 0,      # int: 开始介绍的秒数
            "introduced_count": 0,           # int: 已介绍过的次数
            "selection_weight": 0.902,       # float: 选择权重 (0-1)
        },
        # ... 更多候选
    ],
    "selected_landmark": {       # dict: 推荐选择的 POI (可能为 None)
        "poi_id": "B0FFGFDIAY",
        "name": "中山公园-唐花坞",
        # ... 同上
    },
}

# 【请求】记录地标介绍
# 用途：调用 /record-landmark 接口记录已介绍过的景点
LandmarkIntroRecordPayload = {
    "poi_id": "B0FFGXMJIA",           # str: POI ID (从 /upcoming-landmarks 获取)
    "name": "北京中山公园园史展",     # str: POI 名称
    "location": "116.394101,39.908731",  # str: 经纬度
    "address": "故宫内",               # str: 地址
    "type": "风景名胜;旅游景点",       # str: POI 类型
}

# 【响应】记录成功
LandmarkIntroRecordResponse = {
    "status": "ok",              # str: 成功状态
    "poi_id": "B0FFGXMJIA",      # str: 记录的 POI ID
}


# ==========================================
# 🔄 前端工作流程
# ==========================================

"""
1️⃣  【持续采集 GPS 数据】- 建议频率：**每 10-15 秒一次**
    - 从车辆 GPS 模块读取：纬度、经度、车速、方向
    - 从系统获取：时间、天气（如果支持）
    
2️⃣  【查询前方景点】- 调用频率：**每 30-60 秒一次** (或车速变化显著时)
    POST /upcoming-landmarks
    请求体：LandmarkSearchPayload (使用最新 GPS 数据)
    响应：LandmarkSearchResponse
    
    📌 提示：
    - 系统会自动筛选"前方±90°范围内"的景点
    - 已介绍 ≥5 次的景点会被排除
    - selected_landmark 是系统推荐的首选
    
3️⃣  【用户选择要介绍的景点】
    - 方案A：直接使用系统推荐的 selected_landmark
    - 方案B：让用户从 candidates 列表中选择
    
4️⃣  【生成电台内容】- 调用频率：**用户点击播放时**
    POST /generate-radio
    请求体：RealTimeLocationPayload
             必须包含 poi_name（选中的景点名称）
    响应：MP3 音频 + 字幕信息（HTTP Header: X-Radio-Script）
    
    📌 提示：
    - 生成可能需要 2-5 秒
    - 响应是二进制 MP3 流
    - 字幕通过 HTTP Header 返回（URL 编码的中文）
    
5️⃣  【记录介绍】- 调用频率：**每次介绍后立即调用**
    POST /record-landmark
    请求体：LandmarkIntroRecordPayload
             使用从 /upcoming-landmarks 获取的 POI 信息
    响应：LandmarkIntroRecordResponse
    
    📌 提示：
    - 此步骤会更新本地数据库
    - 下次查询时已介绍次数会增加
    - 防止同一景点过度介绍


# ==========================================
# ⏰ 数据更新频率建议表
# ==========================================

操作                          频率                  说明
─────────────────────────────────────────────────────────
GPS 采集                    10-15 秒              从 GPS 模块持续读取
查询前方景点                30-60 秒              /upcoming-landmarks 调用
                            (或主动)              速度变化 >20km/h、方向变化 >30° 时立即调用
生成电台                    用户触发              仅当用户点击播放按钮时
记录介绍                    电台播放完后          完成介绍后立即调用

# ==========================================
# 🎯 关键字段说明
# ==========================================

【heading (方向/罗盘角度)】
  0° = 正北 (North)
  90° = 正东 (East)
  180° = 正南 (South)
  270° = 正西 (West)
  
  📌 重要：大多数 GPS 模块返回的"course"字段就是 heading

【estimated_arrival_min】
  以当前速度和距离计算，还需多少分钟到达
  值为 inf (无穷大) 时表示车速为 0

【preview_start_seconds】
  建议在到达前多少秒开始介绍（考虑了3分钟提前量）
  通常为 0（表示可以立即开始介绍）

【introduced_count】
  此景点已被介绍过的次数
  >= 5 次的景点会被自动排除（权重为 0）

【selection_weight】
  0.0 ~ 1.0 之间的数值
  数值越大，越推荐选择
  可用于在 UI 中显示"热度"指示器

【poi_id】
  高德地图的唯一 POI 标识
  📌 重要：调用 /record-landmark 时必须传入正确的 poi_id

【location】
  格式为 "lon,lat"（注意顺序是经纬度）
  这是高德标准格式


# ==========================================
# 📝 示例：前端伪代码流程
# ==========================================

```javascript
// 1. 启动时初始化 GPS 监听
startGPSTracking() {
  setInterval(() => {
    currentGPS = getGPSData();  // { lat, lon, speed_kmh, heading }
  }, 10000);  // 每 10 秒采集一次
}

// 2. 定期查询前方景点
queryUpcomingLandmarks() {
  setInterval(async () => {
    let response = await POST("/upcoming-landmarks", {
      lat: currentGPS.lat,
      lon: currentGPS.lon,
      speed_kmh: currentGPS.speed_kmh,
      heading: currentGPS.heading,
      max_results: 5,
    });
    
    // 保存候选列表和推荐选择
    candidates = response.candidates;
    recommendedLandmark = response.selected_landmark;
    
    // 在 UI 中更新可用景点列表
    updateLandmarkList(candidates);
    
  }, 30000);  // 每 30 秒查询一次
}

// 3. 用户点击播放按钮时
playRadio(landmark) {
  // 调用生成接口
  let response = await POST("/generate-radio", {
    lat: currentGPS.lat,
    lon: currentGPS.lon,
    speed_kmh: currentGPS.speed_kmh,
    heading: currentGPS.heading,
    current_music: currentPlayingMusic,
    poi_name: landmark.name,  // 关键！
    weather: getWeather(),
    temperature: getTemperature(),
    time_of_day: getTimeOfDay(),
  });
  
  // response 是 MP3 二进制 + 字幕在 Header 中
  let audioData = response.body;  // MP3 bytes
  let script = decodeURIComponent(response.headers["X-Radio-Script"]);  // 字幕
  
  playAudio(audioData);
  showScript(script);
}

// 4. 电台播放完成后
onAudioFinished(landmark) {
  // 记录此景点已介绍
  await POST("/record-landmark", {
    poi_id: landmark.poi_id,
    name: landmark.name,
    location: landmark.location,
    address: landmark.address,
    type: landmark.type,
  });
}
```


# ==========================================
# ❌ 常见错误
# ==========================================

❌ 问题1：poc_name 为空
   → 后端无法生成合适的剧本
   → 确保 /generate-radio 调用时 poi_name 必填

❌ 问题2：poi_id 错误或丢失
   → /record-landmark 记录失败
   → 确保从 /upcoming-landmarks 的响应中正确复制 poi_id

❌ 问题3：heading 范围错误 (> 360 或 < 0)
   → 地标筛选失效
   → 确保 heading 值在 0-360 之间

❌ 问题4：GPS 数据太旧
   → 查询到的景点可能已经路过
   → 确保 GPS 采集频率 >= 10-15 秒

❌ 问题5：频率调用过高
   → 后端负荷增加，生成时间延长
   → /upcoming-landmarks 建议 30-60 秒调用一次
   → /generate-radio 仅用户触发
"""
