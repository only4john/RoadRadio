import asyncio
import websockets

async def test():
    try:
        async with websockets.connect("ws://echo.websocket.org", additional_headers={"User-Agent": "test"}) as ws:
            print("SUCCESS: additional_headers works")
    except TypeError as e:
        print(f"FAIL: {e}")
    except Exception as e:
        print(f"OTHER FAIL: {e}")

asyncio.run(test())
