"""
Database connection and table model for Agent 3.
Schema: id | name | category | style | price | retailer | image_url | color | product_url
"""
import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, Column, Integer, String, Text, text
from sqlalchemy.orm import declarative_base, sessionmaker

load_dotenv()  # reads the .env file

DATABASE_URL = os.getenv("DATABASE_URL")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    category = Column(String, nullable=False)
    style = Column(String, nullable=False)
    price = Column(Integer, nullable=False)
    retailer = Column(String, nullable=False)
    image_url = Column(Text, nullable=True)
    color = Column(String, nullable=True)        # e.g. "walnut", "navy blue, white"
    product_url = Column(Text, nullable=True)    # retailer's product page


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    Base.metadata.create_all(bind=engine)
    # create_all does not add columns to an existing table, so add the newer ones here
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE products ADD COLUMN IF NOT EXISTS color VARCHAR"))
        connection.execute(text("ALTER TABLE products ADD COLUMN IF NOT EXISTS product_url TEXT"))