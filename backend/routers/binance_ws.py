import os, asyncio, json, logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from dotenv import load_dotenv
from binance import AsyncClient
from backend.routers import unified_ws
import websockets

router = APIRouter()
active_clients = set()
loop = None  # run_coroutine_threadsafe에 사용할 이벤트 루프

# 상태
last_positions = {}        # {symbol: pos(dict)}
last_mark_prices = {}      # {symbol: markPrice(str)}
subscribed_symbols = set() # 현재 마크프라이스 스트림에 구독 중인 심볼들
symbols_changed = asyncio.Event()  # 구독 집합 변경 알림

log = logging.getLogger("binance-positions")
log.setLevel(logging.INFO)

# .env 로드
load_dotenv()
BINANCE_KEY = os.getenv("BINANCE_API_KEY")
BINANCE_SECRET = os.getenv("BINANCE_API_SECRET")
if not all([BINANCE_KEY, BINANCE_SECRET]):
    raise RuntimeError("환경변수 BINANCE_API_KEY, BINANCE_API_SECRET 를 설정하세요.")


def normalize_position(pos: dict):
    """REST 포지션 데이터를 짧은 키로 맞춤"""
    return {
        "pa": pos.get("positionAmt"),        # position amount (string, 부호로 방향)
        "ep": pos.get("entryPrice"),         # entry price (string)
        "up": pos.get("unRealizedProfit"),   # unrealized PnL (string)
        "l": pos.get("liquidationPrice"),    # liquidation price (string)
        "iw": pos.get("isolatedMargin"),     # isolated margin (string, Cross면 None)
        "mt": pos.get("marginType"),         # margin type (ISOLATED / CROSSED)
    }


def broadcast():
    """포지션 + markPrice + 실시간 UPL 합쳐서 브로드캐스트"""
    merged = []

    for symbol, pos in last_positions.items():
        mark = last_mark_prices.get(symbol)

        # 안전 변환
        try:
            size = float(pos.get("pa") or 0)
        except Exception:
            size = 0.0

        try:
            entry = float(pos.get("ep") or 0)
        except Exception:
            entry = 0.0

        upl = pos.get("up")

        # 방향
        if size > 0:
            side = "LONG"
        elif size < 0:
            side = "SHORT"
        else:
            side = "FLAT"

        # UPL 재계산
        try:
            if mark is not None and entry != 0 and size != 0:
                m = float(mark)
                upl = (m - entry) * size if size > 0 else (entry - m) * abs(size)
        except Exception as e:
            log.error(f"Binance UPL 계산 오류: {e}")

        merged.append({
            "exchange": "binance",
            "symbol": symbol,         # 예: PEPEUSDT
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

    if loop is None:
        log.warning("이벤트 루프가 설정되지 않았습니다. WebSocket 전송에 실패할 수 있습니다.")

    for ws in list(active_clients):
        try:
            asyncio.run_coroutine_threadsafe(ws.send_json(merged), loop)
        except Exception as e:
            log.error(f"웹소켓 전송 실패: {e}")

            
    try:
        unified_ws.broadcast()
    except Exception as e:
        log.error(f"통합 브로드캐스트 호출 실패: {e}")



async def refresh_positions_periodic(interval_sec: int = 3):
    """주기적으로 REST 스냅샷을 갱신해서 닫힌 포지션 제거 및 구독 집합 동기화"""
    global last_positions, last_mark_prices, subscribed_symbols

    while True:
        try:
            client = await AsyncClient.create(BINANCE_KEY, BINANCE_SECRET)

            # 전체 포지션 + 계정 정보
            all_positions = await client.futures_position_information()
            account_info = await client.futures_account()
            await client.close_connection()

            margin_map = {p["symbol"]: p.get("isolatedMargin") for p in account_info["positions"]}
            margin_type_map = {p["symbol"]: p.get("marginType") for p in account_info["positions"]}

            updated = {}

            for pos in all_positions:
                sym = pos["symbol"]  # 예: PEPEUSDT
                try:
                    amt = float(pos.get("positionAmt") or 0)
                except Exception:
                    amt = 0.0

                if amt != 0:
                    norm = normalize_position(pos)
                    norm["iw"] = margin_map.get(sym)
                    norm["mt"] = margin_type_map.get(sym)
                    updated[sym] = norm

            # 닫힌 포지션 제거
            to_remove = set(last_positions.keys()) - set(updated.keys())
            for sym in to_remove:
                last_positions.pop(sym, None)
                last_mark_prices.pop(sym, None)

            # 열린/유지 포지션 업데이트
            for sym, norm in updated.items():
                last_positions[sym] = norm

            # ✅ 구독 집합 동기화: 열린 포지션 심볼만 구독
            new_set = set(last_positions.keys())
            if new_set != subscribed_symbols:
                subscribed_symbols = new_set
                symbols_changed.set()  # 스트림 재구성 요청
                log.info(f"구독 심볼 변경: {new_set}")

            broadcast()

        except Exception as e:
            log.error(f"포지션 갱신 오류: {e}")

        await asyncio.sleep(interval_sec)


async def mark_price_stream():
    """심볼별 합친 스트림으로 마크프라이스 수신. 구독 집합 변경 시 재연결."""
    backoff = 1

    async def build_stream_url(symbols):
        # 심볼 없으면 전체 arr 스트림 사용 (유휴 상태)
        if not symbols:
            return "wss://fstream.binance.com/ws/!markPrice@arr@1s"
        streams = [f"{sym.lower()}@markPrice@1s" for sym in symbols]
        joined = "/".join(streams)
        return f"wss://fstream.binance.com/stream?streams={joined}"

    while True:
        try:
            # 현재 구독 집합 확인 및 이벤트 리셋
            current = set(subscribed_symbols)
            symbols_changed.clear()

            url = await build_stream_url(current)
            async with websockets.connect(url, ping_interval=20, ping_timeout=20) as ws:
                log.info(f"마크프라이스 수신 시작 (구독 {len(current)}개): {current or 'ALL'}")
                backoff = 1

                while True:
                    # 구독 변경 이벤트가 오면 재연결하여 재구독
                    if symbols_changed.is_set():
                        log.info("구독 변경 감지 → 스트림 재구성")
                        break

                    raw = await ws.recv()
                    data = json.loads(raw)

                    updated = False

                    # 합친 스트림 형태: dict(payload.data)
                    if isinstance(data, dict) and "data" in data:
                        item = data["data"]
                        if item.get("e") == "markPriceUpdate":
                            sym = item.get("s")
                            if sym in last_positions:
                                last_mark_prices[sym] = item.get("p")
                                updated = True

                    # arr 스트림: list의 각 item
                    elif isinstance(data, list):
                        for item in data:
                            if item.get("e") == "markPriceUpdate":
                                sym = item.get("s")
                                if sym in last_positions:
                                    last_mark_prices[sym] = item.get("p")
                                    updated = True

                    if updated:
                        broadcast()

        except Exception as e:
            log.error(f"markPrice 스트림 오류, 재시도: {e}")
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30)


async def binance_start():
    """백그라운드 태스크를 올려 Bitget 스타일로 동작"""
    # 포지션 리프레시 + 스트림 병행
    asyncio.create_task(refresh_positions_periodic(interval_sec=3))
    asyncio.create_task(mark_price_stream())


@router.websocket("/ws/binance")
async def positions_ws(websocket: WebSocket):
    global loop
    await websocket.accept()
    active_clients.add(websocket)
    loop = asyncio.get_running_loop()
    log.info(f"🌐 Binance 클라이언트 연결됨: {websocket.client}")

    # 최초 상태 푸시
    broadcast()

    try:
        while True:
            await asyncio.sleep(10)
    except WebSocketDisconnect:
        log.info(f"🔌 Binance 클라이언트 연결 해제: {websocket.client}")
        active_clients.discard(websocket)