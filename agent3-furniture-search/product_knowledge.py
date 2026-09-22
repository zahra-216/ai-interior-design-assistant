"""
Domain knowledge used by Agent 3's retrieval:

  - canonical furniture categories + synonyms (so "queen bed", "TV unit",
    "dining chairs" and "bedside table" find the right products)
  - related-category fallbacks when a category has no products
  - size attributes (single/double/queen/king beds, n-seater, n-door)
  - colour families + a harmony table (navy goes with white, grey, light wood)
  - text normalisation: typo fixes seen in retailer data, light stemming,
    style synonyms for query expansion
"""

import re

# ------------------------------------------------------------------
# Text normalisation
# ------------------------------------------------------------------

# Typos found in scraped retailer descriptions
TYPO_FIXES = {
    "woodden": "wooden", "woddern": "wooden", "woden": "wooden",
    "mordern": "modern", "modren": "modern",
    "wardeobe": "wardrobe", "wardorbe": "wardrobe",
    "partical": "particle", "shelve": "shelf",
    "colour": "color", "grey": "gray",
}

# Query expansion: a style word also matches these words in product text
STYLE_SYNONYMS = {
    "modern": ["contemporary", "sleek", "minimalist", "clean"],
    "contemporary": ["modern", "sleek"],
    "minimalist": ["simple", "clean", "sleek", "modern"],
    "minimal": ["simple", "clean", "minimalist"],
    "scandinavian": ["minimalist", "simple", "light", "oak", "white", "clean"],
    "classic": ["traditional", "elegant", "ornate"],
    "traditional": ["classic", "elegant"],
    "luxury": ["elegant", "premium", "royal", "luxurious"],
    "elegant": ["luxury", "classic"],
    "industrial": ["metal", "black", "steel"],
    "rustic": ["wooden", "wood", "natural"],
    "boho": ["rattan", "cane", "natural", "wooden"],
    "wooden": ["wood", "timber", "teak", "walnut", "oak"],
    "wood": ["wooden", "timber"],
    "compact": ["small", "space", "saving", "slim"],
    "small": ["compact", "slim", "space", "saving"],
    "budget": ["low", "cost", "simple", "affordable"],
    "cozy": ["upholstered", "fabric", "soft"],
}

STOPWORDS = {"a", "an", "the", "and", "or", "with", "for", "of", "in", "to", "your", "you", "will", "is",
             "are", "this", "that", "be", "as", "at", "by", "from", "it", "its", "on", "our", "which",
             "suitable", "design", "designed", "made", "product"}


def normalize_text(text: str) -> str:
    text = (text or "").lower().replace("&", " and ")
    words = re.findall(r"[a-z0-9]+", text)
    out = []
    for w in words:
        w = TYPO_FIXES.get(w, w)
        if len(w) > 4 and w.endswith("ves"):      # shelves -> shelf
            w = w[:-3] + "f"
        elif len(w) > 3 and w.endswith("ies"):    # accessories -> accessory
            w = w[:-3] + "y"
        elif len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
            w = w[:-1]
        out.append(TYPO_FIXES.get(w, w))
    return " ".join(out)


def expand_query(text: str) -> str:
    words = normalize_text(text).split()
    expanded = list(words)
    for w in words:
        expanded.extend(STYLE_SYNONYMS.get(w, []))
    return " ".join(w for w in expanded if w not in STOPWORDS)


# ------------------------------------------------------------------
# Categories
# ------------------------------------------------------------------

# canonical category -> phrases that mean it (longest phrase wins)
CATEGORY_SYNONYMS = {
    "bed": ["bed", "king bed", "queen bed", "double bed", "single bed", "bunk bed", "day bed", "sofa cum bed"],
    "baby cot": ["baby cot", "crib", "cot"],
    "bedside table": ["bedside table", "bedside cupboard", "bedside rack", "bedside", "nightstand", "night stand",
                      "night table"],
    "wardrobe": ["wardrobe", "almirah", "closet", "cupboard wardrobe"],
    "cabinet": ["cupboard", "small cupboard", "cabinet", "storage cabinet", "storage cupboard"],
    "chest of drawers": ["chest of drawers", "drawer cabinet", "drawer unit"],
    "dressing table": ["dressing table", "dresser", "vanity", "mirror table"],
    "dressing stool": ["dressing stool", "vanity stool"],
    "stool": ["stool", "bar stool", "ottoman", "pouf"],
    "sofa": ["sofa", "couch", "settee", "sectional", "loveseat", "love seat", "sofa set", "seater"],
    "sofa bed": ["sofa bed", "sofa cum bed"],
    "armchair": ["armchair", "arm chair", "accent chair", "lounge chair", "recliner", "easy chair"],
    "coffee table": ["coffee table", "centre table", "center table"],
    "side table": ["side table", "end table"],
    "tv stand": ["tv stand", "tv unit", "tv cabinet", "tv console", "tv table", "entertainment unit",
                 "tv rack", "wall mounted tv unit"],
    "dining table": ["dining table", "dining set", "dinning table"],
    "dining chair": ["dining chair", "dinning chair"],
    "study desk": ["study desk", "study table", "desk", "computer table", "computer desk", "office table",
                   "work table", "writing table", "office desk"],
    "office chair": ["office chair", "desk chair", "study chair", "computer chair", "executive chair",
                     "visitor chair"],
    "chair": ["chair", "plastic chair"],
    "bookshelf": ["bookshelf", "book shelf", "bookcase", "book case", "book rack"],
    "wall shelf": ["wall shelf", "floating shelf", "shelf", "wall rack", "wall mounted shelf"],
    "shoe rack": ["shoe rack", "shoe cabinet", "shoe cupboard"],
    "mirror": ["mirror", "wall mirror", "full length mirror"],
    "rug": ["rug", "carpet", "floor mat", "area rug"],
    "curtain": ["curtain", "blind", "drape"],
    "lamp": ["lamp", "floor lamp", "table lamp"],
    "sideboard": ["sideboard", "buffet", "crockery cabinet", "showcase", "display cabinet", "console table"],
    "pantry cupboard": ["pantry", "pantry cupboard", "kitchen cabinet", "kitchen cupboard"],
    "refrigerator": ["refrigerator", "fridge", "kitchen refrigerator"],
    "wall art": ["painting", "wall art", "artwork", "photo frame", "wall clock", "clock"],
    "plant": ["plant", "planter"],
}

# When a category has no products, these are acceptable stand-ins (in order)
RELATED_CATEGORIES = {
    "cabinet": ["chest of drawers", "bedside table", "sideboard"],
    "bedside table": ["side table", "chest of drawers"],
    "side table": ["bedside table", "coffee table"],
    "chest of drawers": ["cabinet", "bedside table"],
    "tv stand": ["sideboard", "cabinet"],
    "sideboard": ["cabinet", "tv stand"],
    "chair": ["dining chair", "office chair", "armchair"],
    "office chair": ["chair", "dining chair"],
    "dining chair": ["chair"],
    "dressing stool": ["stool"],
    "stool": ["dressing stool"],
    "bookshelf": ["wall shelf", "cabinet"],
    "wall shelf": ["bookshelf"],
    "sofa bed": ["sofa"],
    "armchair": ["chair"],
    "study desk": [],
}

# Things the user asked for that are not furniture we can buy by matching (skip quietly)
NOT_SEARCHABLE = {"window", "door"}

_PHRASES = sorted(((p, cat) for cat, ps in CATEGORY_SYNONYMS.items() for p in ps),
                  key=lambda x: -len(x[0]))


def resolve_category(text: str):
    """Map free text ('Queen size bed', 'TV unit', 'dining chairs') to a canonical category."""
    norm = " " + normalize_text(text) + " "
    for phrase, cat in _PHRASES:
        if " " + normalize_text(phrase) + " " in norm:
            return cat
    return None


# ------------------------------------------------------------------
# Who a product is made for
# ------------------------------------------------------------------

KIDS_WORDS = {"kid", "child", "children", "junior", "nursery", "baby", "toddler", "snoopy", "cartoon", "bunk"}
CHILD_AUDIENCES = {"child", "baby", "teen", "kid", "kids", "children"}


def is_kids_product(normalized_text: str) -> bool:
    return bool(set(normalized_text.split()) & KIDS_WORDS)


# ------------------------------------------------------------------
# Size attributes
# ------------------------------------------------------------------

BED_SIZES = ["single", "double", "queen", "king"]
BED_SIZE_ALIASES = {"twin": "single", "full": "double", "super king": "king"}


def extract_size(text: str) -> dict:
    """Pull size attributes out of text: bed size, seats, doors, compact/large."""
    t = " " + normalize_text(text) + " "
    size = {}
    # Retailer SKU codes: Singer "WF-BRN-BDQ-RTK" = queen bed, "BDK" king, "BDD" double, "BDS" single
    for code, bed in (("bdq", "queen"), ("bdk", "king"), ("bdd", "double"), ("bds", "single")):
        if f" {code} " in t:
            size["bed"] = bed
    for alias, canonical in BED_SIZE_ALIASES.items():
        if f" {alias} " in t:
            size["bed"] = canonical
    for s in BED_SIZES:
        if f" {s} " in t:
            size["bed"] = s
    m = re.search(r"\b(\d)\s*(?:seater|seat|seats|person)\b", t) or re.search(r"\b(one|two|three|four|five|six|eight)\s*seater", t)
    if m:
        words = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "eight": 8}
        size["seats"] = int(words.get(m.group(1), m.group(1)))
    m = re.search(r"\b(\d)\s*\+\s*(\d)(?:\s*\+\s*(\d))?", text or "")
    if m:  # sofa set like 3+1+1
        size["seats"] = int(m.group(1))
        size["set"] = True
    m = re.search(r"\b(\d)\s*(?:door|dr)\b", t) or re.search(r"\b(\d)dmw?\b", t)
    if m:
        size["doors"] = int(m.group(1))
    if re.search(r"\b(l shape|l shaped|corner|sectional)\b", t):
        size["shape"] = "l"
    if re.search(r"\b(small|compact|slim|mini|space saving)\b", t):
        size["compact"] = True
    if re.search(r"\b(large|big|spacious|huge)\b", t):
        size["large"] = True
    return size


def size_score(wanted: dict, product: dict, category: str):
    """0..1 how well a product's size fits the request, plus a note when it doesn't."""
    if not wanted:
        return 0.7, None
    score, notes = 1.0, []
    if "bed" in wanted:
        have = product.get("bed")
        if have is None:
            score *= 0.55
            notes.append(f"size not listed; check it is a {wanted['bed']} bed")
        elif have != wanted["bed"]:
            gap = abs(BED_SIZES.index(have) - BED_SIZES.index(wanted["bed"]))
            score *= 0.6 if gap == 1 else 0.15
            notes.append(f"this is a {have} bed, not {wanted['bed']}")
    if "seats" in wanted:
        have = product.get("seats")
        if have is None:
            score *= 0.6
        elif have != wanted["seats"]:
            score *= 0.5
            notes.append(f"{have}-seater, you asked for {wanted['seats']}-seater")
        elif product.get("set"):
            score *= 0.85
            notes.append("sold as a set with extra seats")
    if "doors" in wanted:
        have = product.get("doors")
        if have is not None and have != wanted["doors"]:
            score *= 0.4
            notes.append(f"{have}-door, you asked for {wanted['doors']}-door")
    if wanted.get("shape") == "l" and product.get("shape") != "l":
        score *= 0.5
    if wanted.get("compact"):
        if product.get("large"):
            score *= 0.5
        elif product.get("compact"):
            score *= 1.0
        else:
            score *= 0.8
    return score, ("; ".join(notes) or None)


# ------------------------------------------------------------------
# Colours
# ------------------------------------------------------------------

# family -> words that mean it. Shade words mark light/dark variants.
COLOR_FAMILIES = {
    "white": ["white", "ivory", "off white", "snow", "pearl", "alabaster"],
    "beige": ["beige", "cream", "buttermilk", "sand", "ecru", "champagne", "nude", "linen", "latte", "khaki"],
    "gray": ["gray", "charcoal", "ash", "silver", "slate", "graphite", "stone", "smoke"],
    "black": ["black", "ebony", "jet"],
    "light wood": ["oak", "white oak", "light wood", "natural wood", "natural", "maple", "pine", "birch",
                   "beech", "bamboo", "rattan", "cane", "sonoma"],
    "dark wood": ["walnut", "teak", "mahogany", "wenge", "espresso", "dark wood", "rosewood", "chocolate",
                  "coffee brown", "dark brown"],
    "brown": ["brown", "tan", "camel", "caramel", "cognac", "wooden", "wood", "wooden color"],
    "blue": ["blue", "navy", "royal blue", "sky blue", "baby blue", "powder blue", "cobalt", "indigo", "denim",
             "midnight blue"],
    "teal": ["teal", "turquoise", "aqua", "cyan", "peacock"],
    "green": ["green", "sage", "olive", "emerald", "mint", "forest green", "bottle green", "lime", "pistachio"],
    "red": ["red", "maroon", "burgundy", "wine", "crimson", "cherry", "terracotta"],
    "pink": ["pink", "blush", "rose", "dusty pink", "peach", "coral", "salmon"],
    "yellow": ["yellow", "mustard", "gold", "golden", "ochre", "lemon", "brass"],
    "orange": ["orange", "rust", "burnt orange", "amber"],
    "purple": ["purple", "lavender", "lilac", "violet", "plum", "mauve"],
}
DARK_WORDS = {"navy", "dark", "deep", "midnight", "charcoal", "maroon", "burgundy", "wine", "emerald", "forest",
              "bottle", "plum", "espresso", "ebony", "wenge", "cobalt", "indigo", "royal"}
LIGHT_WORDS = {"light", "sky", "baby", "powder", "pastel", "mint", "blush", "lavender", "lilac", "ivory",
               "cream", "pale", "soft", "sage"}

NEUTRALS = {"white", "beige", "gray", "black", "light wood", "dark wood", "brown"}

# How well a product colour (value) sits in a room themed around a colour (key). 1.0 = same family.
HARMONY = {
    "blue": {"white": 0.85, "gray": 0.8, "light wood": 0.8, "beige": 0.75, "yellow": 0.55, "dark wood": 0.6,
             "black": 0.55, "brown": 0.55, "teal": 0.65},
    "teal": {"white": 0.85, "gray": 0.75, "light wood": 0.8, "beige": 0.7, "yellow": 0.6, "blue": 0.65,
             "dark wood": 0.6, "brown": 0.55},
    "green": {"white": 0.85, "beige": 0.8, "light wood": 0.85, "dark wood": 0.7, "brown": 0.7, "gray": 0.65,
              "yellow": 0.55, "teal": 0.65},
    "red": {"white": 0.8, "beige": 0.75, "gray": 0.7, "black": 0.65, "dark wood": 0.7, "brown": 0.6, "pink": 0.6},
    "pink": {"white": 0.9, "gray": 0.8, "beige": 0.8, "light wood": 0.75, "purple": 0.6, "red": 0.5},
    "yellow": {"white": 0.85, "gray": 0.8, "blue": 0.6, "light wood": 0.75, "beige": 0.7, "black": 0.55},
    "orange": {"white": 0.8, "beige": 0.75, "brown": 0.7, "dark wood": 0.7, "light wood": 0.7, "teal": 0.55},
    "purple": {"white": 0.85, "gray": 0.85, "beige": 0.7, "pink": 0.6, "light wood": 0.65, "black": 0.55},
    "white": {"light wood": 0.9, "gray": 0.85, "beige": 0.85, "black": 0.75, "dark wood": 0.75, "brown": 0.7},
    "beige": {"white": 0.9, "light wood": 0.9, "brown": 0.85, "dark wood": 0.8, "gray": 0.65, "black": 0.55},
    "gray": {"white": 0.9, "black": 0.8, "light wood": 0.75, "beige": 0.65, "dark wood": 0.65, "blue": 0.6},
    "black": {"white": 0.9, "gray": 0.85, "dark wood": 0.7, "light wood": 0.6, "beige": 0.6},
    "light wood": {"white": 0.9, "beige": 0.9, "brown": 0.8, "gray": 0.75, "dark wood": 0.65, "black": 0.6},
    "dark wood": {"brown": 0.9, "beige": 0.85, "white": 0.8, "light wood": 0.65, "black": 0.65, "gray": 0.6},
    "brown": {"dark wood": 0.9, "light wood": 0.8, "beige": 0.85, "white": 0.75, "black": 0.6, "gray": 0.6},
}
CLASH = 0.2
UNKNOWN_COLOR = 0.45

# Theme words that expand to several families
THEME_WORDS = {
    "pastel": ["pink:light", "blue:light", "green:light", "yellow:light", "purple:light", "beige", "white"],
    "neutral": ["white", "beige", "gray", "light wood"],
    "earthy": ["brown", "beige", "green", "orange", "dark wood"],
    "warm": ["beige", "brown", "light wood", "orange"],
    "monochrome": ["white", "black", "gray"],
    "black and white": ["black", "white"],
}

# Retailer SKU codes that encode colour (e.g. LF-ROVER-...-WN = walnut)
SKU_COLOR_CODES = {"WN": "walnut", "WO": "white oak", "WHT": "white", "WH": "white", "GR": "gray", "GRY": "gray",
                   "BLK": "black", "BK": "black", "BLUE": "blue", "BEIGE": "beige", "BROWN": "brown",
                   "01BROWN": "brown", "TK": "teak", "OAK": "oak", "SN": "sonoma"}

_COLOR_PHRASES = sorted(((p, fam) for fam, ps in COLOR_FAMILIES.items() for p in ps), key=lambda x: -len(x[0]))


def parse_colors(text: str) -> list:
    """
    Colour words in text -> list of (family, shade) with shade in {"light", "dark", ""},
    in the order they appear (the first one is the main colour).
    "navy blue theme" -> [("blue", "dark")]; "white and light wood" -> [("white",""), ("light wood","light")]
    """
    t = " " + normalize_text(text) + " "
    found = []  # (position, family, shade)

    def blank(text, start, length):
        # keep positions stable so the final order follows the text
        return text[:start] + " " * length + text[start + length:]

    for theme, fams in THEME_WORDS.items():
        key = f" {theme} "
        if key in t:
            idx = t.index(key)
            for n, f in enumerate(fams):
                fam, _, shade = f.partition(":")
                found.append((idx + n * 0.01, fam, shade))
            t = blank(t, idx + 1, len(key) - 2)
    for phrase, fam in _COLOR_PHRASES:
        p = " " + normalize_text(phrase) + " "
        while p in t:
            idx = t.index(p)
            before = t[max(0, idx - 12):idx].split()[-1:]  # word right before, e.g. "light"/"dark"
            words = set(normalize_text(phrase).split()) | set(before)
            shade = "dark" if words & DARK_WORDS else "light" if words & LIGHT_WORDS else ""
            t = blank(t, idx + 1, len(p) - 2)
            if not shade and any(f == fam for _, f, _ in found):
                continue  # "navy blue": the plain "blue" adds nothing
            found.append((idx, fam, shade))
    seen, out = set(), []
    for _, fam, shade in sorted(found):
        if (fam, shade) not in seen:
            seen.add((fam, shade))
            out.append((fam, shade))
    return out


def color_from_sku(*texts) -> str:
    words = []
    for text in texts:
        for part in re.split(r"[-_/.\s()]+", text or ""):
            code = SKU_COLOR_CODES.get(part.upper())
            if code:
                words.append(code)
    return ", ".join(dict.fromkeys(words))


def color_score(theme: list, product_colors: list):
    """
    theme / product_colors: lists of (family, shade).
    Returns (score 0..1, relation) where relation is 'match', 'complements', 'unknown' or 'clash'.
    """
    if not theme:
        return 0.7, None
    if not product_colors:
        return UNKNOWN_COLOR, "unknown"
    best, relation = 0.0, "clash"
    for i, (tfam, tshade) in enumerate(theme):
        weight = 1.0 if i == 0 else 0.92  # the first colour named is the main one
        for pfam, pshade in product_colors:
            if pfam == tfam:
                s = 1.0 if (not tshade or not pshade or tshade == pshade) else 0.75  # sky blue is not navy
                rel = "match"
            elif tfam in ("light wood", "dark wood") and pfam == "brown" or \
                    tfam == "brown" and pfam in ("light wood", "dark wood"):
                s, rel = 0.85, "match"
            else:
                s = HARMONY.get(tfam, {}).get(pfam)
                if s is None:
                    s = 0.6 if pfam in NEUTRALS else CLASH
                rel = "complements" if s >= 0.5 else "clash"
                s *= 0.85  # when a colour was asked for, the same colour should clearly win
            s *= weight
            if s > best:
                best, relation = s, rel
    return best, relation


def describe_colors(colors: list) -> str:
    return " and ".join(f"{shade + ' ' if shade else ''}{fam}" for fam, shade in colors)
