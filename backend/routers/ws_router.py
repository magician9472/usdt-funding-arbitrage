import os, json, asyncio, logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from dotenv import load_dotenv
from pybitget.stream import BitgetWsClient, handel_error

router = APIRouter()
active_clients = set()
loop = None
last_positions = None  # 마지막 포지션 상태 저장

log = logging.getLogger("positions-sub")

# .env 로드
load_dotenv()
API_KEY = os.getenv("BITGET_API_KEY")
API_SECRET = os.getenv("BITGET_API_SECRET")
API_PASS = os.getenv("BITGET_API_PASS")

if not all([API_KEY, API_SECRET, API_PASS]):
    raise RuntimeError("환경변수 BITGET_API_KEY, BITGET_API_SECRET, BITGET_API_PASS 를 설정하세요.")

# Bitget WebSocket 클라이언트 (인증 포함)
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
    global last_positions
    log.info("📩 on_message 호출됨")
    try:
        data = json.loads(message)
        if data.get("arg", {}).get("channel") == "positions":
            payload = data.get("data", [])
            if not payload:
                last_positions = {"msg": "현재 열린 포지션이 없습니다."}
            else:
                last_positions = payload

            # 연결된 모든 클라이언트에 브로드캐스트
            for ws in list(active_clients):
                try:
                    asyncio.run_coroutine_threadsafe(ws.send_json(last_positions), loop)
                except Exception as e:
                    log.error(f"❌ send_json error: {e}")
                    active_clients.discard(ws)
    except Exception as e:
        log.error(f"메시지 파싱 오류: {e}", exc_info=True)

# 클라이언트 WebSocket 엔드포인트
@router.websocket("/ws/positions")
async def positions_ws(websocket: WebSocket):
    await websocket.accept()
    active_clients.add(websocket)
    log.info(f"🌐 클라이언트 연결됨: {websocket.client}")

    # 새로 연결된 클라이언트에 마지막 상태 즉시 전송
    if last_positions is not None:
        await websocket.send_json(last_positions)

    try:
        while True:
            await asyncio.sleep(10)
    except WebSocketDisconnect:
        log.info(f"🔌 클라이언트 연결 해제: {websocket.client}")
        active_clients.discard(websocket)