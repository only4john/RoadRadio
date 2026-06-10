// ==========================================
// 🗂️ 客户端本地 POI 历史管理器 (UserDefaults)
//    每个用户的 iPhone 独立记录自己的播报历史
// ==========================================

import Foundation

class LandmarkHistoryManager {
    static let shared = LandmarkHistoryManager()
    
    private let defaults = UserDefaults.standard
    private let key = "landmark_history_v1"  // 版本化 key，方便未来迁移
    
    private init() {}
    
    // MARK: - 读取全部历史
    
    /// 返回 {poi_id: introduced_count}
    func allHistory() -> [String: Int] {
        guard let data = defaults.data(forKey: key) else { return [:] }
        do {
            let dict = try JSONDecoder().decode([String: Int].self, from: data)
            return dict
        } catch {
            print("⚠️ 读取本地历史失败: \(error)")
            return [:]
        }
    }
    
    // MARK: - 获取某个 POI 的播报次数
    
    func introducedCount(for poiId: String) -> Int {
        return allHistory()[poiId] ?? 0
    }
    
    // MARK: - 记录一次播报（次数+1）
    
    func recordIntroduction(poiId: String) {
        var history = allHistory()
        let newCount = (history[poiId] ?? 0) + 1
        history[poiId] = newCount
        save(history)
        print("📝 本地历史更新: \(poiId) → \(newCount) 次")
    }
    
    // MARK: - 清空历史（调试用）
    
    func clearAll() {
        defaults.removeObject(forKey: key)
        print("🗑️ 本地 POI 历史已清空")
    }
    
    // MARK: - Private
    
    private func save(_ dict: [String: Int]) {
        do {
            let data = try JSONEncoder().encode(dict)
            defaults.set(data, forKey: key)
        } catch {
            print("❌ 保存本地历史失败: \(error)")
        }
    }
}
