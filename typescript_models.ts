// ==========================================
// Web 前端数据模型 (TypeScript)
// 可直接复制到 React / Vue / Angular 项目使用
// ==========================================

// MARK: - 请求体模型

/** 实时位置和环境信息 - 用于 POST /generate-radio */
export interface RealTimeLocationPayload {
  lat: number;              // 纬度
  lon: number;              // 经度
  speed_kmh: number;        // 当前车速 (km/h)
  heading: number;          // 当前方向 (0-360°)
  familiarity_level?: number; // 熟悉度 (保留字段，默认0)
  current_music?: string;   // 当前播放歌曲 (默认"无")
  poi_name: string;         // 即将到达的景点名称 ⭐️ 必填
  weather?: string;         // 天气 (默认"")
  temperature?: number;     // 温度(℃) (默认0)
  time_of_day?: string;     // 当前时段 (默认"")
}

/** 地标查询请求 - 用于 POST /upcoming-landmarks */
export interface LandmarkSearchPayload {
  lat: number;              // 纬度
  lon: number;              // 经度
  speed_kmh: number;        // 当前车速
  heading: number;          // 当前方向 (0-360°)
  max_results?: number;     // 最多返回多少个候选 (默认5)
}

/** 地标介绍记录 - 用于 POST /record-landmark */
export interface LandmarkIntroRecordPayload {
  poi_id: string;           // POI ID (必填)
  name: string;             // 景点名称
  location: string;         // 经纬度 "lon,lat"
  address?: string;         // 地址 (默认"")
  type?: string;            // POI 类型 (默认"")
}

// MARK: - 响应体模型

/** 单个 POI 信息 */
export interface LandmarkInfo {
  poi_id: string;              // POI ID
  name: string;                // 景点名称
  type: string;                // POI 类型
  address: string;             // 地址
  distance_m: number;          // 距离(米)
  location: string;            // 经纬度 "lon,lat"
  estimated_arrival_min: number; // 预计到达时间(分钟)
  preview_start_seconds: number; // 开始介绍的秒数
  introduced_count: number;    // 已介绍次数
  selection_weight: number;    // 选择权重 (0-1)
}

/** 地标查询响应 - /upcoming-landmarks 的返回值 */
export interface LandmarkSearchResponse {
  preview_lead_minutes: number;   // 提前介绍时间(分钟)
  speed_kmh: number;              // 当前车速
  heading: number;                // 当前方向
  search_radius_m: number;        // 搜索半径(米)
  heading_filter: string;         // 方向过滤范围说明
  selection_strategy: string;     // 选择策略说明
  candidates: LandmarkInfo[];     // 候选 POI 列表
  selected_landmark: LandmarkInfo | null; // 推荐选择 (可能为 null)
}

/** 记录成功响应 - /record-landmark 的返回值 */
export interface LandmarkIntroRecordResponse {
  status: string;           // "ok"
  poi_id: string;           // POI ID
}

/** 生成电台响应 - /generate-radio 的返回值 */
export interface GenerateRadioResponse {
  audioData: Blob;          // MP3 音频数据
  script: string;           // 字幕文本
}

// MARK: - API 客户端

export class RadioAPIClient {
  private baseURL: string;

  constructor(baseURL: string = 'http://127.0.0.1:8000') {
    this.baseURL = baseURL;
  }

  /**
   * 查询前方景点
   */
  async queryUpcomingLandmarks(
    payload: LandmarkSearchPayload
  ): Promise<LandmarkSearchResponse> {
    const response = await fetch(`${this.baseURL}/upcoming-landmarks`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      throw new Error(`Failed to query landmarks: ${response.statusText}`);
    }

    return response.json();
  }

  /**
   * 生成电台内容并获取 MP3 + 字幕
   */
  async generateRadio(
    payload: RealTimeLocationPayload
  ): Promise<GenerateRadioResponse> {
    const response = await fetch(`${this.baseURL}/generate-radio`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      throw new Error(`Failed to generate radio: ${response.statusText}`);
    }

    // 从响应头获取字幕 (URL 编码的中文)
    const encodedScript = response.headers.get('X-Radio-Script') || '';
    const script = decodeURIComponent(encodedScript);

    // 从响应体获取 MP3 音频
    const audioData = await response.blob();

    return { audioData, script };
  }

  /**
   * 记录景点介绍
   */
  async recordLandmarkIntro(
    payload: LandmarkIntroRecordPayload
  ): Promise<LandmarkIntroRecordResponse> {
    const response = await fetch(`${this.baseURL}/record-landmark`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      throw new Error(`Failed to record landmark: ${response.statusText}`);
    }

    return response.json();
  }
}

// MARK: - 使用示例

/**
 * React Hook 示例 - 定期查询前方景点
 */
export function useUpcomingLandmarks(gps: {
  lat: number;
  lon: number;
  speed_kmh: number;
  heading: number;
}) {
  const [landmarks, setLandmarks] = React.useState<LandmarkInfo[] | null>(null);
  const [selected, setSelected] = React.useState<LandmarkInfo | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  const client = React.useMemo(() => new RadioAPIClient(), []);

  React.useEffect(() => {
    const interval = setInterval(async () => {
      try {
        setLoading(true);
        setError(null);

        const response = await client.queryUpcomingLandmarks({
          lat: gps.lat,
          lon: gps.lon,
          speed_kmh: gps.speed_kmh,
          heading: gps.heading,
          max_results: 5,
        });

        setLandmarks(response.candidates);
        setSelected(response.selected_landmark);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Unknown error');
      } finally {
        setLoading(false);
      }
    }, 30000); // 每 30 秒查询一次

    return () => clearInterval(interval);
  }, [gps, client]);

  return { landmarks, selected, loading, error };
}

/**
 * React Hook 示例 - 播放电台内容
 */
export async function playRadio(
  gps: { lat: number; lon: number; speed_kmh: number; heading: number },
  landmark: LandmarkInfo,
  context: { weather?: string; temperature?: number; time_of_day?: string }
) {
  const client = new RadioAPIClient();

  try {
    const response = await client.generateRadio({
      lat: gps.lat,
      lon: gps.lon,
      speed_kmh: gps.speed_kmh,
      heading: gps.heading,
      poi_name: landmark.name,
      weather: context.weather || '',
      temperature: context.temperature || 0,
      time_of_day: context.time_of_day || '',
    });

    // 播放音频
    const audioUrl = URL.createObjectURL(response.audioData);
    const audio = new Audio(audioUrl);
    audio.play();

    // 显示字幕
    console.log('Script:', response.script);

    // 播放完成后记录
    audio.onended = async () => {
      await client.recordLandmarkIntro({
        poi_id: landmark.poi_id,
        name: landmark.name,
        location: landmark.location,
        address: landmark.address,
        type: landmark.type,
      });
    };
  } catch (error) {
    console.error('Failed to play radio:', error);
  }
}

// MARK: - 工具函数

/** 转换 GPS course (0-360) 到易读的方向 */
export function headingToDirection(heading: number): string {
  const directions = ['↑ 北', '↗ 东北', '→ 东', '↘ 东南', '↓ 南', '↙ 西南', '← 西', '↖ 西北'];
  const index = Math.round((heading % 360) / 45) % 8;
  return directions[index];
}

/** GPS 速度转换 (m/s 到 km/h) */
export function msToKmh(speed_ms: number): number {
  return Math.round(speed_ms * 3.6);
}

/** 将车速格式化为易读形式 */
export function formatSpeed(speed_kmh: number): string {
  return `${speed_kmh} km/h`;
}

/** 格式化距离 */
export function formatDistance(distance_m: number): string {
  if (distance_m < 1000) {
    return `${distance_m}m`;
  }
  return `${(distance_m / 1000).toFixed(1)}km`;
}

/** 格式化到达时间 */
export function formatArrivalTime(minutes: number): string {
  if (minutes === Infinity || minutes > 1440) {
    return '无限远';
  }
  if (minutes < 1) {
    return `${Math.round(minutes * 60)}秒`;
  }
  if (minutes < 60) {
    return `${Math.round(minutes)}分钟`;
  }
  const hours = Math.floor(minutes / 60);
  const mins = Math.round(minutes % 60);
  return `${hours}小时${mins}分钟`;
}
