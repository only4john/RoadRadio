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
)

WS_CONNECT_TIMEOUT = 15
WS_RECV_TIMEOUT = 30


async def synthesize_audio(dialogue_list: list) -> bytearray:
    """
    调用 MiniMax WebSocket 接口合成音频
    
    Args:
        dialogue_list: 对话列表，每个元素为 {"role": "A" or "B", "text": "..."}
        
    Returns:
        audio_buffer: 合成的MP3音频二进制数据
        
    Raises:
        RuntimeError: MiniMax 返回错误或连接异常
    """
    audio_buffer = bytearray()
    
    ssl_context = ssl.create_default_context()
    
    headers = {
        "Authorization": f"Bearer {MINIMAX_API_KEY}"
    }
    
    print("🎙️ 正在连接 MiniMax 录音棚...")
    
    try:
        for line in dialogue_list:
            role = line.get('role', 'A')
            text = line.get('text', '')
            voice_setting = VOICE_SETTINGS.get(role, VOICE_SETTINGS['A'])
            
            async with websockets.connect(
                MINIMAX_WS_URL,
                extra_headers=headers,
                ssl=ssl_context,
                open_timeout=WS_CONNECT_TIMEOUT,
            ) as ws:
                connected_resp = json.loads(await asyncio.wait_for(ws.recv(), timeout=WS_RECV_TIMEOUT))
                if connected_resp.get("event") != "connected_success":
                    raise RuntimeError(f"MiniMax 连接失败: {connected_resp}")

                task_start_msg = {
                    "event": "task_start",
                    "model": "speech-2.6-hd",
                    "voice_setting": voice_setting,
                    "audio_setting": AUDIO_SETTINGS,
                }
                await ws.send(json.dumps(task_start_msg))

                await ws.send(json.dumps({
                    "event": "task_continue",
                    "text": text
                }))

                while True:
                    res_str = await asyncio.wait_for(ws.recv(), timeout=WS_RECV_TIMEOUT)
                    res_dict = json.loads(res_str)
                    
                    if res_dict.get("event") == "task_started":
                        continue
                    if res_dict.get("event") == "error":
                        raise RuntimeError(f"MiniMax 合成失败: {res_dict}")

                    audio_hex = res_dict.get("data", {}).get("audio", "")
                    if audio_hex:
                        audio_buffer.extend(bytes.fromhex(audio_hex))

                    if res_dict.get("is_final"):
                        await ws.send(json.dumps({"event": "task_finish"}))
                        break

        print("✅ 音频合成与拼接完成！")
        return audio_buffer
        
    except Exception as e:
        print(f"❌ MiniMax WebSocket 异常: {e}")
        raise
