"""
Generates data/mock_inbox.json from the template, filling in purchase dates
and return deadlines relative to *today* so the demo's "days remaining"
numbers are always believable, no matter when you run it.

Run:
    python3 scripts/build_mock_inbox.py
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_PATH = ROOT / "data" / "mock_inbox.json.template"
OUTPUT_PATH = ROOT / "data" / "mock_inbox.json"


def build():
    template = json.loads(TEMPLATE_PATH.read_text())
    today = date.today()
    receipts = []
    for r in template["receipts"]:
        purchase_date = today - timedelta(days=r["days_ago_purchased"])
        return_deadline = today + timedelta(days=r["days_until_deadline"])
        body = r["body_template"].format(
            purchase_date=purchase_date.isoformat(),
            return_deadline=return_deadline.isoformat(),
        )
        receipts.append(
            {
                "id": r["id"],
                "merchant": r["merchant"],
                "category": r["category"],
                "subject": r["subject"],
                "purchase_date": purchase_date.isoformat(),
                "body": body,
                "user_intent": r.get("user_intent"),
            }
        )
    OUTPUT_PATH.write_text(json.dumps({"receipts": receipts}, indent=2))
    print(f"Wrote {len(receipts)} mock emails to {OUTPUT_PATH}")


if __name__ == "__main__":
    build()
