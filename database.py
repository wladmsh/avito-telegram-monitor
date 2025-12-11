from sqlalchemy import create_engine, Column, Integer, String, Text, Boolean, BigInteger
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from config import DATABASE_URL

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

class UserTask(Base):
    __tablename__ = 'usertasks'
    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, nullable=False)
    avito_url = Column(Text, nullable=False)
    min_price = Column(Integer, default=0)
    max_price = Column(Integer, default=999999999)
    last_checked_ad_id = Column(String(255))
    is_active = Column(Boolean, default=True)

Base.metadata.create_all(engine)
