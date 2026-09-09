"""
Agent 4 - Cost Estimation Agent
Takes matched products from Agent 3, calculates total cost and
compares against user's budget.

Run: uvicorn main:app --reload --port 8004
"""
from fastapi import FastAPI
from pydantic import BaseModel
from typing import List, Optional

app = FastAPI(title="Agent 4 - Cost Estimation")


class Product(BaseModel):
    item: str
    product_name: str
    price: int
    retailer: str


class CostRequest(BaseModel):
    products: List[Product]
    budget: int


class CostResponse(BaseModel):
    total_cost: int
    budget: int
    budget_status: str
    breakdown: List[Product]
    suggestion: Optional[str] = None


@app.get("/health")
def health_check():
    return {"status": "Agent 4 is running"}


@app.post("/estimate-cost", response_model=CostResponse)
def estimate_cost(request: CostRequest):
    total = sum(p.price for p in request.products)

    if total <= request.budget:
        status = "within budget"
        remaining = request.budget - total
        suggestion = f"You have LKR {remaining:,} remaining."
    else:
        status = "over budget"
        over = total - request.budget
        suggestion = f"You are over budget by LKR {over:,}. Consider cheaper alternatives."

    return CostResponse(
        total_cost=total,
        budget=request.budget,
        budget_status=status,
        breakdown=request.products,
        suggestion=suggestion
    )


# Example output JSON contract (final result to frontend):
#
# {
#   "total_cost": 145000,
#   "budget": 150000,
#   "budget_status": "within budget",
#   "breakdown": [...],
#   "suggestion": "You have LKR 5,000 remaining."
# }
