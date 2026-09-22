"""
Quick retrieval check: runs typical requests against the products table and prints the
top match + explanation for each. Run after importing products:
    python search_examples.py
"""
from database import SessionLocal
from search_logic import Catalog, search_and_rank
cat = Catalog(SessionLocal())
tests = [
    ("queen bed", "modern", "navy blue", "queen"),
    ("king bed", "modern", "", ""),
    ("single bed", "simple wooden", "", ""),
    ("bedside table", "modern", "white", ""),
    ("3-seater sofa", "modern", "navy blue", ""),
    ("L-shaped sofa", "modern minimalist", "", ""),
    ("wardrobe", "modern", "navy blue", "3 door"),
    ("TV unit", "modern", "white and light wood", ""),
    ("dining chairs", "scandinavian", "pastel", ""),
    ("small cupboard", "modern", "", "small"),
    ("study desk", "modern", "", ""),
    ("wall mirror", "modern", "", ""),
]
for item, style, color, size in tests:
    res = search_and_rank(cat, item, style, color, size, top_k=1)
    if not res:
        print(f"{item:15} [{color or '-'}] -> NOT FOUND"); continue
    r = res[0]
    print(f"{item:15} [{color or '-'}] -> {r.product.name[:30]:30} LKR {r.product.price:>7}  score={r.score}  | {r.note}")
extra = [("study desk","modern","navy blue",""),("desk chair","modern","navy blue",""),("wall mirror","modern","white and gold",""),
         ("bookshelf","scandinavian","white and light wood",""),("rug","modern","navy blue",""),("curtains","modern","navy blue",""),
         ("wardrobe","kids","sky blue","2 door"),("queen bed","modern","grey",""),("king bed","luxury","cream",""),
         ("shoe rack","simple","",""),("sideboard","modern","charcoal",""),("side table","modern","black",""),("armchair","modern","teal","")]
print("---- new categories")
for item, style, color, size in extra:
    res = search_and_rank(cat, item, style, color, size, top_k=1)
    if not res:
        print(f"{item:12} [{color or '-'}] -> NOT FOUND"); continue
    r = res[0]
    print(f"{item:12} [{color or '-'}] -> {r.product.name[:32]:32} LKR {r.product.price:>7} {r.product.retailer:8} | {r.note}")
from collections import Counter
print(Counter(e.category for e in cat.entries))
print("unmapped:", [e.product.name for e in cat.entries if e.category not in __import__('product_knowledge').CATEGORY_SYNONYMS])
