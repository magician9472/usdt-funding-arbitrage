import os, asyncio, json, logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from dotenv import load_dotenv
from binance import AsyncClient
import websockets

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


def normalize_position(pos: dict):
    """REST 포지션 데이터를 짧은 키로 맞춤"""
    return {
        "pa": pos.get("positionAmt"),        # position amount
        "ep": pos.get("entryPrice"),         # entry price
        "up": pos.get("unRealizedProfit"),   # unrealized PnL
        "l": pos.get("liquidationPrice"),    # liquidation price
        "iw": pos.get("isolatedMargin"),     # isolated margin
        "mt": pos.get("marginType"),         # margin type (ISOLATED / CROSSED)
    }


def broadcast():
    """현재 포지션 + markPrice + UPL 계산해서 모든 클라이언트에 전송"""
    merged = []
    for symbol, pos in last_positions.items():
        mark = last_mark_prices.get(symbol)

        try:
            size = float(pos.get("pa") or 0)
        except Exception:
            size = 0.0

        try:
            entry = float(pos.get("ep") or 0)
        except Exception:
            entry = 0.0

        upl = pos.get("up")

        # 방향 계산
        if size > 0:
            side = "LONG"
        elif size < 0:
            side = "SHORT"
        else:
            side = "FLAT"

        # UPL 재계산
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
            "side": side,
            "size": size,
            "upl": upl,
            "entryPrice": entry,
            "markPrice": mark,
            "liqPrice": pos.get("l"),
            "margin": pos.get("iw"),
            "marginType": pos.get("mt"),
        })

    if not merged:
        merged = [{"msg": "현재 열린 포지션이 없습니다."}]

    for ws in list(active_clients):
        asyncio.run_coroutine_threadsafe(ws.send_json(merged), loop)


async def refresh_positions():
    """주기적으로 REST API 스냅샷을 갱신해서 닫힌 포지션 제거"""
    global last_positions
    while True:
        try:
            client = await AsyncClient.create(BINANCE_KEY, BINANCE_SECRET)
            all_positions = await client.futures_position_information()
            account_info = await client.futures_account()
            await client.close_connection()

            margin_map = {p["symbol"]: p.get("isolatedMargin") for p in account_info["positions"]}
            margin_type_map = {p["symbol"]: p.get("marginType") for p in account_info["positions"]}

            updated = {}
            for pos in all_positions:
                amt = float(pos.get("positionAmt") or 0)
                symbol = pos["symbol"]
                if amt != 0:
                    norm = normalize_position(pos)
                    norm["iw"] = margin_map.get(symbol)
                    norm["mt"] = margin_type_map.get(symbol)
                    updated[symbol] = norm

            # ✅ 열린 포지션만 유지, 닫힌 건 자동 제거
            last_positions = updated
            broadcast()

        except Exception as e:
            log.error(f"포지션 갱신 오류: {e}")

        await asyncio.sleep(5)  # 5초마다 갱신


async def binance_worker():
    """Binance markPrice 실시간 업데이트"""
    # markPrice 스트림
    url_mark = "wss://fstream.binance.com/ws/!markPrice@arr@1s"
    async with websockets.connect(url_mark, ping_interval=20, ping_timeout=20) as ws:
        log.info("실시간 markPrice 수신 시작")
        while True:
            raw = await ws.recv()
            data = json.loads(raw)
            if isinstance(data, list):
                for item in data:
                    sym = item.get("s")
                    if item.get("e") == "markPriceUpdate" and sym in last_positions:
                        last_mark_prices[sym] = item["p"]
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