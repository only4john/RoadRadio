import urllib.parse
from fastapi import FastAPI, Response

from config import logger
from models import RealTimeLocationPayload, LandmarkIntroRecordPayload, LandmarkSearchPayload, SelectBestLandmarkPayload
from amap_landmarks import get_upcoming_landmarks
from deepseek_service import generate_radio_script, select_best_landmark
from minimax_service import synthesize_audio

app = FastAPI(title="车载情感电台后端系统")


# ==========================================
# 📍 地标查询接口（只查高德，不做过滤）
# ==========================================
@app.post("/upcoming-landmarks")
async def upcoming_landmarks(payload: LandmarkSearchPayload):
    history_size = len(payload.introduced_poi_ids)
    logger.info(f"[📡 地标查询] 经纬度: {payload.lat},{payload.lon} | 车速: {payload.speed_kmh} km/h | 方向: {payload.heading}° | 历史: {history_size} 条")
    try:
        landmarks = await get_upcoming_landmarks(
            lat=payload.lat,
            lon=payload.lon,
            speed_kmh=payload.speed_kmh,
            heading=payload.heading,
            max_results=payload.max_results,
            introduced_poi_ids=payload.introduced_poi_ids,
        )
    except Exception as e:
        logger.error(f"❌ 高德地标查询失败: {e}")
        return Response(status_code=500, content="Failed to query Amap landmarks")

    # 打印权重最高的前 3 个，便于调试
    for i, lm in enumerate(landmarks[:3]):
        logger.info(f"  [{i+1}] {lm.get('name','?')} 距离={lm.get('distance_m','?')}m 评分={lm.get('rating',0):.1f} 权重={lm.get('selection_weight',0):.4f} ahead={lm.get('is_ahead',True)}")

    return {
        "candidates": landmarks,
    }


# ==========================================
# 🎯 DeepSeek 选最佳 POI（iOS 本地过滤后调用）
# ==========================================
@app.post("/select-best-landmark")
async def select_best(payload: SelectBestLandmarkPayload):
    candidates = [c.model_dump() for c in payload.candidates]
    logger.info(f"[🎯 选POI] 候选数: {len(candidates)}")
    try:
        selected = await select_best_landmark(candidates)
        if selected:
            logger.info(f"[✅ DeepSeek选中] {selected.get('name', '?')} (id={selected.get('poi_id', '?')})")
    except Exception as e:
        logger.error(f"[⚠️ DeepSeek选POI失败，回退第一个] {e}")
        selected = candidates[0] if candidates else None

    return {
        "selected_landmark": selected,
        "reason": selected.get("_selection_reason", "") if selected else "",
    }


# ==========================================
# 💾 地标记录接口
# ==========================================
@app.post("/record-landmark")
async def record_landmark(payload: LandmarkIntroRecordPayload):
    logger.info(f"[📋 播报记录] POI={payload.poi_id} 名称={payload.name}")
    return {"status": "ok", "poi_id": payload.poi_id}


# ==========================================
# 🎙️ 电台生成接口：剧本 -> 音频合成 -> 返回
# ==========================================
@app.post("/generate-radio")
async def generate_radio(payload: RealTimeLocationPayload):
    logger.info(f"[🚀 请求] 车速={payload.speed_kmh}km/h | 音乐={payload.current_music} | POI={payload.poi_name}")
    
    try:
        dialogue_list, knowledge_source = await generate_radio_script(payload)
        
        # 第二步：合成音频
        audio_buffer = await synthesize_audio(dialogue_list)
        logger.info(f"[✅ 成功] 剧本={len(dialogue_list)}轮 来源={knowledge_source} 音频={len(audio_buffer)}字节")
        
    except Exception as e:
        logger.error(f"❌ 电台生成失败: {e}")
        return Response(status_code=500, content="Failed to generate radio")
    
    # 第三步：打包返回 (字幕 + 二进制音频 + 搜索标签)
    full_text = "\n\n".join([f"{item['role']}: {item['text']}" for item in dialogue_list])
    encoded_script = urllib.parse.quote(full_text)

    return Response(
        content=bytes(audio_buffer),
        media_type="audio/mpeg",
        headers={
            "X-Radio-Script": encoded_script,
            "X-Radio-Knowledge": knowledge_source,
        }
    )
