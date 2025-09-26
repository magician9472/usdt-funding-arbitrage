from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import asyncio, os, json, logging
from dotenv import load_dotenv
from pybitget.stream import BitgetWsClient, SubscribeReq, handel_error

router = APIRouter()
active_clients = set()
loop = None

# .env 로드
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
                # 포지션 없음 메시지
                for ws in list(active_clients):
                    asyncio.run_coroutine_threadsafe(
                        ws.send_json({"msg": "현재 열린 포지션이 없습니다."}), loop
                    )
                return
            # 포지션 데이터 브로드캐스트
            for ws in list(active_clients):
                asyncio.run_coroutine_threadsafe(ws.send_json(payload), loop)
    except Exception as e:
        logging.error(f"메시지 파싱 오류: {e}", exc_info=True)

@router.on_event("startup")
async def startup_event():
    global loop
    loop = asyncio.get_running_loop()
    channels = [SubscribeReq("umcbl", "positions", "default")]
    bitget_ws.subscribe(channels, on_message)

@router.websocket("/ws/positions")
async def positions_ws(websocket: WebSocket):
    await websocket.accept()
    active_clients.add(websocket)
    try:
        while True:
            await asyncio.sleep(10)  # keep-alive
    except WebSocketDisconnect:
        active_clients.discard(websocket)