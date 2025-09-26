# backend/routers/ws_router.py
import os
import json
import asyncio
import logging
from typing import Set

from dotenv import load_dotenv
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pybitget.stream import BitgetWsClient, SubscribeReq, handel_error

router = APIRouter()
active_clients: Set[WebSocket] = set()
loop = None  # FastAPI 이벤트 루프
bitget_ws: BitgetWsClient | None = None

# 로그
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("positions-sub")

# .env
load_dotenv()
API_KEY = os.getenv("BITGET_API_KEY")
API_SECRET = os.getenv("BITGET_API_SECRET")
API_PASS = os.getenv("BITGET_API_PASS")
if not all([API_KEY, API_SECRET, API_PASS]):
    raise RuntimeError("환경변수 BITGET_API_KEY, BITGET_API_SECRET, BITGET_API_PASS 를 설정하세요.")

# Bitget → 서버 메시지 콜백
def on_message(message: str):
    try:
        # 원본 로그(초기 디버깅용)
        # log.info("RAW >>> %s", message)
        data = json.loads(message)

        # 구독 ACK 확인(원하면 주석 해제)
        if data.get("event") == "subscribe":
            log.info("✅ subscribe ack: %s", data)

        if data.get("arg", {}).get("channel") == "positions":
            payload = data.get("data", [])

            # 포지션 없을 때도 클라에게 명시적으로 알려주기(선택)
            if not payload:
                for ws in list(active_clients):
                    try:
                        asyncio.run_coroutine_threadsafe(
                            ws.send_json({"msg": "현재 열린 포지션이 없습니다."}),
                            loop
                        )
                    except Exception:
                        active_clients.discard(ws)
                return

            # 브라우저로 그대로 브로드캐스트
            for ws in list(active_clients):
                try:
                    asyncio.run_coroutine_threadsafe(ws.send_json(payload), loop)
                except Exception:
                    active_clients.discard(ws)

    except Exception as e:
        log.exception("메시지 파싱 오류: %s", e)

# 앱 시작: Bitget WS 연결 + 구독
@router.on_event("startup")
async def startup_event():
    global loop, bitget_ws
    loop = asyncio.get_running_loop()

    # 💡 네가 단독 스크립트에서 성공했던 패턴 그대로 적용
    bitget_ws = (
        BitgetWsClient(
            api_key=API_KEY,
            api_secret=API_SECRET,
            passphrase=API_PASS,
            verbose=True
        )
        .error_listener(handel_error)
        .build()
    )

    channels = [SubscribeReq("umcbl", "positions", "default")]  # 너의 성공 코드와 동일
    bitget_ws.subscribe(channels, on_message)

    log.info("Bitget positions 구독 시작")

# 앱 종료: Bitget WS 닫기(권장)
@router.on_event("shutdown")
async def shutdown_event():
    global bitget_ws
    try:
        if bitget_ws:
            bitget_ws.close()
            log.info("Bitget WS 종료")
    except Exception as e:
        log.warning("Bitget WS 종료 중 경고: %s", e)

# 브라우저 ↔ 서버 WS
@router.websocket("/ws/positions")
async def positions_ws(websocket: WebSocket):
    await websocket.accept()
    active_clients.add(websocket)

    # 초기 테스트 메세지(클라 onmessage 파이프 확인용)
    try:
        await websocket.send_json({"_test": "hello"})
    except Exception as e:
        log.exception("initial send error: %s", e)

    try:
        while True:
            await asyncio.sleep(10)  # keep-alive
    except WebSocketDisconnect:
        active_clients.discard(websocket)
