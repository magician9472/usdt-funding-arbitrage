# routers/order_api.py
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


# Binance 주문
@router.post("/binance/order")
async def binance_order(req: OrderRequest):
    try:
        ticker = binance_client.futures_symbol_ticker(symbol=req.symbol)
        current_price = float(ticker["price"])
        quantity = round(req.usdAmount / current_price, 4)

        binance_client.futures_change_leverage(symbol=req.symbol, leverage=req.leverage)
        try:
            binance_client.futures_change_margin_type(symbol=req.symbol, marginType=req.marginMode.upper())
        except Exception:
            pass

        if req.price:
            order = binance_client.futures_create_order(
                symbol=req.symbol, side=req.side, type="LIMIT",
                timeInForce="GTC", quantity=quantity, price=req.price
            )
        else:
            order = binance_client.futures_create_order(
                symbol=req.symbol, side=req.side, type="MARKET", quantity=quantity
            )

        stop_order = None
        if req.stopLoss:
            stop_order = binance_client.futures_create_order(
                symbol=req.symbol,
                side="SELL" if req.side == "BUY" else "BUY",
                type="STOP_MARKET",
                stopPrice=req.stopLoss,
                closePosition=True
            )

        logger.info(f"[BINANCE] 주문 성공: {req.symbol} {req.side} {req.usdAmount}USDT → {order}")
        return {"status": "success", "order": order, "stopLoss": stop_order}
    except Exception as e:
        logger.error(f"[BINANCE] 주문 실패: {req.symbol} {req.side} {req.usdAmount}USDT → {e}")
        return {"status": "error", "message": str(e)}


# Bitget 주문
@router.post("/bitget/order")
async def bitget_order(req: OrderRequest):
    try:
        ticker = bitget_client.mix_get_market_price(symbol=req.symbol)
        current_price = float(ticker["data"]["markPrice"])
        size = str(round(req.usdAmount / current_price, 4))

        bitget_client.mix_set_leverage(
            symbol=req.symbol, marginCoin="USDT",
            leverage=str(req.leverage),
            holdSide="long" if "long" in req.side else "short"
        )
        bitget_client.mix_set_margin_mode(
            symbol=req.symbol, marginCoin="USDT", marginMode=req.marginMode.upper()
        )

        if req.price:
            order = bitget_client.mix_place_order(
                symbol=req.symbol, marginCoin="USDT",
                size=size, side=req.side, orderType="limit", price=str(req.price)
            )
        else:
            order = bitget_client.mix_place_order(
                symbol=req.symbol, marginCoin="USDT",
                size=size, side=req.side, orderType="market"
            )

        stop_order = None
        if req.stopLoss:
            stop_order = bitget_client.mix_place_plan_order(
                symbol=req.symbol, marginCoin="USDT", size=size,
                side="close_long" if req.side == "open_long" else "close_short",
                orderType="market", triggerPrice=str(req.stopLoss),
                triggerType="fill_price"
            )

        logger.info(f"[BITGET] 주문 성공: {req.symbol} {req.side} {req.usdAmount}USDT → {order}")
        return {"status": "success", "order": order, "stopLoss": stop_order}
    except Exception as e:
        logger.error(f"[BITGET] 주문 실패: {req.symbol} {req.side} {req.usdAmount}USDT → {e}")
        return {"status": "error", "message": str(e)}