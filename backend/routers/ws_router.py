import os, asyncio, json, logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from dotenv import load_dotenv
from binance import AsyncClient
import websockets

router = APIRouter()
active_clients = set()
loop = None  # ✅ run_coroutine_threadsafe에 사용할 이벤트 루프

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
        "pa": pos.get("positionAmt"),        # position amount (string)
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

        # positionAmt → float 변환 (부호 유지)
        try:
            size = float(pos.get("pa") or 0)
        except Exception:
            size = 0.0

        try:
            entry = float(pos.get("ep") or 0)
        except Exception:
            entry = 0.0

        upl = pos.get("up")

        # ✅ 방향 계산 (부호 기준)
        if size > 0:
            side = "LONG"
        elif size < 0:
            side = "SHORT"
        else:
            side = "FLAT"

        # ✅ UPL 재계산 (markPrice 기반)
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

    # ✅ 이벤트 루프 설정 확인
    if loop is None:
        log.warning("이벤트 루프가 설정되지 않았습니다. WebSocket에 전송하지 못할 수 있습니다.")

    for ws in list(active_clients):
        try:
            asyncio.run_coroutine_threadsafe(ws.send_json(merged), loop)
        except Exception as e:
            log.error(f"웹소켓 전송 실패: {e}")


async def binance_worker():
    """Binance 포지션 + markPrice 실시간 업데이트"""
    global loop
    loop = asyncio.get_running_loop()  # ✅ 현재 이벤트 루프 저장

    client = await AsyncClient.create(BINANCE_KEY, BINANCE_SECRET)

    # 스냅샷: 모든 열린 포지션 가져오기
    all_positions = await client.futures_position_information()
    account_info = await client.futures_account()
    await client.close_connection()

    margin_map = {p["symbol"]: p.get("isolatedMargin") for p in account_info["positions"]}
    margin_type_map = {p["symbol"]: p.get("marginType") for p in account_info["positions"]}

    # 열린 포지션만 저장
    for pos in all_positions:
        try:
            amt = float(pos.get("positionAmt") or 0)
        except Exception:
            amt = 0.0

        if amt != 0:
            symbol = pos["symbol"]
            norm = normalize_position(pos)
            norm["iw"] = margin_map.get(symbol)
            norm["mt"] = margin_type_map.get(symbol)
            last_positions[symbol] = norm

    if not last_positions:
        log.info("열린 포지션이 없습니다.")
        # ✅ 그래도 리프레시 태스크는 계속 돌려서 이후에 열리면 반영되도록
        asyncio.create_task(refresh_positions_periodic())
        return

    # ✅ 주기적 스냅샷 갱신 태스크 시작 (닫힌 포지션 자동 제거)
    asyncio.create_task(refresh_positions_periodic())

    # ✅ markPrice 스트림 (모든 심볼 수신)
    url_mark = "wss://fstream.binance.com/ws/!markPrice@arr@1s"
    async with websockets.connect(url_mark, ping_interval=20, ping_timeout=20) as ws:
        log.info(f"실시간 markPrice 수신 시작 (심볼 수: {len(last_positions)})")
        while True:
            raw = await ws.recv()
            data = json.loads(raw)
            if isinstance(data, list):
                for item in data:
                    sym = item.get("s")
                    if item.get("e") == "markPriceUpdate" and sym in last_positions:
                        last_mark_prices[sym] = item["p"]
                broadcast()


async def refresh_positions_periodic(interval_sec: int = 5):
    """✅ 주기적으로 REST 스냅샷을 갱신해서 닫힌 포지션 제거"""
    global last_positions, last_mark_prices
    while True:
        try:
            client = await AsyncClient.create(BINANCE_KEY, BINANCE_SECRET)
            all_positions = await client.futures_position_information()
            account_info = await client.futures_account()
            await client.close_connection()

            margin_map = {p["symbol"]: p.get("isolatedMargin") for p in account_info["positions"]}
            margin_type_map = {p["symbol"]: p.get("marginType") for p in account_info["positions"]}

            # 새로 열린/유지된 포지션만 담을 임시 맵
            updated = {}

            for pos in all_positions:
                symbol = pos["symbol"]
                try:
                    amt = float(pos.get("positionAmt") or 0)
                except Exception:
                    amt = 0.0

                if amt != 0:
                    norm = normalize_position(pos)
                    norm["iw"] = margin_map.get(symbol)
                    norm["mt"] = margin_type_map.get(symbol)
                    updated[symbol] = norm

            # ✅ 닫힌 포지션 제거 + 상태 업데이트
            # 삭제 대상: 기존에는 있었는데 updated에는 없는 심볼
            to_remove = set(last_positions.keys()) - set(updated.keys())
            for sym in to_remove:
                last_positions.pop(sym, None)
                last_mark_prices.pop(sym, None)  # 마크프라이스도 같이 제거

            # 유지/추가 대상 업데이트
            for sym, norm in updated.items():
                last_positions[sym] = norm

            broadcast()

        except Exception as e:
            log.error(f"포지션 갱신 오류: {e}")

        await asyncio.sleep(interval_sec)


@router.websocket("/ws/binance")
async def positions_ws(websocket: WebSocket):
    global loop
    await websocket.accept()
    active_clients.add(websocket)
    loop = asyncio.get_running_loop()  # ✅ 웹소켓 연결 시에도 루프 설정 보강
    log.info(f"🌐 Binance 클라이언트 연결됨: {websocket.client}")

    if last_positions:
        broadcast()

    try:
        while True:
            await asyncio.sleep(10)
    except WebSocketDisconnect:
        log.info(f"🔌 Binance 클라이언트 연결 해제: {websocket.client}")
        active_clients.discard(websocket)