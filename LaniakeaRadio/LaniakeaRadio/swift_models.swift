// ==========================================
// iOS 前端数据模型 (Swift)
// 可直接复制到 iOS 项目使用
// ==========================================

import Foundation

// MARK: - 请求体模型

/// 实时位置和环境信息 - 用于 POST /generate-radio
struct RealTimeLocationPayload: Codable {
    let lat: Double               // 纬度
    let lon: Double               // 经度
    let speed_kmh: Int            // 当前车速 (km/h)
    let heading: Int              // 当前方向 (0-360°)
    let familiarity_level: Int    // 熟悉度 (保留字段，可设0)
    let current_music: String     // 当前播放歌曲
    let poi_name: String          // 即将到达的景点名称 ⭐️ 重要
    let weather: String           // 天气
    let temperature: Int          // 温度(℃)
    let time_of_day: String       // 当前时段 (如 "下午3点")
    
    init(
        lat: Double,
        lon: Double,
        speed_kmh: Int,
        heading: Int,
        current_music: String = "无",
        poi_name: String = "",
        weather: String = "",
        temperature: Int = 0,
        time_of_day: String = ""
    ) {
        self.lat = lat
        self.lon = lon
        self.speed_kmh = speed_kmh
        self.heading = heading
        self.familiarity_level = 0
        self.current_music = current_music
        self.poi_name = poi_name
        self.weather = weather
        self.temperature = temperature
        self.time_of_day = time_of_day
    }
}

/// 地标查询请求 - 用于 POST /upcoming-landmarks（只查高德，不带历史）
struct LandmarkSearchPayload: Codable {
    let lat: Double           // 纬度
    let lon: Double           // 经度
    let speed_kmh: Float      // 当前车速
    let heading: Int          // 当前方向 (0-360°)
    let max_results: Int      // 最多返回多少个候选 (默认5)
    
    init(
        lat: Double,
        lon: Double,
        speed_kmh: Float,
        heading: Int,
        max_results: Int = 5
    ) {
        self.lat = lat
        self.lon = lon
        self.speed_kmh = speed_kmh
        self.heading = heading
        self.max_results = max_results
    }
}

// MARK: - 高德原始 POI（/upcoming-landmarks 返回）

struct RawPOICandidate: Codable {
    let poi_id: String
    let name: String
    let type: String
    let typecode: String
    let address: String
    let distance_m: Int
    let location: String
    let rating: Double
    let province: String
    let city: String
    let district: String
}

struct UpcomingLandmarksResponse: Codable {
    let candidates: [RawPOICandidate]
}

// MARK: - DeepSeek 选 POI（/select-best-landmark）

struct SelectBestLandmarkPayload: Codable {
    let candidates: [RawPOICandidate]
    let user_context: [String: String]  // 可选上下文
    
    init(candidates: [RawPOICandidate], user_context: [String: String] = [:]) {
        self.candidates = candidates
        self.user_context = user_context
    }
}

struct SelectBestLandmarkResponse: Codable {
    let selected_landmark: RawPOICandidate?
}

/// 地标介绍记录 - 用于 POST /record-landmark
struct LandmarkIntroRecordPayload: Codable {
    let poi_id: String        // POI ID (必填)
    let name: String          // 景点名称
    let location: String      // 经纬度 "lon,lat"
    let address: String       // 地址
    let type: String          // POI 类型
    
    init(
        poi_id: String,
        name: String,
        location: String,
        address: String = "",
        type: String = ""
    ) {
        self.poi_id = poi_id
        self.name = name
        self.location = location
        self.address = address
        self.type = type
    }
}

// MARK: - 响应体模型

/// 单个 POI 信息
struct LandmarkInfo: Codable {
    let poi_id: String              // POI ID
    let name: String                // 景点名称
    let type: String                // POI 类型
    let address: String             // 地址
    let distance_m: Int             // 距离(米)
    let location: String            // 经纬度 "lon,lat"
    let estimated_arrival_min: Float // 预计到达时间(分钟)
    let preview_start_seconds: Int   // 开始介绍的秒数
    let introduced_count: Int        // 已介绍次数
    let selection_weight: Float      // 选择权重 (0-1)
}

/// 地标查询响应 - /upcoming-landmarks 的返回值
struct LandmarkSearchResponse: Codable {
    let preview_lead_minutes: Int       // 提前介绍时间(分钟)
    let speed_kmh: Float                // 当前车速
    let heading: Int                    // 当前方向
    let search_radius_m: Int            // 搜索半径(米)
    let heading_filter: String          // 方向过滤范围说明
    let selection_strategy: String      // 选择策略说明
    let candidates: [LandmarkInfo]      // 候选 POI 列表
    let selected_landmark: LandmarkInfo? // 推荐选择 (可能为 nil)
}

/// 记录成功响应 - /record-landmark 的返回值
struct LandmarkIntroRecordResponse: Codable {
    let status: String        // "ok"
    let poi_id: String        // POI ID
}

// MARK: - 辅助类：GPS 数据

/// GPS 数据模型 (从系统获取)
struct GPSData {
    let latitude: Double      // 纬度
    let longitude: Double     // 经度
    let speed: Float          // 速度 (m/s，需转换为 km/h)
    let course: Float         // 方向 (0-360°，即 heading)
    
    var speed_kmh: Int {
        return Int(speed * 3.6)  // m/s 转 km/h
    }
    
    var heading: Int {
        return Int(course)
    }
}

// MARK: - HTTP 客户端示例

class RadioAPIClient {
    let baseURL = serverBaseURL  // 后端服务地址，定义在 ContentView.swift
    
    /// 查询前方景点
    func queryUpcomingLandmarks(
        lat: Double,
        lon: Double,
        speed_kmh: Float,
        heading: Int,
        completion: @escaping (LandmarkSearchResponse?, Error?) -> Void
    ) {
        let payload = LandmarkSearchPayload(
            lat: lat,
            lon: lon,
            speed_kmh: speed_kmh,
            heading: heading
        )
        
        post(url: "\(baseURL)/upcoming-landmarks", body: payload) { (result: Result<LandmarkSearchResponse, Error>) in
            switch result {
            case .success(let response):
                completion(response, nil)
            case .failure(let error):
                completion(nil, error)
            }
        }
    }
    
    /// 生成电台内容
    func generateRadio(
        payload: RealTimeLocationPayload,
        completion: @escaping (Data?, String?, Error?) -> Void
    ) {
        guard let url = URL(string: "\(baseURL)/generate-radio") else {
            completion(nil, nil, NSError(domain: "Invalid URL", code: -1))
            return
        }

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try? JSONEncoder().encode(payload)

        URLSession.shared.dataTask(with: request) { data, response, error in
            if let error = error {
                completion(nil, nil, error)
                return
            }
            guard let data = data, let httpResp = response as? HTTPURLResponse else {
                completion(nil, nil, NSError(domain: "No data", code: -1))
                return
            }

            var script: String? = nil
            if let encoded = httpResp.value(forHTTPHeaderField: "X-Radio-Script") {
                script = encoded.removingPercentEncoding
            }

            completion(data, script, nil)
        }.resume()
    }
    
    /// 记录景点介绍
    func recordLandmarkIntro(
        poi_id: String,
        name: String,
        location: String,
        address: String = "",
        type: String = "",
        completion: @escaping (LandmarkIntroRecordResponse?, Error?) -> Void
    ) {
        let payload = LandmarkIntroRecordPayload(
            poi_id: poi_id,
            name: name,
            location: location,
            address: address,
            type: type
        )
        
        post(url: "\(baseURL)/record-landmark", body: payload) { (result: Result<LandmarkIntroRecordResponse, Error>) in
            switch result {
            case .success(let response):
                completion(response, nil)
            case .failure(let error):
                completion(nil, error)
            }
        }
    }
    
    // MARK: - Private Helper
    
    private func post<T: Encodable, R: Decodable>(
        url: String,
        body: T,
        completion: @escaping (Result<R, Error>) -> Void
    ) {
        var request = URLRequest(url: URL(string: url)!)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try? JSONEncoder().encode(body)
        
        URLSession.shared.dataTask(with: request) { data, response, error in
            if let error = error {
                completion(.failure(error))
                return
            }
            
            guard let data = data else {
                completion(.failure(NSError(domain: "No data", code: -1)))
                return
            }
            
            do {
                let result = try JSONDecoder().decode(R.self, from: data)
                completion(.success(result))
            } catch {
                completion(.failure(error))
            }
        }.resume()
    }
}
