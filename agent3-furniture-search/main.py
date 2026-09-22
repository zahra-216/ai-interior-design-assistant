"""
Agent 3 - Furniture Search Agent (Information Retrieval)
Takes the design output from Agent 2 (layout_image_path + furniture_needed),
searches the local furniture database, and returns matched real products
with prices.

Run: uvicorn main:app --reload --port 8003
"""
from fastapi import FastAPI, Depends
from pydantic import BaseModel
from typing import List, Optional
from sqlalchemy.orm import Session

from database import get_db, init_db
from search_logic import Catalog, search_and_rank
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Agent 3 - Furniture Search")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

init_db()  # adds the color / product_url columns if they are missing


class FurnitureRequest(BaseModel):
    item: str
    style: str = ""
    # How many product OPTIONS to return. Agent 4 uses this to fetch alternatives.
    qty: int = 1
    # How many pieces the room needs (e.g. 2 bedside tables). Returned as-is for costing.
    quantity: int = 1
    color: Optional[str] = None      # room colour preference, e.g. "navy blue and white"
    size: Optional[str] = None       # size words from the user, e.g. "queen", "small", "3 door"
    audience: Optional[str] = None   # who the room is for: adult (default) / teen / child / baby
    min_price: Optional[int] = None
    max_price: Optional[int] = None


class DesignInput(BaseModel):
    """
    Matches Agent 2's actual output shape:
    {
      "layout_image_path": "designs/design_v1.png",
      "furniture_needed": [
        {"item": "queen bed", "style": "modern", "qty": 1, "quantity": 1, "color": "navy blue", "size": "queen"},
        {"item": "bedside table", "style": "modern", "qty": 1, "quantity": 2, "color": "navy blue"}
      ]
    }
    """
    layout_image_path: Optional[str] = None
    furniture_needed: List[FurnitureRequest]
    # Also return a row (found=false) for items with no suitable product, so the UI can show them
    include_missing: bool = False


class MatchedProduct(BaseModel):
    item: str
    product_name: str
    price: int
    retailer: str
    link: Optional[str] = None
    match_score: Optional[float] = None
    quantity: int = 1
    found: bool = True
    category: Optional[str] = None
    color: Optional[str] = None
    image_url: Optional[str] = None
    product_url: Optional[str] = None
    note: Optional[str] = None


@app.get("/health")
def health_check():
    return {"status": "Agent 3 is running"}


@app.post("/search-furniture", response_model=List[MatchedProduct])
def search_furniture(payload: DesignInput, db: Session = Depends(get_db)):
    """
    Receives Agent 2's design output, and for each furniture item requested,
    runs the hybrid IR pipeline (see search_logic.py):
      1. Query understanding (category + size from the item name)
      2. Candidate filter (category + price range), related-category fallback
      3. Rank: TF-IDF cosine on style text + colour harmony + size fit
    Returns the top match(es) per item, ready to be forwarded to Agent 4.
    """
    catalog = Catalog(db)
    results = []

    for request in payload.furniture_needed:
        matches = search_and_rank(
            catalog,
            item=request.item,
            style=request.style,
            color=request.color or "",
            size=request.size or "",
            top_k=request.qty,
            min_price=request.min_price,
            max_price=request.max_price,
            audience=request.audience or "adult",
        )

        if not matches:
            if payload.include_missing:
                results.append(MatchedProduct(
                    item=request.item, product_name="", price=0, retailer="",
                    quantity=request.quantity, found=False,
                    note=f"No {request.item} in our product catalog yet",
                ))
            continue

        for match in matches:
            product = match.product
            results.append(
                MatchedProduct(
                    item=request.item,
                    product_name=product.name,
                    price=product.price,
                    retailer=product.retailer,
                    link=product.product_url or product.image_url,
                    match_score=match.score,
                    quantity=request.quantity,
                    category=match.category,
                    color=product.color,
                    image_url=product.image_url,
                    product_url=product.product_url,
                    note=match.note,
                )
            )

    return results


# Example request body (what Agent 2 actually sends):
#
# {
#   "layout_image_path": "designs/design_v1.png",
#   "furniture_needed": [
#     {"item": "queen bed", "style": "modern", "qty": 1, "quantity": 1, "color": "navy blue", "size": "queen"},
#     {"item": "bedside table", "style": "modern", "qty": 1, "quantity": 2, "color": "navy blue"}
#   ],
#   "include_missing": true
# }

# Example output JSON contract (sent to Agent 4):
#
# [
#   {"item": "queen bed", "product_name": "LF-ORGN-BDQ-WHT", "price": 119999, "retailer": "Singer",
#    "match_score": 0.812, "quantity": 1, "found": true, "color": "white",
#    "note": "No dark blue beds in our catalog; this white one goes well with a dark blue theme"},
# ]

# Furniture table schema (PostgreSQL) - for reference:
# id | name | category | style | price | retailer | image_url | color | product_url
