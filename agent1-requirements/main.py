"""
Agent 1 - Requirement Gathering Agent

Handles chat conversation with users and extracts
structured interior design requirements.

Run:
uvicorn main:app --reload --port 8001
"""

from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional
from dotenv import load_dotenv

from google import genai
from sqlalchemy import create_engine, text

import os
import json


# ============================================================
# ENVIRONMENT CONFIGURATION
# ============================================================

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY is not configured in .env")


DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("DATABASE_URL is not configured in .env")

engine = create_engine(DATABASE_URL)


# ============================================================
# GEMINI CLIENT
# ============================================================

client = genai.Client(api_key=GEMINI_API_KEY)

MODEL_NAME = "gemini-3.6-flash"


# ============================================================
# FASTAPI APPLICATION
# ============================================================

app = FastAPI(
    title="Agent 1 - Requirement Gathering"
)


# ============================================================
# TEMPORARY CONVERSATION MEMORY
# ============================================================
# Later this will be replaced with PostgreSQL.

conversation_memory = {}


# ============================================================
# REQUEST MODEL
# ============================================================

class ChatMessage(BaseModel):
    user_id: str
    message: str


# ============================================================
# RESPONSE MODEL
# ============================================================

class ChatResponse(BaseModel):
    reply: str
    requirements_complete: bool = False
    requirements: Optional[dict] = None


# ============================================================
# HEALTH CHECK
# ============================================================

@app.get("/health")
def health_check():
    return {
        "status": "Agent 1 is running"
    }


# ============================================================
# GEMINI SYSTEM PROMPT
# ============================================================

SYSTEM_PROMPT = """
You are Agent 1 - Requirement Gathering Agent
for an AI Interior Design Assistant.

Your ONLY responsibility is to collect the user's
interior design requirements.

You must collect these six fields:

1. room_type
2. style
3. budget
4. room_size
5. must_haves
6. color_preference

Rules:

- Have a friendly conversation with the user.
- Ask only ONE question at a time.
- Do not ask for information the user has already provided.
- Understand natural language answers.
- Budget should be interpreted as an amount in LKR.
- must_haves must be returned as a list.
- Do not generate an interior design.
- Do not recommend furniture yet.
- Do not estimate costs yet.
- Your job is ONLY requirement gathering.

When all six fields are available, return the requirements
as JSON.

Use exactly this structure:

{
    "room_type": "bedroom",
    "style": "modern",
    "budget": 300000,
    "room_size": "12 x 10 feet",
    "must_haves": ["bed", "wardrobe"],
    "color_preference": "white and beige"
}

If information is still missing, ask the user
for the next missing requirement.
"""
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
            updated_at = CURRENT_TIMESTAMP
    """)

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
                )
            }
        )

# ============================================================
# CHAT ENDPOINT
# ============================================================

@app.post("/chat", response_model=ChatResponse)
def chat(payload: ChatMessage):

    user_id = payload.user_id
    user_message = payload.message.strip()

    # --------------------------------------------------------
    # Create memory for new user
    # --------------------------------------------------------

    if user_id not in conversation_memory:

        conversation_memory[user_id] = {
            "messages": [],
            "requirements": {
                "room_type": None,
                "style": None,
                "budget": None,
                "room_size": None,
                "must_haves": None,
                "color_preference": None
            }
        }

    user_data = conversation_memory[user_id]

    # --------------------------------------------------------
    # Add user message to conversation
    # --------------------------------------------------------

    user_data["messages"].append(
        {
            "role": "user",
            "content": user_message
        }
    )

    # --------------------------------------------------------
    # Build conversation for Gemini
    # --------------------------------------------------------

    conversation_text = SYSTEM_PROMPT

    conversation_text += "\n\nCurrent requirements:\n"

    conversation_text += json.dumps(
        user_data["requirements"],
        indent=2
    )

    conversation_text += "\n\nConversation history:\n"

    for message in user_data["messages"]:

        conversation_text += (
            f"{message['role']}: "
            f"{message['content']}\n"
        )

    # --------------------------------------------------------
    # Send conversation to Gemini
    # --------------------------------------------------------

    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=conversation_text
    )

    reply = response.text.strip()

    # --------------------------------------------------------
    # Try to extract JSON from Gemini response
    # --------------------------------------------------------

    requirements_complete = False
    requirements = user_data["requirements"]

    try:

        json_start = reply.find("{")
        json_end = reply.rfind("}")

        if json_start != -1 and json_end != -1:

            json_text = reply[
                json_start:json_end + 1
            ]

            parsed_requirements = json.loads(
                json_text
            )

            required_fields = [
                "room_type",
                "style",
                "budget",
                "room_size",
                "must_haves",
                "color_preference"
            ]

            if all(
                field in parsed_requirements
                and parsed_requirements[field] is not None
                for field in required_fields
            ):
                requirements = parsed_requirements
                user_data["requirements"] = parsed_requirements
                requirements_complete = True
                reply = "Requirement Gathering Complete"

                save_requirements(
                    user_id,
                    requirements
                )

    except json.JSONDecodeError:

        requirements_complete = False

    # --------------------------------------------------------
    # Store Gemini response
    # --------------------------------------------------------

    user_data["messages"].append(
        {
            "role": "assistant",
            "content": reply
        }
    )

    # --------------------------------------------------------
    # Return response
    # --------------------------------------------------------

    return ChatResponse(
        reply=reply,
        requirements_complete=requirements_complete,
        requirements=requirements
    )


# ============================================================
# UPDATE REQUIREMENTS
# ============================================================

@app.post("/requirements/{user_id}/update")
def update_requirements(
    user_id: str,
    updated_fields: dict
):

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

    # Update temporary memory
    if user_id not in conversation_memory:

        conversation_memory[user_id] = {
            "messages": [],
            "requirements": {
                "room_type": None,
                "style": None,
                "budget": None,
                "room_size": None,
                "must_haves": None,
                "color_preference": None
            }
        }

    conversation_memory[user_id][
        "requirements"
    ].update(fields_to_update)

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
def get_requirements(user_id: str):

    sql = text("""
        SELECT
            user_id,
            room_type,
            style,
            budget,
            room_size,
            must_haves,
            color_preference,
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

    return {
        "status": "success",
        "user_id": user_id,
        "requirements": requirements
    }