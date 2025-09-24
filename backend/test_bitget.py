import os
from pybitget import Client
from dotenv import load_dotenv

# .env 불러오기
load_dotenv()
API_KEY = os.getenv("BITGET_API_KEY")
API_SECRET = os.getenv("BITGET_API_SECRET")
API_PASSPHRASE = os.getenv("BITGET_API_PASS")

# Bitget 클라이언트 생성
client = Client(API_KEY, API_SECRET, passphrase=API_PASSPHRASE)

# 선물 계정 잔고 조회 (USDT-M Futures)
# productType='UMCBL' → USDT-M Perpetual
result = client.mix_get_accounts(productType='UMCBL')
print(result)