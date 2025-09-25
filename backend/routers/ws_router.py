import os
import json
import asyncio
import logging
from dotenv import load_dotenv
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from pybitget.stream import BitgetWsClient, SubscribeReq, handel_error
from pybitget import logger

# SQLAlchemy 쿼리 로그 줄이기
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

router = APIRouter()

# 연결된 클라이언트 저장
active_clients = set()

# .env 로드
load_dotenv()

# Bitget WebSocket 클라이언트 생성 (Private 인증 포함)
bitget_ws = (
    BitgetWsClient(
        api_key=os.getenv("BITGET_API_KEY"),
        api_secret=os.getenv("BITGET_API_SECRET"),
        passphrase=os.getenv("BITGET_API_PASS"),
        verbose=True,
    )
    .error_listener(handel_error)
    .build()
)

# Bitget에서 메시지가 오면 FastAPI WS 클라이언트들에게 중계
def on_message(message: str):
    try:
        print("RAW >>>", message)
        data = json.loads(message)

        if data.get("arg", {}).get("channel") == "positions":
            payload = data.get("data", [])

            loop = asyncio.get_event_loop()
            dead_clients = []
            for ws in list(active_clients):
                try:
                    loop.call_soon_threadsafe(asyncio.create_task, ws.send_json(payload))
                except Exception as e:
                    logger.error(f"클라이언트 전송 오류: {e}")
                    dead_clients.append(ws)

            for ws in dead_clients:
                active_clients.discard(ws)

    except Exception as e:
        logger.error(f"메시지 처리 오류: {e}", exc_info=True)

# Bitget 포지션 채널 구독 (instType=USDT-FUTURES, instId=default → 전체 포지션)
channels = [SubscribeReq("umcbl", "positions", "default")]
bitget_ws.subscribe(channels, on_message)

@router.websocket("/ws/positions")
async def positions_ws(websocket: WebSocket):
    await websocket.accept()
    active_clients.add(websocket)
    try:
        # 연결 유지용 루프 (메시지는 서버에서만 push)
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        active_clients.discard(websocket)