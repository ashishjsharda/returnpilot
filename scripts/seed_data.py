"""
Seeds three mock "receipt inbox" entries, mirroring the hackathon demo script:

  1. Amazon USB-C Hub, $29.99   -> plenty of time left, no action
  2. Target Coffee Maker, $89.99 -> user already marked "not keeping" -> return-ready
  3. Best Buy Monitor, $649.99   -> deadline imminent + high value -> human approval

Deadlines are computed relative to *today* (not hardcoded dates) so the demo
always shows a believable "N days remaining" no matter when you run it.

Run:
    python3 scripts/seed_data.py
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.memory import get_store  # noqa: E402
from src.models import Purchase  # noqa: E402

TODAY = datetime.utcnow().date()


def _iso(d):
    return d.isoformat()


MOCK_RECEIPTS = [
    dict(
        id="rcpt-001",
        merchant="Amazon",
        product="USB-C Hub (7-in-1)",
        category="electronics",
        price=29.99,
        purchase_date=_iso(TODAY - timedelta(days=18)),
        return_deadline=_iso(TODAY + timedelta(days=12)),
        user_intent=None,
        status="monitoring",
        source_email_subject="Your Amazon.com order has shipped",
    ),
    dict(
        id="rcpt-002",
        merchant="Target",
        product="Mr. Coffee 12-Cup Coffee Maker",
        category="home",
        price=89.99,
        purchase_date=_iso(TODAY - timedelta(days=12)),
        return_deadline=_iso(TODAY + timedelta(days=3)),
        user_intent="return",  # user already marked "not keeping"
        status="monitoring",
        source_email_subject="Your Target.com receipt",
    ),
    dict(
        id="rcpt-003",
        merchant="Best Buy",
        product="Samsung 27\" Monitor",
        category="electronics",
        price=649.99,
        purchase_date=_iso(TODAY - timedelta(days=13)),
        return_deadline=_iso(TODAY + timedelta(days=2)),
        user_intent=None,
        status="monitoring",
        source_email_subject="Your Best Buy order confirmation",
    ),
]


def seed(reset: bool = True):
    store = get_store()
    if reset:
        store.reset()
    for raw in MOCK_RECEIPTS:
        store.save_purchase(Purchase(**raw))
    # Seed one learned preference so the "memory" beat has something to show
    # on the very first run, before any real approval has happened.
    store.set_preference("Best Buy", "preferred_return_method", "in_store")
    print(f"Seeded {len(MOCK_RECEIPTS)} mock purchases into {store.__class__.__name__}.")


if __name__ == "__main__":
    seed()
