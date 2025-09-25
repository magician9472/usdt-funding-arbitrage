import os
from pybitget import Client
from dotenv import load_dotenv

# # .env 불러오기
# load_dotenv()
# API_KEY = os.getenv("BITGET_API_KEY")
# API_SECRET = os.getenv("BITGET_API_SECRET")
# API_PASSPHRASE = os.getenv("BITGET_API_PASS")

# # Bitget 클라이언트 생성
# client = Client(API_KEY, API_SECRET, passphrase=API_PASSPHRASE)

# # 선물 계정 잔고 조회 (USDT-M Futures)
# # productType='UMCBL' → USDT-M Perpetual
# result = client.mix_get_accounts(productType='UMCBL')
# print(result)

# 비트겟(Bitget) 모든 심볼 가져오기 (ccxt 사용)
# pip install ccxt

# import requests

# BITGET_CONTRACTS_URL = "https://api.bitget.com/api/v2/mix/market/contracts"

# def fetch_usdtm_symbols():
#     params = {"productType": "USDT-FUTURES"}  # USDT-M 선물
#     response = requests.get(BITGET_CONTRACTS_URL, params=params)
#     data = response.json()

#     if data.get("code") == "00000":
#         contracts = data.get("data", [])
#         symbols = [c["symbol"] for c in contracts]
#         print(f"USDT-M 선물 심볼 {len(symbols)}개")
#         for s in symbols:
#             print(s)
#         return symbols
#     else:
#         print("API 호출 실패:", data)
#         return []

# if __name__ == "__main__":
#     fetch_usdtm_symbols()
import httpx
import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

CONTRACTS_URL = "https://api.bitget.com/api/v2/mix/market/contracts"
FUNDING_URL = "https://api.bitget.com/api/v2/mix/market/current-fund-rate"

async def load_contracts():
    """실제 거래 가능한 USDT-FUTURES 심볼 목록 가져오기"""
    async with httpx.AsyncClient() as client:
        res = await client.get(CONTRACTS_URL, params={"productType": "USDT-FUTURES"})
        data = res.json().get("data", [])
        return {c["symbol"] for c in data}

async def fetch_and_show_rates(valid_symbols):
    """현재 펀딩레이트 + 다음 펀딩 시간 출력"""
    kst = ZoneInfo("Asia/Seoul")
    now = datetime.now(kst)

    async with httpx.AsyncClient() as client:
        res = await client.get(FUNDING_URL, params={"productType": "USDT-FUTURES"})
        data = res.json().get("data", [])

        for d in data:
            symbol = d["symbol"]
            if symbol not in valid_symbols:
                continue  # contracts에 없는 심볼은 스킵

            funding_rate = float(d.get("fundingRate") or 0)

            # nextUpdate는 밀리초 단위 Unix timestamp
            next_update_ms = d.get("nextUpdate")
            if next_update_ms:
                next_update = datetime.fromtimestamp(int(next_update_ms) / 1000, tz=kst)
                next_update_str = next_update.strftime("%Y-%m-%d %H:%M:%S")
            else:
                next_update_str = "N/A"

            print(f"[{now}] {symbol}: fundingRate={funding_rate}, nextFundingTime={next_update_str}")

async def main():
    valid_symbols = await load_contracts()
    await fetch_and_show_rates(valid_symbols)

if __name__ == "__main__":
    asyncio.run(main())