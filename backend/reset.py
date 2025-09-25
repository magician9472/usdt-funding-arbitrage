# reset_db.py
import asyncio
from database import SessionLocal
from models import FundingRate
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

async def reset_funding_table():
    async with SessionLocal() as db:
        await db.execute(FundingRate.__table__.delete())
        await db.commit()
        print("✅ FundingRate 테이블 초기화 완료")

if __name__ == "__main__":
    asyncio.run(reset_funding_table())