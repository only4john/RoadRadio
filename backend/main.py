import urllib.parse
from fastapi import FastAPI, Response

from models import RealTimeLocationPayload, LandmarkIntroRecordPayload
from amap_landmarks import (
    LandmarkSearchPayload,
    get_upcoming_landmarks,
    record_landmark_introduction,
)
from deepseek_service import generate_radio_script, select_best_landmark
from minimax_service import synthesize_audio

app = FastAPI(title="车载情感电台后端系统")


# ==========================================
# 📍 地标查询接口
# ==========================================
@app.post("/upcoming-landmarks")
async def upcoming_landmarks(payload: LandmarkSearchPayload):
    print(f"[📡 地标预判] 经纬度: {payload.lat},{payload.lon} | 车速: {payload.speed_kmh} km/h | 方向: {payload.heading}°")
    try:
        landmarks = await get_upcoming_landmarks(
            lat=payload.lat,
            lon=payload.lon,
            speed_kmh=payload.speed_kmh,
            heading=payload.heading,
            max_results=payload.max_results,
            frequency_level=getattr(payload, 'frequency_level', 50),
        )
        selected = select_landmark_for_session(landmarks)
        if selected:
            print(f"[✅ 选中POI] {selected.get('name', '未知')} (id={selected.get('poi_id', 'unknown')})")
        else:
            print(f"[⚠️  无可用POI] 未找到满足条件的地标，候选数：{len(landmarks)}")
    except Exception as e:
        print(f"❌ 高德地标查询失败: {e}")
        return Response(status_code=500, content="Failed to query Amap landmarks")

    return {
        "preview_lead_minutes": 3,
        "speed_kmh": payload.speed_kmh,
        "heading": payload.heading,
        "search_radius_m": max(500, min(int(payload.speed_kmh * 1000 / 20), 5000)),
        "frequency_level": getattr(payload, 'frequency_level', 50),
        "heading_filter": "±90° (前方约180° 扇形范围)",
        "selection_strategy": "选取前方扇形内、距离适中、未介绍过或<5次的 POI；已介绍>=5次排除",
        "candidates": landmarks,
        "selected_landmark": selected,
    }


# ==========================================
# 💾 地标记录接口
# ==========================================
@app.post("/record-landmark")
async def record_landmark(payload: LandmarkIntroRecordPayload):
    print(f"[💾 记录介绍] POI={payload.poi_id} 名称={payload.name}")
    try:
        record_landmark_introduction(
            poi_id=payload.poi_id,
            name=payload.name,
            location=payload.location,
            address=payload.address,
            type=payload.type,
        )
    except Exception as e:
        print(f"❌ 记录失败: {e}")
        return Response(status_code=500, content="Failed to record landmark introduction")

    return {"status": "ok", "poi_id": payload.poi_id}


# ==========================================
# 🎙️ 电台生成接口：剧本 -> 音频合成 -> 返回
# ==========================================
@app.post("/generate-radio")
async def generate_radio(payload: RealTimeLocationPayload):
    print(f"[🚀 收到前端请求] 车速: {payload.speed_kmh}km/h | 音乐: {payload.current_music} | POI: {payload.poi_name}")
    
    try:
        # 第一步：生成剧本
        dialogue_list = await generate_radio_script(payload)
        
        # 第二步：合成音频
        audio_buffer = await synthesize_audio(dialogue_list)
        
    except Exception as e:
        print(f"❌ 电台生成失败: {e}")
        return Response(status_code=500, content="Failed to generate radio")
    
    # 第三步：打包返回 (字幕 + 二进制音频)
    full_text = "\n\n".join([f"{item['role']}: {item['text']}" for item in dialogue_list])
    encoded_script = urllib.parse.quote(full_text)

    return Response(
        content=bytes(audio_buffer),
        media_type="audio/mpeg",
        headers={
            "X-Radio-Script": encoded_script
        }
    )
