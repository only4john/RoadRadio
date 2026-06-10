import SwiftUI
import AVFoundation
import Combine
import CoreLocation
import MediaPlayer

// ==========================================
// 🌐 后端服务器地址（修改这里即可切换）
//    真机请改为 Mac 局域网 IP 或云服务器地址
// ==========================================
let serverBaseURL = "http://49.51.247.112:8000"

// ==========================================
// 1. 后台大管家：双播放器架构（BGM + 人声）
// ==========================================
class RadioManager: NSObject, ObservableObject, AVAudioPlayerDelegate, CLLocationManagerDelegate {
    
    var voicePlayer: AVAudioPlayer?
    var bgmPlayer: AVAudioPlayer?
    private let locationManager = CLLocationManager()

    @Published var latitude: Double = 0
    @Published var longitude: Double = 0
    @Published var speedKmh: Int = 0
    @Published var headingDeg: Int = 0
    @Published var isLoading: Bool = false
    @Published var selectedPOIName: String = ""
    @Published var broadcastFrequency: Int = 50 // 0 = 最低，只播著名景点；100 = 最高，频繁播报

    @Published var weatherDescription: String = ""
    @Published var temperature: Int = 0
    @Published var currentMusicName: String = "无"
    @Published var currentArtist: String = ""
    @Published var generatedAudioFilename: String = ""
    @Published var bgmEnabled: Bool = false
    @Published var candidatePOIs: [[String: Any]] = []
    @Published var deepseekReason: String = ""   // DeepSeek 选择理由

    // 自动播报冷却
    private var lastAutoBroadcastTime: Date = .distantPast
    private var lastAutoBroadcastPOIId: String = ""  // 上次自动播报的 POI，避免重复

    // 模拟器测试覆盖值
    @Published var simulatedLatitude: Double = 30.5444
    @Published var simulatedLongitude: Double = 114.3665
    @Published var simulatedSpeedKmh: Int = 70
    @Published var simulatedHeadingDeg: Int = 0

    // 简化的已选 POI 信息
    private var selectedPOI: [String: Any]? = nil

    var displayLatitude: Double {
        #if targetEnvironment(simulator)
        return simulatedLatitude
        #else
        return latitude
        #endif
    }

    var displayLongitude: Double {
        #if targetEnvironment(simulator)
        return simulatedLongitude
        #else
        return longitude
        #endif
    }

    var displaySpeedKmh: Int {
        #if targetEnvironment(simulator)
        return simulatedSpeedKmh
        #else
        return speedKmh
        #endif
    }

    var displayHeadingDeg: Int {
        #if targetEnvironment(simulator)
        return simulatedHeadingDeg
        #else
        return headingDeg
        #endif
    }
    
    @Published var currentScript: String = ""
    @Published var isPlaying: Bool = false
    
    override init() {
        super.init()
        setupAudioSession()
        setupAndPlayBGM()
        setupLocation()
        setupNowPlayingObserver()
        // 启动时获取一次天气，之后每 30 分钟自动刷新
        Task { await fetchWeatherIfNeeded() }
        startWeatherTimer()
    }

    private func setupLocation() {
        locationManager.delegate = self
        locationManager.requestWhenInUseAuthorization()
        locationManager.desiredAccuracy = kCLLocationAccuracyBest
        locationManager.distanceFilter = 50  // 每 50 米更新一次
        if CLLocationManager.headingAvailable() {
            locationManager.headingFilter = 5
            locationManager.startUpdatingHeading()
        }
        locationManager.startUpdatingLocation()
    }

    deinit {
        NotificationCenter.default.removeObserver(self)
        MPMusicPlayerController.systemMusicPlayer.endGeneratingPlaybackNotifications()
    }

    private func setupNowPlayingObserver() {
        // 延迟至 App 完全启动后再注册，避免 init 阶段触发系统音频中断
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.0) { [weak self] in
            guard let self = self else { return }
            let player = MPMusicPlayerController.systemMusicPlayer
            player.beginGeneratingPlaybackNotifications()
            NotificationCenter.default.addObserver(self, selector: #selector(self.nowPlayingItemChanged), name: .MPMusicPlayerControllerNowPlayingItemDidChange, object: player)
            if let item = player.nowPlayingItem, let title = item.title {
                DispatchQueue.main.async {
                    self.currentMusicName = title
                    self.currentArtist = item.artist ?? ""
                }
            }
        }
    }

    @objc private func nowPlayingItemChanged(notification: Notification) {
        let player = MPMusicPlayerController.systemMusicPlayer
        if let item = player.nowPlayingItem, let title = item.title {
            DispatchQueue.main.async {
                self.currentMusicName = title
                self.currentArtist = item.artist ?? ""
            }
        }
    }

    // CLLocationManagerDelegate
    private var didFetchInitialWeather = false

    func locationManager(_ manager: CLLocationManager, didUpdateLocations locations: [CLLocation]) {
        guard let loc = locations.last else { return }
        let lat = loc.coordinate.latitude
        let lon = loc.coordinate.longitude
        DispatchQueue.main.async {
            self.latitude = lat
            self.longitude = lon
            self.speedKmh = Int(max(0, loc.speed) * 3.6)
            // 优先使用 GPS 路径的 course 作为方向（若有效），否则保留原有 heading
            if loc.course >= 0 {
                self.headingDeg = Int(loc.course)
            }
        }
        // GPS 首次定位后立刻获取天气（用 loc 原始坐标，不依赖 self.latitude 异步赋值）
        if !didFetchInitialWeather {
            didFetchInitialWeather = true
            Task { await self.fetchWeather(lat: lat, lon: lon) }
        }
        // 自动播报：GPS 更新时检测前方 POI 是否需要自动播报
        triggerAutoBroadcastIfNeeded()
    }

    /// 根据当前频率和 POI 权重自动决定是否触发播报
    private func triggerAutoBroadcastIfNeeded() {
        guard !isPlaying else { return }
        // 动态冷却：速度越慢间隔越长（低速时 POI 不轻易变化）
        let cooldown: TimeInterval = displaySpeedKmh > 60 ? 90 : (displaySpeedKmh > 30 ? 150 : 240)
        guard Date().timeIntervalSince(lastAutoBroadcastTime) >= cooldown else { return }
        guard displaySpeedKmh >= 0 else { return }  // 允许低速/静止时也触发

        let threshold: Double
        switch broadcastFrequency {
        case 80...100: threshold = 0.0
        case 50..<80:  threshold = 0.1
        case 20..<50:  threshold = 0.3
        default:       return
        }

        Task {
            await fetchAndSelectPOI()
            guard let poi = selectedPOI,
                  let weight = poi["selection_weight"] as? Double,
                  weight >= threshold else { return }

            // 避免重复播报同一个 POI
            let poiId = poi["poi_id"] as? String ?? ""
            if poiId == lastAutoBroadcastPOIId {
                print("⏭️ 跳过重复 POI: \(poi["name"] ?? "?")")
                return
            }

            lastAutoBroadcastTime = Date()
            lastAutoBroadcastPOIId = poiId
            print("🚗 自动播报触发！POI: \(poi["name"] ?? "?") 权重: \(weight)")
            await generateAndPlayRadio(speed: displaySpeedKmh, music: currentMusicName, prefetchedPOI: poi)
        }
    }

    func locationManager(_ manager: CLLocationManager, didUpdateHeading newHeading: CLHeading) {
        DispatchQueue.main.async {
            let heading = newHeading.trueHeading >= 0 ? newHeading.trueHeading : newHeading.magneticHeading
            self.headingDeg = Int(heading)
        }
    }
    
    private func setupAudioSession() {
        // 不在 init 时触碰 AVAudioSession，避免引起 Apple Music 暂停
        // 仅在播报前由 activateAudioSessionForVoice() 配置并激活
        print("🎧 音频会话待机（未激活，不影响系统音乐）")
    }

    // 播报前激活音频会话并启用闪避，压低 Apple Music 等背景音频
    private func activateAudioSessionForVoice() {
        do {
            let session = AVAudioSession.sharedInstance()
            try session.setCategory(.playback, mode: .default, options: [.duckOthers])
            try session.setActive(true)
            print("🔊 音频会话已激活（系统音乐已压低）")
        } catch {
            print("❌ 音频会话激活失败: \(error)")
        }
    }

    // 播报结束后释放音频会话，让 Apple Music 等恢复原音量
    private func deactivateAudioSession() {
        do {
            try AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
            print("🎵 音频会话已释放，系统音乐应恢复")
        } catch {
            print("⚠️ 音频会话释放失败: \(error)")
        }
    }
    
    // 加载并循环播放本地 BGM
    private func setupAndPlayBGM() {
        // BGM 默认关闭时不创建音频播放器，避免触发系统音频中断
        guard bgmEnabled else {
            print("🔇 BGM 已禁用，不初始化音频引擎")
            return
        }
        guard let bgmURL = Bundle.main.url(forResource: "bgm", withExtension: "mp3") else {
            print("⚠️ 找不到 bgm.mp3！请确保文件已加入项目并勾选了 Target Membership")
            return
        }
        
        do {
            bgmPlayer = try AVAudioPlayer(contentsOf: bgmURL)
            bgmPlayer?.numberOfLoops = -1 // 无限循环
            bgmPlayer?.volume = 0.5       // 初始满音量
            bgmPlayer?.prepareToPlay()
            bgmPlayer?.play()
            DispatchQueue.main.async { self.currentMusicName = bgmURL.lastPathComponent }
            print("🎵 BGM 启动成功！")
        } catch {
            print("❌ BGM 加载失败: \(error)")
        }
    }

    func toggleBGM() {
        bgmEnabled.toggle()
        if bgmEnabled {
            if bgmPlayer == nil {
                setupAndPlayBGM()
            } else {
                bgmPlayer?.play()
            }
            // BGM 需要激活音频会话（不闪避系统音乐）
            do {
                try AVAudioSession.sharedInstance().setCategory(.playback, mode: .default)
                try AVAudioSession.sharedInstance().setActive(true)
            } catch {
                print("⚠️ BGM 音频会话激活失败: \(error)")
            }
        } else {
            bgmPlayer?.stop()
            // 关闭 BGM 时释放音频会话
            do {
                try AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
            } catch {
                print("⚠️ BGM 音频会话释放失败: \(error)")
            }
        }
    }
    
    // 内部闪避：压低 BGM 音量（Apple Music 由 .duckOthers 自动处理）
    private func lowerBGMVolume() {
        bgmPlayer?.setVolume(0.1, fadeDuration: 0.5)
        print("🔊 BGM 已智能压低（Apple Music 系统自动闪避）")
    }
    
    // 内部闪避：恢复 BGM 音量（Apple Music 由 .duckOthers 自动恢复）
    private func restoreBGMVolume() {
        bgmPlayer?.setVolume(bgmEnabled ? 0.5 : 0.0, fadeDuration: 1.0)
        print("✅ BGM 音量已恢复（Apple Music 系统自动恢复）")
    }
    
    // 监听人声播放结束
    func audioPlayerDidFinishPlaying(_ player: AVAudioPlayer, successfully flag: Bool) {
        if player == voicePlayer {
            DispatchQueue.main.async {
                self.isPlaying = false
                self.restoreBGMVolume()
                self.deactivateAudioSession()  // 释放音频会话，恢复系统音乐音量
                self.recordLandmarkIntro()
            }
        }
    }
    
    func generateAndPlayRadio(speed: Int, music: String, prefetchedPOI: [String: Any]? = nil) async {
        // auto-broadcast 已有 POI，不要再查；手动按钮才查
        if let poi = prefetchedPOI {
            self.selectedPOI = poi
        } else {
            await fetchAndSelectPOI()
        }

        // 无可用 POI 时跳过播报
        guard let poi = selectedPOI, let _ = poi["name"] as? String else {
            print("⏭️ 无可播报 POI，跳过")
            DispatchQueue.main.async {
                self.isLoading = false
                self.currentScript = "附近暂无景点，等待中..."
            }
            return
        }

        // 尝试获取天气和时间信息以丰富 payload
        await fetchWeatherIfNeeded()

        guard let url = URL(string: "\(serverBaseURL)/generate-radio") else { return }
        
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        
        var poiName = ""
        if let poi = selectedPOI, let name = poi["name"] as? String {
            poiName = name
        }

        let payload: [String: Any] = [
                    "lat": self.displayLatitude,
                    "lon": self.displayLongitude,
                    "speed_kmh": self.displaySpeedKmh,
                    "heading": self.displayHeadingDeg,
                    "familiarity_level": 1,
                    "current_music": music,
                    "artist": currentArtist,
                    "poi_name": poiName,
                    "province": selectedPOI?["province"] as? String ?? "",
                    "city": selectedPOI?["city"] as? String ?? "",
                    "district": selectedPOI?["district"] as? String ?? "",
                    "frequency_level": broadcastFrequency,
                    "weather": weatherDescription,
                    "temperature": temperature,
                    "time_of_day": formattedTimeOfDay(),
                    "month": formattedMonth()
                ]
        request.httpBody = try? JSONSerialization.data(withJSONObject: payload)
        
        do {
            let (data, response) = try await URLSession.shared.data(for: request)
            guard let httpResponse = response as? HTTPURLResponse, httpResponse.statusCode == 200 else { return }
            
            if let encodedScript = httpResponse.value(forHTTPHeaderField: "X-Radio-Script"),
               let decodedScript = encodedScript.removingPercentEncoding {
                DispatchQueue.main.async {
                    self.currentScript = decodedScript
                }
            }
            
            DispatchQueue.main.async {
                do {
                    self.isLoading = false
                    // 将返回的音频写入临时文件，这样可以显示文件名
                    let tmpName = "radio_\(Int(Date().timeIntervalSince1970)).mp3"
                    let tmpURL = FileManager.default.temporaryDirectory.appendingPathComponent(tmpName)
                    try data.write(to: tmpURL)
                    self.generatedAudioFilename = tmpName

                    self.lowerBGMVolume() // 播放人声前，先压低 BGM
                    self.activateAudioSessionForVoice() // 激活闪避，压低系统音乐

                    self.voicePlayer = try AVAudioPlayer(contentsOf: tmpURL)
                    self.voicePlayer?.delegate = self
                    self.voicePlayer?.prepareToPlay()
                    self.voicePlayer?.play()
                    self.isPlaying = true
                } catch {
                    print("❌ 音频播放失败: \(error)")
                    self.restoreBGMVolume() // 如果报错，也要把 BGM 恢复
                    self.isLoading = false
                }
            }
        } catch {
            print("❌ 网络请求失败: \(error.localizedDescription)")
            DispatchQueue.main.async { self.isLoading = false }
        }
    }

    // ─── 第一步：查高德 POI ─────────────────────────────────
    func fetchUpcomingLandmarks() async -> [RawPOICandidate] {
        guard let url = URL(string: "\(serverBaseURL)/upcoming-landmarks") else { return [] }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")

        let body: [String: Any] = [
            "lat": displayLatitude,
            "lon": displayLongitude,
            "speed_kmh": displaySpeedKmh,
            "heading": displayHeadingDeg,
            "max_results": 10
        ]
        request.httpBody = try? JSONSerialization.data(withJSONObject: body)

        do {
            let (data, response) = try await URLSession.shared.data(for: request)
            guard let httpResponse = response as? HTTPURLResponse, httpResponse.statusCode == 200 else { return [] }
            let decoded = try JSONDecoder().decode(UpcomingLandmarksResponse.self, from: data)
            return decoded.candidates
        } catch {
            print("❌ 获取候选 POI 失败: \(error)")
            return []
        }
    }
    
    // ─── 第二步：iOS 本地过滤（评分<3 排除，≥5次排除）────
    func filterByLocalHistory(_ candidates: [RawPOICandidate]) -> [RawPOICandidate] {
        let history = LandmarkHistoryManager.shared.allHistory()
        return candidates.filter { poi in
            let count = history[poi.poi_id] ?? 0
            if count >= 5 { return false }   // 播过 ≥5 次，排除
            if poi.rating > 0 && poi.rating < 3.0 { return false }  // 有评分但 <3，排除
            return true
        }
    }
    
    // ─── 第三步：DeepSeek 选最佳 ──────────────────────────
    func selectBestLandmark(from filtered: [RawPOICandidate]) async -> (RawPOICandidate?, String) {
        guard !filtered.isEmpty else { return (nil, "") }
        
        // 如果只剩一个，直接返回
        if filtered.count == 1 { return (filtered[0], "（唯一候选）") }
        
        guard let url = URL(string: "\(serverBaseURL)/select-best-landmark") else { return (filtered.first, "") }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        
        let payload = SelectBestLandmarkPayload(candidates: filtered)
        request.httpBody = try? JSONEncoder().encode(payload)
        
        do {
            let (data, response) = try await URLSession.shared.data(for: request)
            guard let httpResponse = response as? HTTPURLResponse, httpResponse.statusCode == 200 else { return (filtered.first, "") }
            let decoded = try JSONDecoder().decode(SelectBestLandmarkResponse.self, from: data)
            if let selected = decoded.selected_landmark {
                let reason = decoded.reason ?? ""
                print("[✅ DeepSeek选中] \(selected.name) — \(reason)")
                return (selected, reason)
            }
        } catch {
            print("[⚠️ DeepSeek选POI失败] \(error)")
        }
        return (filtered.first, "")
    }
    
    // ─── 综合流程：查 → 过滤 → 选 ─────────────────────────
    func fetchAndSelectPOI() async {
        let candidates = await fetchUpcomingLandmarks()
        let filtered = filterByLocalHistory(candidates)
        
        DispatchQueue.main.async {
            let history = LandmarkHistoryManager.shared.allHistory()
            self.candidatePOIs = candidates.map { poi in
                ["name": poi.name, "distance_m": poi.distance_m,
                 "type": poi.type, "poi_id": poi.poi_id,
                 "location": poi.location, "province": poi.province,
                 "city": poi.city, "district": poi.district,
                 "address": poi.address,
                 "rating": poi.rating,
                 "introduced_count": history[poi.poi_id] ?? 0]
            }
        }
        
        let (best, reason) = await selectBestLandmark(from: filtered)
        guard let best = best else {
            print("[⚠️ 无可用POI] 候选\(candidates.count)个，过滤后0个")
            return
        }
        
        self.selectedPOI = [
            "poi_id": best.poi_id,
            "name": best.name,
            "type": best.type,
            "address": best.address,
            "location": best.location,
            "distance_m": best.distance_m,
            "province": best.province,
            "city": best.city,
            "district": best.district,
            "selection_weight": 1.0  // 经本地过滤+DeepSeek选中的，权重设为 1.0
        ]
        DispatchQueue.main.async {
            self.currentScript = "准备播报：\(best.name)"
            self.selectedPOIName = best.name
            self.deepseekReason = reason
        }
    }

    // Fetch weather from Open-Meteo (no API key required) and update weatherDescription & temperature
    func fetchWeatherIfNeeded() async {
        await fetchWeather(lat: latitude, lon: longitude)
    }

    func fetchWeather(lat: Double, lon: Double) async {
        guard lat != 0 || lon != 0 else { return }

        let urlStr = "https://api.open-meteo.com/v1/forecast?latitude=\(lat)&longitude=\(lon)&current_weather=true&timezone=auto"
        guard let url = URL(string: urlStr) else { return }
        var request = URLRequest(url: url)
        request.httpMethod = "GET"

        do {
            let (data, response) = try await URLSession.shared.data(for: request)
            guard let httpResponse = response as? HTTPURLResponse, httpResponse.statusCode == 200 else { return }
            if let json = try JSONSerialization.jsonObject(with: data) as? [String: Any], let current = json["current_weather"] as? [String: Any] {
                if let temp = current["temperature"] as? Double {
                    DispatchQueue.main.async { self.temperature = Int(round(temp)) }
                }
                if let code = current["weathercode"] as? Int {
                    let desc = weatherCodeToDescription(code: code)
                    DispatchQueue.main.async { self.weatherDescription = desc }
                }
            }
        } catch {
            print("❌ 获取天气失败: \(error)")
        }
    }

    // 每 30 分钟自动刷新天气
    private func startWeatherTimer() {
        Timer.scheduledTimer(withTimeInterval: 1800, repeats: true) { [weak self] _ in
            Task { await self?.fetchWeatherIfNeeded() }
        }
    }

    func weatherCodeToDescription(code: Int) -> String {
        // 简单映射，参考 Open-Meteo weathercode
        switch code {
        case 0: return "晴"
        case 1, 2, 3: return "多云"
        case 45, 48: return "雾"
        case 51, 53, 55: return "小雨"
        case 61, 63, 65: return "降雨"
        case 71, 73, 75: return "降雪"
        case 80, 81, 82: return "阵雨"
        case 95, 96, 99: return "雷暴"
        default: return "未知"
        }
    }

    func formattedTimeOfDay() -> String {
        let hour = Calendar.current.component(.hour, from: Date())
        switch hour {
        case 6..<12: return "上午\(hour)点"
        case 12..<18: return "下午\(hour - 12)点"
        case 18..<24: return "晚上\(hour - 12)点"
        default: return "凌晨\(hour)点"
        }
    }

    func formattedMonth() -> String {
        let m = Calendar.current.component(.month, from: Date())
        return "\(m)月"
    }

    // 播放结束时记录介绍
    private func recordLandmarkIntro() {
        guard let poi = selectedPOI, let poi_id = poi["poi_id"] as? String, let name = poi["name"] as? String, let location = poi["location"] as? String else { return }
        
        // ✅ 客户端本地写入（核心：每人独立历史）
        LandmarkHistoryManager.shared.recordIntroduction(poiId: poi_id)
        
        // 服务器同步记录（可选，用于统计分析）
        guard let url = URL(string: "\(serverBaseURL)/record-landmark") else { return }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")

        let payload: [String: Any] = [
            "poi_id": poi_id,
            "name": name,
            "location": location,
            "address": poi["address"] as? String ?? "",
            "type": poi["type"] as? String ?? ""
        ]
        request.httpBody = try? JSONSerialization.data(withJSONObject: payload)

        URLSession.shared.dataTask(with: request) { data, response, error in
            if let error = error {
                print("❌ recordLandmarkIntro failed: \(error)")
                return
            }
            print("✅ recordLandmarkIntro succeeded for \(poi_id)")
        }.resume()
    }
}

// ==========================================
// 2. 前台舞台：特斯拉级上下分屏 UI
// ==========================================
struct ContentView: View {
    @StateObject private var radioManager = RadioManager()
    
    var body: some View {
        GeometryReader { geometry in
            VStack(spacing: 0) {
                // 上半部：环境感知与音乐状态区
                ZStack {
                    LinearGradient(gradient: Gradient(colors: [Color.black, Color.blue.opacity(0.8)]), startPoint: .topLeading, endPoint: .bottomTrailing)
                    
                    VStack(spacing: 12) {
                        Image(systemName: "waveform.circle")
                            .font(.system(size: 50))
                            .foregroundColor(.white)
                            .symbolEffect(.bounce, value: radioManager.isPlaying)
                        
                        Text("一路聊吧")
                            .font(.headline)
                            .foregroundColor(.gray)
                        
                        Text("车速: \(radioManager.displaySpeedKmh) km/h · 方向: \(radioManager.displayHeadingDeg)°")
                            .font(.subheadline)
                            .foregroundColor(.white.opacity(0.8))
                        
                        HStack(spacing: 12) {
                            if !radioManager.weatherDescription.isEmpty {
                                Text("\(radioManager.weatherDescription) \(radioManager.temperature)℃")
                                    .font(.caption)
                                    .foregroundColor(.white.opacity(0.85))
                            }
                            Text(radioManager.formattedTimeOfDay())
                                .font(.caption)
                                .foregroundColor(.white.opacity(0.85))
                        }
                        
                        Text("坐标: \(String(format: "%.5f", radioManager.displayLatitude)), \(String(format: "%.5f", radioManager.displayLongitude))")
                            .font(.caption2)
                            .foregroundColor(.white.opacity(0.6))
                        
                        if !radioManager.currentMusicName.isEmpty && radioManager.currentMusicName != "无" {
                            Text("🎵 \(radioManager.currentMusicName)")
                                .font(.caption2)
                                .foregroundColor(.white.opacity(0.5))
                        }

                        // BGM 开关
                        Button(action: {
                            radioManager.toggleBGM()
                        }) {
                            Label(
                                radioManager.bgmEnabled ? "BGM 开" : "BGM 关",
                                systemImage: radioManager.bgmEnabled ? "speaker.wave.2.fill" : "speaker.slash.fill"
                            )
                            .font(.caption2)
                            .foregroundColor(.white.opacity(0.7))
                        }

                        #if targetEnvironment(simulator)
                        VStack(spacing: 4) {
                            Text("模拟器测试")
                                .font(.caption2)
                                .foregroundColor(.yellow)
                            HStack {
                                Text("速度")
                                    .font(.caption2)
                                    .foregroundColor(.white.opacity(0.7))
                                Slider(value: Binding(get: { Double(radioManager.simulatedSpeedKmh) }, set: { radioManager.simulatedSpeedKmh = Int($0) }), in: 0...120, step: 5)
                                Text("\(radioManager.simulatedSpeedKmh) km/h")
                                    .font(.caption2)
                                    .foregroundColor(.white.opacity(0.7))
                            }
                            HStack {
                                Text("方向")
                                    .font(.caption2)
                                    .foregroundColor(.white.opacity(0.7))
                                Slider(value: Binding(get: { Double(radioManager.simulatedHeadingDeg) }, set: { radioManager.simulatedHeadingDeg = Int($0) }), in: 0...360, step: 5)
                                Text("\(radioManager.simulatedHeadingDeg)°")
                                    .font(.caption2)
                                    .foregroundColor(.white.opacity(0.7))
                            }
                        }
                        #endif

                        // 候选 POI 列表
                        if !radioManager.candidatePOIs.isEmpty {
                            VStack(alignment: .leading, spacing: 3) {
                                Text("前方候选：")
                                    .font(.caption)
                                    .foregroundColor(.white.opacity(0.7))
                                ScrollView(.vertical, showsIndicators: true) {
                                    VStack(alignment: .leading, spacing: 4) {
                                        ForEach(radioManager.candidatePOIs.indices, id: \.self) { idx in
                                            let poi = radioManager.candidatePOIs[idx]
                                            let name = poi["name"] as? String ?? "?"
                                            let dist = poi["distance_m"] as? Int ?? 0
                                            let type = poi["type"] as? String ?? ""
                                            let weight = poi["selection_weight"] as? Double ?? 0
                                            let rating = poi["rating"] as? Double ?? 0
                                            let count = poi["introduced_count"] as? Int ?? 0
                                            let isSelected = (poi["name"] as? String) == radioManager.selectedPOIName
                                            
                                            VStack(alignment: .leading, spacing: 1) {
                                                Text("\(name)  \(dist)m")
                                                    .font(.system(size: 11, weight: .medium))
                                                    .foregroundColor(isSelected ? .yellow : .white)
                                                Text("类别: \(type)  评分: \(String(format: "%.1f", rating))  播过: \(count)次  权重: \(String(format: "%.2f", weight))")
                                                    .font(.system(size: 9))
                                                    .foregroundColor(isSelected ? .yellow.opacity(0.8) : .white.opacity(0.5))
                                            }
                                        }
                                    }
                                }
                                .frame(maxHeight: 120)
                            }
                            .padding(.horizontal, 8)
                        }
                    }
                }
                .frame(height: geometry.size.height / 2)
                
                // 下半部：台词展示与交互区
                ZStack {
                    Color(UIColor.systemBackground)
                    
                    VStack {
                        ScrollView {
                            Text(radioManager.currentScript.isEmpty ? "电台待命中...\n点击下方按钮获取沿途风光播报。" : radioManager.currentScript)
                                .font(.body)
                                .lineSpacing(8)
                                .multilineTextAlignment(.center)
                                .padding()
                                .frame(maxWidth: .infinity)
                        }
                        .background(Color.gray.opacity(0.1))
                        .cornerRadius(15)
                        .padding()
                        
                        Spacer()

                        // 频率滑杆
                        VStack(spacing: 8) {
                            HStack {
                                Text("播报频率")
                                Spacer()
                                Text(broadcastFrequencyDescription(frequency: radioManager.broadcastFrequency))
                                    .foregroundColor(.secondary)
                            }
                            Slider(value: Binding(get: {
                                Double(radioManager.broadcastFrequency)
                            }, set: { newVal in
                                radioManager.broadcastFrequency = Int(newVal)
                            }), in: 0...100, step: 1)
                        }
                        .padding([.leading, .trailing], 24)

                        Button(action: {
                            Task {
                                radioManager.isLoading = true
                                await radioManager.generateAndPlayRadio(speed: radioManager.displaySpeedKmh, music: radioManager.currentMusicName)
                            }
                        }) {
                            if radioManager.isLoading {
                                ProgressView()
                                    .frame(width: 220, height: 55)
                            } else {
                                HStack {
                                    Image(systemName: radioManager.isPlaying ? "speaker.wave.3.fill" : "mic.fill")
                                    Text(radioManager.isPlaying ? "播报中..." : "开始播报 (Talk)")
                                }
                                .font(.headline)
                                .foregroundColor(.white)
                                .frame(width: 220, height: 55)
                                .background(radioManager.isPlaying ? Color.green : Color.blue)
                                .cornerRadius(27.5)
                                .shadow(radius: 5)
                            }
                        }
                        .disabled(radioManager.isPlaying)
                        .padding(.bottom, 40)
                    }
                }
                .frame(height: geometry.size.height / 2)
            }
        }
        .edgesIgnoringSafeArea(.all)
    }
}

#Preview {
    ContentView()
}

// MARK: - Helpers

func broadcastFrequencyDescription(frequency: Int) -> String {
    switch frequency {
    case 0..<20:
        return "仅著名地标"
    case 20..<50:
        return "稀疏播报"
    case 50..<80:
        return "中等频率"
    default:
        return "高频（可达每分钟）"
    }
}
