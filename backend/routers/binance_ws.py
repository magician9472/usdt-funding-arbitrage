import os, asyncio, logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from dotenv import load_dotenv
from binance import AsyncClient, BinanceSocketManager

router = APIRouter()
active_clients = set()
loop = None

last_positions = {}        # {symbol: pos}
last_mark_prices = {}      # {symbol: markPrice}

log = logging.getLogger("binance-positions")

# .env 로드
load_dotenv()
BINANCE_KEY = os.getenv("BINANCE_API_KEY")
BINANCE_SECRET = os.getenv("BINANCE_API_SECRET")

if not all([BINANCE_KEY, BINANCE_SECRET]):
    raise RuntimeError("환경변수 BINANCE_API_KEY, BINANCE_API_SECRET 를 설정하세요.")

def broadcast():
    merged = []
    for symbol, pos in last_positions.items():
        mark = last_mark_prices.get(symbol)
        entry = float(pos.get("entryPrice", 0))
        size = float(pos.get("positionAmt", 0))
        upl = None
        try:
            if mark and entry and size:
                m = float(mark)
                if size > 0:
                    upl = (m - entry) * size
                elif size < 0:
                    upl = (entry - m) * abs(size)
        except Exception as e:
            log.error(f"Binance UPL 계산 오류: {e}")

        merged.append({
            "exchange": "binance",
            "symbol": symbol,
            "side": pos.get("positionSide"),
            "size": size,
            "upl": upl if upl is not None else pos.get("unRealizedProfit"),
            "entryPrice": entry,
            "markPrice": mark,
            "liqPrice": pos.get("liquidationPrice"),
            "margin": pos.get("marginType"),
        })

    if not merged:
        merged = [{"msg": "현재 열린 포지션이 없습니다."}]

    for ws in list(active_clients):
        asyncio.run_coroutine_threadsafe(ws.send_json(merged), loop)

async def binance_worker():
    """Binance 포지션 + markPrice 실시간 업데이트"""
    client = await AsyncClient.create(BINANCE_KEY, BINANCE_SECRET)
    bm = BinanceSocketManager(client)

    # ✅ 초기 스냅샷
    all_positions = await client.futures_position_information()
    for pos in all_positions:
        if float(pos.get("positionAmt", 0)) != 0:
            symbol = pos["symbol"]
            last_positions[symbol] = pos

    # ✅ 전체 markPrice 스트림
    async with bm.multiplex_socket(["!markPrice@arr@1s"]) as stream:
        while True:
            msg = await stream.recv()
            if isinstance(msg, list):
                for item in msg:
                    sym = item.get("s")
                    if sym in last_positions:
                        last_mark_prices[sym] = item.get("p")
                        broadcast()

@router.websocket("/ws/binance")
async def positions_ws(websocket: WebSocket):
    await websocket.accept()
    active_clients.add(websocket)
    log.info(f"🌐 Binance 클라이언트 연결됨: {websocket.client}")

    if last_positions:
        broadcast()

    try:
        while True:
            await asyncio.sleep(10)
    except WebSocketDisconnect:
        log.info(f"🔌 Binance 클라이언트 연결 해제: {websocket.client}")
        active_clients.discard(websocket)