import os
import json
import re
from dotenv import load_dotenv
from google import genai
import matplotlib.pyplot as plt
import matplotlib.patches as patches

load_dotenv()
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))


def parse_room_size(room_size_str: str, default_w=12, default_h=10):
    match = re.search(r'(\d+)\s*x\s*(\d+)', room_size_str)
    if match:
        return int(match.group(1)), int(match.group(2))
    return default_w, default_h


def get_furniture_layout(requirements: dict) -> dict:
    room_w, room_h = parse_room_size(requirements.get('room_size', ''))

    prompt = f"""
You are an interior design assistant. Based on the requirements below,
suggest furniture items and their placement in a 2D room layout,
plus the door and window positions.

Requirements:
- Room type: {requirements['room_type']}
- Style: {requirements['style']}
- Budget: LKR {requirements['budget']}
- Room size: {room_w}ft x {room_h}ft
- Must-have items: {', '.join(requirements.get('must_haves', []))}
- Color preference: {requirements.get('color_preference', 'not specified')}

Return ONLY valid JSON in this exact format, nothing else:
{{
  "furniture": [
    {{"item": "sofa", "x": 1, "y": 2, "width": 2, "height": 1}}
  ],
  "door": {{"wall": "bottom", "position": 1, "length": 3}},
  "window": {{"wall": "top", "position": 5, "length": 3}}
}}

Rules for furniture:
- All x, y, width, height must stay within a {room_w} x {room_h} ft room
- Include all must-have items
- Suggest 1-3 extra furniture pieces that fit the room type/style, only if there's clearly enough space
- Arrange furniture in a natural, realistic way — group related items together (e.g. seating pieces near each other), keep the layout compact and avoid large unused gaps, while leaving walking space and not overlapping
- Leave at least 1.5 ft of clear walking space in front of any furniture that needs to be opened or used directly (wardrobe, desk, bookshelf, drawers) — this space must not be blocked by other furniture.
- Leave at least 2 ft of walking clearance between separate furniture groups so a person can move through the room.

Rules for door/window:
- "wall" must be one of: "top", "bottom", "left", "right"
- "position" is the distance in feet from the start of that wall (left corner for top/bottom, bottom corner for left/right) to where the door/window starts
- "length" is how wide the door/window opening is
- Door and window must be on different walls
- IMPORTANT: Leave a clear square area (roughly matching the door's width) directly in front of the door, extending into the room, completely free of furniture, so the door can open fully and someone can walk through without obstruction.
- Only return the JSON, no explanation text
"""

    response = client.models.generate_content(
        model="gemini-3.6-flash",
        contents=prompt
    )

    raw_text = response.text.strip()
    match = re.search(r'\{.*\}', raw_text, re.DOTALL)
    if not match:
        raise ValueError(f"No JSON found in Gemini response: {raw_text}")

    layout_data = json.loads(match.group())
    layout_data["room_width"] = room_w
    layout_data["room_height"] = room_h

    warnings = validate_layout(layout_data)
    if warnings:
        print("⚠️ Layout validation warnings:")
        for w in warnings:
            print(f"  - {w}")

    return layout_data


COLOR_MAP = {
    "white": "#f5f5f5", "warm wood": "#d2a679", "neutral": "#d8cfc4",
    "blue": "#a8c8e8", "green": "#a8d8b9", "grey": "#c0c0c0", "gray": "#c0c0c0",
    "beige": "#e8dcc8", "black": "#4a4a4a",
}


def get_furniture_color(color_preference: str) -> str:
    color_preference = (color_preference or "").lower()
    for keyword, hex_color in COLOR_MAP.items():
        if keyword in color_preference:
            return hex_color
    return "lightblue"


def wall_to_coords(wall: str, position: float, length: float, room_w: float, room_h: float):
    """Returns (x1, y1, x2, y2) for the opening, and whether it's a horizontal or vertical wall."""
    if wall == "bottom":
        return position, 0, position + length, 0, "horizontal"
    elif wall == "top":
        return position, room_h, position + length, room_h, "horizontal"
    elif wall == "left":
        return 0, position, 0, position + length, "vertical"
    elif wall == "right":
        return room_w, position, room_w, position + length, "vertical"
    return 0, 0, length, 0, "horizontal"


def draw_door(ax, door, room_w, room_h):
    x1, y1, x2, y2, orientation = wall_to_coords(door["wall"], door["position"], door["length"], room_w, room_h)

    # Erase the wall line under the door (white line over the black wall)
    ax.plot([x1, x2], [y1, y2], color='white', linewidth=3, zorder=2)

    if orientation == "horizontal":
        hinge_x, hinge_y = x1, y1
        swing_x, swing_y = x2, y1
        ax.plot([hinge_x, hinge_x], [hinge_y, hinge_y + (door["length"] if hinge_y == 0 else -door["length"])],
                color='saddlebrown', linewidth=1.5, zorder=3)
        direction = 1 if hinge_y == 0 else -1
        arc = patches.Arc((hinge_x, hinge_y), door["length"] * 2, door["length"] * 2,
                           theta1=0 if direction == 1 else 180, theta2=90 if direction == 1 else 270,
                           color='saddlebrown', linewidth=1, zorder=3)
        ax.add_patch(arc)
        ax.plot([hinge_x, swing_x], [hinge_y, hinge_y], color='saddlebrown', linewidth=1.5, zorder=3)
    else:
        hinge_x, hinge_y = x1, y1
        direction = 1 if hinge_x == 0 else -1
        ax.plot([hinge_x, hinge_x + direction * door["length"]], [hinge_y, hinge_y],
                color='saddlebrown', linewidth=1.5, zorder=3)
        arc = patches.Arc((hinge_x, hinge_y), door["length"] * 2, door["length"] * 2,
                           theta1=0 if direction == 1 else 90, theta2=90 if direction == 1 else 180,
                           color='saddlebrown', linewidth=1, zorder=3)
        ax.add_patch(arc)
        ax.plot([hinge_x, hinge_x], [hinge_y, y2], color='saddlebrown', linewidth=1.5, zorder=3)


def draw_window(ax, window, room_w, room_h):
    x1, y1, x2, y2, orientation = wall_to_coords(window["wall"], window["position"], window["length"], room_w, room_h)

    # Erase wall line under window, then draw double-line window symbol
    ax.plot([x1, x2], [y1, y2], color='white', linewidth=3, zorder=2)
    offset = 0.15
    if orientation == "horizontal":
        ax.plot([x1, x2], [y1 - offset, y1 - offset], color='deepskyblue', linewidth=1.2, zorder=3)
        ax.plot([x1, x2], [y1 + offset, y1 + offset], color='deepskyblue', linewidth=1.2, zorder=3)
    else:
        ax.plot([x1 - offset, x1 - offset], [y1, y2], color='deepskyblue', linewidth=1.2, zorder=3)
        ax.plot([x1 + offset, x1 + offset], [y1, y2], color='deepskyblue', linewidth=1.2, zorder=3)


def draw_layout(layout_data: dict, save_path: str = "designs/layout.png", color_preference: str = ""):
    room_width = layout_data.get("room_width", 12)
    room_height = layout_data.get("room_height", 10)
    furniture_color = get_furniture_color(color_preference)

    os.makedirs(os.path.dirname(save_path), exist_ok=True)

    fig, ax = plt.subplots(figsize=(8, 6))
    ax.set_xlim(-1, room_width + 1)
    ax.set_ylim(-1, room_height + 1)
    ax.set_title("Room Layout")
    ax.set_aspect('equal')

    ax.add_patch(patches.Rectangle((0, 0), room_width, room_height, fill=False, edgecolor='black', linewidth=2, zorder=1))

    for furniture in layout_data.get("furniture", []):
        x, y = furniture["x"], furniture["y"]
        w, h = furniture["width"], furniture["height"]
        rect = patches.Rectangle((x, y), w, h, facecolor=furniture_color, edgecolor='dimgray', zorder=2)
        ax.add_patch(rect)

        # Auto-shrink font so the label fits inside the box
        label = furniture["item"]
        box_area = w * h
        fontsize = max(5, min(9, box_area * 2))

        text = ax.text(x + w / 2, y + h / 2, label, ha='center', va='center', fontsize=fontsize, zorder=3)
        text.set_clip_path(rect)

    door = layout_data.get("door")
    if door:
        draw_door(ax, door, room_width, room_height)

    window = layout_data.get("window")
    if window:
        draw_window(ax, window, room_width, room_height)

    plt.savefig(save_path, dpi=150)
    plt.close()
    return save_path

def rects_overlap(x1, y1, w1, h1, x2, y2, w2, h2):
    """Returns True if two rectangles overlap."""
    return not (x1 + w1 <= x2 or x2 + w2 <= x1 or y1 + h1 <= y2 or y2 + h2 <= y1)


def get_door_clearance_zone(door, room_w, room_h):
    """Returns (x, y, width, height) of the door's swing clearance area."""
    length = door["length"]
    wall = door["wall"]
    pos = door["position"]

    if wall == "bottom":
        return pos, 0, length, length
    elif wall == "top":
        return pos, room_h - length, length, length
    elif wall == "left":
        return 0, pos, length, length
    elif wall == "right":
        return room_w - length, pos, length, length
    return 0, 0, 0, 0
    
def check_room_feasibility(layout_data: dict) -> list:
    """Warns if furniture footprint takes up too much of the room, suggesting overcrowding."""
    warnings = []
    room_w = layout_data.get("room_width", 12)
    room_h = layout_data.get("room_height", 10)
    room_area = room_w * room_h
    furniture = layout_data.get("furniture", [])

    total_furniture_area = sum(f["width"] * f["height"] for f in furniture)
    occupied_ratio = total_furniture_area / room_area

    if occupied_ratio > 0.6:
        warnings.append(
            f"Room may be overcrowded — furniture covers {occupied_ratio:.0%} of the floor area. "
            f"Consider removing some items or using a larger room for a comfortable layout."
        )
    return warnings

def validate_layout(layout_data: dict) -> list:
    """
    Checks the AI's layout for problems. Returns a list of warning strings.
    Does not modify the layout — just reports issues so we know if the
    prompt instructions are being followed reliably.
    """
    warnings = []
    room_w = layout_data.get("room_width", 12)
    room_h = layout_data.get("room_height", 10)
    furniture = layout_data.get("furniture", [])

    # 1. Check furniture stays inside room bounds
    for f in furniture:
        if f["x"] < 0 or f["y"] < 0 or f["x"] + f["width"] > room_w or f["y"] + f["height"] > room_h:
            warnings.append(f"'{f['item']}' is placed outside the room bounds.")

    # 2. Check furniture doesn't overlap other furniture
    for i in range(len(furniture)):
        for j in range(i + 1, len(furniture)):
            a, b = furniture[i], furniture[j]
            if rects_overlap(a["x"], a["y"], a["width"], a["height"],
                              b["x"], b["y"], b["width"], b["height"]):
                warnings.append(f"'{a['item']}' overlaps with '{b['item']}'.")

    # 3. Check door and window aren't on the same wall
    door = layout_data.get("door")
    window = layout_data.get("window")
    if door and window and door["wall"] == window["wall"]:
        warnings.append("Door and window are on the same wall.")

    # 4. Check furniture doesn't block the door's clearance zone
    if door:
        dx, dy, dw, dh = get_door_clearance_zone(door, room_w, room_h)
        for f in furniture:
            if rects_overlap(dx, dy, dw, dh, f["x"], f["y"], f["width"], f["height"]):
                warnings.append(f"'{f['item']}' is blocking the door's clearance zone.")

    warnings.extend(check_room_feasibility(layout_data))
    return warnings