"""
MiniMax 音频合成服务
"""
import asyncio
import json
import ssl
import websockets
from config import (
    MINIMAX_API_KEY,
    MINIMAX_WS_URL,
    VOICE_SETTINGS,
    AUDIO_SETTINGS,
    logger,
)

WS_RECV_TIMEOUT = 30


async def _synthesize_one_line(ws_url: str, role: str, text: str, 
                                voice_setting: dict, ssl_context, index: int) -> tuple[int, bytes]:
    """合成一句话，返回 (index, audio_bytes)"""
    headers = {"Authorization": f"Bearer {MINIMAX_API_KEY}"}
    buf = bytearray()
    try:
        async with websockets.connect(ws_url, extra_headers=headers, ssl=ssl_context) as ws:
            connected_resp = json.loads(await asyncio.wait_for(ws.recv(), timeout=WS_RECV_TIMEOUT))
            if connected_resp.get("event") != "connected_success":
                raise RuntimeError(f"MiniMax 连接失败[{index}]: {connected_resp}")

            await ws.send(json.dumps({
                "event": "task_start",
                "model": "speech-2.6-hd",
                "voice_setting": voice_setting,
                "audio_setting": AUDIO_SETTINGS,
            }))
            await ws.send(json.dumps({"event": "task_continue", "text": text}))

            while True:
                res_str = await asyncio.wait_for(ws.recv(), timeout=WS_RECV_TIMEOUT)
                res_dict = json.loads(res_str)
                if res_dict.get("event") == "task_started":
                    continue
                if res_dict.get("event") == "error":
                    raise RuntimeError(f"MiniMax 合成失败[{index}]: {res_dict}")
                audio_hex = res_dict.get("data", {}).get("audio", "")
                if audio_hex:
                    buf.extend(bytes.fromhex(audio_hex))
                if res_dict.get("is_final"):
                    await ws.send(json.dumps({"event": "task_finish"}))
                    break
        return (index, bytes(buf))
    except Exception as e:
        logger.error(f"❌ MiniMax 第{index}句失败: {e}")
        raise


async def synthesize_audio(dialogue_list: list) -> bytearray:
    """
    调用 MiniMax WebSocket 接口并行合成音频
    
    Args:
        dialogue_list: 对话列表，每个元素为 {"role": "A" or "B", "text": "..."}
        
    Returns:
        audio_buffer: 合成的MP3音频二进制数据
        
    Raises:
        RuntimeError: MiniMax 返回错误或连接异常
    """
    ssl_context = ssl.create_default_context()
    logger.info(f"🎙️ 正在并行连接 MiniMax 录音棚 ({len(dialogue_list)} 句)...")
    
    try:
        # 为每一句创建并行合成任务
        tasks = []
        for i, line in enumerate(dialogue_list):
            role = line.get('role', 'A')
            text = line.get('text', '')
            voice_setting = VOICE_SETTINGS.get(role, VOICE_SETTINGS['A'])
            tasks.append(
                _synthesize_one_line(MINIMAX_WS_URL, role, text, voice_setting, ssl_context, i)
            )
        
        # 并行执行所有合成任务
        results = await asyncio.gather(*tasks)
        
        # 按原始顺序拼接
        results.sort(key=lambda x: x[0])
        audio_buffer = bytearray()
        for _, audio_bytes in results:
            audio_buffer.extend(audio_bytes)
        
        logger.info(f"✅ 音频合成与拼接完成！（并行 {len(dialogue_list)} 句）")
        return audio_buffer
        
    except Exception as e:
        logger.error(f"❌ MiniMax WebSocket 异常: {e}")
        raise
