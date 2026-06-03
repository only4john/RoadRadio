# 🎙️ 车载电台后端系统 - 前端集成指南

## 📚 文档结构

前端开发者应按顺序阅读以下文件：

1. **[FRONTEND_INTEGRATION.md](FRONTEND_INTEGRATION.md)** ⭐️ 必读
   - 后端三个 API 接口的完整规范
   - 请求/响应数据模型
   - 前端工作流程
   - 数据更新频率建议
   - 常见错误排查

2. **[FRONTEND_DATA_COLLECTION.md](FRONTEND_DATA_COLLECTION.md)**
   - 如何从 GPS、系统获取所需数据
   - iOS (CLLocationManager) 示例
   - Web (Geolocation API) 示例
   - 状态管理
   - 前端清单 (TODO list)

3. **[swift_models.swift](swift_models.swift)**
   - iOS 前端可直接复制使用的数据模型
   - RadioAPIClient HTTP 客户端实现
   - 完整的 Swift 代码

4. **[typescript_models.ts](typescript_models.ts)**
   - Web 前端可直接复制使用的数据模型
   - RadioAPIClient HTTP 客户端实现
   - React Hook 示例
   - 工具函数 (距离格式化、时间转换等)
   - 完整的 TypeScript 代码


## 🎯 快速开始 (5 分钟)

### iOS 前端

```swift
// 1️⃣ 复制 swift_models.swift 中的所有代码到项目

// 2️⃣ 创建 GPS 追踪器
let gpsTracker = GPSTracker()

// 3️⃣ 定期查询景点
let apiClient = RadioAPIClient()
apiClient.queryUpcomingLandmarks(
    lat: gpsTracker.currentLocation!.latitude,
    lon: gpsTracker.currentLocation!.longitude,
    speed_kmh: Float(gpsTracker.currentSpeed * 3.6),
    heading: Int(gpsTracker.currentHeading?.trueHeading ?? 0)
) { response, error in
    if let response = response {
        // 显示候选景点或使用推荐景点
        let landmark = response.selected_landmark
    }
}

// 4️⃣ 用户点击播放时
apiClient.generateRadio(payload: RealTimeLocationPayload(...)) { audio, script, error in
    // 播放音频
}

// 5️⃣ 播放完成后
apiClient.recordLandmarkIntro(poi_id: ...) { response, error in
    // 已记录
}
```

### Web 前端 (React/TypeScript)

```typescript
// 1️⃣ 复制 typescript_models.ts 中的所有代码到项目

// 2️⃣ 使用 Hook 监听景点
const { landmarks, selected, loading } = useUpcomingLandmarks(currentGPS);

// 3️⃣ 用户点击播放时
await playRadio(currentGPS, selectedLandmark, {
    weather: 'sunny',
    temperature: 28,
    time_of_day: '下午3点',
});

// 4️⃣ 自动记录介绍
const client = new RadioAPIClient();
await client.recordLandmarkIntro({
    poi_id: landmark.poi_id,
    name: landmark.name,
    location: landmark.location,
    // ...
});
```


## 📊 后端 API 速查表

| 接口 | 方法 | 功能 | 频率 |
|------|------|------|------|
| `/upcoming-landmarks` | POST | 查询前方景点候选 | 每 30-60 秒 |
| `/generate-radio` | POST | 生成电台内容 (MP3 + 字幕) | 用户触发 |
| `/record-landmark` | POST | 记录已介绍的景点 | 播放完成后 |


## 🗂️ 前端需要收集的数据

### GPS 数据 (每 10-15 秒采集一次)

| 字段 | 类型 | 单位 | 说明 |
|------|------|------|------|
| `lat` | float | 度 | 纬度 |
| `lon` | float | 度 | 经度 |
| `speed_kmh` | int | km/h | 当前车速 |
| `heading` | int | 度 | 方向 (0=北, 90=东, 180=南, 270=西) |

### 环境信息 (实时获取)

| 字段 | 类型 | 说明 | 获取方式 |
|------|------|------|----------|
| `current_music` | string | 当前播放歌曲 | 音乐播放器 API |
| `weather` | string | 天气情况 | 天气 API 或系统 |
| `temperature` | int | 温度 (℃) | 天气 API 或系统 |
| `time_of_day` | string | 时段 (如"下午3点") | 系统时间 |


## ⏱️ 数据采集频率总结

```
GPS 采集         → 每 10-15 秒
查询景点         → 每 30-60 秒 (或速度/方向变化时)
生成电台         → 用户点击播放
记录介绍         → 播放完成后立即调用
```

⚠️ **重要**：不要以过高的频率调用接口，否则会影响后端性能！


## ❓ 常见问题

**Q: 为什么查询到的景点是错误的？**  
A: 检查以下几点：
- [ ] heading (方向) 是否正确？系统只返回前方 ±90° 范围内的景点
- [ ] GPS 数据是否最新？确保 10-15 秒更新一次
- [ ] 景点是否已被介绍过 5 次？5+ 次会被自动排除

**Q: 音频生成失败？**  
A: 检查 RealTimeLocationPayload：
- [ ] poi_name 是否为空？此字段**必填**
- [ ] 其他字段 (weather, temperature 等) 是否正确格式化？
- [ ] 后端服务是否运行中？

**Q: 记录介绍失败？**  
A: 检查 LandmarkIntroRecordPayload：
- [ ] poi_id 是否准确？从 /upcoming-landmarks 响应中复制
- [ ] 所有必填字段 (poi_id, name, location) 是否有值？

**Q: 前端应该多久查询一次景点？**  
A: 建议 30-60 秒查询一次，或在以下情况主动查询：
- 车速变化 > 20 km/h
- 方向变化 > 30°
- 用户手动刷新


## 🔧 环境配置

### 后端服务地址

在前端代码中配置后端 URL：

```swift
// iOS
let apiClient = RadioAPIClient(baseURL: "http://192.168.1.100:8000")

// Web
const client = new RadioAPIClient('http://192.168.1.100:8000');
```

### 启动后端服务

```bash
cd /Users/fei/opt/laniakea_radio
source venv/bin/activate
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```


## 📝 前端开发清单

- [ ] 阅读 FRONTEND_INTEGRATION.md
- [ ] 阅读 FRONTEND_DATA_COLLECTION.md
- [ ] 复制数据模型 (swift_models.swift 或 typescript_models.ts)
- [ ] 实现 GPS 采集
- [ ] 实现环境信息采集 (天气、时间等)
- [ ] 实现 /upcoming-landmarks 定期查询
- [ ] 实现 /generate-radio 播放功能
- [ ] 实现 /record-landmark 记录功能
- [ ] 实现 UI (景点列表、播放按钮等)
- [ ] 测试各接口
- [ ] 测试数据频率和准确性
- [ ] 测试容错能力 (网络异常、GPS 丢失等)


## 🚀 部署建议

### 生产环境

- 使用环境变量管理 API 密钥，不要硬编码
- 添加请求超时和重试逻辑
- 添加错误日志和上报
- 性能监控 (接口响应时间、内存占用等)
- 缓存景点查询结果 (避免查询相同坐标)

### 调试技巧

- 打印所有 HTTP 请求和响应
- 验证 GPS 数据是否准确
- 使用模拟 GPS 进行测试
- 检查浏览器/设备的地位权限设置


## 📞 技术支持

遇到问题？检查以下资源：

1. 查看后端日志：  
   `tail -f /Users/fei/opt/laniakea_radio/*.log`

2. 检查后端状态：  
   访问 http://127.0.0.1:8000/docs (Swagger UI)

3. 检查 HTTP 请求：  
   在浏览器开发者工具中查看 Network 标签

4. 验证数据格式：  
   参考 FRONTEND_INTEGRATION.md 中的数据模型


---

**更新时间**: 2026-06-03  
**系统版本**: 1.0  
**最后修改**: 模块化重构后
