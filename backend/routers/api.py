from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from backend.models import FundingRate
from backend.database import get_db

router = APIRouter()

@router.get("/api/binance/latest")
async def get_binance_latest(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(FundingRate).where(FundingRate.exchange == "Binance"))
    rows = result.scalars().all()
    return [
        {
            "symbol": r.symbol,
            "funding_rate": r.funding_rate,
            "next_funding_time": r.next_funding_time.isoformat() if r.next_funding_time else None
        }
        for r in rows
    ]

@router.get("/api/bitget/latest")
async def get_bitget_latest(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(FundingRate).where(FundingRate.exchange == "Bitget"))
    rows = result.scalars().all()
    return [
        {
            "symbol": r.symbol,
            "funding_rate": r.funding_rate,
            "next_funding_time": r.next_funding_time.isoformat() if r.next_funding_time else None
        }
        for r in rows
    ]

@router.get("/api/gap")
async def get_gap(db: AsyncSession = Depends(get_db)):
    binance_rows = {r.symbol: r for r in (await db.execute(
        select(FundingRate).where(FundingRate.exchange == "Binance")
    )).scalars().all()}

    bitget_rows = {r.symbol: r for r in (await db.execute(
        select(FundingRate).where(FundingRate.exchange == "Bitget")
    )).scalars().all()}

    gaps = []
    for symbol, b_row in binance_rows.items():
        if symbol in bitget_rows:
            g_row = bitget_rows[symbol]
            gap = b_row.funding_rate - g_row.funding_rate
            gaps.append({
                "symbol": symbol,
                "binance_rate": b_row.funding_rate,
                "bitget_rate": g_row.funding_rate,
                "gap": gap,
                "next_funding_time": b_row.next_funding_time.isoformat() if b_row.next_funding_time else None
            })
    return gaps