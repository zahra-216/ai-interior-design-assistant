"""
Deterministic furniture placement engine for Agent 2.

Gemini decides WHAT goes in the room (items, sizes, relations such as
"mirror above small cupboard"). This module decides WHERE, using hard rules
the LLM kept breaking:

  - pieces never overlap and keep a minimum gap from unrelated pieces
  - every piece keeps its own clearance (wardrobe doors, bed sides, desk chair)
  - the door swing area is always clear
  - tall pieces (wardrobes, shelves) never stand in front of a window
  - a walkway check (grid BFS from the door) proves every piece can be reached
  - wall-mounted items (mirror, TV, shelves) go on the wall, above their target

If a piece cannot be placed without breaking a rule, the rules are relaxed step
by step; if it still does not fit it is reported instead of being squeezed in.

Coordinates are in feet. (0, 0) is the bottom-left corner of the room, x runs
along the bottom wall (room width), y along the left wall (room length).
"""

import itertools
import math
import re
import time
from collections import deque
from dataclasses import dataclass, field

import numpy as np

CELL = 0.25  # grid resolution in feet
EPS = 1e-6

WALLS = ("bottom", "top", "left", "right")
FACING_FOR_WALL = {"bottom": "up", "top": "down", "left": "right", "right": "left"}
WALL_FOR_FACING = {v: k for k, v in FACING_FOR_WALL.items()}
OPPOSITE_FACING = {"up": "down", "down": "up", "left": "right", "right": "left"}
OPPOSITE_WALL = {"bottom": "top", "top": "bottom", "left": "right", "right": "left"}

# Relaxation levels: (min gap to unrelated pieces, clearance multiplier, walker radius)
LEVELS = [(0.5, 1.0, 0.75), (0.25, 0.8, 0.65), (0.0, 0.6, 0.55)]
TALL_FT = 4.0  # anything taller than this must not stand in front of a window
SEARCH_TIME_BUDGET_S = 4.0  # max time spent trying alternative layouts

# ------------------------------------------------------------------
# Typical sizes (feet) of furniture sold in Sri Lanka.
# w = front face length, d = depth, h = height, fc = front clearance,
# sc = side clearance (beds), side_mode "both"/"one", all = clearance on all sides.
# ------------------------------------------------------------------
CATALOG = [
    (("king bed", "king size bed"), dict(w=6.0, d=6.8, h=2.5, placement="wall", fc=2.0, sc=2.0, side_mode="both", center=True, priority=100)),
    (("queen bed", "queen size bed"), dict(w=5.0, d=6.7, h=2.5, placement="wall", fc=2.0, sc=2.0, side_mode="both", center=True, priority=100)),
    (("double bed",), dict(w=4.5, d=6.5, h=2.5, placement="wall", fc=2.0, sc=1.75, side_mode="both", center=True, priority=100)),
    (("single bed", "kids bed", "bunk bed", "day bed", "daybed"), dict(w=3.0, d=6.5, h=2.5, placement="wall", fc=1.5, sc=1.75, side_mode="one", priority=100)),
    (("bed",), dict(w=5.0, d=6.5, h=2.5, placement="wall", fc=2.0, sc=2.0, side_mode="both", center=True, priority=100)),
    (("crib", "baby cot"), dict(w=2.5, d=4.5, h=3.0, placement="wall", fc=2.0, priority=80)),
    (("wardrobe", "almirah", "closet"), dict(w=4.0, d=2.0, h=6.5, placement="wall", fc=2.5, priority=90)),
    (("bedside", "nightstand", "night stand"), dict(w=1.5, d=1.5, h=2.0, placement="wall", fc=0.0, priority=30)),
    (("dressing table", "dresser", "vanity"), dict(w=3.5, d=1.5, h=2.6, placement="wall", fc=2.0, priority=50)),
    (("chest of drawers", "drawers"), dict(w=3.0, d=1.5, h=3.0, placement="wall", fc=2.0, priority=50)),
    (("small cupboard", "small cabinet"), dict(w=2.5, d=1.5, h=3.0, placement="wall", fc=2.0, priority=55)),
    (("cupboard", "cabinet", "pantry"), dict(w=3.0, d=1.5, h=6.0, placement="wall", fc=2.0, priority=60)),
    (("bookshelf", "book shelf", "bookcase", "book rack"), dict(w=3.0, d=1.0, h=6.0, placement="wall", fc=2.0, priority=50)),
    (("shoe rack",), dict(w=2.5, d=1.2, h=3.0, placement="wall", fc=1.5, priority=40)),
    (("sideboard", "buffet", "console table", "crockery cabinet", "showcase"), dict(w=5.0, d=1.5, h=3.0, placement="wall", fc=2.0, priority=60)),
    (("study desk", "study table", "computer table", "office table", "work table", "desk"), dict(w=4.0, d=2.0, h=2.5, placement="wall", fc=2.5, priority=70)),
    (("dining table",), dict(w=5.0, d=3.0, h=2.5, placement="free", fc=0.0, all=2.5, priority=85)),
    (("dining chair",), dict(w=1.5, d=1.5, h=3.0, placement="free", fc=0.0, priority=20)),
    (("office chair", "desk chair", "study chair", "stool", "chair"), dict(w=1.8, d=1.8, h=3.0, placement="free", fc=0.0, priority=20)),
    (("l-shaped sofa", "l shaped sofa", "sectional", "corner sofa"), dict(w=8.0, d=3.0, h=3.0, placement="wall", fc=1.5, center=True, priority=92)),
    (("3-seater", "3 seater", "three seater"), dict(w=7.0, d=3.0, h=3.0, placement="wall", fc=1.5, center=True, priority=90)),
    (("2-seater", "2 seater", "two seater", "loveseat", "love seat"), dict(w=5.0, d=3.0, h=3.0, placement="wall", fc=1.5, center=True, priority=88)),
    (("sofa bed",), dict(w=6.0, d=3.0, h=3.0, placement="wall", fc=2.5, center=True, priority=90)),
    (("sofa", "couch", "settee"), dict(w=6.5, d=3.0, h=3.0, placement="wall", fc=1.5, center=True, priority=90)),
    (("armchair", "arm chair", "accent chair", "lounge chair", "recliner"), dict(w=2.8, d=2.8, h=3.0, placement="wall", fc=1.5, priority=45)),
    (("coffee table", "centre table", "center table"), dict(w=3.5, d=2.0, h=1.5, placement="free", fc=0.0, priority=35)),
    (("side table", "end table"), dict(w=1.5, d=1.5, h=2.0, placement="wall", fc=0.0, priority=25)),
    (("tv unit", "tv stand", "tv cabinet", "tv console", "entertainment unit"), dict(w=5.0, d=1.5, h=2.0, placement="wall", fc=2.0, center=True, priority=60)),
    (("fridge", "refrigerator"), dict(w=2.5, d=2.5, h=6.0, placement="wall", fc=3.0, priority=70)),
    (("washing machine",), dict(w=2.0, d=2.0, h=3.0, placement="wall", fc=2.0, priority=60)),
    (("bench",), dict(w=4.0, d=1.3, h=1.5, placement="wall", fc=1.0, priority=30)),
    (("bean bag", "beanbag"), dict(w=2.5, d=2.5, h=2.0, placement="free", fc=0.0, priority=20)),
    (("ottoman", "pouf"), dict(w=1.5, d=1.5, h=1.5, placement="free", fc=0.0, priority=20)),
    (("floor lamp", "lamp"), dict(w=1.2, d=1.2, h=5.0, placement="corner", fc=0.0, priority=15)),
    (("plant", "planter"), dict(w=1.5, d=1.5, h=3.0, placement="corner", fc=0.0, priority=15)),
    # Wall mounted / overlay items (no floor footprint)
    (("wall mounted tv", "wall-mounted tv", "mounted tv", "television", "tv"), dict(w=4.0, d=0.3, h=2.5, placement="mounted", fc=0.0, priority=10)),
    (("mirror",), dict(w=2.0, d=0.2, h=3.0, placement="mounted", fc=0.0, priority=10)),
    (("wall shelf", "floating shelf", "shelf", "shelves"), dict(w=3.0, d=0.8, h=0.3, placement="mounted", fc=0.0, priority=10)),
    (("painting", "wall art", "artwork", "photo frame", "frame", "clock"), dict(w=2.5, d=0.1, h=2.0, placement="mounted", fc=0.0, priority=5)),
    (("air conditioner", "ac unit"), dict(w=3.0, d=0.8, h=1.0, placement="mounted", fc=0.0, priority=5)),
    (("curtain", "blind"), dict(w=4.0, d=0.2, h=6.0, placement="window", fc=0.0, priority=5)),
    (("rug", "carpet"), dict(w=5.0, d=7.0, h=0.0, placement="rug", fc=0.0, priority=5)),
]
DEFAULT_SPEC = dict(w=2.5, d=2.0, h=3.0, placement="wall", fc=2.0, priority=40)

VALID_PLACEMENTS = {"wall", "corner", "free", "mounted", "rug", "window"}

RELATION_ALIASES = {
    "beside": "next_to", "next to": "next_to", "adjacent": "next_to", "adjacent_to": "next_to",
    "near": "next_to", "by": "next_to", "on_each_side_of": "next_to", "either_side_of": "next_to",
    "in front of": "in_front_of", "front_of": "in_front_of",
    "over": "above", "on the wall above": "above",
    "on": "on_top_of", "on top of": "on_top_of", "on_top": "on_top_of",
    "under": "below", "underneath": "below", "beneath": "below",
    "opposite_to": "opposite", "across_from": "opposite",
    "against": "against_wall", "against wall": "against_wall", "on_wall": "against_wall",
    "corner": "in_corner", "near window": "near_window", "near door": "near_door",
}


def catalog_spec(name: str) -> dict:
    lowered = name.lower()
    best, best_len = None, 0
    for keywords, spec in CATALOG:
        for keyword in keywords:
            # allow plurals: "dining chairs", "wall shelves", "bedside tables"
            if re.search(r"\b" + re.escape(keyword) + r"(s|es)?\b", lowered) and len(keyword) > best_len:
                best, best_len = spec, len(keyword)
    return dict(best or DEFAULT_SPEC)


def normalize_relation(relation: str) -> str:
    relation = (relation or "").strip().lower()
    relation = RELATION_ALIASES.get(relation, relation)
    return relation.replace(" ", "_")


# ------------------------------------------------------------------
# Geometry helpers. A rect is (x, y, w, h).
# ------------------------------------------------------------------

def overlaps(a, b):
    return not (a[0] + a[2] <= b[0] + EPS or b[0] + b[2] <= a[0] + EPS or
                a[1] + a[3] <= b[1] + EPS or b[1] + b[3] <= a[1] + EPS)


def rect_gap(a, b):
    dx = max(0.0, b[0] - (a[0] + a[2]), a[0] - (b[0] + b[2]))
    dy = max(0.0, b[1] - (a[1] + a[3]), a[1] - (b[1] + b[3]))
    return math.hypot(dx, dy)


def center(r):
    return r[0] + r[2] / 2, r[1] + r[3] / 2


def frange(start, stop, step):
    values, v = [], start
    while v <= stop + EPS:
        values.append(round(v, 4))
        v += step
    return values


def front_rect(r, facing, dist):
    x, y, w, h = r
    if dist <= 0:
        return None
    return {"up": (x, y + h, w, dist), "down": (x, y - dist, w, dist),
            "right": (x + w, y, dist, h), "left": (x - dist, y, dist, h)}[facing]


def side_rects(r, facing, dist):
    x, y, w, h = r
    if facing in ("up", "down"):
        return [(x - dist, y, dist, h), (x + w, y, dist, h)]
    return [(x, y - dist, w, dist), (x, y + h, w, dist)]


# ------------------------------------------------------------------
# Data classes
# ------------------------------------------------------------------

@dataclass
class Item:
    uid: str
    name: str
    width: float
    depth: float
    height: float
    placement: str
    front_clearance: float = 0.0
    side_clearance: float = 0.0
    side_mode: str = ""
    all_sides: float = 0.0
    center: bool = False
    priority: int = 40
    preferred_wall: str = "any"
    relations: list = field(default_factory=list)  # [{"relation", "target", "source"}]
    source: str = "user"

    def footprint(self, facing):
        return (self.width, self.depth) if facing in ("up", "down") else (self.depth, self.width)


@dataclass
class Placed:
    item: Item
    rect: tuple
    facing: str
    wall: str
    zones: list
    access: list
    kind: str = "floor"  # floor | mounted | rug | window
    attached_to: str = ""


def build_item(uid: str, data: dict) -> Item:
    """Create an Item from a plan entry, sanity-checking the LLM's sizes against the catalog."""
    name = (data.get("name") or "item").strip()
    spec = catalog_spec(name)

    def pick(key, llm_value, lo, hi):
        default = spec[key]
        try:
            value = float(llm_value)
        except (TypeError, ValueError):
            return default
        if value < lo or value > hi:
            return default
        # Reject wildly unrealistic sizes (more than 2x off the typical size)
        if default > 0.3 and not (default / 2 <= value <= default * 2):
            return default
        return value

    placement = (data.get("placement") or "").lower().strip()
    if spec["placement"] in ("mounted", "rug", "window"):
        placement = spec["placement"]  # a mirror is always wall-mounted, whatever the LLM says
    elif placement not in VALID_PLACEMENTS or placement in ("rug", "window"):
        placement = spec["placement"]

    relations = []
    for rel in data.get("relations") or []:
        relation = normalize_relation(rel.get("relation"))
        if relation:
            relations.append({"relation": relation, "target": (rel.get("target") or "").strip(),
                              "source": rel.get("source") or data.get("source") or "suggested"})

    preferred_wall = (data.get("preferred_wall") or "any").lower()
    return Item(
        uid=uid,
        name=name,
        width=pick("w", data.get("width_ft"), 0.5, 20),
        depth=pick("d", data.get("depth_ft"), 0.1, 12),
        height=pick("h", data.get("height_ft"), 0.0, 9) if spec["h"] > 0 else 0.0,
        placement=placement,
        front_clearance=spec["fc"],
        side_clearance=spec.get("sc", 0.0),
        side_mode=spec.get("side_mode", ""),
        all_sides=spec.get("all", 0.0),
        center=spec.get("center", False),
        priority=spec["priority"],
        preferred_wall=preferred_wall if preferred_wall in WALLS else "any",
        relations=relations,
        source=data.get("source") or "user",
    )


# ------------------------------------------------------------------
# Openings (doors / windows)
# ------------------------------------------------------------------

def wall_length(wall, room_w, room_h):
    return room_w if wall in ("bottom", "top") else room_h


def resolve_openings(openings: list, room_w: float, room_h: float) -> list:
    """
    Turn loose door/window descriptions into exact positions.
    Accepts {"type", "wall", "position": "left"/"center"/"right" or feet, "length"}.
    Guarantees exactly one door, at least one window, all inside their walls and not overlapping.
    """
    resolved = []

    def fits(candidate):
        for other in resolved:
            if other["wall"] == candidate["wall"]:
                if not (candidate["position"] + candidate["length"] + 0.5 <= other["position"] or
                        other["position"] + other["length"] + 0.5 <= candidate["position"]):
                    return False
        return True

    def add(kind, wall, position, length):
        wl = wall_length(wall, room_w, room_h)
        length = max(1.5, min(length, wl - 1.0))
        if isinstance(position, str) or position is None:
            hint = (position or "").lower()
            if kind == "door":
                slots = {"left": 0.5, "start": 0.5, "right": wl - length - 0.5, "end": wl - length - 0.5,
                         "center": (wl - length) / 2, "middle": (wl - length) / 2}
                position = slots.get(hint, 0.5)
            else:
                slots = {"left": wl * 0.2, "start": wl * 0.2, "right": wl * 0.8 - length, "end": wl * 0.8 - length}
                position = slots.get(hint, (wl - length) / 2)
        position = max(0.25, min(float(position), wl - length - 0.25))
        candidate = {"type": kind, "wall": wall, "position": round(position, 2), "length": round(length, 2)}
        if fits(candidate):
            resolved.append(candidate)
            return True
        # Slide along the wall to the nearest free spot
        for offset in frange(0.25, wl, 0.25):
            for sign in (1, -1):
                p = position + sign * offset
                if 0.25 <= p <= wl - length - 0.25:
                    candidate["position"] = round(p, 2)
                    if fits(candidate):
                        resolved.append(candidate)
                        return True
        return False

    doors = [o for o in openings if o.get("type") == "door"]
    windows = [o for o in openings if o.get("type") == "window"]

    door = doors[0] if doors else {}
    door_wall = door.get("wall") if door.get("wall") in WALLS else "bottom"
    add("door", door_wall, door.get("position"), float(door.get("length") or 3.0))

    placed_window = False
    for window in windows:
        wall = window.get("wall")
        if wall not in WALLS:
            # Unknown: put it opposite the door (most common) unless another window already sits there
            wall = OPPOSITE_WALL[door_wall]
        placed_window = add("window", wall, window.get("position"), float(window.get("length") or 4.0)) or placed_window
    if not placed_window:
        add("window", OPPOSITE_WALL[door_wall], None, 4.0)
    return resolved


def opening_span_rect(opening, room_w, room_h, depth, margin=0.25):
    """Rect in front of a door/window, extending `depth` into the room."""
    p, length, wall = opening["position"] - margin, opening["length"] + 2 * margin, opening["wall"]
    if wall == "bottom":
        return (p, 0, length, depth)
    if wall == "top":
        return (p, room_h - depth, length, depth)
    if wall == "left":
        return (0, p, depth, length)
    return (room_w - depth, p, depth, length)


# ------------------------------------------------------------------
# The engine
# ------------------------------------------------------------------

class LayoutEngine:
    def __init__(self, room_w, room_h, openings, previous_positions=None):
        self.W, self.H = float(room_w), float(room_h)
        self.nx, self.ny = int(round(self.W / CELL)), int(round(self.H / CELL))
        self.openings = openings
        self.doors = [o for o in openings if o["type"] == "door"]
        self.windows = [o for o in openings if o["type"] == "window"]
        self.door_zones = [opening_span_rect(d, self.W, self.H, d["length"] + 0.5) for d in self.doors]
        self.window_zones = [opening_span_rect(w, self.W, self.H, 1.5) for w in self.windows]
        self.previous = previous_positions or {}
        self.choices = {}      # uid -> index of the alternative position to use (layout search)
        self.total_score = 0.0
        self._zone_cache = {}
        self.placed = []
        self.warnings = []
        self.items = []
        self.related_pairs = set()
        self.window_sensitive = set()

    # ---------------- relations ----------------

    def resolve_target(self, target: str, exclude_uid: str = ""):
        """Find the item a relation points at, by name (exact, then partial match)."""
        t = (target or "").lower().strip()
        if not t or t in ("window", "door", "wall", "room") or t in WALLS:
            return None
        candidates = [i for i in self.items if i.uid != exclude_uid]
        words = set(re.findall(r"[a-z0-9]+", t)) - {"a", "the", "my"}
        filler = {"small", "large", "big", "medium", "wall", "mounted"}
        for match in (lambda i: i.name.lower() == t,
                      lambda i: words <= set(re.findall(r"[a-z0-9]+", i.name.lower())),
                      lambda i: (words - filler) & (set(re.findall(r"[a-z0-9]+", i.name.lower())) - filler)):
            found = [i for i in candidates if match(i)]
            if found:
                return found
        return None

    def targets_of(self, item):
        out = []
        for rel in item.relations:
            found = self.resolve_target(rel["target"], item.uid)
            if found:
                out.append((rel, found))
        return out

    def is_related(self, a: Item, b: Item):
        return (a.uid, b.uid) in self.related_pairs or (b.uid, a.uid) in self.related_pairs

    def placed_by_uid(self, uid):
        for p in self.placed:
            if p.item.uid == uid:
                return p
        return None

    def placed_targets(self, found):
        """Placed instances among the candidate target items (nearest-first ordering is up to caller)."""
        return [p for p in (self.placed_by_uid(i.uid) for i in found) if p]

    # ---------------- ordering ----------------

    def ordered_items(self):
        floor = [i for i in self.items if i.placement in ("wall", "corner", "free")]
        rest = [i for i in self.items if i not in floor]
        deps = {i.uid: {t.uid for _, found in self.targets_of(i) for t in found[:1]} for i in self.items}
        order, done = [], set()
        # Like a designer: big wall pieces first, then free-standing tables in the space left
        def effective_priority(i):
            return i.priority - 40 if i.placement == "free" else i.priority
        pending = sorted(floor, key=lambda i: (-effective_priority(i), -i.width * i.depth))
        while pending:
            ready = [i for i in pending if deps[i.uid] <= done | {x.uid for x in rest}]
            nxt = ready[0] if ready else pending[0]  # break cycles by priority
            order.append(nxt)
            done.add(nxt.uid)
            pending.remove(nxt)
        # mounted / rugs / window decor go last, after the things they hang above
        return order + sorted(rest, key=lambda i: -i.priority)

    # ---------------- candidate generation ----------------

    def wall_candidates(self, item, walls):
        for wall in walls:
            facing = FACING_FOR_WALL[wall]
            w, h = item.footprint(facing)
            if w > self.W + EPS or h > self.H + EPS:
                continue
            if wall in ("bottom", "top"):
                y = 0.0 if wall == "bottom" else self.H - h
                for x in frange(0, self.W - w, CELL):
                    yield (x, y, w, h), facing, wall
            else:
                x = 0.0 if wall == "left" else self.W - w
                for y in frange(0, self.H - h, CELL):
                    yield (x, y, w, h), facing, wall

    def free_candidates(self, item):
        for facing in ("up", "down", "left", "right"):
            w, h = item.footprint(facing)
            for x in frange(0, self.W - w, 0.5):
                for y in frange(0, self.H - h, 0.5):
                    yield (x, y, w, h), facing, self.touching_wall((x, y, w, h), facing)

    def touching_wall(self, r, facing):
        wall = WALL_FOR_FACING[facing]
        x, y, w, h = r
        touching = {"bottom": y <= EPS, "top": y + h >= self.H - EPS,
                    "left": x <= EPS, "right": x + w >= self.W - EPS}
        return wall if touching[wall] else ""

    def relation_candidates(self, item):
        """Positions that directly satisfy the item's relations to already-placed pieces."""
        for rel, found in self.targets_of(item):
            relation = rel["relation"]
            for target in self.placed_targets(found):
                tx, ty, tw, th = target.rect
                tcx, tcy = center(target.rect)
                if relation in ("next_to", "below"):
                    if target.wall:
                        facing = target.facing
                        w, h = item.footprint(facing)
                        g = 0.15
                        if facing == "up":
                            spots = [(tx - w - g, ty), (tx + tw + g, ty)]
                        elif facing == "down":
                            spots = [(tx - w - g, ty + th - h), (tx + tw + g, ty + th - h)]
                        elif facing == "right":
                            spots = [(tx, ty - h - g), (tx, ty + th + g)]
                        else:
                            spots = [(tx + tw - w, ty - h - g), (tx + tw - w, ty + th + g)]
                        for x, y in spots:
                            yield (x, y, w, h), facing, target.wall
                    else:
                        # around a free-standing piece (e.g. chairs around a dining table), facing it
                        for facing, (x, y) in self._around(item, target.rect):
                            yield (x, y) + item.footprint(facing), facing, ""
                elif relation in ("in_front_of", "facing") and target.wall:
                    facing = OPPOSITE_FACING[target.facing]
                    w, h = item.footprint(facing)
                    dist = self.front_distance(item)
                    for shift in (0, -0.5, 0.5, -1.0, 1.0):
                        if target.facing == "up":
                            x, y = tcx - w / 2 + shift, ty + th + dist
                        elif target.facing == "down":
                            x, y = tcx - w / 2 + shift, ty - dist - h
                        elif target.facing == "right":
                            x, y = tx + tw + dist, tcy - h / 2 + shift
                        else:
                            x, y = tx - dist - w, tcy - h / 2 + shift
                        yield (x, y, w, h), facing, ""

    @staticmethod
    def front_distance(item):
        """Comfortable gap between a piece and the thing it stands in front of."""
        lowered = item.name.lower()
        if "chair" in lowered or "stool" in lowered:
            return -0.6  # tucked partly under the desk / dressing table
        if "coffee" in lowered or "cent" in lowered or item.height <= 1.8:
            return 1.4  # knee space between sofa and coffee table
        return 2.5

    def _around(self, item, t):
        """Spots along every side of a free-standing piece, facing it (e.g. 6 chairs round a table)."""
        tx, ty, tw, th = t
        g = 0.1
        w, h = item.footprint("down")
        for x in frange(tx, tx + tw - w, CELL):
            yield "down", (x, ty + th + g)
        w, h = item.footprint("up")
        for x in frange(tx, tx + tw - w, CELL):
            yield "up", (x, ty - h - g)
        w, h = item.footprint("left")
        for y in frange(ty, ty + th - h, CELL):
            yield "left", (tx + tw + g, y)
        w, h = item.footprint("right")
        for y in frange(ty, ty + th - h, CELL):
            yield "right", (tx - w - g, y)

    def candidates(self, item, level):
        walls = list(WALLS)
        forced_wall = None
        for rel in item.relations:
            if rel["relation"] == "against_wall" and rel["target"].lower() in WALLS:
                forced_wall = rel["target"].lower()
        if forced_wall and level < 2:
            walls = [forced_wall]

        seen = set()
        sources = [self.relation_candidates(item)]
        if item.placement == "free":
            sources.append(self.free_candidates(item))
        else:
            sources.append(self.wall_candidates(item, walls))
            # Last resort: let a wall piece float if that is the only way it fits. Not for pieces
            # with a mirror/shelf hanging above them - those need a wall behind them.
            if level >= 1 and item.uid not in self.window_sensitive:
                sources.append(self.free_candidates(item))
        for source in sources:
            for rect, facing, wall in source:
                key = (round(rect[0], 2), round(rect[1], 2), facing)
                if key not in seen:
                    seen.add(key)
                    yield rect, facing, wall

    # ---------------- zones ----------------

    def zones_for(self, item, rect, facing, level):
        """Keep-clear zones and access zones for an item at a position. Returns None if impossible."""
        mult = LEVELS[level][1]
        radius = LEVELS[level][2]
        zones, access = [], []
        fc = item.front_clearance * mult
        front = front_rect(rect, facing, fc)
        if front:
            if not self.inside(front):
                return None  # facing straight into a wall
            zones.append(front)
            access.append(front_rect(rect, facing, max(fc, radius + 0.5)))
        if item.side_clearance > 0:
            sides = [s for s in side_rects(rect, facing, item.side_clearance * mult) if self.inside(s)]
            need = 2 if (item.side_mode == "both" and level == 0) else 1
            if len(sides) < need:
                return None
            zones.extend(sides)
            access.extend(sides)
        if item.all_sides > 0:
            around = (rect[0] - item.all_sides * mult, rect[1] - item.all_sides * mult,
                      rect[2] + 2 * item.all_sides * mult, rect[3] + 2 * item.all_sides * mult)
            # Chair space on every side of a dining table; only when squeezed may one side touch a wall
            if level == 0 and not self.inside(around):
                return None
            zones.append(around)
            access.append(around)
        return zones, access

    def inside(self, r):
        return r[0] >= -EPS and r[1] >= -EPS and r[0] + r[2] <= self.W + EPS and r[1] + r[3] <= self.H + EPS

    # ---------------- hard rules ----------------

    def passes_rules(self, item, rect, facing, zones, level):
        if not self.inside(rect):
            return False
        min_gap = LEVELS[level][0]
        for dz in self.door_zones:
            if overlaps(rect, dz):
                return False
        if item.height > TALL_FT or item.uid in self.window_sensitive:
            for wz in self.window_zones:
                if overlaps(rect, wz):
                    return False
        # A chair tucked into its desk's own clearance area is part of using the desk, so it
        # may share that area with neighbouring clearances (not with other furniture bodies).
        in_parent_zone = self._inside_parent_zone(item, rect)
        for p in self.placed:
            if p.kind != "floor":
                continue
            if overlaps(rect, p.rect) and not (in_parent_zone and self.is_related(item, p.item)):
                return False  # (a chair may tuck under its own desk)
            if self.is_related(item, p.item):
                continue
            if rect_gap(rect, p.rect) < min_gap - EPS:
                return False
            p_zones = self._zones_at_level(p, level)
            if not in_parent_zone and any(overlaps(rect, z) for z in p_zones):
                return False
            # The chair pull-out space round a dining table can't double as another piece's
            # clearance (the rest of the space round the table may be shared walkway)
            if item.all_sides > 0 and any(overlaps(self._chair_zone(rect), pz) for pz in p_zones):
                return False
            if p.item.all_sides > 0 and any(overlaps(z, self._chair_zone(p.rect)) for z in zones):
                return False
            if any(overlaps(z, p.rect) for z in zones):
                return False
        return True

    def _zones_at_level(self, placed, level):
        """
        Clearances of an already-placed piece under the current relaxation level: when the room
        is tight, every piece gives up some clearance, not only the one being placed now.
        """
        if level == 0:
            return placed.zones
        key = (id(placed), level)
        if key not in self._zone_cache:
            relaxed = self.zones_for(placed.item, placed.rect, placed.facing, level)
            self._zone_cache[key] = relaxed[0] if relaxed else placed.zones
        return self._zone_cache[key]

    @staticmethod
    def _chair_zone(rect, pull_out=1.75):
        return (rect[0] - pull_out, rect[1] - pull_out, rect[2] + 2 * pull_out, rect[3] + 2 * pull_out)

    def _inside_parent_zone(self, item, rect):
        if item.placement != "free":
            return False
        for rel, found in self.targets_of(item):
            if rel["relation"] not in ("in_front_of", "facing"):
                continue
            for parent in self.placed_targets(found):
                front = parent.zones[0] if parent.zones else None
                if not front:
                    continue
                x0 = min(parent.rect[0], front[0]) - EPS
                y0 = min(parent.rect[1], front[1]) - EPS
                x1 = max(parent.rect[0] + parent.rect[2], front[0] + front[2]) + EPS
                y1 = max(parent.rect[1] + parent.rect[3], front[1] + front[3]) + EPS
                if rect[0] >= x0 and rect[1] >= y0 and rect[0] + rect[2] <= x1 and rect[1] + rect[3] <= y1:
                    return True
        return False

    # ---------------- walkway check ----------------

    def walkable(self, extra: Placed, level):
        radius = LEVELS[level][2]
        occ = np.zeros((self.nx, self.ny), dtype=bool)
        bodies = [p for p in self.placed if p.kind == "floor"] + [extra]
        for p in bodies:
            self._mark(occ, p.rect)
        k = int(math.ceil(radius / CELL))
        blocked = self._dilate(occ, k)
        # the walker's centre cannot be closer than `radius` to a wall
        edge = int(math.ceil(radius / CELL - 0.5))
        if edge > 0:
            blocked[:edge, :] = True
            blocked[-edge:, :] = True
            blocked[:, :edge] = True
            blocked[:, -edge:] = True

        starts = []
        for dz in self.door_zones:
            starts.extend(self._cells_in(dz, blocked))
        if not starts:
            return False

        reached = np.zeros_like(blocked)
        queue = deque(starts)
        for c in starts:
            reached[c] = True
        while queue:
            i, j = queue.popleft()
            for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                a, b = i + di, j + dj
                if 0 <= a < self.nx and 0 <= b < self.ny and not blocked[a, b] and not reached[a, b]:
                    reached[a, b] = True
                    queue.append((a, b))

        for p in bodies:
            if not p.access:
                continue
            # Skip pieces used through a movable related piece in their clearance (chair at a desk,
            # coffee table in front of a sofa): the walker reaches the chair, not the desk front.
            if any(q is not p and q.item.placement == "free" and self.is_related(p.item, q.item)
                   and any(overlaps(q.rect, a) for a in p.access) for q in bodies):
                continue
            if not any(reached[c] for a in p.access for c in self._cells_in(a, None)):
                return False
        return True

    def _mark(self, grid, r):
        i0, i1 = int(math.floor(r[0] / CELL + EPS)), int(math.ceil((r[0] + r[2]) / CELL - EPS))
        j0, j1 = int(math.floor(r[1] / CELL + EPS)), int(math.ceil((r[1] + r[3]) / CELL - EPS))
        grid[max(0, i0):min(self.nx, i1), max(0, j0):min(self.ny, j1)] = True

    def _cells_in(self, r, blocked):
        i0, i1 = max(0, int(math.floor(r[0] / CELL))), min(self.nx, int(math.ceil((r[0] + r[2]) / CELL)))
        j0, j1 = max(0, int(math.floor(r[1] / CELL))), min(self.ny, int(math.ceil((r[1] + r[3]) / CELL)))
        return [(i, j) for i in range(i0, i1) for j in range(j0, j1) if blocked is None or not blocked[i, j]]

    @staticmethod
    def _dilate(grid, k):
        if k <= 0:
            return grid.copy()
        out = grid.copy()
        padded = np.pad(grid, k)
        n, m = grid.shape
        for di in range(-k, k + 1):
            for dj in range(-k, k + 1):
                out |= padded[k + di:k + di + n, k + dj:k + dj + m]
        return out

    # ---------------- scoring (lower is better) ----------------

    def score(self, item, rect, facing, wall):
        cx, cy = center(rect)
        s = 0.0

        if item.preferred_wall in WALLS and wall != item.preferred_wall:
            s += 3.0
        if item.placement in ("wall", "corner") and not wall:
            s += 25.0  # a wall piece floating in the room is a last resort

        if wall and item.center:
            along = cx if wall in ("bottom", "top") else cy
            s += abs(along - wall_length(wall, self.W, self.H) / 2) * 0.6

        if item.placement == "corner":
            corner_dist = min(math.hypot(cx - a, cy - b) for a in (0, self.W) for b in (0, self.H))
            s += corner_dist * 1.5

        if item.all_sides > 0:  # dining tables look right in the middle of the room
            s += math.hypot(cx - self.W / 2, cy - self.H / 2) * 0.5

        # Breathing room: prefer at least ~1 ft between unrelated pieces
        for p in self.placed:
            if p.kind != "floor":
                continue
            if self.is_related(item, p.item):
                continue
            gap = rect_gap(rect, p.rect)
            if gap < 1.0:
                s += (1.0 - gap) * 4.0

        # Low pieces may sit under a window, but it is still better not to
        for wz in self.window_zones:
            if overlaps(rect, wz):
                s += 2.0

        # Stay out of the way of the door
        for d in self.doors:
            dcx, dcy = center(opening_span_rect(d, self.W, self.H, 0.1))
            dist = math.hypot(cx - dcx, cy - dcy)
            if dist < 5 and item.height > TALL_FT:
                s += (5 - dist) * 1.0

        for rel in item.relations:
            weight = 10.0 if rel["source"] == "user" else 3.0
            s += weight * self.relation_cost(item, rel, rect, facing, wall)

        prev = self.previous.get(item.name.lower())
        if prev:
            s += min(math.hypot(cx - px, cy - py) for px, py in prev) * 0.8
        return s

    def relation_cost(self, item, rel, rect, facing, wall):
        relation = rel["relation"]
        cx, cy = center(rect)
        target = rel["target"].lower()

        def nearest(points):
            return min((math.hypot(cx - x, cy - y) for x, y in points), default=0.0)

        window_centers = [center(opening_span_rect(w, self.W, self.H, 0.1)) for w in self.windows]
        door_centers = [center(opening_span_rect(d, self.W, self.H, 0.1)) for d in self.doors]

        if relation == "near_window":
            return nearest(window_centers) / 2
        if relation == "away_from_window":
            return max(0.0, 8 - nearest(window_centers)) / 2
        if relation == "near_door":
            return nearest(door_centers) / 2
        if relation == "away_from_door":
            return max(0.0, 10 - nearest(door_centers)) / 2
        if relation == "in_corner":
            return min(math.hypot(cx - a, cy - b) for a in (0, self.W) for b in (0, self.H)) / 2
        if relation == "centered":
            return math.hypot(cx - self.W / 2, cy - self.H / 2) / 3
        if relation == "against_wall":
            if target in WALLS:
                return 0.0 if wall == target else 3.0
            return 0.0 if wall else 3.0

        found = self.resolve_target(rel["target"], item.uid)
        placed = self.placed_targets(found) if found else []
        if not placed:
            return 0.0
        costs = []
        for t in placed:
            tcx, tcy = center(t.rect)
            if relation in ("next_to", "below"):
                cost = rect_gap(rect, t.rect)
                if not t.wall:
                    # Around a free-standing piece (chairs at a dining table): sit squarely
                    # along one side, facing it, not diagonally at a corner.
                    ox = max(0.0, min(rect[0] + rect[2], t.rect[0] + t.rect[2]) - max(rect[0], t.rect[0])) / rect[2]
                    oy = max(0.0, min(rect[1] + rect[3], t.rect[1] + t.rect[3]) - max(rect[1], t.rect[1])) / rect[3]
                    cost += (1.0 - max(ox, oy)) * 3.0
                    dx, dy = tcx - cx, tcy - cy
                    expected = ("right" if dx > 0 else "left") if abs(dx) > abs(dy) else ("up" if dy > 0 else "down")
                    if facing != expected:
                        cost += 1.0
                costs.append(cost)
            elif relation in ("in_front_of", "facing"):
                axis_offset = abs(cx - tcx) if t.facing in ("up", "down") else abs(cy - tcy)
                costs.append(abs(rect_gap(rect, t.rect) - self.front_distance(item)) * 2 + axis_offset / 2)
            elif relation == "opposite":
                if t.wall and wall == OPPOSITE_WALL[t.wall]:
                    along = abs(cx - tcx) if wall in ("bottom", "top") else abs(cy - tcy)
                    costs.append(along / 2)
                else:
                    costs.append(4.0)
            else:
                costs.append(0.0)
        return min(costs)

    # ---------------- placement ----------------

    def is_companion(self, item):
        """A movable piece that belongs with another one: desk chair, dining chair, coffee table."""
        if item.placement != "free":
            return False
        return any(rel["relation"] in ("in_front_of", "facing", "next_to") and self.placed_targets(found)
                   for rel, found in self.targets_of(item))

    def place_floor_item(self, item):
        # A desk chair should sit at its desk even if that needs relaxed rules; it may only
        # go somewhere else in the room if there is truly no space at the desk.
        if self.is_companion(item):
            for level in range(len(LEVELS)):
                if self._place_at_level(item, level, self.relation_candidates(item)):
                    return True
        for level in range(len(LEVELS)):
            if self._place_at_level(item, level, self.candidates(item, level)):
                return True
        return False

    def _place_at_level(self, item, level, candidates):
        scored = []
        for rect, facing, wall in candidates:
            zones = self.zones_for(item, rect, facing, level)
            if zones is None:
                continue
            if not self.passes_rules(item, rect, facing, zones[0], level):
                continue
            scored.append((self.score(item, rect, facing, wall), rect, facing, wall, zones))
        scored.sort(key=lambda s: s[0])
        skip = self.choices.get(item.uid, 0)  # take the n-th best distinct option (layout search)
        used_orientations = set()
        for score, rect, facing, wall, (zones, access) in scored[:150]:
            if skip and (wall, facing) in used_orientations:
                continue
            candidate = Placed(item, rect, facing, wall, zones, access)
            if self.walkable(candidate, level):
                if skip:
                    used_orientations.add((wall, facing))
                    skip -= 1
                    continue
                self.placed.append(candidate)
                self.total_score += score + level * 20
                return True
        return False

    def place_mounted(self, item, use_targets=True):
        """Wall items: mirror above cupboard, TV opposite sofa, shelves... no floor footprint."""
        wall, along_center, attached = None, None, ""
        for rel, found in (self.targets_of(item) if use_targets else []):
            targets = self.placed_targets(found)
            if not targets:
                continue
            t = targets[0]
            tcx, tcy = center(t.rect)
            if rel["relation"] in ("above", "on_top_of", "next_to", "below", "in_front_of") and t.wall:
                wall, attached = t.wall, t.item.name
                along_center = tcx if wall in ("bottom", "top") else tcy
                break
            if rel["relation"] in ("opposite", "facing") and t.wall:
                wall = OPPOSITE_WALL[t.wall]
                along_center = tcx if wall in ("bottom", "top") else tcy
                break
        for rel in item.relations:
            if wall is None and rel["relation"] == "against_wall" and rel["target"].lower() in WALLS:
                wall = rel["target"].lower()
        if wall is None:
            wall = item.preferred_wall if item.preferred_wall in WALLS else self._freest_wall()
        wl = wall_length(wall, self.W, self.H)
        width = min(item.width, wl - 0.5)
        if attached:
            # A mirror above a cupboard should not be wider than the cupboard
            target = next(p for p in self.placed if p.item.name == attached)
            span = target.rect[2] if wall in ("bottom", "top") else target.rect[3]
            width = min(width, span)
        if along_center is None:
            along_center = wl / 2
        # Attached items sit exactly over their target; others may slide to find free wall space
        offsets = [0.0] if attached else [0.0] + [s * o for o in frange(0.25, wl, 0.25) for s in (1, -1)]
        for offset in offsets:
            start = along_center - width / 2 + offset
            if start < 0 or start + width > wl + EPS:
                continue
            if self._wall_segment_free(wall, start, width):
                self.placed.append(Placed(item, self._wall_strip(wall, start, width), FACING_FOR_WALL[wall],
                                          wall, [], [], kind="mounted", attached_to=attached))
                return True
        if use_targets:
            # e.g. two mounted things above the same cupboard: find any free wall space instead
            return self.place_mounted(item, use_targets=False)
        return False

    def _wall_strip(self, wall, start, width, depth=0.35):
        if wall == "bottom":
            return (start, 0, width, depth)
        if wall == "top":
            return (start, self.H - depth, width, depth)
        if wall == "left":
            return (0, start, depth, width)
        return (self.W - depth, start, depth, width)

    def _wall_segment_free(self, wall, start, width):
        for o in self.openings:
            if o["wall"] == wall and not (start + width <= o["position"] or o["position"] + o["length"] <= start):
                return False
        for p in self.placed:
            if p.kind == "mounted" and p.wall == wall:
                ps = p.rect[0] if wall in ("bottom", "top") else p.rect[1]
                pw = p.rect[2] if wall in ("bottom", "top") else p.rect[3]
                if not (start + width + 0.25 <= ps or ps + pw + 0.25 <= start):
                    return False
        return True

    def _freest_wall(self):
        best, best_free = "top", -1
        for wall in WALLS:
            used = sum(o["length"] for o in self.openings if o["wall"] == wall)
            used += sum((p.rect[2] if wall in ("bottom", "top") else p.rect[3])
                        for p in self.placed if p.kind == "mounted" and p.wall == wall)
            free = wall_length(wall, self.W, self.H) - used
            if free > best_free:
                best, best_free = wall, free
        return best

    def place_rug(self, item):
        w = min(item.width, self.W * 0.7)
        h = min(item.depth, self.H * 0.7)
        cx, cy = self.W / 2, self.H / 2
        attached = ""
        for rel, found in self.targets_of(item):
            targets = self.placed_targets(found)
            if targets:
                cx, cy = center(targets[0].rect)
                attached = targets[0].item.name
                break
        x = min(max(0, cx - w / 2), self.W - w)
        y = min(max(0, cy - h / 2), self.H - h)
        self.placed.append(Placed(item, (x, y, w, h), "up", "", [], [], kind="rug", attached_to=attached))
        return True

    def place_window_decor(self, item):
        used = {p.attached_to for p in self.placed if p.kind == "window"}
        for i, window in enumerate(self.windows):
            label = f"window {i + 1}"
            if label in used and i < len(self.windows) - 1:
                continue
            wall = window["wall"]
            rect = self._wall_strip(wall, window["position"] - 0.25, window["length"] + 0.5, depth=0.2)
            self.placed.append(Placed(item, rect, FACING_FOR_WALL[wall], wall, [], [], kind="window", attached_to=label))
            return True
        return False

    # ---------------- main entry ----------------

    def run(self, items):
        self.items = items
        for item in items:
            for rel, found in self.targets_of(item):
                if rel["relation"] in ("next_to", "in_front_of", "facing", "on_top_of", "above", "below"):
                    for t in found:
                        self.related_pairs.add((item.uid, t.uid))
                if rel["relation"] in ("above", "on_top_of") and item.placement == "mounted":
                    # Something hangs above this piece, so it must not sit under a window
                    for t in found:
                        self.window_sensitive.add(t.uid)

        floor_area = sum(i.width * i.depth for i in items if i.placement in ("wall", "corner", "free"))
        if floor_area > 0.55 * self.W * self.H:
            self.warnings.append(
                f"The furniture needs about {floor_area / (self.W * self.H):.0%} of the floor. "
                "Rooms feel cramped above ~50%, so consider fewer or smaller pieces."
            )

        not_placed, skipped, shrunk = [], [], []
        for item in self.ordered_items():
            orphan_of = self._missing_parent(item, not_placed)
            if orphan_of:
                skipped.append((item.name, orphan_of))
                not_placed.append(item.name)
                continue
            if item.placement in ("wall", "corner", "free"):
                ok = self.place_floor_item(item)
                if not ok and item.width >= 2.5:
                    # Try a compact version before giving up (e.g. a 3.2 ft study table)
                    original = (item.width, item.depth)
                    item.width, item.depth = round(item.width * 0.8, 2), round(max(item.depth * 0.85, 1.0), 2)
                    ok = self.place_floor_item(item)
                    if ok:
                        shrunk.append((item.name, item.width))
                    else:
                        item.width, item.depth = original
            elif item.placement == "mounted":
                ok = self.place_mounted(item)
            elif item.placement == "rug":
                ok = self.place_rug(item)
            else:
                ok = self.place_window_decor(item)
            if not ok:
                not_placed.append(item.name)

        for name, width in shrunk:
            self.warnings.append(f"Used a compact {name} (about {width:g} ft wide) so it fits comfortably.")
        skipped_names = {name for name, _ in skipped}
        for name, parent in skipped:
            self.warnings.append(f"Left out the {name} because the {parent} did not fit.")
        for name in [n for n in not_placed if n not in skipped_names]:
            self.warnings.append(
                f"Could not fit the {name} without blocking the door, a window or a walkway. "
                "Try a smaller one, or remove another piece."
            )
        self._check_user_relations()
        self.warnings = list(dict.fromkeys(self.warnings))  # two bedside tables -> one note
        return self.placed, not_placed, self.warnings

    def _missing_parent(self, item, not_placed):
        """A chair for a desk that did not fit, a rug for a missing coffee table, ..."""
        if item.source == "user" and item.placement in ("wall", "corner"):
            return None
        for rel, found in self.targets_of(item):
            if rel["relation"] in ("in_front_of", "next_to", "below", "on_top_of") and                     all(f.name in not_placed for f in found) and item.placement in ("free", "rug", "mounted"):
                return found[0].name
        return None

    def _check_user_relations(self):
        """Tell the user when one of their own placement wishes could not be honoured."""
        for p in self.placed:
            for rel in p.item.relations:
                if rel["source"] != "user" and not (p.item.source == "user" and rel["relation"] == "next_to"):
                    continue
                relation = rel["relation"]
                if relation in ("above", "on_top_of") and p.kind == "mounted":
                    found = self.resolve_target(rel["target"], p.item.uid) or []
                    if found and p.attached_to not in [f.name for f in found]:
                        self.warnings.append(f"Couldn't hang the {p.item.name} {relation.replace('_', ' ')} the {rel['target']}.")
                elif relation == "next_to" and p.kind == "floor":
                    found = self.resolve_target(rel["target"], p.item.uid) or []
                    targets = self.placed_targets(found)
                    if targets and min(rect_gap(p.rect, t.rect) for t in targets) > 0.6:
                        self.warnings.append(f"There wasn't space for the {p.item.name} right next to the "
                                             f"{rel['target']}, so it's placed nearby.")
                elif relation == "against_wall" and rel["target"].lower() in WALLS and p.wall != rel["target"].lower():
                    self.warnings.append(f"The {p.item.name} didn't fit against the {rel['target']} wall.")
                elif relation in ("near_window", "near_door"):
                    spots = self.windows if relation == "near_window" else self.doors
                    cx, cy = center(p.rect)
                    dist = min((math.hypot(cx - ox, cy - oy) for ox, oy in
                                (center(opening_span_rect(o, self.W, self.H, 0.1)) for o in spots)), default=0)
                    if dist > 4.5:
                        where = "window" if relation == "near_window" else "door"
                        self.warnings.append(f"The {where} wall was needed for other pieces, so the "
                                             f"{p.item.name} couldn't go near the {where}.")


def generate_layout(room_w, room_h, plan_items, openings, previous_positions=None):
    """
    plan_items: list of dicts {name, width_ft, depth_ft, height_ft, placement, preferred_wall, relations, source}
    openings:   list of dicts {type, wall, position, length} (loose; resolved here)
    Returns layout_data dict ready to draw and store.
    """
    resolved = resolve_openings(openings, room_w, room_h)

    def attempt(choices):
        items = [build_item(f"i{n}", data) for n, data in enumerate(plan_items)]
        engine = LayoutEngine(room_w, room_h, resolved, previous_positions)
        engine.choices = choices
        placed, not_placed, warnings = engine.run(items)
        lost = sum(i.priority + 50 for i in items if i.name in not_placed)
        # Wishes the user stated ("desk near the window", "mirror above the cupboard") weigh
        # more than design defaults ("bedside table right next to the bed")
        broken_wishes = sum(2.5 if w.startswith(("Couldn't", "The ")) else 0.75
                            for w in warnings if w.startswith(("Couldn't", "The ", "There wasn't")))
        return (lost * 1000 + broken_wishes * 200 + engine.total_score), (placed, not_placed, warnings), engine

    # Greedy placement can paint itself into a corner (the bed takes the only spot the desk
    # could use). Try a few alternative spots for the biggest pieces and keep the best layout.
    best_cost, best, engine = attempt({})

    def has_problems(result):
        _, not_placed, warnings = result
        return bool(not_placed) or any(not w.startswith("Used a compact") for w in warnings)

    anchors = [i.uid for i in engine.ordered_items() if i.placement in ("wall", "corner", "free")][:3]
    if anchors and has_problems(best):
        started = time.time()
        options = [range(4), range(3), range(2)][:len(anchors)]
        for combo in itertools.product(*options):
            if not any(combo):
                continue
            if time.time() - started > SEARCH_TIME_BUDGET_S:
                break
            cost, result, _ = attempt(dict(zip(anchors, combo)))
            if cost < best_cost:
                best_cost, best = cost, result
                if not has_problems(best):
                    break
    placed, not_placed, warnings = best

    furniture = []
    for p in placed:
        x, y, w, h = p.rect
        furniture.append({
            "item": p.item.name,
            "x": round(x, 2), "y": round(y, 2), "width": round(w, 2), "height": round(h, 2),
            "facing": p.facing,
            "wall": p.wall,
            "kind": p.kind,
            "attached_to": p.attached_to,
            "source": p.item.source,
        })

    door = next((o for o in resolved if o["type"] == "door"), None)
    window = next((o for o in resolved if o["type"] == "window"), None)
    return {
        "room_width": room_w,
        "room_height": room_h,
        "furniture": furniture,
        "door": door,
        "window": window,
        "openings": resolved,
        "not_placed": not_placed,
        "warnings": warnings,
        "plan": plan_items,
    }
