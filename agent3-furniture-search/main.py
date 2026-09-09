"""
Agent 3 - Furniture Search Agent (Information Retrieval)
Takes furniture list from Agent 2, searches the local furniture database,
and returns matched real products with prices.

Run: uvicorn main:app --reload --port 8003
"""
from fastapi import FastAPI
from pydantic import BaseModel
from typing import List, Optional

app = FastAPI(title="Agent 3 - Furniture Search")


class FurnitureRequest(BaseModel):
    item: str
    style: str
    qty: int = 1


class MatchedProduct(BaseModel):
    item: str
    product_name: str
    price: int
    retailer: str
    link: Optional[str] = None


@app.get("/health")
def health_check():
    return {"status": "Agent 3 is running"}


@app.post("/search-furniture", response_model=List[MatchedProduct])
def search_furniture(items: List[FurnitureRequest]):
    """
    TODO:
    1. For each item, query PostgreSQL furniture table
       (category/style keyword match, or TF-IDF/cosine similarity for
       more flexible matching)
    2. Return best-matching real product(s) with price + retailer
    """
    # Placeholder response
    return [
        MatchedProduct(
            item=i.item,
            product_name=f"Sample {i.item.title()}",
            price=25000,
            retailer="Damro",
            link=None
        )
        for i in items
    ]


# Example output JSON contract (sent to Agent 4):
#
# [
#   {"item": "3-seater sofa", "product_name": "Damro Comfort Sofa", "price": 65000, "retailer": "Damro"},
#   {"item": "coffee table", "product_name": "Singer Oak Table", "price": 18000, "retailer": "Singer"}
# ]

# Furniture table schema (PostgreSQL) - for reference:
# id | name | category | style | price | retailer | image_url
