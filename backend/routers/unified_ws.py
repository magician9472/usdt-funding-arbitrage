import asyncio
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

# Binance / Bitget 모듈 import
from backend.routers import binance_ws, ws_router as bitget_ws

router = APIRouter()
active_clients = set()
loop = None

log = logging.getLogger("unified-positions")


def build_unified_positions():
    """Binance + Bitget 포지션을 공통 포맷으로 합쳐서 반환"""
    merged = []

    # ✅ Binance 포맷
    for symbol, pos in binance_ws.last_positions.items():
        mark = binance_ws.last_mark_prices.get(symbol)
        try:
            size = float(pos.get("pa") or 0)
        except Exception:
            size = 0.0
        try:
            entry = float(pos.get("ep") or 0)
        except Exception:
            entry = 0.0

        if size > 0:
            side = "LONG"
        elif size < 0:
            side = "SHORT"
        else:
            side = "FLAT"

        upl = pos.get("up")
        try:
            if mark and entry and size:
                m = float(mark)
                upl = (m - entry) * size if size > 0 else (entry - m) * abs(size)
        except Exception:
            pass

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
        })

    # ✅ Bitget 포맷
    for (instId, side), pos in bitget_ws.last_positions.items():
        base_symbol = bitget_ws.pos_to_base.get((instId, side))
        mark_price = bitget_ws.last_mark_prices.get(base_symbol)
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
        except Exception:
            pass

        merged.append({
            "exchange": "bitget",
            "symbol": base_symbol,
            "side": side.upper(),
            "size": pos.get("total"),
            "upl": upl if upl is not None else pos.get("upl"),
            "entryPrice": pos.get("averageOpenPrice"),
            "markPrice": mark_price,
            "liqPrice": pos.get("liqPx"),
            "margin": pos.get("margin"),
        })

    if not merged:
        merged = [{"msg": "현재 열린 포지션이 없습니다."}]
    return merged


def broadcast():
    """모든 클라이언트에 통합 포지션 전송"""
    merged = build_unified_positions()
    for ws in list(active_clients):
        try:
            asyncio.run_coroutine_threadsafe(ws.send_json(merged), loop)
        except Exception:
            active_clients.discard(ws)


@router.websocket("/ws/positions/all")
async def unified_positions_ws(websocket: WebSocket):
    global loop
    await websocket.accept()
    active_clients.add(websocket)
    loop = asyncio.get_running_loop()
    log.info(f"🌐 통합 클라이언트 연결됨: {websocket.client}")

    # 최초 상태 푸시
    merged = build_unified_positions()
    await websocket.send_json(merged)

    try:
        while True:
            await asyncio.sleep(10)
    except WebSocketDisconnect:
        log.info(f"🔌 통합 클라이언트 해제: {websocket.client}")
        active_clients.discard(websocket)