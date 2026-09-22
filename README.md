# AI Interior Design Assistant

An agentic AI system that helps Sri Lankan homeowners design a room affordably —
understanding requirements through chat, generating a 2D layout, finding matching
local furniture, and estimating total cost.

IT 3041 - Information Retrieval and Web Analytics | SLIIT

## System Architecture

```
User (React frontend)
   -> Agent 1: Requirement Gathering  (port 8001)
   -> Agent 2: Design Generation      (port 8002)   [feedback loop with user]
   -> Agent 3: Furniture Search (IR)  (port 8003)
   -> Agent 4: Cost Estimation        (port 8004)
   -> Final output: design + shopping list + total cost
```

## Repo Structure

```
/agent1-requirements     - Chat, requirement extraction, user auth (FastAPI + Gemini + PostgreSQL)
/agent2-design            - 2D layout generation (FastAPI + Gemini + matplotlib/PIL + PostgreSQL)
/agent3-furniture-search  - Furniture matching / IR (FastAPI + PostgreSQL)
/agent4-cost-estimation   - Cost calculation (FastAPI)
/frontend                 - React app
```

## Setup (per agent)

```bash
cd agent1-requirements
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8001
```

Repeat for agent2 (port 8002), agent3 (port 8003), agent4 (port 8004).

Each agent needs a `.env` file for secrets (Gemini API key, DB connection string) —
create `.env` in each agent folder, never commit it (already in `.gitignore`).

## Login and security

Agent 1 issues a signed login token at `/signup` and `/login` (HMAC-SHA256, valid 7 days).
The frontend sends it as `Authorization: Bearer <token>` to Agents 1 and 2, which take the user
from the token and refuse other users' data (401 = not logged in / expired, 403 = not yours).
Agent 2 forwards the token when it syncs requirement changes to Agent 1. Agents 3 and 4 hold no
user data and stay open. Both `agent1-requirements/.env` and `agent2-design/.env` need the same:

```
AUTH_SECRET=<long random string>
AUTH_TOKEN_TTL_HOURS=168
```

## Database and "My rooms"

The agents create their own tables on startup, so a new machine only needs an empty PostgreSQL
database and `DATABASE_URL` in each agent's `.env`:

| Table | Created by | Holds |
|---|---|---|
| `users`, `projects`, `conversations`, `requirements` | Agent 1 | accounts, rooms, chats, final requirements |
| `designs` | Agent 2 | layout versions (images in `agent2-design/designs/`) |
| `products` | Agent 3 | catalog; fill it with `python import_csv.py real_products.csv` |

Each user can have several rooms (**projects**). A project has one chat, one set of final
requirements and any number of design versions. *New chat* starts a new room; earlier rooms stay
under *My rooms*. Older databases (one chat per user) are upgraded automatically on Agent 1's
first start: each user's existing data becomes their first room.

## JSON Contracts Between Agents

**Agent 1 -> Agent 2:**
```json
{
  "room_type": "living room",
  "style": "modern minimalist",
  "budget": 150000,
  "room_size": "12x10 ft",
  "must_haves": ["sofa", "coffee table", "TV unit"],
  "color_preference": "neutral tones",
  "furniture": [{"name": "small cupboard", "qty": 1, "size": "small", "notes": ""}],
  "placements": [{"item": "mirror", "relation": "above", "target": "small cupboard", "notes": ""}],
  "openings": [{"type": "door", "wall": "bottom", "position": "left", "notes": ""}],
  "other_notes": []
}
```

`furniture`, `placements` and `openings` carry the details (sizes, "mirror above cupboard",
door/window walls). Walls use plan view: the door wall is `bottom`, the far wall `top`.

**Gemini availability:** agents 1 and 2 share `gemini_client.py`, which falls back through
several models when one is busy (503) or out of quota (429). Override the order in `.env`:
`GEMINI_MODELS=gemini-3.6-flash,gemini-3.8-flash,gemini-3.5-flash-lite`

**Layout generation (Agent 2):** Gemini only plans *what* goes in the room;
`layout_engine.py` decides *where*, with hard rules (no overlaps, gaps, clear door swing,
no tall furniture in front of windows, walkway to every piece). If Gemini is down, a
layout is still produced from the built-in size catalog.

**Agent 2 -> Agent 3:**
```json
{
  "layout_image_path": "designs/design_v1.png",
  "furniture_needed": [
    {"item": "queen bed", "style": "modern", "qty": 1, "quantity": 1, "color": "navy blue and white", "size": "queen"},
    {"item": "bedside table", "style": "modern", "qty": 1, "quantity": 2, "color": "navy blue and white"}
  ],
  "include_missing": true
}
```
`qty` = how many product options to return (Agent 4 asks for several when looking for cheaper
alternatives); `quantity` = how many pieces the room needs. `include_missing` adds a
`found: false` row for items with no product in the catalog.

**Agent 3 -> Agent 4:**
```json
[
  {"item": "queen bed", "product_name": "Gracia Bed (78\" x 60\")", "price": 79200, "retailer": "Damro",
   "quantity": 1, "found": true, "color": "gray", "product_url": "https://www.damro.lk/product/...",
   "note": "Gray, matches your grey theme"},
  {"item": "bedside table", "product_name": "Carlow Bedside Cupboard", "price": 41000, "retailer": "Damro",
   "quantity": 2, "found": true, "color": "charcoal gray", "note": "..."}
]
```

**Product catalog (Agent 3):** `agent3-furniture-search/real_products.csv`, 136 real products from
Damro, Singer, Softlogic, Cityro, Home 47 and House of Fashions (prices as listed on their websites on
2026-09-22). Columns: `name, category, style, price, retailer, image_url, color, product_url`.
Re-run `python import_csv.py real_products.csv` after editing; existing rows are updated.
Search understands synonyms/sizes ("queen bed", "TV unit", "3-seater"), matches colours by family and
harmony (navy goes with white, grey, light wood), and explains every match in `note`.

**Agent 4 - budget fitting (`POST /optimize-budget`):** takes the chosen products (with each
item's colour theme, size, occupant and priority) and the budget. For every item it asks Agent 3 for
cheaper products that still suit the room, then swaps greedily by *money saved per unit of match
quality lost* (designer-added extras first, the user's own items last), and undoes any swap that
turns out not to be needed. If the budget still can't be met, `suggestions` says how much more is
needed or which pieces to leave out. The frontend shows this behind a "Fit to my budget" button.

**Agent 4 -> Frontend (final result):**
```json
{
  "total_cost": 145000,
  "budget": 150000,
  "budget_status": "within budget",
  "breakdown": [...],
  "suggestion": "You have LKR 5,000 remaining."
}
```

## Development Approach

All 4 agents can be built in **parallel** — each is an independent FastAPI service.
Use the sample JSON above as mock input/output while building your agent standalone;
integrate with real agents once each one works individually.

## Contributors

| Member | Agent |
|---|---|
| TBD | Agent 1 - Requirement Gathering |
| TBD | Agent 2 - Design Generation |
| TBD | Agent 3 - Furniture Search |
| TBD | Agent 4 - Cost Estimation |
