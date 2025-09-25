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
        # 청산 (롱/숏)
        # -------------------------------
        elif req.side == "CLOSE_LONG":
            order = binance_client.futures_create_order(
                symbol=req.symbol, side="SELL", type="MARKET", closePosition=True
            )
        elif req.side == "CLOSE_SHORT":
            order = binance_client.futures_create_order(
                symbol=req.symbol, side="BUY", type="MARKET", closePosition=True
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
        ticker = bitget_client.mix_get_market_price(symbol=req.symbol)
        current_price = float(ticker["data"]["markPrice"])

        symbols_info = bitget_client.mix_get_symbols_info("umcbl")
        symbol_info = next(s for s in symbols_info["data"] if s["symbol"] == req.symbol)

        min_trade_num = float(symbol_info.get("minTradeNum", 0))
        price_place = int(symbol_info.get("pricePlace", 4))
        quantity_place = int(symbol_info.get("quantityPlace") or symbol_info.get("volumePlace", 0))

        raw_size = req.usdAmount / current_price
        size = round(raw_size, quantity_place)

        if size < min_trade_num:
            return {"status": "error", "message": f"주문 수량이 최소 요구치({min_trade_num}) 미만입니다."}

        # side 매핑
        def map_side_for_bitget(side: str) -> str:
            side = side.lower()
            if side == "buy":
                return "open_long"
            elif side == "sell":
                return "open_short"
            elif side == "close_long":
                return "close_long"
            elif side == "close_short":
                return "close_short"
            return side

        bitget_side = map_side_for_bitget(req.side)

        # marginMode 보정
        margin_mode = req.marginMode.lower()

        # 레버리지/마진 모드 설정 (Binance와 동일하게)
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
            holdSide="long" if "long" in bitget_side else "short"
        )

        # 주문 생성 → 기본 MARKET
        if req.price:
            price = round(req.price, price_place)
            order = bitget_client.mix_place_order(
                symbol=req.symbol, marginCoin="USDT",
                size=str(size), side=bitget_side,
                orderType="limit", price=str(price)
            )
        else:
            order = bitget_client.mix_place_order(
                symbol=req.symbol, marginCoin="USDT",
                size=str(size), side=bitget_side,
                orderType="market"
            )

        logger.info(f"[BITGET] 주문 성공: {req.symbol} {bitget_side} {size}개 ≈ {req.usdAmount}USDT")
        return {"status": "success", "order": order}

    except Exception as e:
        logger.error(f"[BITGET] 주문 실패: {req.symbol} {req.side} {req.usdAmount}USDT → {e}")
        return {"status": "error", "message": str(e)}