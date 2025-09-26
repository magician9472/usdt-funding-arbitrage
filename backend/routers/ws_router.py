import os
import json
import asyncio
import logging
from dotenv import load_dotenv
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pybitget.stream import BitgetWsClient, SubscribeReq, handel_error

router = APIRouter()
active_clients = set()
loop = None  # FastAPI 이벤트 루프 저장용

# 로그 설정
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("positions-sub")

# .env 로드
load_dotenv()


# 메시지 콜백
def on_message(message: str):
    try:
        data = json.loads(message)
        if data.get("arg", {}).get("channel") == "positions":
            payload = data.get("data", [])
            if not payload:
                # 포지션 없을 때도 클라이언트에 알림
                for ws in list(active_clients):
                    try:
                        asyncio.run_coroutine_threadsafe(
                            ws.send_json({"msg": "현재 열린 포지션이 없습니다."}), loop
                        )
                    except Exception:
                        active_clients.discard(ws)
                return

            for ws in list(active_clients):
                try:
                    asyncio.run_coroutine_threadsafe(ws.send_json(payload), loop)
                except Exception:
                    active_clients.discard(ws)
    except Exception as e:
        log.error(f"메시지 파싱 오류: {e}", exc_info=True)

# FastAPI 시작 시 Bitget 구독 시작
@router.on_event("startup")
async def startup_event():
    load_dotenv()
    api_key = os.getenv("BITGET_API_KEY")
    secret  = os.getenv("BITGET_API_SECRET")
    passwd  = os.getenv("BITGET_API_PASS")
    if not all([api_key, secret, passwd]):
        raise RuntimeError("환경변수 BITGET_API_KEY/SECRET/PASS 설정 필요")

    global loop, bitget_ws
    loop = asyncio.get_running_loop()

    bitget_ws = BitgetWsClient(
        api_key=api_key,
        api_secret=secret,
        passphrase=passwd,
        # 중요: private 채널이면 True
        is_private=True,
        # 필요 시 멀티 스레드 off 등 옵션 확인
    )

    channels = [SubscribeReq("umcbl", "positions", "default")]
    bitget_ws.subscribe(channels, on_message)
    log.info("Bitget positions 구독 시작")


# WebSocket 엔드포인트
@router.websocket("/ws/positions")
async def positions_ws(websocket: WebSocket):
    await websocket.accept()
    active_clients.add(websocket)

    # ▶ 테스트 메시지: 접속 즉시 무조건 한 줄 쏘기
    try:
        await websocket.send_text(json.dumps({
            "_test": "hello",
            "ts": __import__("time").time()
        }))
    except Exception as e:
        log.exception("initial send error: %s", e)

    try:
        while True:
            await asyncio.sleep(10)  # keep-alive
    except WebSocketDisconnect:
        active_clients.discard(websocket)
