import asyncio, httpx
from datetime import datetime
from zoneinfo import ZoneInfo
from backend.database import SessionLocal
from backend.models import FundingRate
from sqlalchemy.future import select

# Binance & Bitget API
BINANCE_URL = "https://fapi.binance.com/fapi/v1/premiumIndex"
BITGET_CONTRACTS_URL = "https://api.bitget.com/api/v2/mix/market/contracts"
BITGET_FUNDING_URL   = "https://api.bitget.com/api/v2/mix/market/current-fund-rate"


# -----------------------------
# Binance: fundingRate + nextFundingTime
# -----------------------------
async def fetch_and_save_binance():
    kst = ZoneInfo("Asia/Seoul")
    now = datetime.now(kst)

    async with httpx.AsyncClient() as client:
        res = await client.get(BINANCE_URL)
        binance_data = res.json()

    async with SessionLocal() as db:
        for d in binance_data:
            if d["symbol"].endswith("USDT"):
                nft = datetime.fromtimestamp(int(d["nextFundingTime"]) // 1000, tz=kst)

                existing = await db.execute(
                    select(FundingRate).where(
                        (FundingRate.symbol == d["symbol"]) &
                        (FundingRate.exchange == "Binance")
                    )
                )
                row = existing.scalars().first()

                if row:
                    row.funding_rate = float(d["lastFundingRate"])
                    row.next_funding_time = nft
                    row.timestamp = now
                else:
                    fr = FundingRate(
                        symbol=d["symbol"],
                        exchange="Binance",
                        funding_rate=float(d["lastFundingRate"]),
                        next_funding_time=nft,
                        timestamp=now
                    )
                    db.add(fr)

        await db.commit()


# -----------------------------
# Bitget: fundingRate + nextFundingTime (contracts + current-fund-rate)
# -----------------------------
async def fetch_and_save_bitget():
    """매 분마다 실행: contracts 기준으로 실제 거래 가능한 심볼만 저장"""
    kst = ZoneInfo("Asia/Seoul")
    now = datetime.now(kst)

    async with httpx.AsyncClient() as client:
        # 1) contracts: 실제 거래 가능한 심볼 목록
        res_contracts = await client.get(
            BITGET_CONTRACTS_URL,
            params={"productType": "USDT-FUTURES"}
        )
        contracts_data = res_contracts.json().get("data", [])
        valid_symbols = {c["symbol"] for c in contracts_data}

        # 2) current-fund-rate: 펀딩레이트 + nextFundingTime
        res_funding = await client.get(
            BITGET_FUNDING_URL,
            params={"productType": "USDT-FUTURES"}
        )
        funding_data = res_funding.json().get("data", [])

        async with SessionLocal() as db:
            for d in funding_data:
                symbol = d["symbol"]
                if symbol not in valid_symbols:
                    # contracts에 없는 심볼은 스킵
                    continue

                funding_rate = float(d.get("fundingRate") or 0)

                # nextUpdate → 다음 펀딩 시간
                next_update_ms = d.get("nextUpdate")
                nft = None
                if next_update_ms:
                    nft = datetime.fromtimestamp(int(next_update_ms) / 1000, tz=kst)

                existing = await db.execute(
                    select(FundingRate).where(
                        (FundingRate.symbol == symbol) &
                        (FundingRate.exchange == "Bitget")
                    )
                )
                row = existing.scalars().first()

                if row:
                    row.funding_rate = funding_rate
                    row.next_funding_time = nft
                    row.timestamp = now
                else:
                    fr = FundingRate(
                        symbol=symbol,
                        exchange="Bitget",
                        funding_rate=funding_rate,
                        next_funding_time=nft,
                        timestamp=now
                    )
                    db.add(fr)

            await db.commit()


# -----------------------------
# Update Loop (매 분 55초에 실행)
# -----------------------------
async def update_loop():
    try:
        await fetch_and_save_binance()
        await fetch_and_save_bitget()
        print("✅ Initial funding data updated")
    except Exception as e:
        print("❌ Initial fetch error:", e)

    while True:
        now = datetime.now(ZoneInfo("Asia/Seoul"))
        next_minute = (now.minute + 1) % 60
        next_hour = now.hour + (1 if next_minute == 0 else 0)
        target = now.replace(hour=next_hour % 24, minute=next_minute, second=55, microsecond=0)

        if now.second < 55:
            target = now.replace(second=55, microsecond=0)

        sleep_seconds = (target - now).total_seconds()
        await asyncio.sleep(sleep_seconds)

        try:
            await fetch_and_save_binance()
            await fetch_and_save_bitget()
            print(f"✅ Funding data updated at {datetime.now(ZoneInfo('Asia/Seoul'))}")
        except Exception as e:
            print("❌ Error:", e)