"""
Simulates what Agent 2 will eventually do: send its design output
over HTTP to Agent 3's /search-furniture endpoint and read back
the matched products.

Uses real categories/styles that exist in real_products.csv, imported
into the database via import_csv.py.

Before running this:
1. Make sure your Agent 3 server is running in another terminal:
   uvicorn main:app --reload --port 8003
2. Then run this script in a second terminal:
   python test_integration.py
"""
import requests

AGENT3_URL = "http://127.0.0.1:8003/search-furniture"

# This mimics Agent 2's actual output shape, using real categories/styles
# that exist in your imported product data
mock_agent2_output = {
    "layout_image_path": "designs/design_v1.png",
    "furniture_needed": [
        {"item": "sofa", "style": "modern fabric", "qty": 1, "max_price": 150000},
        {"item": "coffee table", "style": "modern wood", "qty": 1},
        {"item": "wardrobe", "style": "modern wooden", "qty": 1},
        {"item": "dressing table", "style": "modern mirror", "qty": 1},
        {"item": "bed", "style": "modern queen", "qty": 1},
    ]
}


def run_test():
    print(f"Sending request to Agent 3 at {AGENT3_URL} ...\n")
    print("Request body (what Agent 2 would send):")
    print(mock_agent2_output)
    print()

    response = requests.post(AGENT3_URL, json=mock_agent2_output)

    if response.status_code != 200:
        print(f"FAILED - status code {response.status_code}")
        print(response.text)
        return

    matches = response.json()
    print(f"SUCCESS - got {len(matches)} matched product(s) back:\n")
    for m in matches:
        print(
            f"  - {m['item']}: {m['product_name']} "
            f"({m['retailer']}, LKR {m['price']}, score={m['match_score']})"
        )


if __name__ == "__main__":
    run_test()