import os
import json
import asyncio
import logging
from dotenv import load_dotenv
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from pybitget.stream import BitgetWsClient, SubscribeReq, handel_error
from pybitget import logger

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("positions-sub")

router = APIRouter()
active_clients = set()

# .env 로드
load_dotenv()

API_KEY = os.getenv("BITGET_API_KEY")
API_SECRET = os.getenv("BITGET_API_SECRET")
API_PASS = os.getenv("BITGET_API_PASS")

if not all([API_KEY, API_SECRET, API_PASS]):
    raise RuntimeError("환경변수 BITGET_API_KEY, BITGET_API_SECRET, BITGET_API_PASS 를 설정하세요.")

# Bitget WebSocket 클라이언트 생성
bitget_ws = (
    BitgetWsClient(
        api_key=API_KEY,
        api_secret=API_SECRET,
        passphrase=API_PASS,
        verbose=True,
    )
    .error_listener(handel_error)
    .build()
)

# 메시지 콜백
def on_message(message: str):
    try:
        log.info(f"RAW >>> {message}")
        data = json.loads(message)

        if data.get("arg", {}).get("channel") == "positions":
            payload = data.get("data", [])
            if not payload:
                log.info("포지션 데이터 없음 (현재 열린 포지션이 없습니다).")
                return

            # 연결된 모든 클라이언트에 브로드캐스트
            loop = asyncio.get_event_loop()
            dead_clients = []

            for ws in list(active_clients):
                async def _send(ws=ws, payload=payload):
                    try:
                        await ws.send_json(payload)
                    except Exception:
                        dead_clients.append(ws)

                loop.call_soon_threadsafe(asyncio.create_task, _send())

            for ws in dead_clients:
                active_clients.discard(ws)

    except Exception as e:
        log.error(f"메시지 파싱 오류: {e}", exc_info=True)

# FastAPI 서버가 뜰 때 Bitget 구독 시작
@router.on_event("startup")
async def startup_event():
    channels = [SubscribeReq("umcbl", "positions", "default")]
    bitget_ws.subscribe(channels, on_message)
    log.info("Bitget 포지션 채널 구독 시작...")

# WebSocket 엔드포인트
@router.websocket("/ws/positions")
async def positions_ws(websocket: WebSocket):
    await websocket.accept()
    active_clients.add(websocket)
    try:
        while True:
            await asyncio.sleep(10)  # keep-alive
    except WebSocketDisconnect:
        active_clients.discard(websocket)