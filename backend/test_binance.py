import os
from binance.client import Client
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv("BINANCE_API_KEY")
api_secret = os.getenv("BINANCE_API_SECRET")

client = Client(api_key, api_secret)

def get_futures_balance():
    balances = client.futures_account_balance()
    for b in balances:
        asset = b["asset"]
        balance = float(b["balance"])
        available = float(b["availableBalance"]) 
        if balance > 0:
            print(f"{asset}: 총 {balance}, 사용 가능 {available}")

if __name__ == "__main__":
    get_futures_balance()