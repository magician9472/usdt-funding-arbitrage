import os, json, asyncio, logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from dotenv import load_dotenv
from pybitget.stream import BitgetWsClient, handel_error, SubscribeReq

router = APIRouter()
active_clients = set()
loop = None
last_positions = {}
last_mark_prices = {}
subscribed_tickers = set()

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

def broadcast():
    merged = []
    for symbol, pos in last_positions.items():
        merged.append({
            "symbol": symbol,
            "side": pos.get("holdSide"),
            "size": pos.get("total"),
            "upl": pos.get("upl"),  # Bitget 제공 UPL
            "entryPrice": pos.get("avgOpenPrice"),
            "markPrice": last_mark_prices.get(symbol, pos.get("markPrice")),
            "liqPrice": pos.get("liqPx"),
            "margin": pos.get("margin"),
        })

    if not merged:
        merged = {"msg": "현재 열린 포지션이 없습니다."}

    for ws in list(active_clients):
        asyncio.run_coroutine_threadsafe(ws.send_json(merged), loop)

def on_message(message: str):
    global last_positions, last_mark_prices, subscribed_tickers
    try:
        data = json.loads(message)
        arg = data.get("arg", {})
        channel = arg.get("channel")
        payload = data.get("data", [])

        if channel == "positions":
            # 현재 포지션 목록 업데이트
            current_symbols = set()
            last_positions = {}
            for pos in payload:
                instId = pos["instId"]
                last_positions[instId] = pos
                current_symbols.add(instId)

                # 새 포지션 심볼이면 ticker 구독
                if instId not in subscribed_tickers:
                    bitget_ws.subscribe(
                        [SubscribeReq("umcbl", "ticker", instId)], on_message
                    )
                    subscribed_tickers.add(instId)

            # 포지션이 사라진 심볼은 ticker 구독 해제
            removed = subscribed_tickers - current_symbols
            for instId in removed:
                bitget_ws.unsubscribe(
                    [SubscribeReq("umcbl", "ticker", instId)], on_message
                )
                subscribed_tickers.remove(instId)
                last_mark_prices.pop(instId, None)

            broadcast()

        elif channel == "ticker":
            for t in payload:
                last_mark_prices[t["instId"]] = t["markPrice"]
            broadcast()

    except Exception as e:
        log.error(f"메시지 파싱 오류: {e}", exc_info=True)

@router.websocket("/ws/positions")
async def positions_ws(websocket: WebSocket):
    await websocket.accept()
    active_clients.add(websocket)
    log.info(f"🌐 클라이언트 연결됨: {websocket.client}")

    if last_positions:
        broadcast()

    try:
        while True:
            await asyncio.sleep(10)
    except WebSocketDisconnect:
        log.info(f"🔌 클라이언트 연결 해제: {websocket.client}")
        active_clients.discard(websocket)