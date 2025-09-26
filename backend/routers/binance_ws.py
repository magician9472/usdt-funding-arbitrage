import os, asyncio, json, logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from dotenv import load_dotenv
from binance import AsyncClient
import websockets

router = APIRouter()
active_clients = set()

last_positions = {}        # {symbol: pos}
last_mark_prices = {}      # {symbol: markPrice}
TARGET_SYMBOL = None

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
        "iw": pos.get("isolatedMargin"),     # REST에서는 isolatedMargin → iw
    }


async def broadcast():
    """현재 포지션 + markPrice + UPL 계산해서 모든 클라이언트에 전송"""
    merged = []
    for symbol, pos in last_positions.items():
        mark = last_mark_prices.get(symbol)
        entry = float(pos.get("ep", 0) or 0)
        size = float(pos.get("pa", 0) or 0)
        upl = pos.get("up")

        # 포지션 방향 계산
        if size > 0:
            side = "LONG"
        elif size < 0:
            side = "SHORT"
        else:
            side = "FLAT"

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
            "margin": pos.get("iw"),   # ← 항상 iw 로 통일
        })

    if not merged:
        merged = [{"msg": "현재 열린 포지션이 없습니다."}]

    for ws in list(active_clients):
        try:
            await ws.send_json(merged)
        except Exception as e:
            log.error(f"WebSocket 전송 오류: {e}")
            active_clients.discard(ws)


async def binance_worker():
    """Binance 포지션 + markPrice + ACCOUNT_UPDATE 실시간 업데이트"""
    global TARGET_SYMBOL

    client = await AsyncClient.create(BINANCE_KEY, BINANCE_SECRET)

    # ✅ 스냅샷: 열린 포지션 하나만 선택
    all_positions = await client.futures_position_information()
    account_info = await client.futures_account()

    margin_map = {p["symbol"]: p.get("isolatedMargin") for p in account_info["positions"]}

    for pos in all_positions:
        if float(pos.get("positionAmt", 0) or 0) != 0:
            symbol = pos["symbol"]
            TARGET_SYMBOL = symbol
            norm = normalize_position(pos)
            norm["iw"] = margin_map.get(symbol)
            last_positions[symbol] = norm
            break

    if not TARGET_SYMBOL:
        log.info("열린 포지션이 없습니다.")
        await client.close_connection()
        return

    # ✅ listenKey 발급 (User Data Stream)
    listen_key = await client.futures_stream_get_listen_key()
    await client.close_connection()

    url_mark = "wss://fstream.binance.com/ws/!markPrice@arr@1s"
    url_user = f"wss://fstream.binance.com/ws/{listen_key}"

    async def mark_stream():
        async with websockets.connect(url_mark, ping_interval=20, ping_timeout=20) as ws:
            log.info(f"실시간 markPrice 수신 시작: {TARGET_SYMBOL}")
            while True:
                raw = await ws.recv()
                data = json.loads(raw)
                if isinstance(data, list):
                    for item in data:
                        if item.get("e") == "markPriceUpdate" and item.get("s") == TARGET_SYMBOL:
                            last_mark_prices[item["s"]] = item["p"]
                            await broadcast()

    async def user_stream():
        async with websockets.connect(url_user, ping_interval=20, ping_timeout=20) as ws:
            log.info("✅ User Data Stream 연결됨")
            while True:
                raw = await ws.recv()
                data = json.loads(raw)
                if data.get("e") == "ACCOUNT_UPDATE":
                    for p in data["a"].get("P", []):
                        sym = p["s"]
                        last_positions[sym] = {
                            "pa": p["pa"],
                            "ep": p["ep"],
                            "up": p["up"],
                            "l": p.get("l"),
                            "iw": p["iw"],   # ← 실시간 증거금 (iw)
                            "ps": p["ps"],
                        }
                    await broadcast()

    # 두 스트림 동시에 실행
    await asyncio.gather(mark_stream(), user_stream())


@router.websocket("/ws/binance")
async def positions_ws(websocket: WebSocket):
    await websocket.accept()
    active_clients.add(websocket)
    log.info(f"🌐 Binance 클라이언트 연결됨: {websocket.client}")

    if last_positions:
        await broadcast()

    try:
        while True:
            await asyncio.sleep(10)
    except WebSocketDisconnect:
        log.info(f"🔌 Binance 클라이언트 연결 해제: {websocket.client}")
        active_clients.discard(websocket)