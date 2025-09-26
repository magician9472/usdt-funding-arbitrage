import os, json, asyncio, logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from dotenv import load_dotenv
from pybitget.stream import BitgetWsClient, handel_error, SubscribeReq

router = APIRouter()
active_clients = set()
loop = None
last_positions = {}
last_mark_prices = {}
pos_to_base = {}            # 포지션 심볼 → ticker 심볼 매핑
subscribed_symbols = set()  # ticker 채널에 구독한 심볼(PEPEUSDT 등)

log = logging.getLogger("positions-ticker")

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
    """포지션 + markPrice 합쳐서 브로드캐스트"""
    merged = []
    for pos_symbol, pos in last_positions.items():
        base_symbol = pos_to_base.get(pos_symbol)  # 매핑된 심볼
        merged.append({
            "symbol": pos_symbol,  # 예: PEPEUSDT_UMCBL
            "side": pos.get("holdSide"),
            "size": pos.get("total"),
            "upl": pos.get("upl"),
            "entryPrice": pos.get("averageOpenPrice"),
            "markPrice": last_mark_prices.get(base_symbol),  # ticker 채널에서 받은 markPrice
            "liqPrice": pos.get("liqPx"),
            "margin": pos.get("margin"),
        })

    if not merged:
        merged = {"msg": "현재 열린 포지션이 없습니다."}

    for ws in list(active_clients):
        asyncio.run_coroutine_threadsafe(ws.send_json(merged), loop)

def on_message(message: str):
    global last_positions, last_mark_prices, subscribed_symbols, pos_to_base
    try:
        data = json.loads(message)
        arg = data.get("arg", {})
        channel = arg.get("channel")
        payload = data.get("data", [])

        # ✅ 포지션 채널
        if channel == "positions":
            current_symbols = set()
            last_positions = {}
            for pos in payload:
                instId = pos["instId"]              # 예: "PEPEUSDT_UMCBL"
                base_symbol = instId.split("_")[0]  # "PEPEUSDT"

                last_positions[instId] = pos
                pos_to_base[instId] = base_symbol   # 매핑 저장
                current_symbols.add(instId)

                # 새 심볼이면 ticker 채널 구독
                if base_symbol not in subscribed_symbols:
                    bitget_ws.subscribe(
                        [SubscribeReq("mc", "ticker", base_symbol)], on_message
                    )
                    subscribed_symbols.add(base_symbol)

            # 포지션이 사라진 심볼은 ticker 구독 해제
            removed = {pos_to_base[s] for s in pos_to_base if s not in current_symbols}
            for base_symbol in removed:
                if base_symbol in subscribed_symbols:
                    bitget_ws.unsubscribe(
                        [SubscribeReq("mc", "ticker", base_symbol)], on_message
                    )
                    subscribed_symbols.remove(base_symbol)
                    last_mark_prices.pop(base_symbol, None)

            broadcast()

        # ✅ ticker 채널 (markPrice 포함)
        elif channel == "ticker":
            for t in payload:
                instId = t["instId"]  # 예: "PEPEUSDT"
                last_mark_prices[instId] = t.get("markPrice")
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