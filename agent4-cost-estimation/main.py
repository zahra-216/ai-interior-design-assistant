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
from fastapi import FastAPI
from pydantic import BaseModel, Field
from typing import List, Optional, Literal

AGENT3_URL = "http://127.0.0.1:8003"

app = FastAPI(
    title="Agent 4 - Cost Estimation & Budget Optimization"
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


class Product(BaseModel):
    item: str = Field(min_length=1, max_length=100)
    product_name: str = Field(min_length=1, max_length=200)
    price: float = Field(ge=0, le=1_000_000_000)
    quantity: int = Field(default=1, ge=1, le=1000)
    priority: Literal["essential", "flexible", "optional"] = "flexible"
    style: Optional[str] = Field(default=None, max_length=100)
    quality: Literal["high", "medium", "low"] = "medium"


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
            f"Flexible and optional items should be considered "
            f"first for cost reduction."
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
    max_price: Optional[int] = None
) -> List[Agent3Product]:

    payload = {
        "layout_image_path": None,
        "furniture_needed": [
            {
                "item": item,
                "style": style,
                "qty": qty,
                "min_price": min_price,
                "max_price": max_price
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
# FIND BEST ALTERNATIVE
# ============================================================

def find_best_alternative(product: Product) -> Optional[AlternativeProduct]:
    """
    Find a cheaper alternative for a product using Agent 3.

    The user's quality preference controls the trade-off between
    preserving the Agent 3 style/match score and reducing price.

    Agent 3 does not provide a direct product-quality rating.
    Therefore, quality is interpreted as how strongly the user wants
    to preserve the product/style match while optimizing cost.
    """

    search_qty = 10
    style = product.style or "modern"
    max_price = int(product.price) - 1

    item_query = product.item.strip().lower()

    item_mapping = {
        "dining chairs": "dining chair",
        "dining tables": "dining table",
        "coffee tables": "coffee table",
        "area rugs": "area rug",
        "sofas": "sofa",
        "beds": "bed",
        "wardrobes": "wardrobe",
        "dressing tables": "dressing table",
    }

    item_query = item_mapping.get(item_query, item_query)

    try:
        agent3_products = search_agent3(
            item=item_query,
            style=style,
            qty=search_qty,
            max_price=max_price
        )
    except Exception as e:
        print(f"Agent 3 alternative search failed: {e}")
        return None

    cheaper_products = [
        p for p in agent3_products
        if p.price < product.price
        and p.product_name != product.product_name
    ]

    if not cheaper_products:
        return None

    quality = (product.quality or "medium").strip().lower()
    if quality not in {"high", "medium", "low"}:
        quality = "medium"

    def match_score(product_result: Agent3Product) -> float:
        if product_result.match_score is None:
            return 0.0
        return float(product_result.match_score)

    # HIGH: preserve the strongest style/product match.
    if quality == "high":
        best_product = max(
            cheaper_products,
            key=lambda p: (match_score(p), -p.price)
        )

    # LOW: maximize cost reduction.
    elif quality == "low":
        best_product = min(
            cheaper_products,
            key=lambda p: p.price
        )

    # MEDIUM: balance match quality and savings.
    else:
        max_price_value = max(p.price for p in cheaper_products)
        min_price_value = min(p.price for p in cheaper_products)
        price_range = max_price_value - min_price_value

        def balanced_score(p: Agent3Product):
            if price_range > 0:
                savings_preference = (
                    max_price_value - p.price
                ) / price_range
            else:
                savings_preference = 1.0

            return (
                0.60 * match_score(p)
                + 0.40 * savings_preference
            )

        best_product = max(
            cheaper_products,
            key=balanced_score
        )

    saving = product.price - best_product.price

    return AlternativeProduct(
        item=product.item,
        product_name=best_product.product_name,
        price=best_product.price,
        retailer=best_product.retailer,
        saving=round(saving, 2),
        style=product.style
    )


# ============================================================
# AUTOMATIC BUDGET OPTIMIZATION
# ============================================================

def optimize_products(
    products: List[Product],
    budget: float,
    preferences: Optional[UserPreferences] = None
):

    # Make a copy so the original request isn't modified
    optimized_products = [
        Product(**product.model_dump())
        for product in products
    ]

    # Apply user preferences before optimization.
    if preferences is not None:
        preference_map = {
            pref.item.strip().lower(): pref
            for pref in preferences.preferences
        }

        for index, product in enumerate(optimized_products):
            pref = preference_map.get(product.item.strip().lower())

            if pref is None:
                continue

            updated_style = product.style or preferences.style

            optimized_products[index] = Product(
                item=product.item,
                product_name=product.product_name,
                price=product.price,
                quantity=product.quantity,
                priority=pref.priority,
                style=updated_style,
                quality=pref.quality
            )

    optimized_items = []

    max_iterations = 20
    iteration = 0

    while iteration < max_iterations:

        iteration += 1

        current_total = calculate_total(
            optimized_products
        )

        # Already within budget
        if current_total <= budget:
            break

        # Identify candidates
        candidates = identify_optimization_candidates(
            optimized_products,
            budget,
            current_total
        )

        if not candidates:
            break

        changed = False

        # Try candidates in priority order
        for candidate in candidates:

            product_index = next(
                (
                    index
                    for index, product
                    in enumerate(optimized_products)
                    if (
                        product.item == candidate.item
                        and product.product_name
                        == candidate.product_name
                    )
                ),
                None
            )

            if product_index is None:
                continue

            current_product = (
                optimized_products[product_index]
            )

            alternative = find_best_alternative(
                current_product
            )

            if alternative is None:
                continue

            # Safety check: alternative must actually be cheaper
            if alternative.price >= current_product.price:
                continue

            original_total_cost = (
                current_product.price *
                current_product.quantity
            )

            optimized_total_cost = (
                alternative.price *
                current_product.quantity
            )

            saving = (
                original_total_cost -
                optimized_total_cost
            )

            optimized_items.append(
                OptimizedItem(
                    item=current_product.item,

                    original_product=(
                        current_product.product_name
                    ),

                    original_price=(
                        current_product.price
                    ),

                    optimized_product=(
                        alternative.product_name
                    ),

                    optimized_price=(
                        alternative.price
                    ),

                    quantity=(
                        current_product.quantity
                    ),

                    total_original_cost=round(
                        original_total_cost,
                        2
                    ),

                    total_optimized_cost=round(
                        optimized_total_cost,
                        2
                    ),

                    saving=round(
                        saving,
                        2
                    ),

                    retailer=alternative.retailer,

                    priority=(
                        current_product.priority
                    ),

                    quality=(
                        current_product.quality
                    )
                )
            )

            # Replace current product
            optimized_products[product_index] = Product(
                item=current_product.item,

                product_name=(
                    alternative.product_name
                ),

                price=alternative.price,

                quantity=current_product.quantity,

                priority=current_product.priority,

                style=(
                    alternative.style
                    or current_product.style
                ),

                quality=current_product.quality
            )

            changed = True

            # Recalculate immediately
            new_total = calculate_total(
                optimized_products
            )

            if new_total <= budget:
                break

        if not changed:
            break

    return optimized_products, optimized_items


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

    original_total = calculate_total(
        request.products
    )

    original_over_budget = max(
        original_total - request.budget,
        0
    )

    # Already within budget
    if original_total <= request.budget:

        return OptimizationResponse(

            original_total=original_total,

            budget=request.budget,

            original_over_budget=0,

            optimized_total=original_total,

            final_remaining_budget=round(
                request.budget - original_total,
                2
            ),

            final_over_budget_amount=0,

            total_savings=0,

            optimization_successful=True,

            optimized_items=[],

            message=(
                "The design is already within budget. "
                "No optimization was required."
            )
        )

    (
        optimized_products,
        optimized_items
    ) = optimize_products(
        request.products,
        request.budget,
        request.preferences
    )

    optimized_total = calculate_total(
        optimized_products
    )

    total_savings = (
        original_total -
        optimized_total
    )

    final_remaining_budget = max(
        request.budget -
        optimized_total,
        0
    )

    final_over_budget_amount = max(
        optimized_total -
        request.budget,
        0
    )

    optimization_successful = (
        optimized_total <= request.budget
    )

    if optimization_successful:

        message = (
            f"Budget optimization completed successfully. "
            f"The original cost was LKR "
            f"{original_total:,.0f} and the optimized cost is "
            f"LKR {optimized_total:,.0f}. "
            f"Total savings: LKR {total_savings:,.0f}."
        )

    else:

        message = (
            f"Budget optimization was attempted, but the "
            f"design is still over budget by LKR "
            f"{final_over_budget_amount:,.0f}. "
            f"More suitable alternatives may be required."
        )

    return OptimizationResponse(

        original_total=original_total,

        budget=request.budget,

        original_over_budget=round(
            original_over_budget,
            2
        ),

        optimized_total=optimized_total,

        final_remaining_budget=round(
            final_remaining_budget,
            2
        ),

        final_over_budget_amount=round(
            final_over_budget_amount,
            2
        ),

        total_savings=round(
            total_savings,
            2
        ),

        optimization_successful=(
            optimization_successful
        ),

        optimized_items=optimized_items,

        message=message
    )