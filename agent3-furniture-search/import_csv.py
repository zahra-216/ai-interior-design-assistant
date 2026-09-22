"""
Imports furniture products from a CSV file into the products table.
Safe to re-run: a row whose name AND retailer already exist is UPDATED
(so fixing a price, colour or category in the CSV and re-running applies
the fix); new rows are inserted.

CSV columns:
  required: name, category, style, price, retailer
  optional: image_url, color, product_url

If `color` is empty, it is detected from the name, description and the
retailer's SKU codes (e.g. "-WN" = walnut, "-WHT" = white).

Usage: python import_csv.py real_products.csv
"""
import csv
import sys
from database import SessionLocal, Product, init_db
from product_knowledge import COLOR_FAMILIES, color_from_sku, normalize_text

_COLOR_WORDS = sorted({w for words in COLOR_FAMILIES.values() for w in words}, key=len, reverse=True)


def detect_color(name: str, style: str, image_url: str) -> str:
    """
    Best-effort colour words from the description and SKU codes. The product name is only
    used for SKU codes: names are often model names ("Pearl Dining Table", "Rose Sofa").
    """
    text = " " + normalize_text(style) + " "
    for phrase in ("coffee table", "coffee tables"):  # a category, not a colour
        text = text.replace(" " + phrase + " ", " ")
    found = []
    for word in _COLOR_WORDS:
        w = " " + normalize_text(word) + " "
        if w in text and not any(word in f for f in found):
            found.append(word)
            text = text.replace(w, " ")
    sku = color_from_sku(name, (image_url or "").rsplit("/", 1)[-1])
    for word in sku.split(", "):
        if word and word not in found:
            found.append(word)
    return ", ".join(found)


def read_rows(filepath: str):
    # Retailer data is often saved as Windows-1252 from Excel; accept both
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            with open(filepath, newline="", encoding=encoding) as f:
                return list(csv.DictReader(f))
        except UnicodeDecodeError:
            continue
    with open(filepath, newline="", encoding="utf-8", errors="replace") as f:
        return list(csv.DictReader(f))


def clean(value) -> str:
    return " ".join((value or "").replace(" ", " ").split())


def import_csv(filepath: str):
    init_db()
    db = SessionLocal()

    added = updated = skipped = 0

    try:
        for row in read_rows(filepath):
            name = clean(row["name"])
            retailer = clean(row["retailer"])
            if not name or not retailer:
                skipped += 1
                continue

            digits_only = "".join(c for c in row["price"] if c.isdigit())
            if not digits_only:
                print(f"  SKIPPED (bad price '{row['price']}'): {name}")
                skipped += 1
                continue

            fields = dict(
                category=clean(row["category"]).lower(),
                style=clean(row["style"]),
                price=int(digits_only),
                image_url=clean(row.get("image_url")) or None,
                product_url=clean(row.get("product_url")) or None,
            )
            fields["color"] = clean(row.get("color")) or detect_color(name, fields["style"], fields["image_url"]) or None

            existing = (
                db.query(Product)
                .filter(Product.name == name, Product.retailer == retailer)
                .first()
            )
            if existing:
                changed = False
                for key, value in fields.items():
                    if getattr(existing, key) != value:
                        setattr(existing, key, value)
                        changed = True
                updated += changed
                skipped += not changed
                continue

            db.add(Product(name=name, retailer=retailer, **fields))
            added += 1

        db.commit()
        print(f"Done. Added {added}, updated {updated}, unchanged/skipped {skipped}.")

    except FileNotFoundError:
        print(f"ERROR: could not find file '{filepath}'. Check the path/filename.")
    except KeyError as e:
        print(f"ERROR: CSV is missing expected column {e}. Check your header row.")
    finally:
        db.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python import_csv.py <path_to_csv>")
        sys.exit(1)

    import_csv(sys.argv[1])
