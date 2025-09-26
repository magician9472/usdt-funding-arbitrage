import os, asyncio, json, logging
from typing import Set
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from dotenv import load_dotenv
from binance import AsyncClient
import websockets

router = APIRouter()
active_clients: Set[WebSocket] = set()

# 공유 상태 + 락
last_positions = {}        # {symbol: pos}
last_mark_prices = {}      # {symbol: markPrice}
state_lock = asyncio.Lock()

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
        "pa": pos.get("positionAmt"),        # position amount (string)
        "ep": pos.get("entryPrice"),         # entry price
        "up": pos.get("unRealizedProfit"),   # unrealized PnL
        "l": pos.get("liquidationPrice"),    # liquidation price
        "iw": pos.get("isolatedMargin"),     # isolated margin
        "mt": pos.get("marginType"),         # margin type (ISOLATED / CROSSED)
    }


async def broadcast():
    """현재 포지션 + markPrice + UPL 계산해서 모든 클라이언트에 전송"""
    async with state_lock:
        merged = []
        for symbol, pos in last_positions.items():
            mark = last_mark_prices.get(symbol)

            # 안전한 변환
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

        # 끊어진 클라이언트 제거하면서 전송
        dead = []
        for ws in active_clients.copy():
            try:
                await ws.send_json(merged)
            except Exception:
                dead.append(ws)
        for ws in dead:
            active_clients.discard(ws)


async def refresh_positions(interval_sec: int = 5):
    """주기적으로 REST 스냅샷을 갱신하고 닫힌 포지션 제거"""
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

            async with state_lock:
                # 열린 포지션만 유지, 닫힌 것은 제거
                last_positions.clear()
                last_positions.update(updated)

            await broadcast()

        except Exception as e:
            log.error(f"포지션 갱신 오류: {e}")

        await asyncio.sleep(interval_sec)


async def mark_price_stream():
    """Binance markPrice 실시간 업데이트 (자동 재연결)"""
    url_mark = "wss://fstream.binance.com/ws/!markPrice@arr@1s"
    backoff = 1
    while True:
        try:
            async with websockets.connect(url_mark, ping_interval=20, ping_timeout=20) as ws:
                log.info("실시간 markPrice 수신 시작")
                backoff = 1  # 연결 성공 시 백오프 리셋
                while True:
                    raw = await ws.recv()
                    data = json.loads(raw)
                    if isinstance(data, list):
                        updated = False
                        async with state_lock:
                            for item in data:
                                if item.get("e") != "markPriceUpdate":
                                    continue
                                sym = item.get("s")
                                # 열린 포지션만 추적
                                if sym in last_positions:
                                    last_mark_prices[sym] = item["p"]
                                    updated = True
                        if updated:
                            await broadcast()
        except Exception as e:
            log.error(f"markPrice 스트림 오류, 재시도 예정: {e}")
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30)  # 최대 30초 백오프


@router.websocket("/ws/binance")
async def positions_ws(websocket: WebSocket):
    await websocket.accept()
    active_clients.add(websocket)
    log.info(f"🌐 Binance 클라이언트 연결됨: {websocket.client}")

    # 현재 상태 즉시 푸시
    await broadcast()

    try:
        while True:
            # 클라이언트 핑 대용 (유휴 루프)
            await asyncio.sleep(10)
    except WebSocketDisconnect:
        log.info(f"🔌 Binance 클라이언트 연결 해제: {websocket.client}")
        active_clients.discard(websocket)
    except Exception:
        active_clients.discard(websocket)