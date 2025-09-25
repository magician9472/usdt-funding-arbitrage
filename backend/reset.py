# reset_db.py
import asyncio
from backend.database import SessionLocal
from backend.models import FundingRate

async def reset_funding_table():
    async with SessionLocal() as db:
        await db.execute(FundingRate.__table__.delete())
        await db.commit()
        print("✅ FundingRate 테이블 초기화 완료")

if __name__ == "__main__":
    asyncio.run(reset_funding_table())