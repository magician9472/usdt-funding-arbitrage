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
    side: str
    usdAmount: float
    price: Optional[float] = None
    leverage: int = 10
    marginMode: str = "cross"
    stopLoss: Optional[float] = None


def adjust_to_step(value: float, step: float) -> float:
    """주어진 stepSize에 맞게 수량/가격을 내림 조정"""
    return (value // step) * step


# -------------------------
# Binance 주문
# -------------------------
@router.post("/binance/order")
async def binance_order(req: OrderRequest):
    try:
        ticker = binance_client.futures_symbol_ticker(symbol=req.symbol)
        current_price = float(ticker["price"])

        # 심볼 정보 조회
        info = binance_client.futures_exchange_info()
        symbol_info = next(s for s in info["symbols"] if s["symbol"] == req.symbol)

        lot_size = next(f for f in symbol_info["filters"] if f["filterType"] == "LOT_SIZE")
        step_size = float(lot_size["stepSize"])

        price_filter = next(f for f in symbol_info["filters"] if f["filterType"] == "PRICE_FILTER")
        tick_size = float(price_filter["tickSize"])

        notional_filter = next(f for f in symbol_info["filters"] if f["filterType"] == "MIN_NOTIONAL")
        min_notional = float(notional_filter["notional"])

        # 수량 계산
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

        # 주문 생성
        if req.price:
            price = adjust_to_step(req.price, tick_size)
            order = binance_client.futures_create_order(
                symbol=req.symbol, side=req.side, type="LIMIT",
                timeInForce="GTC", quantity=quantity, price=price
            )
        else:
            order = binance_client.futures_create_order(
                symbol=req.symbol, side=req.side, type="MARKET", quantity=quantity
            )

        # 스탑로스
        stop_order = None
        if req.stopLoss:
            stop_price = adjust_to_step(req.stopLoss, tick_size)
            stop_order = binance_client.futures_create_order(
                symbol=req.symbol,
                side="SELL" if req.side == "BUY" else "BUY",
                type="STOP_MARKET",
                stopPrice=stop_price,
                closePosition=True
            )

        logger.info(f"[BINANCE] 주문 성공: {req.symbol} {req.side} {quantity}개 ≈ {req.usdAmount}USDT → {order}")
        return {"status": "success", "order": order, "stopLoss": stop_order}

    except Exception as e:
        logger.error(f"[BINANCE] 주문 실패: {req.symbol} {req.side} {req.usdAmount}USDT → {e}")
        return {"status": "error", "message": str(e)}


# -------------------------
# Bitget 주문
# -------------------------
@router.post("/bitget/order")
async def bitget_order(req: OrderRequest):
    try:
        ticker = bitget_client.mix_get_market_price(symbol=req.symbol)
        current_price = float(ticker["data"]["markPrice"])

        # 심볼 정보 조회 (mix_get_symbols_info 사용)
        symbols_info = bitget_client.mix_get_symbols_info("umcbl")
        symbol_info = next(s for s in symbols_info["data"] if s["symbol"] == req.symbol)

        # 안전하게 필드 조회
        min_trade_num = float(symbol_info.get("minTradeNum", 0))
        price_place = int(symbol_info.get("pricePlace", 4))
        quantity_place = int(symbol_info.get("quantityPlace") or symbol_info.get("volumePlace", 0))

        # 수량 계산
        raw_size = req.usdAmount / current_price
        size = round(raw_size, quantity_place)

        if size < min_trade_num:
            return {"status": "error", "message": f"주문 수량이 최소 요구치({min_trade_num}) 미만입니다."}

        # 레버리지/마진 모드 설정
        bitget_client.mix_adjust_leverage(
            symbol=req.symbol,
            marginCoin="USDT",
            leverage=str(req.leverage),
            holdSide="long" if "long" in req.side else "short"
        )
        bitget_client.mix_adjust_margintype(
            symbol=req.symbol,
            marginCoin="USDT",
            marginMode=req.marginMode.lower()  # "crossed" 또는 "isolated"
        )

        # 주문 생성
        if req.price:
            price = round(req.price, price_place)
            order = bitget_client.mix_place_order(
                symbol=req.symbol, marginCoin="USDT",
                size=str(size), side=req.side, orderType="limit", price=str(price)
            )
        else:
            order = bitget_client.mix_place_order(
                symbol=req.symbol, marginCoin="USDT",
                size=str(size), side=req.side, orderType="market"
            )

        # 스탑로스
        stop_order = None
        if req.stopLoss:
            stop_price = round(req.stopLoss, price_place)
            stop_order = bitget_client.mix_place_plan_order(
                symbol=req.symbol, marginCoin="USDT", size=str(size),
                side="close_long" if req.side == "open_long" else "close_short",
                orderType="market", triggerPrice=str(stop_price),
                triggerType="fill_price"
            )

        logger.info(f"[BITGET] 주문 성공: {req.symbol} {req.side} {size}개 ≈ {req.usdAmount}USDT → {order}")
        return {"status": "success", "order": order, "stopLoss": stop_order}

    except Exception as e:
        logger.error(f"[BITGET] 주문 실패: {req.symbol} {req.side} {req.usdAmount}USDT → {e}")
        return {"status": "error", "message": str(e)}
