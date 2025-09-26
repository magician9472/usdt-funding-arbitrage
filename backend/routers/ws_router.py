import json, asyncio, logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pybitget.stream import BitgetWsClient, SubscribeReq, handel_error
import os
from dotenv import load_dotenv
from pybitget.stream import BitgetWsClient, handel_error

router = APIRouter()
active_clients = set()
loop = None

log = logging.getLogger("positions-sub")



load_dotenv()
API_KEY = os.getenv("BITGET_API_KEY")
API_SECRET = os.getenv("BITGET_API_SECRET")
API_PASS = os.getenv("BITGET_API_PASS")

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
    log.info("📩 on_message 호출됨")
    try:
        data = json.loads(message)
        if data.get("arg", {}).get("channel") == "positions":
            payload = data.get("data", [])
            if not payload:
                for ws in list(active_clients):
                    asyncio.run_coroutine_threadsafe(
                        ws.send_json({"msg": "현재 열린 포지션이 없습니다."}), loop
                    )
                return
            for ws in list(active_clients):
                asyncio.run_coroutine_threadsafe(ws.send_json(payload), loop)
    except Exception as e:
        log.error(f"메시지 파싱 오류: {e}", exc_info=True)

# 클라이언트 WebSocket 엔드포인트
@router.websocket("/ws/positions")
async def positions_ws(websocket: WebSocket):
    await websocket.accept()
    active_clients.add(websocket)
    log.info(f"🌐 클라이언트 연결됨: {websocket.client}")
    try:
        while True:
            await asyncio.sleep(10)
    except WebSocketDisconnect:
        log.info(f"🔌 클라이언트 연결 해제: {websocket.client}")
        active_clients.discard(websocket)