"""
Agent 2 - Design Generation Agent
Takes requirements from Agent 1, generates a 2D room layout with
furniture placement, and returns the furniture list to Agent 3.
Supports a feedback loop for design changes.

Run: uvicorn main:app --reload --port 8002
"""
import os
import re
import json
import requests
import uuid
from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, field_validator
from typing import List, Optional
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from fastapi.middleware.cors import CORSMiddleware

from design_generator import (
    get_furniture_layout,
    draw_layout,
    revise_furniture_layout,
)
from gemini_client import GeminiUnavailableError
from auth import current_user, ensure_owner

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL)

AGENT1_URL = "http://127.0.0.1:8001"

app = FastAPI(title="Agent 2 - Design Generation")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

os.makedirs("designs", exist_ok=True)
app.mount("/designs", StaticFiles(directory="designs"), name="designs")


class Requirements(BaseModel):
    user_id: str
    room_type: str
    style: str
    budget: int
    room_size: Optional[str] = None
    must_haves: List[str] = []
    color_preference: Optional[str] = None
    # Structured details from Agent 1 (item sizes, placement wishes, doors/windows)
    occupant: Optional[str] = "adult"   # adult / teen / child / baby
    furniture: List[dict] = []
    placements: List[dict] = []
    openings: List[dict] = []
    other_notes: List[str] = []

    @field_validator('budget')
    @classmethod
    def budget_must_be_positive(cls, v):
        if v <= 0:
            raise ValueError('budget must be greater than 0')
        return v

    @field_validator('room_type', 'style')
    @classmethod
    def must_not_be_empty(cls, v):
        if not v or not v.strip():
            raise ValueError('field cannot be empty')
        return v


class FurnitureItem(BaseModel):
    item: str
    style: str
    qty: int = 1                      # product options wanted from Agent 3
    quantity: int = 1                 # pieces needed in the room (2 bedside tables -> 2)
    color: Optional[str] = None       # room colour preference, for colour matching in Agent 3
    size: Optional[str] = None        # size words from the user / layout ("small", "queen", "compact")
    audience: Optional[str] = None    # who the room is for, so Agent 3 skips kids' furniture in adult rooms
    priority: str = "flexible"        # "optional" for extras the designer added; cut first by Agent 4


class DesignResponse(BaseModel):
    layout_image_path: str
    furniture_needed: List[FurnitureItem]
    warnings: List[str] = []
    # Core requirements the user changed through a revision (e.g. {"budget": 250000})
    requirement_updates: dict = {}


class ChangeRequest(BaseModel):
    user_id: str
    original_requirements: Requirements
    change_text: str


def get_latest_layout(user_id: str) -> Optional[dict]:
    sql = text("""
        SELECT layout_data FROM designs
        WHERE user_id = :user_id
        ORDER BY created_at DESC, id DESC
        LIMIT 1
    """)
    with engine.connect() as connection:
        row = connection.execute(sql, {"user_id": user_id}).first()
    return row[0] if row else None


def _words(text: str) -> set:
    return set(re.findall(r"[a-z0-9]+", (text or "").lower()))


def furniture_needed_from(layout_data: dict, requirements: dict) -> List[FurnitureItem]:
    """
    One entry per distinct piece, with how many are needed, the room colour and any size words.
    Curtains/rugs/mirrors are still things to buy, so every placed piece is listed.
    """
    counts, suggested_only = {}, {}
    for f in layout_data.get("furniture", []):
        counts[f["item"]] = counts.get(f["item"], 0) + 1
        suggested_only[f["item"]] = suggested_only.get(f["item"], True) and f.get("source") == "suggested"

    compact = {w.split("compact ", 1)[1].split(" (")[0] for w in layout_data.get("warnings", [])
               if w.startswith("Used a compact ")}
    requested = requirements.get("furniture") or []

    items = []
    for name, quantity in counts.items():
        sizes = []
        for f in requested:  # the user's own size words, e.g. "small" cupboard, "queen" bed
            if f.get("size") and (_words(f["name"]) <= _words(name) or _words(name) <= _words(f["name"])):
                sizes.append(f["size"])
        if name in compact:
            sizes.append("compact")
        items.append(FurnitureItem(
            item=name,
            style=requirements.get("style") or "",
            quantity=quantity,
            color=requirements.get("color_preference"),
            size=" ".join(sizes) or None,
            audience=requirements.get("occupant") or "adult",
            priority="optional" if suggested_only.get(name) else "flexible",
        ))
    return items


def save_design(user_id: str, requirements: dict, layout_data: dict, image_path: str):
    sql = text("""
        INSERT INTO designs (user_id, requirements, layout_data, image_path)
        VALUES (:user_id, :requirements, :layout_data, :image_path)
    """)
    with engine.begin() as connection:
        connection.execute(sql, {
            "user_id": user_id,
            "requirements": json.dumps(requirements),
            "layout_data": json.dumps(layout_data),
            "image_path": image_path
        })


@app.get("/health")
def health_check():
    return {"status": "Agent 2 is running"}


@app.post("/generate-design", response_model=DesignResponse)
def generate_design(requirements: Requirements, me: str = Depends(current_user)):
    ensure_owner(me, requirements.user_id)
    layout_data = get_furniture_layout(requirements.model_dump())
    image_path = draw_layout(
        layout_data,
        save_path=f"designs/{uuid.uuid4().hex}.png",
        color_preference=requirements.color_preference
    )

    furniture_needed = furniture_needed_from(layout_data, requirements.model_dump())
    layout_data["furniture_needed"] = [f.model_dump() for f in furniture_needed]  # for session restore
    save_design(requirements.user_id, requirements.model_dump(), layout_data, image_path)

    return DesignResponse(
        layout_image_path=image_path,
        furniture_needed=furniture_needed,
        warnings=layout_data.get("warnings", [])
    )


@app.post("/revise-design", response_model=DesignResponse)
def revise_design(change: ChangeRequest, me: str = Depends(current_user),
                  authorization: str = Header(default="")):
    ensure_owner(me, change.user_id)
    requirements = change.original_requirements.model_dump()
    try:
        layout_data, updated_fields = revise_furniture_layout(
            requirements, change.change_text, get_latest_layout(change.user_id)
        )
    except GeminiUnavailableError:
        raise HTTPException(status_code=503, detail="The AI is busy right now. Please try the change again in a minute.")

    image_path = draw_layout(
        layout_data,
        save_path=f"designs/{uuid.uuid4().hex}.png",
        color_preference=updated_fields.get("color_preference") or change.original_requirements.color_preference
    )

    if updated_fields:
        try:
            requests.post(
                f"{AGENT1_URL}/requirements/{change.user_id}/update",
                json=updated_fields,
                headers={"Authorization": authorization},  # act as the logged-in user
                timeout=5
            )
        except requests.exceptions.RequestException:
            print("WARNING: Could not reach Agent 1 to sync updated requirements")

    updated_requirements = {**requirements, **updated_fields}
    furniture_needed = furniture_needed_from(layout_data, updated_requirements)
    layout_data["furniture_needed"] = [f.model_dump() for f in furniture_needed]  # for session restore
    save_design(change.user_id, updated_requirements, layout_data, image_path)

    return DesignResponse(
        layout_image_path=image_path,
        furniture_needed=furniture_needed,
        warnings=layout_data.get("warnings", []),
        requirement_updates=updated_fields
    )


# NOTE: not under /designs/..., which is where the layout images are served from
# (the static mount would swallow these routes).
@app.get("/design-history/{user_id}")
def get_designs(user_id: str, me: str = Depends(current_user)):
    ensure_owner(me, user_id)
    sql = text("""
        SELECT id, requirements, layout_data, image_path, created_at
        FROM designs
        WHERE user_id = :user_id
        ORDER BY created_at DESC
    """)
    with engine.connect() as connection:
        results = connection.execute(sql, {"user_id": user_id}).mappings().all()

    return {"user_id": user_id, "designs": [dict(r) for r in results]}


# Example output JSON contract (sent to Agent 3):
#
# {
#   "layout_image_path": "designs/design_v1.png",
#   "furniture_needed": [
#     {"item": "3-seater sofa", "style": "modern", "qty": 1},
#     {"item": "coffee table", "style": "minimalist", "qty": 1}
#   ]
# }

@app.delete("/design-history/{user_id}")
def delete_designs(user_id: str, me: str = Depends(current_user)):
    ensure_owner(me, user_id)
    sql = text("DELETE FROM designs WHERE user_id = :user_id")
    with engine.begin() as connection:
        connection.execute(sql, {"user_id": user_id})
    return {"status": "deleted", "user_id": user_id}