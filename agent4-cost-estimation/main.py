"""
Agent 4 - Cost Estimation & Budget Optimization

Current capabilities:
1. Cost calculation
2. Budget analysis
3. Optimization candidate identification
4. Real Agent 3 cheaper-alternative search
5. Automatic budget optimization
6. User preference handling (priority, quality, style)

NOTE:
Agent 4 communicates with Agent 3 through its /search-furniture endpoint
to obtain real product alternatives and prices.
"""

import httpx
from dataclasses import dataclass
from fastapi import FastAPI
from pydantic import BaseModel, Field
from typing import List, Optional, Literal
from fastapi.middleware.cors import CORSMiddleware

AGENT3_URL = "http://127.0.0.1:8003"

app = FastAPI(
    title="Agent 4 - Cost Estimation & Budget Optimization"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# MODELS
# ============================================================

class Agent3Product(BaseModel):
    item: str = Field(min_length=1, max_length=100)
    product_name: str = Field(min_length=1, max_length=200)
    price: float = Field(ge=0, le=1_000_000_000)
    retailer: str = Field(min_length=1, max_length=100)
    link: Optional[str] = Field(default=None, max_length=1000)
    match_score: Optional[float] = Field(default=None, ge=0, le=1)
    product_url: Optional[str] = None
    note: Optional[str] = None


class Product(BaseModel):
    item: str = Field(min_length=1, max_length=100)
    product_name: str = Field(min_length=1, max_length=200)
    price: float = Field(ge=0, le=1_000_000_000)
    quantity: int = Field(default=1, ge=1, le=1000)
    priority: Literal["essential", "flexible", "optional"] = "flexible"
    style: Optional[str] = Field(default=None, max_length=100)
    quality: Literal["high", "medium", "low"] = "medium"
    # Optional context so cheaper alternatives still suit the room (sent on to Agent 3)
    retailer: Optional[str] = None
    match_score: Optional[float] = Field(default=None, ge=0, le=1)
    product_url: Optional[str] = None
    color: Optional[str] = None      # the room's colour theme
    size: Optional[str] = None       # size words, e.g. "queen", "3 door"
    audience: Optional[str] = None   # adult / teen / child / baby


class CostRequest(BaseModel):
    products: List[Product] = Field(min_length=1, max_length=100)
    budget: float = Field(gt=0, le=1_000_000_000)


class BreakdownItem(BaseModel):
    item: str
    product_name: str
    unit_price: float
    quantity: int
    total_price: float
    priority: str


class OptimizationCandidate(BaseModel):
    item: str
    product_name: str
    priority: str
    current_cost: float
    reason: str


class AlternativeProduct(BaseModel):
    item: str
    product_name: str
    price: float
    retailer: str
    saving: float
    style: Optional[str] = None


class OptimizedItem(BaseModel):
    item: str
    original_product: str
    original_price: float
    optimized_product: str
    optimized_price: float
    quantity: int
    total_original_cost: float
    total_optimized_cost: float
    saving: float
    retailer: str
    priority: str
    quality: str
    note: Optional[str] = None           # Agent 3's explanation, e.g. colour match
    product_url: Optional[str] = None
    match_score: Optional[float] = None


class CostResponse(BaseModel):
    total_cost: float
    budget: float
    budget_status: str
    budget_utilization: float
    remaining_budget: float
    over_budget_amount: float

    essential_cost: float
    flexible_cost: float
    optional_cost: float

    required_savings: float
    optimization_needed: bool

    optimization_candidates: List[OptimizationCandidate]

    breakdown: List[BreakdownItem]

    suggestion: str

class ItemPreference(BaseModel):
    item: str = Field(min_length=1, max_length=100)
    priority: Literal["essential", "flexible", "optional"] = "flexible"
    quality: Literal["high", "medium", "low"] = "medium"


class UserPreferences(BaseModel):
    budget: float = Field(gt=0, le=1_000_000_000)
    style: Optional[str] = Field(default=None, max_length=100)
    quality: Literal["high", "medium", "low"] = "medium"
    preferences: List[ItemPreference] = Field(default_factory=list, max_length=100)


class OptimizationRequest(BaseModel):
    products: List[Product] = Field(min_length=1, max_length=100)
    budget: float = Field(gt=0, le=1_000_000_000)
    preferences: Optional[UserPreferences] = None


class OptimizationResponse(BaseModel):
    original_total: float
    budget: float
    original_over_budget: float

    optimized_total: float
    final_remaining_budget: float
    final_over_budget_amount: float

    total_savings: float

    optimization_successful: bool

    optimized_items: List[OptimizedItem]

    message: str

    # When the budget can't be met: what the user could do
    suggestions: List[str] = []


# ============================================================
# HEALTH CHECK
# ============================================================

@app.get("/health")
def health_check():
    return {
        "status": "Agent 4 is running"
    }

@app.post("/preferences")
def set_preferences(preferences: UserPreferences):
    return {
        "message": "User preferences received successfully",
        "preferences": preferences
    }

# ============================================================
# COST CALCULATION
# ============================================================

def calculate_total(products: List[Product]) -> float:
    """
    Calculate the total cost of all products.
    """

    total = sum(
        product.price * product.quantity
        for product in products
    )

    return round(total, 2)


# ============================================================
# BUDGET ANALYSIS
# ============================================================

def analyze_budget(
    total: float,
    budget: float
):
    """
    Compare total cost with the user's budget.
    """

    if total > budget:
        status = "over budget"
    elif total == budget:
        status = "exact budget"
    elif total >= budget * 0.9:
        status = "near budget limit"
    else:
        status = "within budget"

    utilization = (
        (total / budget) * 100
        if budget > 0
        else 0
    )

    remaining = max(budget - total, 0)
    over_budget = max(total - budget, 0)

    return (
        status,
        round(utilization, 2),
        round(remaining, 2),
        round(over_budget, 2)
    )


# ============================================================
# COST PRIORITY ANALYSIS
# ============================================================

def analyze_cost_priorities(
    products: List[Product]
):
    """
    Calculate total spending according to priority.
    """

    essential_cost = 0
    flexible_cost = 0
    optional_cost = 0

    for product in products:

        item_cost = product.price * product.quantity

        if product.priority == "essential":
            essential_cost += item_cost

        elif product.priority == "optional":
            optional_cost += item_cost

        else:
            flexible_cost += item_cost

    return (
        round(essential_cost, 2),
        round(flexible_cost, 2),
        round(optional_cost, 2)
    )


# ============================================================
# OPTIMIZATION CANDIDATES
# ============================================================

def identify_optimization_candidates(
    products: List[Product],
    budget: float,
    total: float
) -> List[OptimizationCandidate]:

    candidates = []

    if total <= budget:
        return candidates

    priority_order = {
        "optional": 0,
        "flexible": 1,
        "essential": 2
    }

    sorted_products = sorted(
        products,
        key=lambda product: (
            priority_order.get(product.priority, 1),
            -(product.price * product.quantity)
        )
    )

    required_savings = total - budget
    accumulated_savings = 0

    for product in sorted_products:

        item_total = product.price * product.quantity

        if product.priority == "optional":

            reason = (
                "Optional item. Consider replacing or removing "
                "this item first to reduce cost."
            )

        elif product.priority == "flexible":

            reason = (
                "Flexible item. Consider a lower-cost alternative "
                "while maintaining the overall design."
            )

        else:

            reason = (
                "Essential item. Keep this item unless other "
                "cost-saving options are insufficient."
            )

        candidates.append(
            OptimizationCandidate(
                item=product.item,
                product_name=product.product_name,
                priority=product.priority,
                current_cost=round(item_total, 2),
                reason=reason
            )
        )

        accumulated_savings += item_total

        # Keep all priority-ordered candidates available.
        # Agent 3 determines whether a cheaper alternative actually exists.

    return candidates


# ============================================================
# BREAKDOWN
# ============================================================

def create_breakdown(
    products: List[Product]
) -> List[BreakdownItem]:

    breakdown = []

    for product in products:

        total_price = (
            product.price * product.quantity
        )

        breakdown.append(
            BreakdownItem(
                item=product.item,
                product_name=product.product_name,
                unit_price=round(product.price, 2),
                quantity=product.quantity,
                total_price=round(total_price, 2),
                priority=product.priority
            )
        )

    return breakdown


# ============================================================
# BUDGET ADVICE
# ============================================================

def generate_budget_advice(
    total: float,
    budget: float,
    status: str,
    utilization: float,
    remaining: float,
    over_budget: float
) -> str:

    if status == "over budget":

        return (
            f"The design exceeds your budget by "
            f"LKR {over_budget:,.0f}. "
            f"Use 'Fit to my budget' to swap in cheaper matching products."
        )

    elif status == "exact budget":

        return (
            "The design exactly matches your budget. "
            "No additional budget is available."
        )

    elif status == "near budget limit":

        return (
            f"The design is within budget but uses "
            f"{utilization:.1f}% of your budget. "
            f"You have LKR {remaining:,.0f} remaining."
        )

    else:

        return (
            f"The design is within budget. "
            f"You have LKR {remaining:,.0f} remaining."
        )


# ============================================================
# ESTIMATE COST ENDPOINT
# ============================================================

@app.post(
    "/estimate-cost",
    response_model=CostResponse
)
def estimate_cost(request: CostRequest):

    total = calculate_total(request.products)

    (
        status,
        utilization,
        remaining,
        over_budget
    ) = analyze_budget(
        total,
        request.budget
    )

    (
        essential_cost,
        flexible_cost,
        optional_cost
    ) = analyze_cost_priorities(
        request.products
    )

    optimization_candidates = (
        identify_optimization_candidates(
            request.products,
            request.budget,
            total
        )
    )

    required_savings = max(
        total - request.budget,
        0
    )

    optimization_needed = (
        total > request.budget
    )

    breakdown = create_breakdown(
        request.products
    )

    suggestion = generate_budget_advice(
        total,
        request.budget,
        status,
        utilization,
        remaining,
        over_budget
    )

    return CostResponse(

        total_cost=total,

        budget=request.budget,

        budget_status=status,

        budget_utilization=utilization,

        remaining_budget=remaining,

        over_budget_amount=over_budget,

        essential_cost=essential_cost,

        flexible_cost=flexible_cost,

        optional_cost=optional_cost,

        required_savings=round(
            required_savings,
            2
        ),

        optimization_needed=optimization_needed,

        optimization_candidates=(
            optimization_candidates
        ),

        breakdown=breakdown,

        suggestion=suggestion
    )


# ============================================================
# REAL AGENT 3 INTEGRATION
# ============================================================

def search_agent3(
    item: str,
    style: str,
    qty: int = 1,
    min_price: Optional[int] = None,
    max_price: Optional[int] = None,
    color: Optional[str] = None,
    size: Optional[str] = None,
    audience: Optional[str] = None
) -> List[Agent3Product]:
    """
    Ask Agent 3 for up to `qty` product options for one item. Colour theme, size and
    occupant are passed on so alternatives still suit the room (no kids' wardrobe in
    an adult bedroom, no red sofa in a navy room).
    """

    payload = {
        "layout_image_path": None,
        "furniture_needed": [
            {
                "item": item,
                "style": style,
                "qty": qty,
                "min_price": min_price,
                "max_price": max_price,
                "color": color,
                "size": size,
                "audience": audience
            }
        ]
    }

    response = httpx.post(
        f"{AGENT3_URL}/search-furniture",
        json=payload,
        timeout=30
    )

    response.raise_for_status()

    return [
        Agent3Product(**product)
        for product in response.json()
        if product.get("found", True) and product.get("product_name")
    ]


@app.get("/test-agent3")
def test_agent3():

    products = search_agent3(
        item="sofa",
        style="modern fabric",
        qty=1
    )

    return {
        "message": "Successfully connected to Agent 3",
        "products": products
    }


# ============================================================
# PRODUCT OPTIONS (current pick + cheaper alternatives)
# ============================================================

SEARCH_OPTIONS = 12

# How reluctant we are to downgrade an item. Designer-added extras (optional) go first,
# the pieces the user asked for (flexible) next, anything marked essential last.
PRIORITY_WEIGHT = {"optional": 0.5, "flexible": 1.0, "essential": 2.5}

# The user's quality preference: "high" protects the match, "low" chases savings.
QUALITY_WEIGHT = {"high": 2.0, "medium": 1.0, "low": 0.4}

MIN_MATCH_LOSS = 0.02


@dataclass
class Option:
    product_name: str
    price: float
    retailer: str
    score: float
    note: Optional[str] = None
    product_url: Optional[str] = None


def product_options(product: Product) -> List[Option]:
    """
    Current product first, then cheaper alternatives from Agent 3 (most expensive first).
    One Agent 3 search without a price cap, so every option's match score is on the same scale.
    """

    current_score = product.match_score if product.match_score is not None else 0.8
    options = [Option(product.product_name, product.price, product.retailer or "", current_score,
                      None, product.product_url)]

    try:
        results = search_agent3(
            item=product.item,
            style=product.style or "",
            qty=SEARCH_OPTIONS,
            color=product.color,
            size=product.size,
            audience=product.audience
        )
    except Exception as e:
        print(f"Agent 3 alternative search failed for {product.item}: {e}")
        return options

    for result in results:
        if result.product_name == product.product_name:
            # Re-score the current pick on the same scale as its alternatives
            options[0].score = result.match_score or current_score
            continue
        if result.price < product.price:
            options.append(Option(result.product_name, result.price, result.retailer,
                                  result.match_score or 0.0, result.note, result.product_url or result.link))

    options[1:] = sorted(options[1:], key=lambda o: -o.price)
    return options


# Kept for compatibility: the single best cheaper alternative for one product
def find_best_alternative(product: Product) -> Optional[AlternativeProduct]:
    options = product_options(product)
    if len(options) < 2:
        return None
    weight = QUALITY_WEIGHT.get(product.quality, 1.0)
    current = options[0]
    best = max(options[1:], key=lambda o: (current.price - o.price) /
               (max(MIN_MATCH_LOSS, current.score - o.score) * weight))
    return AlternativeProduct(
        item=product.item,
        product_name=best.product_name,
        price=best.price,
        retailer=best.retailer,
        saving=round(product.price - best.price, 2),
        style=product.style
    )


# ============================================================
# AUTOMATIC BUDGET OPTIMIZATION
# ============================================================

def apply_preferences(products: List[Product], preferences: Optional[UserPreferences]) -> List[Product]:
    """Copy the products, applying the user's per-item priority/quality preferences."""

    updated = [Product(**product.model_dump()) for product in products]
    if preferences is None:
        return updated

    preference_map = {pref.item.strip().lower(): pref for pref in preferences.preferences}
    for index, product in enumerate(updated):
        pref = preference_map.get(product.item.strip().lower())
        data = product.model_dump()
        data["style"] = product.style or preferences.style
        if pref is not None:
            data["priority"] = pref.priority
            data["quality"] = pref.quality
        else:
            data["quality"] = preferences.quality
        updated[index] = Product(**data)
    return updated


def optimize_products(
    products: List[Product],
    budget: float,
    preferences: Optional[UserPreferences] = None
):
    """
    Choose one option per item so the room fits the budget while losing as little
    match quality as possible.

    Greedy by efficiency: repeatedly make the downgrade that saves the most money per
    unit of match score lost (weighted by the item's priority and the user's quality
    preference). Once under budget, undo downgrades that are no longer needed, so no
    item is cheapened more than necessary.
    """

    optimized_products = apply_preferences(products, preferences)
    options = [product_options(p) for p in optimized_products]
    choice = [0] * len(optimized_products)

    def total():
        return sum(options[i][choice[i]].price * p.quantity for i, p in enumerate(optimized_products))

    def weight(i):
        p = optimized_products[i]
        return PRIORITY_WEIGHT.get(p.priority, 1.0) * QUALITY_WEIGHT.get(p.quality, 1.0)

    # 1. Downgrade until the room fits (or nothing cheaper is left)
    while total() > budget:
        best = None
        for i, p in enumerate(optimized_products):
            current = options[i][choice[i]]
            for j in range(choice[i] + 1, len(options[i])):
                option = options[i][j]
                saving = (current.price - option.price) * p.quantity
                if saving <= 0:
                    continue
                loss = max(MIN_MATCH_LOSS, current.score - option.score)
                efficiency = saving / (loss * weight(i))
                if best is None or efficiency > best[0]:
                    best = (efficiency, i, j)
        if best is None:
            break
        _, i, j = best
        choice[i] = j

    # 2. Give back: move items back up to better options while the room still fits
    if total() <= budget:
        improved = True
        while improved:
            improved = False
            for i, p in sorted(enumerate(optimized_products), key=lambda x: -weight(x[0])):
                for j in range(0, choice[i]):
                    extra = (options[i][j].price - options[i][choice[i]].price) * p.quantity
                    if total() + extra <= budget and options[i][j].score > options[i][choice[i]].score:
                        choice[i] = j
                        improved = True
                        break

    optimized_items = []
    final_products = []
    for i, p in enumerate(optimized_products):
        chosen, original = options[i][choice[i]], options[i][0]
        final_products.append(Product(**{**p.model_dump(), "product_name": chosen.product_name,
                                         "price": chosen.price, "retailer": chosen.retailer,
                                         "match_score": chosen.score, "product_url": chosen.product_url}))
        if choice[i] == 0:
            continue
        optimized_items.append(
            OptimizedItem(
                item=p.item,
                original_product=original.product_name,
                original_price=original.price,
                optimized_product=chosen.product_name,
                optimized_price=chosen.price,
                quantity=p.quantity,
                total_original_cost=round(original.price * p.quantity, 2),
                total_optimized_cost=round(chosen.price * p.quantity, 2),
                saving=round((original.price - chosen.price) * p.quantity, 2),
                retailer=chosen.retailer,
                priority=p.priority,
                quality=p.quality,
                note=chosen.note,
                product_url=chosen.product_url,
                match_score=round(chosen.score, 3)
            )
        )

    cheapest_total = sum(min(o.price for o in options[i]) * p.quantity for i, p in enumerate(optimized_products))
    return final_products, optimized_items, cheapest_total


def shortfall_suggestions(products: List[Product], budget: float, cheapest_total: float) -> List[str]:
    """What the user could do when even the cheapest matching products don't fit."""

    gap = cheapest_total - budget
    if gap <= 0:
        return []
    suggestions = [f"Increase the budget to about LKR {cheapest_total:,.0f} (LKR {gap:,.0f} more)."]

    # Which items would have to go: optional ones first, then the priciest
    order = sorted(products, key=lambda p: (PRIORITY_WEIGHT.get(p.priority, 1.0), -p.price * p.quantity))
    removed, saved = [], 0.0
    for p in order:
        if saved >= gap:
            break
        removed.append(p.item + (f" (x{p.quantity})" if p.quantity > 1 else ""))
        saved += p.price * p.quantity
    if removed:
        suggestions.append("Or leave out: " + ", ".join(removed) + " for now, and buy later.")
    return suggestions


# ============================================================
# OPTIMIZE BUDGET ENDPOINT
# ============================================================

@app.post(
    "/optimize-budget",
    response_model=OptimizationResponse
)
def optimize_budget(
    request: OptimizationRequest
):

    original_total = calculate_total(request.products)
    original_over_budget = max(original_total - request.budget, 0)

    # Already within budget
    if original_total <= request.budget:
        return OptimizationResponse(
            original_total=original_total,
            budget=request.budget,
            original_over_budget=0,
            optimized_total=original_total,
            final_remaining_budget=round(request.budget - original_total, 2),
            final_over_budget_amount=0,
            total_savings=0,
            optimization_successful=True,
            optimized_items=[],
            message="The design is already within budget. No optimization was required."
        )

    optimized_products, optimized_items, cheapest_total = optimize_products(
        request.products,
        request.budget,
        request.preferences
    )

    optimized_total = calculate_total(optimized_products)
    total_savings = original_total - optimized_total
    final_remaining_budget = max(request.budget - optimized_total, 0)
    final_over_budget_amount = max(optimized_total - request.budget, 0)
    optimization_successful = optimized_total <= request.budget

    if optimization_successful:
        message = (
            f"Swapping {len(optimized_items)} item(s) for cheaper matching products brings the room "
            f"from LKR {original_total:,.0f} to LKR {optimized_total:,.0f}, within your budget. "
            f"Total savings: LKR {total_savings:,.0f}."
        )
        suggestions = []
    else:
        message = (
            f"Even with the cheapest suitable product for every item, the room costs "
            f"LKR {optimized_total:,.0f}, which is LKR {final_over_budget_amount:,.0f} over your budget."
        )
        suggestions = shortfall_suggestions(optimized_products, request.budget, cheapest_total)

    return OptimizationResponse(
        original_total=original_total,
        budget=request.budget,
        original_over_budget=round(original_over_budget, 2),
        optimized_total=optimized_total,
        final_remaining_budget=round(final_remaining_budget, 2),
        final_over_budget_amount=round(final_over_budget_amount, 2),
        total_savings=round(total_savings, 2),
        optimization_successful=optimization_successful,
        optimized_items=optimized_items,
        message=message,
        suggestions=suggestions
    )
