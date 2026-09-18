"""
Agent 2 - Design Generation Agent
Takes requirements from Agent 1, generates a 2D room layout with
furniture placement, and returns the furniture list to Agent 3.
Supports a feedback loop for design changes.

Run: uvicorn main:app --reload --port 8002
"""
from fastapi import FastAPI
from pydantic import BaseModel
from typing import List, Optional
from design_generator import get_furniture_layout, draw_layout

app = FastAPI(title="Agent 2 - Design Generation")


class Requirements(BaseModel):
    room_type: str
    style: str
    budget: int
    room_size: Optional[str] = None
    must_haves: List[str] = []
    color_preference: Optional[str] = None


class FurnitureItem(BaseModel):
    item: str
    style: str
    qty: int = 1


class DesignResponse(BaseModel):
    layout_image_path: str
    furniture_needed: List[FurnitureItem]


class ChangeRequest(BaseModel):
    user_id: str
    original_requirements: Requirements
    change_text: str


@app.get("/health")
def health_check():
    return {"status": "Agent 2 is running"}


@app.post("/generate-design", response_model=DesignResponse)
def generate_design(requirements: Requirements):
    layout_data = get_furniture_layout(requirements.dict())
    image_path = draw_layout(layout_data, color_preference=requirements.color_preference)

    furniture_list = [
        FurnitureItem(item=f["item"], style=requirements.style, qty=1)
        for f in layout_data.get("furniture", [])
    ]

    return DesignResponse(
        layout_image_path=image_path,
        furniture_needed=furniture_list
    )


@app.post("/revise-design", response_model=DesignResponse)
def revise_design(change: ChangeRequest):
    """
    TODO:
    1. Re-prompt Gemini with original_requirements + change_text
    2. Re-render the layout image with updated furniture/placement
    3. If the change affects a core requirement (budget/style/room_type),
       call Agent 1's /requirements/{user_id}/update endpoint to keep data in sync
    """
    return DesignResponse(
        layout_image_path="designs/placeholder_v2.png",
        furniture_needed=[
            FurnitureItem(item="3-seater sofa", style="updated style", qty=1),
        ]
    )


# Example output JSON contract (sent to Agent 3):
#
# {
#   "layout_image_path": "designs/design_v1.png",
#   "furniture_needed": [
#     {"item": "3-seater sofa", "style": "modern", "qty": 1},
#     {"item": "coffee table", "style": "minimalist", "qty": 1}
#   ]
# }
