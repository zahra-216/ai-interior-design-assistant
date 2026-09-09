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

## JSON Contracts Between Agents

**Agent 1 -> Agent 2:**
```json
{
  "room_type": "living room",
  "style": "modern minimalist",
  "budget": 150000,
  "room_size": "12x10 ft",
  "must_haves": ["sofa", "coffee table", "TV unit"],
  "color_preference": "neutral tones"
}
```

**Agent 2 -> Agent 3:**
```json
{
  "layout_image_path": "designs/design_v1.png",
  "furniture_needed": [
    {"item": "3-seater sofa", "style": "modern", "qty": 1},
    {"item": "coffee table", "style": "minimalist", "qty": 1}
  ]
}
```

**Agent 3 -> Agent 4:**
```json
[
  {"item": "3-seater sofa", "product_name": "Damro Comfort Sofa", "price": 65000, "retailer": "Damro"},
  {"item": "coffee table", "product_name": "Singer Oak Table", "price": 18000, "retailer": "Singer"}
]
```

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
