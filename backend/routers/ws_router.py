import os, json, asyncio, logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from dotenv import load_dotenv
from pybitget.stream import BitgetWsClient, handel_error, SubscribeReq

router = APIRouter()
active_clients = set()
loop = None
last_positions = {}         # {(instId, side): pos}
last_mark_prices = {}
pos_to_base = {}            # (instId, side) → ticker 심볼 매핑
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
    """포지션 + markPrice + 실시간 UPL 합쳐서 브로드캐스트"""
    merged = []
    for (pos_symbol, side), pos in last_positions.items():
        base_symbol = pos_to_base.get((pos_symbol, side))
        mark_price = last_mark_prices.get(base_symbol)

        # upl 실시간 계산
        upl = None
        try:
            entry = float(pos.get("averageOpenPrice", 0))
            size = float(pos.get("total", 0))
            if mark_price and entry and size:
                mark = float(mark_price)
                if side == "long":
                    upl = (mark - entry) * size
                elif side == "short":
                    upl = (entry - mark) * size
        except Exception as e:
            log.error(f"UPL 계산 오류: {e}")

        merged.append({
            "symbol": pos_symbol,   # 예: PEPEUSDT_UMCBL
            "side": side,
            "size": pos.get("total"),
            "upl": upl if upl is not None else pos.get("upl"),
            "entryPrice": pos.get("averageOpenPrice"),
            "markPrice": mark_price,
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
            current_keys = set()
            for pos in payload:
                instId = pos["instId"]              # 예: "PEPEUSDT_UMCBL"
                base_symbol = instId.split("_")[0]  # "PEPEUSDT"
                side = pos["holdSide"]              # "long" 또는 "short"

                key = (instId, side)
                last_positions[key] = pos
                pos_to_base[key] = base_symbol
                current_keys.add(key)

                # 새 심볼이면 ticker 채널 구독
                if base_symbol not in subscribed_symbols:
                    bitget_ws.subscribe(
                        [SubscribeReq("mc", "ticker", base_symbol)], on_message
                    )
                    subscribed_symbols.add(base_symbol)

            # 사라진 포지션 제거
            removed = {k for k in list(last_positions) if k not in current_keys}
            for key in removed:
                base_symbol = pos_to_base.pop(key, None)
                last_positions.pop(key, None)
                # ticker 구독 해제는 심볼 단위로만
                if base_symbol and base_symbol in subscribed_symbols:
                    # 다른 방향 포지션이 남아있으면 유지
                    still_has = any(bs == base_symbol for bs in pos_to_base.values())
                    if not still_has:
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