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

        notional_filter = next(f for f in symbol_info["filters"] if f["filterType"] == "MIN_NOTIONAL")
        min_notional = float(notional_filter["notional"])

        raw_qty = req.usdAmount / current_price
        quantity = adjust_to_step(raw_qty, step_size)

        if quantity * current_price < min_notional and req.side in ["BUY", "SELL"]:
            return {"status": "error", "message": f"주문 금액이 최소 요구치({min_notional} USDT) 미만입니다."}

        # 레버리지/마진 모드 설정
        binance_client.futures_change_leverage(symbol=req.symbol, leverage=req.leverage)
        try:
            binance_client.futures_change_margin_type(symbol=req.symbol, marginType=req.marginMode.upper())
        except Exception:
            pass

        order = None

        # -------------------------------
        # 진입 (롱/숏) → MARKET
        # -------------------------------
        if req.side == "BUY":
            order = binance_client.futures_create_order(
                symbol=req.symbol, side="BUY", type="MARKET", quantity=quantity
            )
        elif req.side == "SELL":
            order = binance_client.futures_create_order(
                symbol=req.symbol, side="SELL", type="MARKET", quantity=quantity
            )

        # -------------------------------
        # 청산 (롱/숏) → 포지션 조회 후 반대 주문
        # -------------------------------
        elif req.side == "CLOSE_LONG":
            positions = binance_client.futures_position_information(symbol=req.symbol)
            pos = next((p for p in positions if p["symbol"] == req.symbol), None)
            if pos and float(pos["positionAmt"]) > 0:
                qty = abs(float(pos["positionAmt"]))
                order = binance_client.futures_create_order(
                    symbol=req.symbol, side="SELL", type="MARKET",
                    quantity=qty, reduceOnly=True
                )

        elif req.side == "CLOSE_SHORT":
            positions = binance_client.futures_position_information(symbol=req.symbol)
            pos = next((p for p in positions if p["symbol"] == req.symbol), None)
            if pos and float(pos["positionAmt"]) < 0:
                qty = abs(float(pos["positionAmt"]))
                order = binance_client.futures_create_order(
                    symbol=req.symbol, side="BUY", type="MARKET",
                    quantity=qty, reduceOnly=True
                )

        logger.info(f"[BINANCE] 주문 성공: {req.symbol} {req.side} → {order}")
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
        quantity_place = int(symbol_info.get("quantityPlace") or symbol_info.get("volumePlace", 0))

        raw_size = req.usdAmount / current_price
        size = round(raw_size, quantity_place)

        if size < min_trade_num and req.side in ["BUY", "SELL"]:
            return {"status": "error", "message": f"주문 수량이 최소 요구치({min_trade_num}) 미만입니다."}

        # 마진 모드 설정 (포지션 없을 때만 가능)
        resp = bitget_client.mix_adjust_margintype(
            symbol=req.symbol,
            marginCoin="USDT",
            marginMode="fixed"
        )
        if resp.get("code") != "00000":
            logger.error(f"[BITGET] 마진 모드 변경 실패: {resp}")
        else:
            logger.info(f"[BITGET] 마진 모드 변경 성공: {req.symbol} → {req.marginMode.lower()}")

        # 레버리지 설정
        bitget_client.mix_adjust_leverage(
            symbol=req.symbol,
            marginCoin="USDT",
            leverage=str(req.leverage),
            holdSide="long" if req.side.upper() in ["BUY", "CLOSE_SHORT"] else "short"
        )

        order = None

        # -------------------------------
        # 진입 (롱/숏) → MARKET
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
        # 청산 (롱/숏) → 포지션 조회 후 반대 주문
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