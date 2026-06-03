"""
MiniMax 音频合成服务
"""
import json
import ssl
import websockets
from config import (
    MINIMAX_API_KEY,
    MINIMAX_WS_URL,
    VOICE_SETTINGS,
    AUDIO_SETTINGS,
)


async def synthesize_audio(dialogue_list: list) -> bytearray:
    """
    调用 MiniMax WebSocket 接口合成音频
    
    Args:
        dialogue_list: 对话列表，每个元素为 {"role": "A" or "B", "text": "..."}
        
    Returns:
        audio_buffer: 合成的MP3音频二进制数据
        
    Raises:
        Exception: MiniMax 请求失败或连接异常
    """
    audio_buffer = bytearray()
    
    # SSL 上下文配置（用于WebSocket连接）
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    
    headers = {
        "Authorization": f"Bearer {MINIMAX_API_KEY}"
    }
    
    print("🎙️ 正在连接 MiniMax 录音棚...")
    
    try:
        # 为每一句话单独建立一次 WebSocket 连接
        for line in dialogue_list:
            role = line.get('role', 'A')
            text = line.get('text', '')
            voice_setting = VOICE_SETTINGS.get(role, VOICE_SETTINGS['A'])
            
            async with websockets.connect(MINIMAX_WS_URL, additional_headers=headers, ssl=ssl_context) as ws:
                # 0. 连接握手确认
                connected_resp = json.loads(await ws.recv())
                if connected_resp.get("event") != "connected_success":
                    raise RuntimeError(f"MiniMax 连接失败: {connected_resp}")

                # 1. 发送发音任务
                task_start_msg = {
                    "event": "task_start",
                    "model": "speech-2.8-hd",
                    "voice_setting": voice_setting,
                    "audio_setting": AUDIO_SETTINGS,
                }
                await ws.send(json.dumps(task_start_msg))

                # 2. 发送文本
                await ws.send(json.dumps({
                    "event": "task_continue",
                    "text": text
                }))

                # 3. 循环接收音频片段 (二进制 Hex 编码)
                while True:
                    res_str = await ws.recv()
                    res_dict = json.loads(res_str)
                    
                    if res_dict.get("event") == "task_started":
                        continue
                    if res_dict.get("event") == "error":
                        print(f"❌ MiniMax 报错: {res_dict}")
                        break

                    # 处理音频片段
                    audio_hex = res_dict.get("data", {}).get("audio", "")
                    if audio_hex:
                        audio_buffer.extend(bytes.fromhex(audio_hex))

                    # 结束条件：服务端告知本次语音合成完成
                    if res_dict.get("is_final"):
                        await ws.send(json.dumps({"event": "task_finish"}))
                        break

        print("✅ 音频合成与拼接完成！")
        return audio_buffer
        
    except Exception as e:
        print(f"❌ MiniMax WebSocket 异常: {e}")
        raise
