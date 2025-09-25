from fastapi import APIRouter
from binance.client import Client as BinanceClient
from pybitget import Client as BitgetClient
from pydantic import BaseModel
from typing import Optional
import os
import logging

# 기본 로거 설정
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

router = APIRouter()

# Binance 클라이언트
binance_client = BinanceClient(
    os.getenv("BINANCE_API_KEY"),
    os.getenv("BINANCE_API_SECRET")
)

# Bitget 클라이언트
bitget_client = BitgetClient(
    os.getenv("BITGET_API_KEY"),
    os.getenv("BITGET_API_SECRET"),
    passphrase=os.getenv("BITGET_API_PASS")
)

# ✅ 요청 바디 모델 정의
class OrderRequest(BaseModel):
    symbol: str
    side: str   # BUY, SELL, CLOSE_LONG, CLOSE_SHORT
    usdAmount: float
    price: Optional[float] = None
    leverage: int = 10
    marginMode: str = "isolated"


def adjust_to_step(value: float, step: float) -> float:
    """주어진 stepSize에 맞게 수량/가격을 내림 조정"""
    return (value // step) * step


# -------------------------------
# Binance 주문
# -------------------------------
@router.post("/binance/order")
async def binance_order(req: OrderRequest):
    try:
        ticker = binance_client.futures_symbol_ticker(symbol=req.symbol)
        current_price = float(ticker["price"])

        info = binance_client.futures_exchange_info()
        symbol_info = next(s for s in info["symbols"] if s["symbol"] == req.symbol)

        lot_size = next(f for f in symbol_info["filters"] if f["filterType"] == "LOT_SIZE")
        step_size = float(lot_size["stepSize"])

        price_filter = next(f for f in symbol_info["filters"] if f["filterType"] == "PRICE_FILTER")
        tick_size = float(price_filter["tickSize"])

        notional_filter = next(f for f in symbol_info["filters"] if f["filterType"] == "MIN_NOTIONAL")
        min_notional = float(notional_filter["notional"])

        raw_qty = req.usdAmount / current_price
        quantity = adjust_to_step(raw_qty, step_size)

        if quantity * current_price < min_notional:
            return {"status": "error", "message": f"주문 금액이 최소 요구치({min_notional} USDT) 미만입니다."}

        # 레버리지/마진 모드 설정
        binance_client.futures_change_leverage(symbol=req.symbol, leverage=req.leverage)
        try:
            binance_client.futures_change_margin_type(symbol=req.symbol, marginType=req.marginMode.upper())
        except Exception:
            pass

        order = None
        # -------------------------------
        # 진입 (롱/숏) → 기본 MARKET
        # -------------------------------
        if req.side in ["BUY", "SELL"]:
            # 무조건 MARKET으로 진입
            order = binance_client.futures_create_order(
                symbol=req.symbol,
                side=req.side,
                type="MARKET",
                quantity=quantity
            )

        # -------------------------------
        # CLOSE (롱/숏)
        # -------------------------------
        elif req.side == "CLOSE_LONG":
            # 현재 포지션 수량 조회
            positions = binance_client.futures_position_information(symbol=req.symbol)
            pos = next((p for p in positions if p["symbol"] == req.symbol), None)
            if pos and float(pos["positionAmt"]) > 0:
                qty = abs(float(pos["positionAmt"]))
                order = binance_client.futures_create_order(
                    symbol=req.symbol,
                    side="SELL",
                    type="MARKET",
                    quantity=qty,
                    reduceOnly=True   # 새 포지션이 열리지 않도록 안전장치
                )

        elif req.side == "CLOSE_SHORT":
            positions = binance_client.futures_position_information(symbol=req.symbol)
            pos = next((p for p in positions if p["symbol"] == req.symbol), None)
            if pos and float(pos["positionAmt"]) < 0:
                qty = abs(float(pos["positionAmt"]))
                order = binance_client.futures_create_order(
                    symbol=req.symbol,
                    side="BUY",
                    type="MARKET",
                    quantity=qty,
                    reduceOnly=True
                )


        logger.info(f"[BINANCE] 주문 성공: {req.symbol} {req.side} {quantity}개 ≈ {req.usdAmount}USDT → {order}")
        return {"status": "success", "order": order}

    except Exception as e:
        logger.error(f"[BINANCE] 주문 실패: {req.symbol} {req.side} {req.usdAmount}USDT → {e}")
        return {"status": "error", "message": str(e)}


# -------------------------------
# Bitget 주문
# -------------------------------
@router.post("/bitget/order")
async def bitget_order(req: OrderRequest):
    try:
        # 현재가 조회
        ticker = bitget_client.mix_get_market_price(symbol=req.symbol)
        current_price = float(ticker["data"]["markPrice"])

        # 심볼 정보 조회
        symbols_info = bitget_client.mix_get_symbols_info("umcbl")
        symbol_info = next(s for s in symbols_info["data"] if s["symbol"] == req.symbol)

        min_trade_num = float(symbol_info.get("minTradeNum", 0))
        price_place = int(symbol_info.get("pricePlace", 4))
        quantity_place = int(symbol_info.get("quantityPlace") or symbol_info.get("volumePlace", 0))

        # 수량 계산 (진입 시에만 사용)
        raw_size = req.usdAmount / current_price
        size = round(raw_size, quantity_place)

        if size < min_trade_num and req.side in ["BUY", "SELL"]:
            return {"status": "error", "message": f"주문 수량이 최소 요구치({min_trade_num}) 미만입니다."}

        # marginMode 보정
        margin_mode = req.marginMode.lower()
        if margin_mode == "cross":
            margin_mode = "crossed"

        # 레버리지/마진 모드 설정
        bitget_client.mix_set_margin_mode(
            symbol=req.symbol,
            productType="umcbl",
            marginCoin="USDT",
            marginMode=margin_mode
        )
        bitget_client.mix_adjust_leverage(
            symbol=req.symbol,
            marginCoin="USDT",
            leverage=str(req.leverage),
            holdSide="long" if req.side.lower() in ["buy", "close_short"] else "short"
        )

        order = None

        # -------------------------------
        # 진입 (롱/숏) → MARKET 기본
        # -------------------------------
        if req.side.upper() == "BUY":
            order = bitget_client.mix_place_order(
                symbol=req.symbol, marginCoin="USDT",
                size=str(size), side="open_long",
                orderType="market"
            )
        elif req.side.upper() == "SELL":
            order = bitget_client.mix_place_order(
                symbol=req.symbol, marginCoin="USDT",
                size=str(size), side="open_short",
                orderType="market"
            )

        # -------------------------------
        # CLOSE (롱/숏) → 포지션 조회 후 반대 주문
        # -------------------------------
        elif req.side.upper() == "CLOSE_LONG":
            pos = bitget_client.mix_get_single_position(symbol=req.symbol, marginCoin="USDT")
            qty = float(pos["data"]["total"])
            if qty > 0:
                order = bitget_client.mix_place_order(
                    symbol=req.symbol, marginCoin="USDT",
                    size=str(qty), side="close_long",
                    orderType="market", reduceOnly="true"
                )
        elif req.side.upper() == "CLOSE_SHORT":
            pos = bitget_client.mix_get_single_position(symbol=req.symbol, marginCoin="USDT")
            qty = float(pos["data"]["total"])
            if qty > 0:
                order = bitget_client.mix_place_order(
                    symbol=req.symbol, marginCoin="USDT",
                    size=str(qty), side="close_short",
                    orderType="market", reduceOnly="true"
                )

        logger.info(f"[BITGET] 주문 성공: {req.symbol} {req.side} → {order}")
        return {"status": "success", "order": order}

    except Exception as e:
        logger.error(f"[BITGET] 주문 실패: {req.symbol} {req.side} {req.usdAmount}USDT → {e}")
        return {"status": "error", "message": str(e)}