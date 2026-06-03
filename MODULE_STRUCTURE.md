# 车载电台后端系统 - 模块结构说明

## 📁 项目组织

重构后的项目按功能分离为以下模块：

```
laniakea_radio/
├── main.py                    # 🚀 FastAPI 应用入口 (仅包含路由定义)
├── models.py                  # 📦 所有 Pydantic 数据模型
├── config.py                  # ⚙️ 配置和 API 密钥
├── deepseek_service.py        # 🧠 DeepSeek 剧本生成服务
├── minimax_service.py         # 🎙️ MiniMax 音频合成服务
├── amap_landmarks.py          # 📍 高德地标查询和选择逻辑
└── landmark_history.db        # 💾 本地地标介绍历史数据库
```

## 🔧 模块职责

### **main.py** (入口)
- FastAPI 应用初始化
- API 路由定义 (`/upcoming-landmarks`, `/record-landmark`, `/generate-radio`)
- 请求/响应处理

### **models.py** (数据模型)
- `RealTimeLocationPayload` - 实时位置和环境信息
- `LandmarkIntroRecordPayload` - 地标介绍记录请求

### **config.py** (配置)
- API 密钥（DeepSeek、MiniMax）
- 语音合成参数（音色、速度等）
- DeepSeek 提示词模板

### **deepseek_service.py** (剧本生成)
- `generate_radio_script()` - 调用 DeepSeek API 生成对话剧本
- 处理中文编码和 JSON 响应解析

### **minimax_service.py** (音频合成)
- `synthesize_audio()` - 调用 MiniMax WebSocket 接口
- 管理多个 WebSocket 连接（每句话一个连接）
- MP3 音频流拼接

### **amap_landmarks.py** (地标查询)
- `get_upcoming_landmarks()` - 查询前方 POI
- `select_landmark_for_session()` - 智能选择一个值得介绍的 POI
- `record_landmark_introduction()` - 记录介绍历史
- 本地 SQLite 数据库管理

## 🔄 数据流

```
前端请求 /generate-radio
    ↓
main.py 路由处理
    ↓
deepseek_service.generate_radio_script()  [生成剧本]
    ↓
minimax_service.synthesize_audio()        [合成音频]
    ↓
响应 (MP3 + 字幕)
```

## 🚀 启动方式

```bash
# 激活虚拟环境
source venv/bin/activate

# 启动服务器
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

## 📝 配置说明

所有敏感信息（API 密钥）存放在 `config.py` 中，生产环境应使用环境变量替代：

```python
# config.py 应改为：
import os

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
MINIMAX_API_KEY = os.getenv("MINIMAX_API_KEY", "")
```
