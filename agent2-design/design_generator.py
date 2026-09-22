"""
Agent 2 design logic.

Pipeline:
  1. Gemini plans WHAT goes in the room: each piece with realistic Sri Lankan
     sizes, whether it stands on the floor or hangs on the wall, and how pieces
     relate ("mirror above small cupboard", "coffee table in front of sofa").
  2. The user's own placement wishes from Agent 1 are re-applied to the plan,
     so the LLM can never silently drop them.
  3. layout_engine places everything with hard rules (no overlaps, gaps,
     clear door swing, windows not blocked, walkable path to every piece).
  4. matplotlib draws the plan.

If Gemini is unavailable the plan is built from the built-in size catalog,
so a layout is still produced.
"""

import os
import re
import textwrap
from typing import List, Optional

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from pydantic import BaseModel, Field

from gemini_client import generate_json, GeminiUnavailableError
from layout_engine import generate_layout, catalog_spec, normalize_relation, WALLS


# ------------------------------------------------------------------
# Room size parsing
# ------------------------------------------------------------------

def parse_room_size(room_size_str: str, default_w=12, default_h=10):
    """Accepts '12 x 10 ft', '12x10', '12 by 10', '12.5 x 10', "12' x 10'", '3m x 4m', '3.5 x 4 meters'."""
    s = (room_size_str or "").lower()
    match = re.search(r"(\d+(?:\.\d+)?)\s*(m|ft|feet|foot|'|meters?|metres?)?\s*(?:x|by|\*|×)\s*(\d+(?:\.\d+)?)\s*(m|ft|feet|foot|'|meters?|metres?)?", s)
    if not match:
        return default_w, default_h
    w, h = float(match.group(1)), float(match.group(3))
    units = (match.group(2) or "") + (match.group(4) or "")
    is_metric = ("m" in units and "ft" not in units and "feet" not in units and "foot" not in units) or \
                (not units and re.search(r"\b(m|meters?|metres?)\b", s))
    if is_metric:
        w, h = w * 3.281, h * 3.281
    # Keep to sensible residential sizes
    w = min(max(round(w * 2) / 2, 6), 40)
    h = min(max(round(h * 2) / 2, 6), 40)
    return w, h


# ------------------------------------------------------------------
# Gemini plan schema
# ------------------------------------------------------------------

class PlanRelation(BaseModel):
    relation: str = Field(description=(
        "One of: next_to, in_front_of, opposite, above, on_top_of, below, against_wall, "
        "in_corner, near_window, away_from_window, near_door, away_from_door, centered"
    ))
    target: str = Field(description="Exact name of another item in this plan, or 'window', 'door', or a wall: top/bottom/left/right")
    source: str = Field(description="'user' if the user asked for it, 'suggested' if it is your design choice")


class PlanItem(BaseModel):
    name: str = Field(description="Short product-style name, e.g. 'queen bed', 'small cupboard', 'wall mirror'")
    width_ft: float = Field(description="Length of the front face in feet")
    depth_ft: float = Field(description="Front-to-back depth in feet")
    height_ft: float = Field(description="Height in feet")
    placement: str = Field(description="'wall' (back against a wall), 'corner', 'free' (stands in the room), 'mounted' (hangs on a wall), or 'rug'")
    preferred_wall: str = Field(description="'top', 'bottom', 'left', 'right' or 'any'")
    relations: List[PlanRelation]
    source: str = Field(description="'user' if the user asked for this item, 'suggested' if you added it")


class PlanOpening(BaseModel):
    type: str = Field(description="'door' or 'window'")
    wall: str = Field(description="'top', 'bottom', 'left', 'right' or 'unknown'")
    position: str = Field(description="'left', 'center', 'right' or ''")


class DesignPlan(BaseModel):
    items: List[PlanItem]


class RequirementUpdates(BaseModel):
    room_type: Optional[str]
    style: Optional[str]
    budget: Optional[float]
    room_size: Optional[str]
    color_preference: Optional[str]


class RevisionPlan(BaseModel):
    items: List[PlanItem]
    openings: List[PlanOpening] = Field(description="Door and window positions after the change")
    requirement_updates: RequirementUpdates = Field(description="Only fields the user explicitly changed; null for everything else")


PLAN_RULES = """
Rules:
- List EVERY physical piece separately (2 bedside tables = 2 entries with the same name).
- Include every item the user asked for, with the user's size words ("small cupboard" must be small).
- Keep every user placement wish exactly as a relation with source "user".
- Add sensible design relations with source "suggested", e.g. bedside table next_to bed,
  coffee table in_front_of sofa, TV unit opposite sofa, desk chair in_front_of desk,
  rug below coffee table.
- Mirrors, wall TVs, shelves, paintings, clocks and AC units are "mounted" (they hang on a wall
  and take no floor space). "Mirror above cupboard" = mirror, mounted, relation above -> cupboard.
- Use realistic sizes available in Sri Lanka. Scale pieces down to suit the room
  (e.g. a double bed instead of king in a 10 x 10 ft room). Furniture on the floor should cover
  well under half of the floor area.
- You may add at most 2 small extra pieces that suit the room type and style, only if there is clearly space.
- Do NOT give coordinates. Placement is calculated separately.
"""


def _describe_requirements(req: dict, room_w: float, room_h: float) -> str:
    lines = [
        f"- Room type: {req.get('room_type')}",
        f"- Style: {req.get('style')}",
        f"- Budget: LKR {req.get('budget')}",
        f"- Room size: {room_w} ft wide x {room_h} ft long ({room_w * room_h:.0f} sq ft)",
        f"- Colour preference: {req.get('color_preference') or 'not specified'}",
        f"- Room is for: {req.get('occupant') or 'adult'} (choose furniture sizes and types to suit)",
    ]
    furniture = req.get("furniture") or []
    if furniture:
        lines.append("- Items requested:")
        for f in furniture:
            extra = ", ".join(x for x in [f.get("size"), f.get("notes")] if x)
            lines.append(f"    * {f.get('qty', 1)} x {f['name']}" + (f" ({extra})" if extra else ""))
    else:
        lines.append(f"- Must-have items: {', '.join(req.get('must_haves') or [])}")
    for p in req.get("placements") or []:
        target = f" {p['target']}" if p.get("target") else ""
        lines.append(f"- User placement wish: {p['item']} {p['relation']}{target}" +
                     (f" (\"{p['notes']}\")" if p.get("notes") else ""))
    for o in req.get("openings") or []:
        lines.append(f"- {o['type']} is on the {o.get('wall', 'unknown')} wall" +
                     (f", towards the {o['position']}" if o.get("position") else ""))
    for note in req.get("other_notes") or []:
        lines.append(f"- Note: {note}")
    return "\n".join(lines)


# ------------------------------------------------------------------
# Plan helpers
# ------------------------------------------------------------------

def _names_match(a: str, b: str) -> bool:
    a, b = (a or "").lower().strip(), (b or "").lower().strip()
    if not a or not b:
        return False
    # Whole-word match, so "cupboard" matches "small cupboard" but "bed" does not match "bedside table"
    wa, wb = set(re.findall(r"[a-z0-9]+", a)), set(re.findall(r"[a-z0-9]+", b))
    return a == b or wa <= wb or wb <= wa


def fallback_plan(req: dict) -> list:
    """Build a plan without Gemini, from the requested items and the size catalog."""
    furniture = req.get("furniture") or [{"name": n, "qty": 1} for n in (req.get("must_haves") or [])]
    items = []
    for f in furniture:
        spec = catalog_spec(f["name"])
        for _ in range(max(1, int(f.get("qty") or 1))):
            items.append({
                "name": f["name"], "width_ft": spec["w"], "depth_ft": spec["d"], "height_ft": spec["h"],
                "placement": spec["placement"], "preferred_wall": "any", "relations": [], "source": "user",
            })
    add_default_relations(items)
    return items


DEFAULT_RELATIONS = [
    (("bedside", "nightstand", "night stand"), "next_to", ("bed",)),
    (("coffee table", "centre table", "center table"), "in_front_of", ("sofa", "couch", "settee")),
    (("tv unit", "tv stand", "tv cabinet", "tv"), "opposite", ("sofa", "couch", "bed")),
    (("chair", "stool"), "in_front_of", ("desk", "study table", "computer table", "dressing table")),
    (("dining chair",), "next_to", ("dining table",)),
    (("rug", "carpet"), "below", ("coffee table", "bed", "dining table")),
    (("side table", "end table"), "next_to", ("sofa", "armchair")),
]


def add_default_relations(items: list):
    """Add obvious design relations the plan is missing (bedside table next to bed, ...)."""
    names = [i["name"].lower() for i in items]
    for item in items:
        lowered = item["name"].lower()
        if item["relations"]:
            continue
        for keywords, relation, targets in DEFAULT_RELATIONS:
            if any(k in lowered for k in keywords):
                target = next((n for t in targets for n in names if t in n and n != lowered), None)
                if target:
                    item["relations"].append({"relation": relation, "target": target, "source": "suggested"})
                    break


def enforce_user_wishes(items: list, req: dict) -> list:
    """Make sure every requested item and every user placement wish is in the plan."""
    furniture = req.get("furniture") or [{"name": n, "qty": 1} for n in (req.get("must_haves") or [])]
    for f in furniture:
        wanted = max(1, int(f.get("qty") or 1))
        have = sum(1 for i in items if _names_match(i["name"], f["name"]))
        spec = catalog_spec(f["name"])
        for _ in range(wanted - have):
            items.append({
                "name": f["name"], "width_ft": spec["w"], "depth_ft": spec["d"], "height_ft": spec["h"],
                "placement": spec["placement"], "preferred_wall": "any", "relations": [], "source": "user",
            })

    for wish in req.get("placements") or []:
        relation = normalize_relation(wish.get("relation"))
        if not relation:
            continue
        matching = [i for i in items if _names_match(i["name"], wish.get("item", ""))]
        target = (wish.get("target") or "").strip()
        # point the target at the plan's own name for that item, if it was renamed
        plan_target = next((i["name"] for i in items if target and _names_match(i["name"], target)), target)
        for item in matching:
            rels = item.setdefault("relations", [])
            existing = [r for r in rels if normalize_relation(r.get("relation")) == relation and
                        (not plan_target or _names_match(r.get("target", ""), plan_target))]
            if existing:
                for r in existing:
                    r["source"] = "user"
            else:
                rels.insert(0, {"relation": relation, "target": plan_target, "source": "user"})
            if relation == "against_wall" and target.lower() in WALLS:
                item["preferred_wall"] = target.lower()
    add_default_relations(items)
    return items


def previous_positions(previous_layout: Optional[dict]) -> dict:
    positions = {}
    for f in (previous_layout or {}).get("furniture", []):
        positions.setdefault(f["item"].lower(), []).append((f["x"] + f["width"] / 2, f["y"] + f["height"] / 2))
    return positions


def _plan_to_dicts(items) -> list:
    return [dict(i) if isinstance(i, dict) else i.model_dump() for i in items]


# ------------------------------------------------------------------
# Public API used by main.py
# ------------------------------------------------------------------

def get_furniture_layout(requirements: dict) -> dict:
    room_w, room_h = parse_room_size(requirements.get("room_size", ""))

    prompt = f"""
You are an interior designer planning the furniture for a room.

Requirements:
{_describe_requirements(requirements, room_w, room_h)}
{PLAN_RULES}
"""
    try:
        plan = generate_json(prompt, response_schema=DesignPlan, temperature=0.3)
        items = _plan_to_dicts(plan.get("items") or [])
    except (GeminiUnavailableError, ValueError) as e:
        print("WARNING: Gemini unavailable for planning, using catalog fallback:", repr(e))
        items = []

    items = enforce_user_wishes(items or fallback_plan(requirements), requirements)
    layout_data = generate_layout(room_w, room_h, items, requirements.get("openings") or [])
    _log_warnings(layout_data)
    return layout_data


def revise_furniture_layout(original_requirements: dict, change_text: str, previous_layout: Optional[dict] = None):
    """
    Apply a user's change request. Returns (layout_data, requirement_updates).
    One Gemini call both updates the plan and detects core requirement changes.
    """
    requirements = dict(original_requirements)
    room_w, room_h = parse_room_size(requirements.get("room_size", ""))
    current_items = (previous_layout or {}).get("plan") or fallback_plan(requirements)
    current_openings = (previous_layout or {}).get("openings") or requirements.get("openings") or []

    prompt = f"""
You are an interior designer updating an existing room plan.

Original requirements:
{_describe_requirements(requirements, room_w, room_h)}

Current plan (items):
{current_items}

Current doors/windows (position = feet from the start of the wall):
{current_openings}

The user now wants this change: "{change_text}"

Return the FULL updated plan. Keep everything the user did not ask to change.
If the change moves the door or a window, update "openings"; otherwise repeat the current walls.
In requirement_updates, fill only fields the user explicitly changed (budget, style, room type,
room size, colour); leave the others null.
{PLAN_RULES}
"""
    requirement_updates = {}
    openings = current_openings
    try:
        result = generate_json(prompt, response_schema=RevisionPlan, temperature=0.3)
        items = _plan_to_dicts(result.get("items") or []) or current_items
        requirement_updates = {k: v for k, v in (result.get("requirement_updates") or {}).items() if v not in (None, "")}
        new_openings = result.get("openings") or []
        if new_openings and _openings_changed(new_openings, current_openings):
            openings = new_openings
    except (GeminiUnavailableError, ValueError) as e:
        print("WARNING: Gemini unavailable for revision:", repr(e))
        raise

    if requirement_updates.get("room_size"):
        requirements["room_size"] = requirement_updates["room_size"]
        room_w, room_h = parse_room_size(requirements["room_size"])

    # Only re-apply user wishes that still refer to items in the plan (the user may have removed some)
    kept = dict(requirements)
    kept["furniture"] = []
    kept["must_haves"] = []
    kept["placements"] = [p for p in requirements.get("placements") or []
                          if any(_names_match(i["name"], p.get("item", "")) for i in items)]
    items = enforce_user_wishes(items, kept)

    layout_data = generate_layout(room_w, room_h, items, openings, previous_positions(previous_layout))
    _log_warnings(layout_data)
    return layout_data, requirement_updates


def _openings_changed(new, current) -> bool:
    def walls(openings):
        return sorted((o.get("type"), o.get("wall")) for o in openings)
    return walls(new) != walls(current)


def _log_warnings(layout_data):
    if layout_data.get("warnings"):
        print("WARNING: Layout notes:")
        for w in layout_data["warnings"]:
            print(f"  - {w}")


# ------------------------------------------------------------------
# Drawing
# ------------------------------------------------------------------

COLOR_MAP = {
    "white": "#f1efe9", "warm wood": "#d2a679", "wood": "#d2a679", "neutral": "#d8cfc4",
    "blue": "#a8c8e8", "green": "#a8d8b9", "grey": "#c0c0c0", "gray": "#c0c0c0",
    "beige": "#e8dcc8", "black": "#6a6a6a", "brown": "#b88a64", "pink": "#efc6c6",
    "yellow": "#f1dc9c", "cream": "#efe6d2",
}


def get_furniture_color(color_preference: str) -> str:
    color_preference = (color_preference or "").lower()
    for keyword, hex_color in COLOR_MAP.items():
        if keyword in color_preference:
            return hex_color
    return "#cfdde8"


def _draw_door(ax, door, room_w, room_h):
    p, length, wall = door["position"], door["length"], door["wall"]
    if wall == "bottom":
        gap, hinge, leaf_end, arc = ((p, 0), (p + length, 0)), (p, 0), (p, length), (0, 90)
    elif wall == "top":
        gap, hinge, leaf_end, arc = ((p, room_h), (p + length, room_h)), (p, room_h), (p, room_h - length), (270, 360)
    elif wall == "left":
        gap, hinge, leaf_end, arc = ((0, p), (0, p + length)), (0, p), (length, p), (0, 90)
    else:
        gap, hinge, leaf_end, arc = ((room_w, p), (room_w, p + length)), (room_w, p), (room_w - length, p), (90, 180)

    ax.plot([gap[0][0], gap[1][0]], [gap[0][1], gap[1][1]], color="white", linewidth=5, zorder=5)
    ax.plot([hinge[0], leaf_end[0]], [hinge[1], leaf_end[1]], color="saddlebrown", linewidth=1.8, zorder=6)
    ax.add_patch(patches.Arc(hinge, length * 2, length * 2, theta1=arc[0], theta2=arc[1],
                             color="saddlebrown", linewidth=1, linestyle="--", zorder=6))
    lx, ly = (gap[0][0] + gap[1][0]) / 2, (gap[0][1] + gap[1][1]) / 2
    offset = {"bottom": (0, -0.45), "top": (0, 0.45), "left": (-0.55, 0), "right": (0.55, 0)}[wall]
    ax.text(lx + offset[0], ly + offset[1], "DOOR", ha="center", va="center", fontsize=6.5,
            color="saddlebrown", rotation=90 if wall in ("left", "right") else 0, zorder=6)


def _draw_window(ax, window, room_w, room_h):
    p, length, wall = window["position"], window["length"], window["wall"]
    if wall in ("bottom", "top"):
        y = 0 if wall == "bottom" else room_h
        ax.plot([p, p + length], [y, y], color="white", linewidth=5, zorder=5)
        for off in (-0.12, 0, 0.12):
            ax.plot([p, p + length], [y + off, y + off], color="deepskyblue", linewidth=1.1, zorder=6)
        ax.text(p + length / 2, y + (-0.45 if wall == "bottom" else 0.45), "WINDOW", ha="center", va="center",
                fontsize=6.5, color="steelblue", zorder=6)
    else:
        x = 0 if wall == "left" else room_w
        ax.plot([x, x], [p, p + length], color="white", linewidth=5, zorder=5)
        for off in (-0.12, 0, 0.12):
            ax.plot([x + off, x + off], [p, p + length], color="deepskyblue", linewidth=1.1, zorder=6)
        ax.text(x + (-0.55 if wall == "left" else 0.55), p + length / 2, "WINDOW", ha="center", va="center",
                fontsize=6.5, color="steelblue", rotation=90, zorder=6)


def _front_edge(x, y, w, h, facing):
    return {"up": ([x, x + w], [y + h, y + h]), "down": ([x, x + w], [y, y]),
            "right": ([x + w, x + w], [y, y + h]), "left": ([x, x], [y, y + h])}[facing]


def _label(ax, text, x, y, w, h, pts_per_ft, zorder=4, color="#222"):
    """Fit a label inside a w x h box: rotate for tall narrow boxes, wrap on words, shrink font."""
    rotate = h > w * 1.4
    box_len, box_thick = (h, w) if rotate else (w, h)
    fontsize = max(5.0, min(8.5, box_thick * pts_per_ft * 0.28))
    longest = max((len(word) for word in text.split()), default=1)
    fontsize = max(4.5, min(fontsize, box_len * pts_per_ft * 0.9 / (0.6 * longest)))
    chars = max(longest, int(box_len * pts_per_ft * 0.9 / (0.6 * fontsize)))
    wrapped = "\n".join(textwrap.wrap(text, chars, break_long_words=False)[:3])
    ax.text(x, y, wrapped, ha="center", va="center", fontsize=fontsize, color=color, zorder=zorder,
            rotation=90 if rotate else 0)


def draw_layout(layout_data: dict, save_path: str = "designs/layout.png", color_preference: str = ""):
    room_w = layout_data.get("room_width", 12)
    room_h = layout_data.get("room_height", 10)
    fill = get_furniture_color(color_preference)

    os.makedirs(os.path.dirname(save_path) or ".", exist_ok=True)

    scale = 0.55
    fig_w, fig_h = max(6, room_w * scale + 2), max(5, room_h * scale + 2)
    fig, ax = plt.subplots(figsize=(fig_w, fig_h))
    # points per foot, for sizing labels (axes keep equal aspect, so the tighter side wins)
    pts_per_ft = min(fig_w * 72 * 0.78 / (room_w + 3), fig_h * 72 * 0.78 / (room_h + 3))
    ax.set_xlim(-1.5, room_w + 1.5)
    ax.set_ylim(-1.5, room_h + 1.5)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_title(f"Room layout  ·  {room_w:g} ft x {room_h:g} ft", fontsize=11)

    # Floor with a 1 ft grid
    ax.add_patch(patches.Rectangle((0, 0), room_w, room_h, facecolor="#faf8f4", edgecolor="none", zorder=0))
    for gx in range(1, int(room_w) + 1):
        ax.plot([gx, gx], [0, room_h], color="#ece8e0", linewidth=0.5, zorder=0)
    for gy in range(1, int(room_h) + 1):
        ax.plot([0, room_w], [gy, gy], color="#ece8e0", linewidth=0.5, zorder=0)
    ax.add_patch(patches.Rectangle((0, 0), room_w, room_h, fill=False, edgecolor="#333", linewidth=3, zorder=4))

    ax.text(room_w / 2, -1.05, f"{room_w:g} ft", ha="center", va="center", fontsize=8, color="#555")
    ax.text(-1.05, room_h / 2, f"{room_h:g} ft", ha="center", va="center", fontsize=8, color="#555", rotation=90)

    furniture = layout_data.get("furniture", [])

    for f in furniture:
        if f.get("kind") == "rug":
            ax.add_patch(patches.Rectangle((f["x"], f["y"]), f["width"], f["height"], facecolor=fill, alpha=0.25,
                                           edgecolor="#999", linestyle="--", linewidth=0.8, zorder=1))
            ax.text(f["x"] + 0.2, f["y"] + 0.2, f["item"], fontsize=6, color="#777", zorder=1)

    for f in furniture:
        if f.get("kind", "floor") != "floor":
            continue
        x, y, w, h = f["x"], f["y"], f["width"], f["height"]
        ax.add_patch(patches.FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=0.12",
                                            facecolor=fill, edgecolor="#555", linewidth=1, zorder=2))
        if f.get("facing"):
            ex, ey = _front_edge(x, y, w, h, f["facing"])
            ax.plot(ex, ey, color="#333", linewidth=2.2, zorder=3, solid_capstyle="butt")
        _label(ax, f["item"], x + w / 2, y + h / 2, w, h, pts_per_ft)

    for f in furniture:
        if f.get("kind") not in ("mounted", "window"):
            continue
        x, y, w, h = f["x"], f["y"], f["width"], f["height"]
        ax.add_patch(patches.Rectangle((x, y), w, h, facecolor="#8a6fb0", edgecolor="#5b4480",
                                       alpha=0.85, linewidth=0.8, zorder=7))
        wall = f.get("wall")
        label = f["item"] + (f" (above {f['attached_to']})" if f.get("attached_to") and f.get("kind") == "mounted" else "")
        # Label outside the wall, so it never covers the furniture below it
        if wall == "bottom":
            lx, ly, rot = x + w / 2, -0.45, 0
        elif wall == "top":
            lx, ly, rot = x + w / 2, room_h + 0.45, 0
        elif wall == "left":
            lx, ly, rot = -0.5, y + h / 2, 90
        else:
            lx, ly, rot = room_w + 0.5, y + h / 2, 90
        ax.text(lx, ly, label, ha="center", va="center", fontsize=6, color="#5b4480", rotation=rot, zorder=8,
                bbox=dict(boxstyle="round,pad=0.15", facecolor="white", edgecolor="none", alpha=0.8))

    for opening in layout_data.get("openings") or []:
        if opening["type"] == "door":
            _draw_door(ax, opening, room_w, room_h)
        else:
            _draw_window(ax, opening, room_w, room_h)

    ax.text(room_w + 1.4, -1.35, "Thick edge = front of furniture   ·   Purple = wall-mounted",
            ha="right", va="bottom", fontsize=6, color="#777")

    plt.savefig(save_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return save_path
