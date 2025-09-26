import os, json, asyncio, logging
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from dotenv import load_dotenv
from binance import ThreadedWebsocketManager, Client
from pybitget.stream import BitgetWsClient, handel_error, SubscribeReq

app = FastAPI()
log = logging.getLogger("positions")

# 상태 저장소
active_clients = set()
loop = asyncio.get_event_loop()

# Bitget
last_positions_bitget = {}
last_mark_prices_bitget = {}
pos_to_base = {}
subscribed_symbols = set()

# Binance
positions_binance = {}
mark_prices_binance = {}

# 환경변수
load_dotenv()
BITGET_KEY = os.getenv("BITGET_API_KEY")
BITGET_SECRET = os.getenv("BITGET_API_SECRET")
BITGET_PASS = os.getenv("BITGET_API_PASS")
BINANCE_KEY = os.getenv("BINANCE_API_KEY")
BINANCE_SECRET = os.getenv("BINANCE_API_SECRET")

# Bitget WebSocket 클라이언트
bitget_ws = (
    BitgetWsClient(api_key=BITGET_KEY, api_secret=BITGET_SECRET, passphrase=BITGET_PASS)
    .error_listener(handel_error)
    .build()
)

# Binance REST + WS 클라이언트
binance_client = Client(BINANCE_KEY, BINANCE_SECRET)

# ✅ 브로드캐스트
def broadcast():
    merged = []

    # Bitget 포지션
    for (pos_symbol, side), pos in last_positions_bitget.items():
        base_symbol = pos_to_base.get((pos_symbol, side))
        mark_price = last_mark_prices_bitget.get(base_symbol)
        merged.append({
            "source": "bitget",
            "symbol": pos_symbol,
            "side": side,
            "size": pos.get("total"),
            "entryPrice": pos.get("averageOpenPrice"),
            "markPrice": mark_price,
            "upl": pos.get("upl"),
            "liqPrice": pos.get("liqPx"),
            "margin": pos.get("margin"),
        })

    # Binance 포지션
    for symbol, pos in positions_binance.items():
        mark_price = mark_prices_binance.get(symbol)
        merged.append({
            "source": "binance",
            "symbol": symbol,
            "side": pos.get("ps"),
            "size": pos.get("pa"),
            "entryPrice": pos.get("ep"),
            "markPrice": mark_price,
            "upl": pos.get("up"),
            "liqPrice": pos.get("l"),
            "marginType": pos.get("mt"),
        })

    for ws in list(active_clients):
        asyncio.run_coroutine_threadsafe(ws.send_json(merged), loop)

# ✅ Bitget 메시지 핸들러
def on_bitget_message(message: str):
    data = json.loads(message)
    arg = data.get("arg", {})
    channel = arg.get("channel")
    payload = data.get("data", [])

    if channel == "positions":
        for pos in payload:
            instId = pos["instId"]
            base_symbol = instId.split("_")[0]
            side = pos["holdSide"]
            key = (instId, side)
            last_positions_bitget[key] = pos
            pos_to_base[key] = base_symbol
            if base_symbol not in subscribed_symbols:
                bitget_ws.subscribe([SubscribeReq("mc", "ticker", base_symbol)], on_bitget_message)
                subscribed_symbols.add(base_symbol)
        broadcast()

    elif channel == "ticker":
        for t in payload:
            instId = t["instId"]
            last_mark_prices_bitget[instId] = t.get("markPrice")
        broadcast()

# ✅ Binance 핸들러
def handle_user_data(msg):
    if msg.get("e") == "ACCOUNT_UPDATE":
        for pos in msg["a"]["P"]:
            symbol = pos["s"]
            if float(pos.get("pa", 0)) != 0:
                positions_binance[symbol] = pos
            else:
                positions_binance.pop(symbol, None)
        broadcast()

def handle_mark_price(msg):
    if msg.get("e") == "markPriceUpdate":
        symbol = msg["s"]
        mark_prices_binance[symbol] = msg["p"]
        broadcast()

# ✅ Binance 초기 스냅샷
def load_initial_positions():
    all_positions = binance_client.futures_position_information()
    for pos in all_positions:
        if float(pos.get("positionAmt", 0)) != 0:
            positions_binance[pos["symbol"]] = {
                "s": pos["symbol"],
                "pa": pos.get("positionAmt"),
                "ep": pos.get("entryPrice"),
                "up": pos.get("unRealizedProfit"),
                "ps": pos.get("positionSide"),
                "mt": pos.get("marginType"),          # ✅ 안전하게 get
                "l": pos.get("liquidationPrice"),     # ✅ 안전하게 get
            }

# ✅ Binance WebSocket 시작
def start_binance_ws():
    twm = ThreadedWebsocketManager(api_key=BINANCE_KEY, api_secret=BINANCE_SECRET)
    twm.start()
    twm.start_futures_user_socket(callback=handle_user_data)
    twm.start_symbol_mark_price_socket(symbol="BTCUSDT", callback=handle_mark_price, fast=True)
    twm.start_symbol_mark_price_socket(symbol="ETHUSDT", callback=handle_mark_price, fast=True)
    return twm

# ✅ FastAPI WebSocket 엔드포인트
@app.websocket("/ws/positions")
async def positions_ws(websocket: WebSocket):
    await websocket.accept()
    active_clients.add(websocket)
    if positions_binance or last_positions_bitget:
        broadcast()
    try:
        while True:
            await asyncio.sleep(10)
    except WebSocketDisconnect:
        active_clients.discard(websocket)

# 실행 시 초기화
load_initial_positions()
twm = start_binance_ws()