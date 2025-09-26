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
bitget_ws = None  # 전역 참조

# 로그 설정
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("positions-sub")

load_dotenv()

def on_message(message: str):
    try:
        data = json.loads(message)

        # 디버그: 어떤 이벤트가 오는지 보고 싶다면 잠시 활성화
        # log.info("WS IN < %s", message)

        if data.get("arg", {}).get("channel") == "positions":
            payload = data.get("data", [])
            if not payload:
                # 포지션 없음을 클라에 통지
                for ws in list(active_clients):
                    try:
                        asyncio.run_coroutine_threadsafe(
                            ws.send_json({"msg": "현재 열린 포지션이 없습니다."}),
                            loop
                        )
                    except Exception:
                        active_clients.discard(ws)
                return

            # 정상 payload 브로드캐스트
            for ws in list(active_clients):
                try:
                    asyncio.run_coroutine_threadsafe(ws.send_json(payload), loop)
                except Exception:
                    active_clients.discard(ws)

    except Exception as e:
        log.error(f"메시지 파싱 오류: {e}", exc_info=True)

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

    # ✅ 콜백을 생성자 위치 인자로 넣는 패턴
    bitget_ws = BitgetWsClient(on_message, handel_error)

    # ✅ 내부 루프 시작 → 로그인 → 구독 (이 순서 중요)
    try:
        bitget_ws.start()
    except Exception as e:
        log.warning("bitget_ws.start() skip or already started: %s", e)

    # 로그인(프라이빗 채널 권한 부여)
    bitget_ws.login(api_key, secret, passwd)

    # positions 구독
    channels = [SubscribeReq("umcbl", "positions", "default")]
    bitget_ws.subscribe(channels, on_message)

    log.info("Bitget positions 구독 시작")

@router.websocket("/ws/positions")
async def positions_ws(websocket: WebSocket):
    await websocket.accept()
    active_clients.add(websocket)

    # 접속 직후 테스트 메시지 (클라 onmessage 파이프 확인용)
    try:
        await websocket.send_text(json.dumps({"_test": "hello"}))
    except Exception as e:
        log.exception("initial send error: %s", e)

    try:
        while True:
            await asyncio.sleep(10)  # keep-alive
    except WebSocketDisconnect:
        active_clients.discard(websocket)
