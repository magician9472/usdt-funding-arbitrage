from sqlalchemy import Column, Integer, String, Float, DateTime
from backend.database import Base

class FundingRate(Base):
    __tablename__ = "funding_rates"

    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String, index=True)
    exchange = Column(String)
    funding_rate = Column(Float)
    next_funding_time = Column(DateTime(timezone=True))
    timestamp = Column(DateTime(timezone=True))
