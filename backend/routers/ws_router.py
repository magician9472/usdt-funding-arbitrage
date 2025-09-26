import os, json, asyncio, logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from dotenv import load_dotenv
from pybitget.stream import BitgetWsClient, handel_error

router = APIRouter()
active_clients = set()
loop = None
last_positions = {}     # 심볼별 포지션 상태
last_mark_prices = {}   # 심볼별 최신 마크프라이스

log = logging.getLogger("positions-sub")

# .env 로드
load_dotenv()
API_KEY = os.getenv("BITGET_API_KEY")
API_SECRET = os.getenv("BITGET_API_SECRET")
API_PASS = os.getenv("BITGET_API_PASS")

if not all([API_KEY, API_SECRET, API_PASS]):
    raise RuntimeError("환경변수 BITGET_API_KEY, BITGET_API_SECRET, BITGET_API_PASS 를 설정하세요.")

# Bitget WebSocket 클라이언트
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

def calc_pnl(entry, mark, size, side):
    """실시간 PNL 계산"""
    try:
        entry, mark, size = float(entry), float(mark), float(size)
    except (TypeError, ValueError):
        return None
    if side == "long":
        return (mark - entry) * size
    elif side == "short":
        return (entry - mark) * size
    return None

def broadcast():
    """포지션 + 마크프라이스 합쳐서 클라이언트에 전송"""
    merged = []
    for symbol, pos in last_positions.items():
        entry = pos.get("avgEntryPrice")
        size = pos.get("total")
        side = pos.get("holdSide")
        mark = last_mark_prices.get(symbol, pos.get("markPrice"))

        pnl = calc_pnl(entry, mark, size, side)

        merged.append({
            "symbol": symbol,
            "side": side,
            "size": size,
            "entryPrice": entry,
            "markPrice": mark,
            "liqPrice": pos.get("liqPx"),
            "margin": pos.get("margin"),
            "pnl": pnl,
        })

    if not merged:
        merged = {"msg": "현재 열린 포지션이 없습니다."}

    for ws in list(active_clients):
        asyncio.run_coroutine_threadsafe(ws.send_json(merged), loop)

def on_message(message: str):
    global last_positions, last_mark_prices
    try:
        data = json.loads(message)
        arg = data.get("arg", {})
        channel = arg.get("channel")
        payload = data.get("data", [])

        if channel == "positions":
            if not payload:
                last_positions = {}
            else:
                for pos in payload:
                    last_positions[pos["instId"]] = pos
            broadcast()

        elif channel == "markPrice":
            for mp in payload:
                last_mark_prices[mp["instId"]] = mp["markPrice"]
            broadcast()

    except Exception as e:
        log.error(f"메시지 파싱 오류: {e}", exc_info=True)

@router.websocket("/ws/positions")
async def positions_ws(websocket: WebSocket):
    await websocket.accept()
    active_clients.add(websocket)
    log.info(f"🌐 클라이언트 연결됨: {websocket.client}")

    # 새 연결 시 마지막 상태 전송
    if last_positions:
        broadcast()

    try:
        while True:
            await asyncio.sleep(10)
    except WebSocketDisconnect:
        log.info(f"🔌 클라이언트 연결 해제: {websocket.client}")
        active_clients.discard(websocket)