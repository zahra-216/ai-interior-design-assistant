"""
Search and ranking logic for Agent 3.
Separated from main.py so the retrieval algorithm can be tested
and modified independently of the API layer.

Pipeline for one requested item (e.g. "queen bed", style "modern", colour "navy blue"):

  1. Query understanding  - map the item to a canonical category ("queen bed" -> bed)
                            and pull out size attributes ({"bed": "queen"})
  2. Candidate filter     - products in that category (+ price range). If none,
                            fall back to related categories and say so.
  3. Ranking (hybrid)     - TF-IDF + cosine similarity on normalised, query-expanded
                            text (style/material words), combined with a colour
                            harmony score and a size fit score.
  4. Explanation          - a short note: "No navy blue wardrobes in our catalog;
                            this white one goes well with a navy blue theme."
"""
import re
from dataclasses import dataclass, field
from typing import List, Optional

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from database import Product
from product_knowledge import (
    CHILD_AUDIENCES, RELATED_CATEGORIES, STOPWORDS, color_score, describe_colors, expand_query,
    extract_size, is_kids_product, normalize_text, parse_colors, resolve_category, size_score,
)

# Ranking weights (sum to 1). Colour gets no weight when the user gave no colour.
W_TEXT, W_COLOR, W_SIZE = 0.25, 0.45, 0.30


@dataclass
class CatalogEntry:
    product: Product
    category: str
    text: str
    colors: list
    size: dict
    kids: bool = False


@dataclass
class SearchResult:
    product: Optional[Product]
    score: float
    note: Optional[str] = None
    category: Optional[str] = None
    colors: list = field(default_factory=list)


class Catalog:
    """All products, pre-processed once per request batch (the catalog is small)."""

    def __init__(self, db):
        self.entries = []
        for p in db.query(Product).all():
            category = resolve_category(p.category) or resolve_category(p.name) or (p.category or "").lower()
            color_text = p.color or ""
            colors = parse_colors(color_text)
            text = normalize_text(f"{p.name} {p.category} {p.style} {color_text}")
            self.entries.append(CatalogEntry(p, category, text, colors, extract_size(f"{p.name} {p.style} {p.category}"),
                                             is_kids_product(text)))

        self.vectorizer = None
        if self.entries:
            self.vectorizer = TfidfVectorizer(stop_words=list(STOPWORDS), sublinear_tf=True)
            self.matrix = self.vectorizer.fit_transform([e.text for e in self.entries])

    def in_category(self, category, min_price=None, max_price=None):
        return [
            (i, e) for i, e in enumerate(self.entries)
            if e.category == category
            and (min_price is None or e.product.price >= min_price)
            and (max_price is None or e.product.price <= max_price)
        ]

    def text_scores(self, query: str, indices: list):
        if not self.vectorizer or not indices:
            return []
        q = self.vectorizer.transform([query])
        return cosine_similarity(q, self.matrix[indices]).flatten()


def _theme_label(color: str) -> str:
    """The user's own colour words, e.g. 'Navy blue theme please' -> 'navy blue'."""
    words = [w for w in re.findall(r"[a-zA-Z]+", (color or "").lower())
             if w not in {"theme", "themed", "colour", "colours", "color", "colors", "tone", "tones", "please",
                          "shade", "shades", "palette", "room", "with", "a", "the", "some"}]
    return " ".join(words)


def _plural(category: str) -> str:
    if category.endswith(("s", "sh", "ch")):
        return category + "es"
    return category + "s"


def search_and_rank(catalog: Catalog, item: str, style: str = "", color: str = "", size: str = "",
                    top_k: int = 1, min_price: int = None, max_price: int = None,
                    audience: str = "adult") -> List[SearchResult]:
    """
    Full hybrid pipeline for one furniture request.
    Returns up to `top_k` SearchResults, best first. An empty list means nothing suitable.
    """
    category = resolve_category(item) or resolve_category(size)
    if not category:
        return []

    candidates = catalog.in_category(category, min_price, max_price)
    fallback_note = None
    if not candidates:
        for related in RELATED_CATEGORIES.get(category, []):
            candidates = catalog.in_category(related, min_price, max_price)
            if candidates:
                fallback_note = f"No {_plural(category)} in our catalog, so this is a {related} instead"
                break
    if not candidates:
        return []

    # Kids' furniture only for children's rooms (unless it is all the catalog has)
    for_child = (audience or "adult").lower() in CHILD_AUDIENCES
    audience_note = None
    if not for_child:
        grown_up = [(i, e) for i, e in candidates if not e.kids]
        if grown_up:
            candidates = grown_up
        else:
            audience_note = "Only kids' designs are available in our catalog for this"

    wanted_size = extract_size(f"{item} {size}")
    theme = parse_colors(color)
    indices = [i for i, _ in candidates]
    query = expand_query(f"{item} {style} {size} {color}")
    raw_text = catalog.text_scores(query, indices)
    best_text = max(raw_text) if len(raw_text) and max(raw_text) > 0 else 1.0

    w_text, w_color, w_size = (W_TEXT, W_COLOR, W_SIZE) if theme else (0.55, 0.0, 0.45)

    scored = []
    for (i, entry), t in zip(candidates, raw_text):
        text_s = t / best_text
        c_s, c_rel = color_score(theme, entry.colors)
        s_s, s_note = size_score(wanted_size, entry.size, category)
        total = w_text * text_s + w_color * c_s + w_size * s_s
        if for_child and entry.kids:
            total += 0.15  # designed for children
        scored.append((total, entry, c_rel, s_note))
    scored.sort(key=lambda x: (-x[0], x[1].product.price))

    any_color_match = any(rel == "match" for _, _, rel, _ in scored)
    theme_words = _theme_label(color) or describe_colors(theme)

    results = []
    for total, entry, c_rel, s_note in scored[:max(1, top_k)]:
        notes = [n for n in (fallback_note, audience_note) if n]
        if for_child and entry.kids:
            notes.append("Designed for kids")
        product_colors = (entry.product.color or "").strip() or describe_colors(entry.colors) or "unlisted colour"
        if theme:
            if c_rel == "match":
                notes.append(f"{product_colors.capitalize()}, matches your {theme_words} theme")
            elif c_rel == "complements":
                either = theme_words.replace(" and ", " or ")  # "no navy blue or white desks"
                prefix = f"No {either} {_plural(category)} in our catalog; this" if not any_color_match else "This"
                notes.append(f"{prefix} {product_colors} one goes well with a {theme_words} theme")
            elif c_rel == "unknown":
                notes.append(f"The retailer doesn't list its colour, so check it suits your {theme_words} theme")
            else:
                notes.append(f"Closest option, but its {product_colors} colour may not suit a {theme_words} theme")
        if s_note:
            notes.append(s_note[0].upper() + s_note[1:])
        results.append(SearchResult(entry.product, round(min(1.0, total), 3), ". ".join(notes) or None,
                                    entry.category, entry.colors))
    return results
