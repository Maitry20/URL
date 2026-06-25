from sqlalchemy import Column, Integer, String, Text, DateTime
from datetime import datetime, timezone
from database import Base

class ShortURL(Base):
    __tablename__ = "short_urls"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(6), unique=True, index=True, nullable=False)
    original_url = Column(Text, nullable=False)
    created_by = Column(String(255), index=True, nullable=False) # User's email
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
