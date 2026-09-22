"""
Agent 1 - Requirement Gathering Agent

Handles chat conversation with users and extracts
structured interior design requirements.

Every turn Gemini returns structured JSON (reply + the full, updated
requirements), so details like "a mirror above a small cupboard" are captured
the moment the user says them instead of only at the end.

Run:
uvicorn main:app --reload --port 8001
"""

from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import List, Optional
from dotenv import load_dotenv
from passlib.hash import bcrypt
from google.genai import types
from sqlalchemy import create_engine, text
from fastapi.middleware.cors import CORSMiddleware

import os
import json

from gemini_client import generate_json, GeminiUnavailableError
from auth import create_token, current_user, ensure_owner

# ============================================================
# ENVIRONMENT CONFIGURATION
# ============================================================

load_dotenv()

if not os.getenv("GEMINI_API_KEY"):
    raise ValueError("GEMINI_API_KEY is not configured in .env")


DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("DATABASE_URL is not configured in .env")

engine = create_engine(DATABASE_URL)

# Extra structured details (items, placements, doors/windows) live in a JSONB
# column next to the original six fields. Additive and safe to run every start.
with engine.begin() as _connection:
    _connection.execute(text("ALTER TABLE requirements ADD COLUMN IF NOT EXISTS details JSONB"))


# ============================================================
# FASTAPI APPLICATION
# ============================================================

app = FastAPI(
    title="Agent 1 - Requirement Gathering"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================
# REQUEST MODEL
# ============================================================

class ChatMessage(BaseModel):
    user_id: str
    message: str
    # Set when the user answered with the door/window picker instead of typing:
    # [{"type": "door"|"window", "wall": "bottom"|"top"|"left"|"right", "position": "left"|"center"|"right"|"start"|"end"}]
    openings: Optional[List[dict]] = None


# ============================================================
# RESPONSE MODEL
# ============================================================

class ChatResponse(BaseModel):
    reply: str
    requirements_complete: bool = False
    requirements: Optional[dict] = None
    # "openings" when the reply asks where the door/windows are, so the UI can show the picker
    widget: Optional[str] = None

class SignupRequest(BaseModel):
    username: str
    password: str


class LoginRequest(BaseModel):
    username: str
    password: str


class AuthResponse(BaseModel):
    user_id: str
    username: str
    token: str          # send as "Authorization: Bearer <token>" to Agents 1 and 2
    expires_at: int     # unix seconds; log in again after this


# ============================================================
# STRUCTURED OUTPUT SCHEMA (what Gemini must return each turn)
# ============================================================

class FurnitureRequest(BaseModel):
    name: str = Field(description="Furniture item, e.g. 'small cupboard', 'queen bed', 'wall mirror'")
    qty: int = Field(description="How many of this item. 1 if the user did not say")
    size: str = Field(description="'small', 'medium', 'large', exact dimensions if given, or '' if not said")
    notes: str = Field(description="Any other detail the user gave about this item (material, colour, type), plus 'quantity assumed' if you chose the qty, or ''")


class PlacementRequest(BaseModel):
    item: str = Field(description="Name of the item being placed (must match an item name)")
    relation: str = Field(description=(
        "One of: above, below, on_top_of, next_to, in_front_of, facing, opposite, "
        "against_wall, in_corner, near_window, away_from_window, near_door, away_from_door, centered"
    ))
    target: str = Field(description=(
        "What it relates to: another item name, 'window', 'door', a wall "
        "('top', 'bottom', 'left', 'right') or '' if not needed"
    ))
    notes: str = Field(description="The user's own words for this placement")


class OpeningRequest(BaseModel):
    type: str = Field(description="'door' or 'window'")
    wall: str = Field(description="'top', 'bottom', 'left', 'right' or 'unknown'")
    position: str = Field(description=(
        "On the top/bottom walls: 'left', 'center' or 'right'. On the left/right walls: "
        "'start' (near the entrance), 'center' or 'end' (far end). '' if not said"
    ))
    notes: str = Field(description="The user's own words, or ''")


class RequirementsState(BaseModel):
    room_type: Optional[str]
    style: Optional[str]
    budget: Optional[float] = Field(description="Budget in LKR as a plain number, e.g. 150000")
    room_size: Optional[str] = Field(description="Normalised as '<width> x <length> ft', e.g. '12 x 10 ft'")
    color_preference: Optional[str]
    occupant: str = Field(description=(
        "Who mainly uses the room: 'adult', 'teen', 'child' or 'baby'. 'adult' unless the user says or "
        "clearly implies otherwise (kids room, nursery, my son's room, for my 8 year old)"
    ))
    furniture: List[FurnitureRequest]
    placements: List[PlacementRequest]
    openings: List[OpeningRequest]
    other_notes: List[str] = Field(description="Anything else relevant: who uses the room, things to avoid, etc.")


class TurnOutput(BaseModel):
    # Field order matters: Gemini writes fields in this order, so it records what the
    # latest message said BEFORE writing the reply (and won't re-ask for it).
    requirements: RequirementsState
    ready: bool = Field(description="True only when all required fields are filled and nothing else needs asking")
    reply: str = Field(description="Your next message to the user. Never ask for anything already in requirements")
    asks_about_openings: bool = Field(description="True if your reply asks where the door or windows are")


# ============================================================
# HEALTH CHECK
# ============================================================

@app.get("/health")
def health_check():
    return {
        "status": "Agent 1 is running"
    }

# ============================================================
# SIGNUP
# ============================================================

@app.post("/signup", response_model=AuthResponse)
def signup(payload: SignupRequest):
    username = payload.username.strip()
    password = payload.password

    if not username or not password:
        raise HTTPException(status_code=400, detail="Username and password are required")

    if len(password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")

    password_hash = bcrypt.hash(password)

    sql = text("""
        INSERT INTO users (username, password_hash)
        VALUES (:username, :password_hash)
        RETURNING id
    """)

    try:
        with engine.begin() as connection:
            result = connection.execute(sql, {
                "username": username,
                "password_hash": password_hash
            })
            user_id = result.scalar()
    except Exception:
        raise HTTPException(status_code=409, detail="Username already taken")

    token, expires_at = create_token(user_id)
    return AuthResponse(user_id=str(user_id), username=username, token=token, expires_at=expires_at)


# ============================================================
# LOGIN
# ============================================================

@app.post("/login", response_model=AuthResponse)
def login(payload: LoginRequest):
    username = payload.username.strip()
    password = payload.password

    sql = text("SELECT id, password_hash FROM users WHERE username = :username")

    with engine.connect() as connection:
        result = connection.execute(sql, {"username": username}).mappings().first()

    if not result or not bcrypt.verify(password, result["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid username or password")

    token, expires_at = create_token(result["id"])
    return AuthResponse(user_id=str(result["id"]), username=username, token=token, expires_at=expires_at)

# ============================================================
# GEMINI SYSTEM PROMPT
# ============================================================

SYSTEM_PROMPT = """
You are Agent 1 - Requirement Gathering Agent for an AI Interior Design
Assistant for Sri Lankan homes. Your ONLY job is to collect the user's
requirements. Do not design, recommend products or estimate costs.

REQUIRED fields (must all be filled before you finish):
  room_type, style, budget, room_size, furniture (at least one item), color_preference

ALSO CAPTURE whenever the user mentions them (never ignore these details):
  - furniture: every item with qty, size ("small", "large", "6ft", ...) and notes
  - placements: every spatial wish, as item + relation + target
  - openings: where the door(s) and window(s) are
  - occupant: who the room is for (adult / teen / child / baby). Infer it, don't ask:
    "kids room", "nursery", "my daughter's room" -> child/baby; otherwise adult.
    This decides whether kids' furniture is suitable, so never guess child without a hint.
  - other_notes: anything else useful (who uses the room, things to avoid, ...)

Examples of what to capture:
  "I want a mirror above a small cupboard"
    furniture: [{name:"small cupboard", qty:1, size:"small"}, {name:"mirror", qty:1, size:""}]
    placements: [{item:"mirror", relation:"above", target:"small cupboard"}]
  "bed against the left wall, two bedside tables on each side"
    furniture: [{name:"bed"...}, {name:"bedside table", qty:2 ...}]
    placements: [{item:"bed", relation:"against_wall", target:"left"},
                 {item:"bedside table", relation:"next_to", target:"bed"}]
  "study desk near the window"
    placements: [{item:"study desk", relation:"near_window", target:"window"}]
  "TV mounted on the wall opposite the sofa"
    furniture: [{name:"wall-mounted TV"...}]
    placements: [{item:"wall-mounted TV", relation:"opposite", target:"sofa"}]

Wall convention (plan view): the wall with the main door is "bottom" unless the
user says otherwise. Standing in the doorway looking into the room, the wall on
your left is "left", on your right is "right", the far wall is "top".
"Window opposite the door" means the window is on the "top" wall.

Conversation rules:
  - Friendly, short messages. Ask only ONE question at a time.
  - Never ask for something the user already told you.
  - Budget is in LKR. Convert "1.5 lakhs" to 150000, "300k" to 300000.
  - Convert room size to feet, formatted "<width> x <length> ft"
    (e.g. "3m x 4m" becomes "10 x 13 ft", "12 by 10" becomes "12 x 10 ft").
  - Quantities:
      * No number given for a single thing ("a wardrobe", "wardrobe"): qty 1.
      * A number given ("two bedside tables", "a pair of", "3 chairs"): use it.
      * A plural with no number ("some chairs", "dining chairs", "a few shelves"):
        choose a sensible qty (e.g. 4 dining chairs for a 4-seater table, 2 bedside
        tables for a double bed) and add "quantity assumed" to that item's notes.
      * Ask about a quantity ONLY if it clearly changes the design and you cannot
        infer it (e.g. "chairs" with no table and no room context). Ask at most once.
  - After the required fields are filled, if the user has not said where the door
    and window are, ask ONCE, in plain words, and set asks_about_openings=true.
    The app then shows a small room picker. Never mention "top"/"bottom" walls to
    the user; say "the wall you walk in through", "the wall opposite the door",
    "the left wall as you walk in", etc. If they don't know, set wall "unknown"
    and move on.
  - The user may add, change or remove things at any time. Always return the FULL
    updated requirements. Only remove an item or placement if the user asked to.
  - Set ready=true only when every required field is filled and you have asked
    about the door/window. When ready, keep the reply to one short friendly line.
"""

REQUIRED_FIELDS = ["room_type", "style", "budget", "room_size", "must_haves", "color_preference"]
LOCKED_REPLY = (
    "Your requirements are final and your design is ready. To change it (add or remove a piece, "
    "move something, change the budget or colours), use the 'Request a change' box under the layout. "
    "For a completely different room, click New chat."
)
OCCUPANTS = {"adult": "adults", "teen": "a teenager", "child": "a child", "baby": "a baby"}


def empty_requirements() -> dict:
    return {
        "room_type": None,
        "style": None,
        "budget": None,
        "room_size": None,
        "must_haves": None,
        "color_preference": None,
        "occupant": "adult",
        "furniture": [],
        "placements": [],
        "openings": [],
        "other_notes": [],
    }


def normalize_requirements(state: dict) -> dict:
    """Turn Gemini's state into the requirements dict other agents consume."""
    requirements = empty_requirements()
    for key in ["room_type", "style", "room_size", "color_preference"]:
        value = state.get(key)
        requirements[key] = value.strip() if isinstance(value, str) and value.strip() else None

    occupant = (state.get("occupant") or "").strip().lower()
    requirements["occupant"] = occupant if occupant in OCCUPANTS else "adult"

    budget = state.get("budget")
    try:
        budget = float(str(budget).replace(",", "")) if budget is not None else None
    except (ValueError, TypeError):
        budget = None
    requirements["budget"] = budget if budget and budget > 0 else None

    furniture = [f for f in state.get("furniture") or [] if (f.get("name") or "").strip()]
    for f in furniture:
        f["name"] = f["name"].strip()
        f["qty"] = max(1, int(f.get("qty") or 1))
    requirements["furniture"] = furniture
    # must_haves stays a flat list of names for backwards compatibility
    requirements["must_haves"] = [f["name"] for f in furniture] or None

    requirements["placements"] = [p for p in state.get("placements") or [] if (p.get("item") or "").strip()]
    requirements["openings"] = [o for o in state.get("openings") or [] if o.get("type") in ("door", "window")]
    requirements["other_notes"] = [n for n in state.get("other_notes") or [] if n and n.strip()]
    return requirements


def missing_fields(requirements: dict) -> list:
    return [field for field in REQUIRED_FIELDS if not requirements.get(field)]


# Plan-view wall labels (used by Agent 2) in words a user understands
WALL_NAMES = {
    "bottom": "the wall you walk in through",
    "top": "the wall opposite the door",
    "left": "the left wall (as you walk in)",
    "right": "the right wall (as you walk in)",
}
POSITION_NAMES = {
    "left": "on the left", "right": "on the right", "center": "in the middle",
    "start": "near the entrance", "end": "at the far end",
}
VALID_POSITIONS = {"bottom": {"left", "center", "right"}, "top": {"left", "center", "right"},
                   "left": {"start", "center", "end"}, "right": {"start", "center", "end"}}


def clean_openings(openings) -> list:
    """Validate door/window picks coming straight from the UI picker."""
    cleaned = []
    for o in openings or []:
        kind, wall, position = o.get("type"), o.get("wall"), o.get("position") or ""
        if kind in ("door", "window") and wall in VALID_POSITIONS:
            cleaned.append({"type": kind, "wall": wall,
                            "position": position if position in VALID_POSITIONS[wall] else "",
                            "notes": "picked on the room picker"})
    return cleaned


def completion_summary(requirements: dict) -> str:
    budget = requirements.get("budget")
    lines = [
        "Great, I have everything I need. Here's what I noted:",
        f"• {requirements['room_type'].capitalize()}, {requirements['style']} style, {requirements['room_size']}",
        f"• Budget: LKR {budget:,.0f}" if budget else "",
        f"• Colours: {requirements['color_preference']}",
        f"• For: {OCCUPANTS[requirements.get('occupant') or 'adult']}",
    ]
    items = []
    for f in requirements.get("furniture", []):
        label = f["name"]
        if f.get("size") and f["size"].lower() not in label.lower():
            label = f"{label} ({f['size']})"
        if f.get("qty", 1) > 1:
            label = f"{f['qty']} x {label}"
        items.append(label)
    if items:
        lines.append("• Items: " + ", ".join(items))
    for p in requirements.get("placements", []):
        relation = p["relation"].replace("_", " ")
        target = f" {p['target']}" if p.get("target") and p["target"] not in relation else ""
        lines.append(f"• {p['item']} {relation}{target}")
    for o in requirements.get("openings", []):
        if o.get("wall") in WALL_NAMES:
            spot = POSITION_NAMES.get(o.get("position") or "", "")
            lines.append(f"• {o['type'].capitalize()}: {WALL_NAMES[o['wall']]}" + (f", {spot}" if spot else ""))
    assumed = [f["name"] for f in requirements.get("furniture", []) if "quantity assumed" in (f.get("notes") or "").lower()]
    if assumed:
        lines.append(f"• I assumed how many {', '.join(assumed)} you need. Tell me if that's wrong.")
    for note in requirements.get("other_notes", []):
        lines.append(f"• {note}")
    lines.append("Generating your layout now. For small changes, use the box under the layout. "
                 "For a different room, start a New chat.")
    return "\n".join(line for line in lines if line)


# ============================================================
# DATABASE HELPERS
# ============================================================

def save_requirements(user_id, requirements):

    sql = text("""
        INSERT INTO requirements (
            user_id,
            room_type,
            style,
            budget,
            room_size,
            must_haves,
            color_preference,
            details,
            updated_at
        )
        VALUES (
            :user_id,
            :room_type,
            :style,
            :budget,
            :room_size,
            :must_haves,
            :color_preference,
            :details,
            CURRENT_TIMESTAMP
        )
        ON CONFLICT (user_id)
        DO UPDATE SET
            room_type = EXCLUDED.room_type,
            style = EXCLUDED.style,
            budget = EXCLUDED.budget,
            room_size = EXCLUDED.room_size,
            must_haves = EXCLUDED.must_haves,
            color_preference = EXCLUDED.color_preference,
            details = EXCLUDED.details,
            updated_at = CURRENT_TIMESTAMP
    """)

    details = {key: requirements.get(key, []) for key in ["furniture", "placements", "openings", "other_notes"]}
    details["occupant"] = requirements.get("occupant") or "adult"

    with engine.begin() as connection:

        connection.execute(
            sql,
            {
                "user_id": user_id,
                "room_type": requirements.get("room_type"),
                "style": requirements.get("style"),
                "budget": requirements.get("budget"),
                "room_size": requirements.get("room_size"),
                "must_haves": json.dumps(
                    requirements.get("must_haves")
                ),
                "color_preference": requirements.get(
                    "color_preference"
                ),
                "details": json.dumps(details)
            }
        )

def get_conversation(user_id: str) -> dict:
    sql = text("SELECT messages, requirements FROM conversations WHERE user_id = :user_id")
    with engine.connect() as connection:
        result = connection.execute(sql, {"user_id": user_id}).mappings().first()

    if result:
        requirements = empty_requirements()
        requirements.update(result["requirements"] or {})
        return {
            "messages": result["messages"],
            "requirements": requirements
        }

    return {
        "messages": [],
        "requirements": empty_requirements()
    }


def save_conversation(user_id: str, messages: list, requirements: dict):
    sql = text("""
        INSERT INTO conversations (user_id, messages, requirements, updated_at)
        VALUES (:user_id, :messages, :requirements, CURRENT_TIMESTAMP)
        ON CONFLICT (user_id)
        DO UPDATE SET
            messages = EXCLUDED.messages,
            requirements = EXCLUDED.requirements,
            updated_at = CURRENT_TIMESTAMP
    """)
    with engine.begin() as connection:
        connection.execute(sql, {
            "user_id": user_id,
            "messages": json.dumps(messages),
            "requirements": json.dumps(requirements)
        })


def requirements_saved(user_id: str) -> bool:
    sql = text("SELECT 1 FROM requirements WHERE user_id = :user_id")
    with engine.connect() as connection:
        return connection.execute(sql, {"user_id": user_id}).first() is not None


def build_contents(messages: list) -> list:
    contents = []
    for message in messages:
        role = "model" if message["role"] == "assistant" else "user"
        contents.append(types.Content(role=role, parts=[types.Part.from_text(text=message["content"])]))
    return contents


# ============================================================
# CHAT ENDPOINT
# ============================================================

@app.post("/chat", response_model=ChatResponse)
def chat(payload: ChatMessage, me: str = Depends(current_user)):

    ensure_owner(me, payload.user_id)
    user_id = payload.user_id
    user_message = payload.message.strip()

    # Requirements are final once the design is generated. Changes go through the layout
    # (Agent 2's revise box); a different room needs a new chat. Don't re-open them here.
    if requirements_saved(user_id):
        return ChatResponse(
            reply=LOCKED_REPLY,
            requirements_complete=False,
            requirements=get_conversation(user_id)["requirements"]
        )

    user_data = get_conversation(user_id)
    user_data["messages"].append({
        "role": "user",
        "content": user_message
    })

    # Door/window picked on the room picker: exact data, no need for Gemini to interpret it
    picked_openings = clean_openings(payload.openings) if payload.openings is not None else None
    if picked_openings:
        user_data["requirements"]["openings"] = picked_openings

    current = dict(user_data["requirements"])
    current.pop("must_haves", None)  # derived from furniture
    system_instruction = (
        SYSTEM_PROMPT
        + "\n\nRequirements captured so far (update and return the full object):\n"
        + json.dumps(current, indent=2)
        + f"\n\nRequired fields missing BEFORE the user's latest message: "
        + f"{missing_fields(user_data['requirements']) or 'none'}. "
        + "First record everything the latest message provides, then ask only for what is still missing."
    )

    try:
        turn = generate_json(
            build_contents(user_data["messages"]),
            response_schema=TurnOutput,
            system_instruction=system_instruction,
        )
    except GeminiUnavailableError as e:
        print("GEMINI ERROR:", repr(e))
        return ChatResponse(
            reply="Our AI assistant is very busy right now. Please send your message again in a minute.",
            requirements_complete=False,
            requirements=user_data["requirements"]
        )
    except Exception as e:
        print("GEMINI ERROR:", repr(e))
        return ChatResponse(
            reply="Sorry, something went wrong on my side. Please send that again.",
            requirements_complete=False,
            requirements=user_data["requirements"]
        )

    requirements = normalize_requirements(turn.get("requirements") or {})
    if picked_openings:
        requirements["openings"] = picked_openings
    missing = missing_fields(requirements)
    requirements_complete = not missing and bool(turn.get("ready"))

    widget = None
    if requirements_complete:
        reply = completion_summary(requirements)
        save_requirements(user_id, requirements)
    else:
        reply = (turn.get("reply") or "").strip()
        if not reply:
            reply = f"Could you tell me your {missing[0].replace('_', ' ')}?" if missing else "Anything else?"
        if turn.get("asks_about_openings") and payload.openings is None:
            widget = "openings"

    assistant_message = {"role": "assistant", "content": reply}
    if widget:
        assistant_message["widget"] = widget
    user_data["messages"].append(assistant_message)

    save_conversation(user_id, user_data["messages"], requirements)

    return ChatResponse(
        reply=reply,
        requirements_complete=requirements_complete,
        requirements=requirements,
        widget=widget
    )

@app.get("/chat-history/{user_id}")
def get_chat_history(user_id: str, me: str = Depends(current_user)):
    ensure_owner(me, user_id)
    data = get_conversation(user_id)
    return {
        "user_id": user_id,
        "messages": data["messages"],
        "requirements": data["requirements"],
        "requirements_complete": requirements_saved(user_id),
    }

# ============================================================
# UPDATE REQUIREMENTS
# ============================================================

@app.post("/requirements/{user_id}/update")
def update_requirements(
    user_id: str,
    updated_fields: dict,
    me: str = Depends(current_user)   # Agent 2 forwards the user's token
):
    ensure_owner(me, user_id)

    allowed_fields = {
        "room_type",
        "style",
        "budget",
        "room_size",
        "must_haves",
        "color_preference"
    }

    # Keep only valid requirement fields
    fields_to_update = {
        key: value
        for key, value in updated_fields.items()
        if key in allowed_fields
    }

    if not fields_to_update:
        return {
            "status": "error",
            "message": "No valid requirement fields provided"
        }

    # Keep the conversation's copy in sync so the chat agent sees the change
    user_data = get_conversation(user_id)
    user_data["requirements"].update(fields_to_update)
    save_conversation(user_id, user_data["messages"], user_data["requirements"])

    # Prepare SQL update
    set_clauses = []

    parameters = {
        "user_id": user_id
    }

    for field, value in fields_to_update.items():

        set_clauses.append(
            f"{field} = :{field}"
        )

        if field == "must_haves":
            parameters[field] = json.dumps(value)
        else:
            parameters[field] = value

    set_clauses.append(
        "updated_at = CURRENT_TIMESTAMP"
    )

    sql = text(f"""
        UPDATE requirements
        SET {", ".join(set_clauses)}
        WHERE user_id = :user_id
    """)

    with engine.begin() as connection:

        result = connection.execute(
            sql,
            parameters
        )

    if result.rowcount == 0:

        return {
            "status": "not_found",
            "user_id": user_id
        }

    return {
        "status": "updated",
        "user_id": user_id,
        "updated_fields": fields_to_update
    }


# ============================================================
# GET REQUIREMENTS
# ============================================================

@app.get("/requirements/{user_id}")
def get_requirements(user_id: str, me: str = Depends(current_user)):
    ensure_owner(me, user_id)

    sql = text("""
        SELECT
            user_id,
            room_type,
            style,
            budget,
            room_size,
            must_haves,
            color_preference,
            details,
            created_at,
            updated_at
        FROM requirements
        WHERE user_id = :user_id
    """)

    with engine.connect() as connection:

        result = connection.execute(
            sql,
            {"user_id": user_id}
        ).mappings().first()

    if not result:

        return {
            "status": "not_found",
            "user_id": user_id,
            "requirements": None
        }

    requirements = dict(result)

    # Convert JSON string back into a Python list
    if requirements["must_haves"]:

        requirements["must_haves"] = json.loads(
            requirements["must_haves"]
        )

    # Flatten the structured details next to the core fields
    requirements.update(requirements.pop("details") or {})

    return {
        "status": "success",
        "user_id": user_id,
        "requirements": requirements
    }

@app.delete("/conversation/{user_id}")
def delete_conversation(user_id: str, me: str = Depends(current_user)):
    ensure_owner(me, user_id)
    with engine.begin() as connection:
        connection.execute(text("DELETE FROM conversations WHERE user_id = :user_id"), {"user_id": user_id})
        connection.execute(text("DELETE FROM requirements WHERE user_id = :user_id"), {"user_id": user_id})
    return {"status": "deleted", "user_id": user_id}
