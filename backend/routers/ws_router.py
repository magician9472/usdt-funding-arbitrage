from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import asyncio
import json
import os
import logging

from pybitget.stream import BitgetWsClient, SubscribeReq, handel_error
from pybitget.enums import *
from pybitget import logger

# SQLAlchemy 쿼리 로그 줄이기
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

router = APIRouter()

# 연결된 클라이언트 저장
active_clients = set()

# Bitget WebSocket 클라이언트 생성
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
        data = json.loads(message)

        # 포지션 채널 이벤트만 처리
        if data.get("arg", {}).get("channel") == "positions":
            for pos in data.get("data", []):
                print("포지션 이벤트:", pos["instId"], pos["holdSide"], pos["total"])

            # 연결된 모든 클라이언트에 브로드캐스트
            for ws in list(active_clients):
                try:
                    asyncio.create_task(ws.send_json(data.get("data", [])))
                except Exception as e:
                    logger.error(f"클라이언트 전송 오류: {e}")

    except Exception as e:
        logger.error(f"메시지 처리 오류: {e}")


# Bitget 포지션 채널 구독 (instType="UMCBL" → USDT 무기한 계약)
channels = [SubscribeReq("USDT-FUTURES", "positions", "default")]
bitget_ws.subscribe(channels, on_message)


@router.websocket("/ws/positions")
async def positions_ws(websocket: WebSocket):
    await websocket.accept()
    active_clients.add(websocket)
    logger.info("웹소켓 클라이언트 연결됨")

    try:
        while True:
            # 클라이언트에서 오는 메시지는 특별히 처리하지 않고 대기
            await websocket.receive_text()
    except WebSocketDisconnect:
        active_clients.remove(websocket)
        logger.info("웹소켓 연결 종료")