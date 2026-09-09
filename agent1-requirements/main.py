"""
Agent 1 - Requirement Gathering Agent
Handles chat conversation with user, extracts structured requirements,
handles user authentication.

Run: uvicorn main:app --reload --port 8001
"""
from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional

app = FastAPI(title="Agent 1 - Requirement Gathering")


class ChatMessage(BaseModel):
    user_id: str
    message: str


class ChatResponse(BaseModel):
    reply: str
    requirements_complete: bool = False
    requirements: Optional[dict] = None


@app.get("/health")
def health_check():
    return {"status": "Agent 1 is running"}


@app.post("/chat", response_model=ChatResponse)
def chat(payload: ChatMessage):
    """
    TODO:
    1. Send payload.message to Gemini API along with conversation history
       and a system prompt instructing it to gather: room_type, style,
       budget, room_size, must_haves, color_preference
    2. If the LLM determines enough info has been gathered, set
       requirements_complete=True and return the structured JSON
    3. Otherwise return the LLM's next follow-up question as `reply`
    """
    # Placeholder response
    return ChatResponse(
        reply="What room are you designing today?",
        requirements_complete=False,
        requirements=None
    )


@app.post("/requirements/{user_id}/update")
def update_requirements(user_id: str, updated_fields: dict):
    """
    Called by Agent 2 when a design change affects a core requirement
    (e.g. budget or style), so Agent 1's stored data stays in sync.
    TODO: update requirements in PostgreSQL for this user_id
    """
    return {"status": "updated", "user_id": user_id, "updated_fields": updated_fields}


# Example output JSON contract (sent to Agent 2 once requirements_complete=True):
#
# {
#   "room_type": "living room",
#   "style": "modern minimalist",
#   "budget": 150000,
#   "room_size": "12x10 ft",
#   "must_haves": ["sofa", "coffee table", "TV unit"],
#   "color_preference": "neutral tones"
# }
