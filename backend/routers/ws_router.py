from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import asyncio, os, json, logging
from dotenv import load_dotenv
from pybitget.stream import BitgetWsClient, SubscribeReq, handel_error

router = APIRouter()
active_clients = set()
loop = None  # 이벤트 루프 저장용

log = logging.getLogger("positions-sub")
logging.basicConfig(level=logging.INFO)

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

def on_message(message: str):
    try:
        data = json.loads(message)
        if data.get("arg", {}).get("channel") == "positions":
            payload = data.get("data", [])
            if not payload:
                return
            for ws in list(active_clients):
                try:
                    asyncio.run_coroutine_threadsafe(ws.send_json(payload), loop)
                except Exception:
                    active_clients.discard(ws)
    except Exception as e:
        log.error(f"메시지 파싱 오류: {e}", exc_info=True)

@router.on_event("startup")
async def startup_event():
    global loop
    loop = asyncio.get_running_loop()
    channels = [SubscribeReq("umcbl", "positions", "default")]
    bitget_ws.subscribe(channels, on_message)
    log.info("Bitget positions 구독 시작")

@router.websocket("/ws/positions")
async def positions_ws(websocket: WebSocket):
    await websocket.accept()
    active_clients.add(websocket)
    try:
        while True:
            await asyncio.sleep(10)
    except WebSocketDisconnect:
        active_clients.discard(websocket)