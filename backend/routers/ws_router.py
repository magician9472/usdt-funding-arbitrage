import os, json, asyncio, logging
from dotenv import load_dotenv
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pybitget.stream import BitgetWsClient, SubscribeReq, handel_error

router = APIRouter()
active_clients: set[WebSocket] = set()
loop = None
bitget_ws = None

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("positions-sub")

load_dotenv()
API_KEY = os.getenv("BITGET_API_KEY")
API_SECRET = os.getenv("BITGET_API_SECRET")
API_PASS = os.getenv("BITGET_API_PASS")
if not all([API_KEY, API_SECRET, API_PASS]):
    raise RuntimeError("환경변수 BITGET_API_KEY, BITGET_API_SECRET, BITGET_API_PASS 를 설정하세요.")

def on_message(message: str):
    try:
        data = json.loads(message)
        if data.get("event") == "subscribe":
            log.info("✅ subscribe ack: %s", data)
        if data.get("arg", {}).get("channel") == "positions":
            payload = data.get("data", [])
            if not payload:
                for ws in list(active_clients):
                    asyncio.run_coroutine_threadsafe(ws.send_json({"msg": "현재 열린 포지션이 없습니다."}), loop)
                return
            for ws in list(active_clients):
                asyncio.run_coroutine_threadsafe(ws.send_json(payload), loop)
    except Exception as e:
        log.exception("메시지 파싱 오류: %s", e)

@router.on_event("startup")
async def startup_event():
    global loop, bitget_ws
    loop = asyncio.get_running_loop()

    # 1) 생성 → 리스너 등록 → build()
    bitget_ws = (
        BitgetWsClient(api_key=API_KEY, api_secret=API_SECRET, passphrase=API_PASS, verbose=True)
        .message_listener(on_message)   # ← 이 줄이 중요 (버전에 따라 필요)
        .error_listener(handel_error)
        .build()
    )

    # 2) (버전에 따라) 명시적 start() 필요
    try:
        bitget_ws.start()
    except Exception as e:
        log.warning("bitget_ws.start() skip or already started: %s", e)

    # 3) (일부 버전) login이 여전히 필요합니다
    try:
        bitget_ws.login(API_KEY, API_SECRET, API_PASS)
    except Exception as e:
        log.info("login skipped or not required: %s", e)

    # 4) 구독
    channels = [SubscribeReq("UMCBL", "positions", "default")]
    bitget_ws.subscribe(channels, on_message)

    log.info("Bitget positions 구독 시작")

@router.websocket("/ws/positions")
async def positions_ws(websocket: WebSocket):
    await websocket.accept()
    active_clients.add(websocket)
    try:
        await websocket.send_json({"_test": "hello"})
        while True:
            await asyncio.sleep(10)
    except WebSocketDisconnect:
        active_clients.discard(websocket)
