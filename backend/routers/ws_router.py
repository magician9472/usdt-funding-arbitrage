from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import asyncio
import json
from pybitget.stream import BitgetWsClient, SubscribeReq, handel_error
from pybitget.enums import *
from pybitget import logger
import os
from pybitget import Client as BitgetClient

router = APIRouter()


# FastAPI 웹소켓에 연결된 클라이언트들을 저장
active_clients = set()

# Bitget WebSocket 클라이언트 생성
bitget_ws = BitgetWsClient(
    os.getenv("BITGET_API_KEY"),
    os.getenv("BITGET_API_SECRET"),
    passphrase=os.getenv("BITGET_API_PASS"),
    verbose=True
).error_listener(handel_error).build()



# Bitget에서 메시지가 오면 FastAPI WS 클라이언트들에게 중계
def on_message(message):
    try:
        data = json.loads(message)
        if data.get("arg", {}).get("channel") == "positions":
            # 연결된 모든 클라이언트에 브로드캐스트
            for ws in list(active_clients):
                asyncio.create_task(ws.send_json(data.get("data", [])))
    except Exception as e:
        logger.error(f"메시지 처리 오류: {e}")

# Bitget 포지션 채널 구독 (instId="default" → 전체 포지션)
channels = [SubscribeReq("UMCBL", "positions", "default")]
bitget_ws.subscribe(channels, on_message)


@router.websocket("/ws/positions")
async def positions_ws(websocket: WebSocket):
    await websocket.accept()
    active_clients.add(websocket)
    try:
        while True:
            # 클라이언트에서 오는 메시지는 특별히 처리하지 않고 대기
            await websocket.receive_text()
    except WebSocketDisconnect:
        active_clients.remove(websocket)
        print("웹소켓 연결 종료")