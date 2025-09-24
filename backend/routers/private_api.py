import os
from fastapi import APIRouter
from dotenv import load_dotenv
from binance.client import Client as BinanceClient
from pybitget import Client as BitgetClient

load_dotenv()
router = APIRouter()

# Binance Client
binance_client = BinanceClient(
    os.getenv("BINANCE_API_KEY"),
    os.getenv("BINANCE_API_SECRET")
)

# Bitget Client (api_key, secret_key, passphrase)
bitget_client = BitgetClient(
    os.getenv("BITGET_API_KEY"),
    os.getenv("BITGET_API_SECRET"),
    passphrase=os.getenv("BITGET_API_PASS")
)

# Binance 계정 조회
@router.get("/binance/account")
async def binance_account():
    account_info = binance_client.futures_account()
    balances = [
        {
            "asset": a["asset"],
            "walletBalance": a["walletBalance"],
            "availableBalance": a["availableBalance"]
        }
        for a in account_info["assets"]
        if float(a["walletBalance"]) > 0 or float(a["availableBalance"]) > 0
    ]
    return {
        "totalWalletBalance": account_info["totalWalletBalance"],
        "availableBalance": account_info["availableBalance"],
        "assets": balances
    }

# Bitget 계정 조회 (Binance 포맷으로 변환)
@router.get("/bitget/account")
async def bitget_account():
    try:
        res = bitget_client.mix_get_accounts(productType="UMCBL")
        if "data" not in res:
            return {
                "totalWalletBalance": 0,
                "availableBalance": 0,
                "assets": []
            }

        data = res["data"]

        balances = [
            {
                "asset": d.get("marginCoin"),          # Binance의 asset과 동일
                "walletBalance": f"{float(d.get('equity', 0)):.8f}",      # 총 자산
                "availableBalance": f"{float(d.get('available', 0)):.8f}" # 사용 가능
            }
            for d in data
        ]

        return {
            "totalWalletBalance": f"{sum(float(d.get('equity', 0)) for d in data):.8f}",
            "availableBalance": f"{sum(float(d.get('available', 0)) for d in data):.8f}",
            "assets": balances
        }

    except Exception as e:
        return {
            "totalWalletBalance": 0,
            "availableBalance": 0,
            "assets": [],
            "error": str(e)
        }