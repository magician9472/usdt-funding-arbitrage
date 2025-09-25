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

import requests

BITGET_CONTRACTS_URL = "https://api.bitget.com/api/v2/mix/market/contracts"

def fetch_usdtm_symbols():
    params = {"productType": "USDT-FUTURES"}  # USDT-M 선물
    response = requests.get(BITGET_CONTRACTS_URL, params=params)
    data = response.json()

    if data.get("code") == "00000":
        contracts = data.get("data", [])
        symbols = [c["symbol"] for c in contracts]
        print(f"USDT-M 선물 심볼 {len(symbols)}개")
        for s in symbols:
            print(s)
        return symbols
    else:
        print("API 호출 실패:", data)
        return []

if __name__ == "__main__":
    fetch_usdtm_symbols()