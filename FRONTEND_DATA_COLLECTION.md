"""
前端数据采集与系统集成指南

此文档指导前端如何采集 GPS 数据、环境信息等，
并以正确的频率调用后端接口。
"""

# ==========================================
# 📍 iOS 前端 - GPS 数据采集
# ==========================================

## 使用 CLLocationManager 采集 GPS 数据

```swift
import CoreLocation

class GPSTracker: NSObject, CLLocationManagerDelegate {
    let locationManager = CLLocationManager()
    var currentLocation: CLLocationCoordinate2D?
    var currentSpeed: CLLocationSpeed = 0  // m/s
    var currentHeading: CLHeading?
    
    override init() {
        super.init()
        
        // 请求权限
        locationManager.requestWhenInUseAuthorization()
        locationManager.delegate = self
        
        // 设置采集参数
        locationManager.desiredAccuracy = kCLLocationAccuracyBest
        locationManager.distanceFilter = 10  // 距离 10m 更新一次
        locationManager.headingFilter = 5    // 方向 5° 更新一次
        
        // 启动采集
        locationManager.startUpdatingLocation()
        locationManager.startUpdatingHeading()
    }
    
    // MARK: - CLLocationManagerDelegate
    
    func locationManager(_ manager: CLLocationManager, didUpdateLocations locations: [CLLocation]) {
        guard let location = locations.last else { return }
        
        currentLocation = location.coordinate
        currentSpeed = location.speed  // m/s
        
        // 转换为前端所需的格式
        let gpsData = GPSData(
            latitude: location.coordinate.latitude,
            longitude: location.coordinate.longitude,
            speed: Float(location.speed),  // m/s，会自动转换为 km/h
            course: Float(location.course)  // 0-360°
        )
        
        // 保存到全局状态或通过 delegate 回调
        updateGPSData(gpsData)
    }
    
    func locationManager(_ manager: CLLocationManager, didUpdateHeading newHeading: CLHeading) {
        currentHeading = newHeading
    }
}
```

## 获取时间和天气信息

```swift
import WeatherKit
import Foundation

func getTimeOfDay() -> String {
    let hour = Calendar.current.component(.hour, from: Date())
    switch hour {
    case 6..<12: return "上午\(hour)点"
    case 12..<18: return "下午\((hour - 12) % 12)点"
    case 18..<24: return "晚上\((hour - 12))点"
    default: return "凌晨\(hour)点"
    }
}

// iOS 16+ 使用 WeatherKit
@available(iOS 16.0, *)
func getWeatherInfo() async -> (weather: String, temperature: Int) {
    do {
        let weather = try await WeatherService.shared.weather(for: CLLocationCoordinate2D(latitude: 39.9, longitude: 116.4))
        let description = weather.currentWeather.symbolName  // 如 "sun.max", "cloud.rain"
        let temp = Int(weather.currentWeather.temperature.value)
        return (description, temp)
    } catch {
        return ("未知", 0)
    }
}

// 或使用第三方 API (如 OpenWeatherMap)
func getWeatherFromAPI() async -> (weather: String, temperature: Int) {
    // ... 调用天气 API
    return ("晴天", 28)
}
```


# ==========================================
# 🌐 Web 前端 - GPS 数据采集 (Geolocation API)
# ==========================================

```typescript
// 启动 GPS 采集 (每 10-15 秒一次)
function startGPSTracking(onGPSUpdate: (gps: GPSData) => void) {
  if (!navigator.geolocation) {
    console.error('浏览器不支持 Geolocation API');
    return;
  }

  setInterval(() => {
    navigator.geolocation.getCurrentPosition(
      (position) => {
        const { latitude, longitude, speed, heading, accuracy } = position.coords;
        
        const gpsData: GPSData = {
          lat: latitude,
          lon: longitude,
          speed_kmh: speed ? Math.round(speed * 3.6) : 0,  // m/s -> km/h
          heading: heading || 0,  // 0-360°
        };
        
        onGPSUpdate(gpsData);
      },
      (error) => {
        console.error('GPS 获取失败:', error);
      },
      {
        enableHighAccuracy: true,
        timeout: 5000,
        maximumAge: 0,
      }
    );
  }, 10000);  // 每 10 秒采集一次
}

// 获取时间
function getTimeOfDay(): string {
  const hour = new Date().getHours();
  if (hour >= 6 && hour < 12) return `上午${hour}点`;
  if (hour >= 12 && hour < 18) return `下午${hour - 12}点`;
  if (hour >= 18 && hour < 24) return `晚上${hour - 12}点`;
  return `凌晨${hour}点`;
}

// 获取天气 (可选，需要调用天气 API)
async function getWeather(): Promise<{ weather: string; temperature: number }> {
  // 这里需要调用真实的天气 API
  // 示例: OpenWeatherMap, WeatherAPI 等
  return {
    weather: '晴天',  // 示例
    temperature: 28,
  };
}
```


# ==========================================
# 🎵 前端状态管理 - 播放中的音乐
# ==========================================

```typescript
// 需要追踪的状态
interface AppState {
  currentGPS: {
    lat: number;
    lon: number;
    speed_kmh: number;
    heading: number;
  };
  currentMusic: string;         // 当前播放的歌曲名
  weather: string;              // 天气
  temperature: number;          // 温度
  upcomingLandmarks: LandmarkInfo[] | null;  // 候选 POI
  selectedLandmark: LandmarkInfo | null;     // 选中的 POI
}

// 状态更新流程
const appState: AppState = {
  currentGPS: { lat: 0, lon: 0, speed_kmh: 0, heading: 0 },
  currentMusic: '无',
  weather: '',
  temperature: 0,
  upcomingLandmarks: null,
  selectedLandmark: null,
};

// 每 10 秒更新 GPS
setInterval(() => {
  navigator.geolocation.getCurrentPosition((position) => {
    appState.currentGPS = {
      lat: position.coords.latitude,
      lon: position.coords.longitude,
      speed_kmh: Math.round((position.coords.speed || 0) * 3.6),
      heading: position.coords.heading || 0,
    };
  });
}, 10000);

// 每 30 秒查询景点
setInterval(async () => {
  const response = await apiClient.queryUpcomingLandmarks({
    lat: appState.currentGPS.lat,
    lon: appState.currentGPS.lon,
    speed_kmh: appState.currentGPS.speed_kmh,
    heading: appState.currentGPS.heading,
  });
  
  appState.upcomingLandmarks = response.candidates;
  appState.selectedLandmark = response.selected_landmark;
  
  updateUI();  // 刷新 UI
}, 30000);
```


# ==========================================
# 📊 数据调用时间线
# ==========================================

时间轴：

0 秒   → 用户启动 App
        → 启动 GPS 采集 (每 10-15 秒)
        → 启动天气更新 (每 5 分钟 或系统更新时)

10 秒  → 获取第 1 次 GPS 数据
20 秒  → 获取第 2 次 GPS 数据
30 秒  → 获取第 3 次 GPS 数据 + 调用 /upcoming-landmarks
        → 显示候选景点列表或自动选择推荐景点

60 秒  → 获取第 6 次 GPS 数据 + 调用 /upcoming-landmarks (第 2 次)
        → 更新候选景点列表

用户点击播放 → 调用 /generate-radio (获取 MP3 + 字幕)
           → 播放音频
           
播放完成   → 调用 /record-landmark (记录介绍)
           → 继续循环


# ==========================================
# ⚠️ 重点注意事项
# ==========================================

1. ✅ GPS 采集
   - 频率：10-15 秒一次
   - 确保 heading 有效 (某些 GPS 模块需要移动才能获取方向)
   - speed 单位需要转换 (m/s → km/h) 乘以 3.6

2. ✅ 景点查询
   - 频率：30-60 秒一次
   - 或在以下情况下主动查询：
     * 车速变化 > 20 km/h
     * 方向变化 > 30°
   - 使用最新 GPS 数据

3. ✅ 生成电台
   - 频率：用户触发 (点击播放按钮)
   - poi_name **必须** 有值，否则剧本生成失败
   - 响应包含 MP3 + 字幕，需分别处理

4. ✅ 记录介绍
   - 频率：每次介绍完成后立即调用
   - poi_id 必须准确复制 (来自 /upcoming-landmarks 的响应)
   - 此步骤会更新本地数据库

5. ❌ 避免的错误
   - ❌ 频率过高 (如 1 秒查询一次景点) → 后端负荷过大
   - ❌ poi_name 为空 → 剧本生成失败
   - ❌ heading 无效 (始终为 0) → 地标筛选失效
   - ❌ poi_id 错误或丢失 → 记录失败
   - ❌ GPS 数据太旧 (> 2 分钟) → 查询到已路过的景点


# ==========================================
# 📋 前端清单 - 需要实现的功能
# ==========================================

[ ] GPS 数据采集 (每 10-15 秒)
    - 纬度、经度
    - 速度 (转换为 km/h)
    - 方向 heading (0-360°)

[ ] 环境信息采集
    - 当前时间 (时段描述)
    - 天气信息
    - 温度

[ ] 正在播放的音乐信息
    - 歌曲名称
    - (可选) 歌手、专辑等

[ ] 景点查询接口集成
    - 定期调用 /upcoming-landmarks (30-60 秒)
    - 显示候选景点列表
    - 显示推荐景点

[ ] 音乐播放集成
    - 从系统获取当前播放的歌曲
    - 更新到 appState

[ ] 生成电台接口集成
    - 用户点击播放时调用 /generate-radio
    - 正确设置 poi_name
    - 处理 MP3 音频播放
    - 显示字幕

[ ] 记录介绍接口集成
    - 播放完成后调用 /record-landmark
    - 传入正确的 POI 信息

[ ] UI 显示
    - 显示当前 GPS 坐标
    - 显示当前速度和方向
    - 显示候选景点列表
    - 显示推荐景点
    - 播放/暂停按钮
    - 显示字幕
    - 显示加载状态和错误信息

[ ] 测试
    - 测试 GPS 数据准确性
    - 测试景点查询响应
    - 测试音频播放
    - 测试记录功能
    - 测试数据频率
"""
