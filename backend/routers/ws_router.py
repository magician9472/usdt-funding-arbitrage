from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import asyncio

router = APIRouter()

@router.websocket("/ws/positions")
async def positions_ws(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            # TODO: Bitget WebSocket에서 받은 데이터로 교체
            dummy = [
                {"instId": "BTCUSDT_UMCBL", "holdSide": "long", "total": "0.01"},
                {"instId": "ETHUSDT_UMCBL", "holdSide": "short", "total": "0.02"}
            ]
            await websocket.send_json(dummy)
            await asyncio.sleep(5)
    except WebSocketDisconnect:
        print("웹소켓 연결 종료")