import asyncio, httpx
from datetime import datetime
from zoneinfo import ZoneInfo
from database import SessionLocal
from models import FundingRate
from sqlalchemy.future import select

# Binance & Bitget API
BINANCE_URL = "https://fapi.binance.com/fapi/v1/premiumIndex"
BITGET_TICKERS_URL = "https://api.bitget.com/api/v2/mix/market/tickers"
BITGET_TIME_URL = "https://api.bitget.com/api/v2/mix/market/funding-time"


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
# Bitget: fundingRate (tickers)
# -----------------------------
async def fetch_and_save_bitget_rates():
    """매 분마다 실행: fundingRate만 갱신"""
    kst = ZoneInfo("Asia/Seoul")
    now = datetime.now(kst)

    async with httpx.AsyncClient() as client:
        res = await client.get(BITGET_TICKERS_URL, params={"productType": "usdt-futures"})
        data = res.json()["data"]

        async with SessionLocal() as db:
            for d in data:
                symbol = d["symbol"]

                # 만기물(delivery contracts)은 스킵
                if "deliveryTime" in d and d["deliveryTime"] not in (None, "0"):
                    continue

                funding_rate = float(d.get("fundingRate", 0))

                existing = await db.execute(
                    select(FundingRate).where(
                        (FundingRate.symbol == symbol) &
                        (FundingRate.exchange == "Bitget")
                    )
                )
                row = existing.scalars().first()

                if row:
                    row.funding_rate = funding_rate
                    row.timestamp = now
                else:
                    fr = FundingRate(
                        symbol=symbol,
                        exchange="Bitget",
                        funding_rate=funding_rate,
                        next_funding_time=None,  # 별도 주기에서 갱신
                        timestamp=now
                    )
                    db.add(fr)

            await db.commit()


# -----------------------------
# Bitget: nextFundingTime (funding-time)
# -----------------------------
async def fetch_and_save_bitget_times():
    """1시간마다 실행: nextFundingTime 갱신"""
    kst = ZoneInfo("Asia/Seoul")

    async with httpx.AsyncClient() as client:
        res = await client.get(BITGET_TICKERS_URL, params={"productType": "usdt-futures"})
        data = res.json()["data"]
        symbols = [d["symbol"] for d in data if "deliveryTime" not in d or d["deliveryTime"] in (None, "0")]

        async with SessionLocal() as db:
            for symbol in symbols:
                try:
                    r = await client.get(BITGET_TIME_URL, params={
                        "symbol": symbol,
                        "productType": "usdt-futures"
                    })
                    time_data = r.json()["data"][0]
                    nft = datetime.fromtimestamp(int(time_data["nextFundingTime"]) // 1000, tz=kst)

                    existing = await db.execute(
                        select(FundingRate).where(
                            (FundingRate.symbol == symbol) &
                            (FundingRate.exchange == "Bitget")
                        )
                    )
                    row = existing.scalars().first()
                    if row:
                        row.next_funding_time = nft
                except Exception as e:
                    print(f"⚠️ Bitget funding-time fetch failed for {symbol}: {e}")

            await db.commit()


# -----------------------------
# Update Loop (매 분 55초에 실행)
# -----------------------------
async def update_loop():
    try:
        await fetch_and_save_binance()
        await fetch_and_save_bitget_rates()
        await fetch_and_save_bitget_times()
        print("✅ Initial funding data updated")
    except Exception as e:
        print("❌ Initial fetch error:", e)

    counter = 0
    while True:
        now = datetime.now(ZoneInfo("Asia/Seoul"))

        # 다음 실행 시각 = 다음 분의 55초
        next_minute = (now.minute + 1) % 60
        next_hour = now.hour + (1 if next_minute == 0 else 0)
        target = now.replace(hour=next_hour % 24, minute=next_minute, second=55, microsecond=0)

        # 만약 지금이 이미 55초 이후라면 → 이번 분의 55초로 맞춤
        if now.second < 55:
            target = now.replace(second=55, microsecond=0)

        sleep_seconds = (target - now).total_seconds()
        await asyncio.sleep(sleep_seconds)

        try:
            await fetch_and_save_binance()
            await fetch_and_save_bitget_rates()
            counter += 1

            # 60분마다 nextFundingTime 갱신
            if counter % 60 == 0:
                await fetch_and_save_bitget_times()

            print(f"✅ Funding data updated at {datetime.now(ZoneInfo('Asia/Seoul'))}")
        except Exception as e:
            print("❌ Error:", e)
