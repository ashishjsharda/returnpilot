"""
ReturnPilot's Strands tools.

Each @tool function below is one node in the agent loop diagram:

    scan_receipts -> extract_purchase -> lookup_return_policy -> save_purchase
                                                                        |
                                                                        v
                         check_deadlines -> (agent reasons) -> initiate_return
                                                              -> request_human_approval
                                                              -> create_calendar_reminder
                                                              -> update_purchase_state
                                                              -> remember_preference

In production, scan_receipts would call a real Gmail/Outlook API and
initiate_return would call a real merchant returns API. Both are mocked here
so the agent's *reasoning* — the actual point of the demo — runs end-to-end
without needing OAuth or merchant API access.
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path

from strands import tool

from src import config
from src.memory import get_store
from src.models import Purchase
from src.return_policies import lookup_return_policy as _lookup_policy

ROOT = Path(__file__).resolve().parent.parent
INBOX_PATH = ROOT / "data" / "mock_inbox.json"

_PRICE_RE = re.compile(r"\$([0-9]+\.[0-9]{2})")
_RETURN_BY_RE = re.compile(r"Return by:\s*(\d{4}-\d{2}-\d{2})")


@tool
def scan_receipts() -> str:
    """Scan the receipt inbox for purchase emails that haven't been processed yet.

    Returns a JSON list of raw emails (id, merchant, subject, body) that are
    not already tracked in purchase memory. In production this hits the
    Gmail/Outlook API; here it reads a mock inbox file so the ingestion demo
    doesn't depend on OAuth.
    """
    if not INBOX_PATH.exists():
        return json.dumps({"emails": [], "note": "No mock inbox found — run scripts/build_mock_inbox.py"})

    inbox = json.loads(INBOX_PATH.read_text())["receipts"]
    store = get_store()
    known_ids = {p.id for p in store.list_purchases()}
    new_emails = [e for e in inbox if e["id"] not in known_ids]
    return json.dumps({"emails": new_emails, "count": len(new_emails)})


@tool
def extract_purchase(raw_email_json: str) -> str:
    """Extract structured purchase fields (product, merchant, purchase date, price,
    and the return deadline if the receipt states one) from a single raw receipt email.

    Args:
        raw_email_json: JSON string of one email object, as returned by scan_receipts
            (must include id, merchant, subject, body, purchase_date).

    Returns a JSON object with: id, merchant, product, category, price, purchase_date,
    and explicit_return_deadline (null if the receipt didn't state one — in that case
    call lookup_return_policy to compute it instead).
    """
    email = json.loads(raw_email_json)
    body = email.get("body", "")

    price_match = _PRICE_RE.search(body)
    price = float(price_match.group(1)) if price_match else 0.0

    return_by_match = _RETURN_BY_RE.search(body)
    explicit_return_deadline = return_by_match.group(1) if return_by_match else None

    # Product name: first non-empty line of the body that isn't a boilerplate header.
    product = None
    for line in body.splitlines():
        line = line.strip()
        if not line:
            continue
        if any(skip in line.lower() for skip in ("order", "confirmation", "purchase date", "date of", "thanks")):
            continue
        product = line
        break
    product = product or email.get("subject", "Unknown item")

    result = {
        "id": email["id"],
        "merchant": email["merchant"],
        "product": product,
        "category": email.get("category", "general"),
        "price": price,
        "purchase_date": email["purchase_date"],
        "source_email_subject": email.get("subject", ""),
        "user_intent": email.get("user_intent"),
        "explicit_return_deadline": explicit_return_deadline,
    }
    return json.dumps(result)


@tool
def lookup_return_policy(merchant: str, purchase_date: str) -> str:
    """Look up a merchant's return window and compute the return deadline for a purchase.

    Args:
        merchant: Merchant name, e.g. "Amazon", "Target", "Best Buy".
        purchase_date: ISO date string the item was purchased.

    Returns a JSON object with: merchant, window_days, preferred_method, return_deadline.
    """
    policy = _lookup_policy(merchant)
    p_date = datetime.fromisoformat(purchase_date).date()
    deadline = p_date + timedelta(days=policy.window_days)
    return json.dumps(
        {
            "merchant": policy.merchant,
            "window_days": policy.window_days,
            "preferred_method": policy.preferred_method,
            "return_deadline": deadline.isoformat(),
            "notes": policy.notes,
        }
    )


@tool
def save_purchase(purchase_json: str) -> str:
    """Save a fully-extracted purchase into long-term memory (DynamoDB/local store).

    Args:
        purchase_json: JSON object with id, merchant, product, category, price,
            purchase_date, return_deadline, and optionally user_intent.

    Returns a confirmation JSON with the saved purchase id and days remaining.
    """
    data = json.loads(purchase_json)
    purchase = Purchase(
        id=data["id"],
        merchant=data["merchant"],
        product=data["product"],
        category=data.get("category", "general"),
        price=float(data["price"]),
        purchase_date=data["purchase_date"],
        return_deadline=data["return_deadline"],
        source_email_subject=data.get("source_email_subject", ""),
        user_intent=data.get("user_intent"),
        status="monitoring",
    )
    get_store().save_purchase(purchase)
    return json.dumps(
        {"saved": True, "id": purchase.id, "days_remaining": purchase.days_remaining()}
    )


@tool
def check_deadlines(warn_within_days: int = 5) -> str:
    """List all tracked purchases with their days-remaining, flagging which ones
    are approaching their return deadline.

    Args:
        warn_within_days: Purchases with this many days or fewer left are flagged
            as deadline_approaching = true.

    Returns a JSON list of purchases with merchant, product, price, days_remaining,
    deadline_approaching, user_intent, and status.
    """
    store = get_store()
    purchases = store.list_purchases()
    out = []
    for p in purchases:
        days = p.days_remaining()
        out.append(
            {
                "id": p.id,
                "merchant": p.merchant,
                "product": p.product,
                "price": p.price,
                "days_remaining": days,
                "deadline_approaching": days <= warn_within_days,
                "user_intent": p.user_intent,
                "status": p.status,
            }
        )
    return json.dumps(out)


@tool
def get_preference(merchant: str, key: str) -> str:
    """Look up a remembered user preference for a merchant (e.g. preferred return method).

    Args:
        merchant: Merchant name.
        key: Preference key, e.g. "preferred_return_method".

    Returns a JSON object: {"merchant": ..., "key": ..., "value": ... or null}.
    """
    value = get_store().get_preference(merchant, key)
    return json.dumps({"merchant": merchant, "key": key, "value": value})


@tool
def remember_preference(merchant: str, key: str, value: str) -> str:
    """Save/update a learned user preference for a merchant, so future decisions
    for that merchant use it automatically without asking again.

    Args:
        merchant: Merchant name.
        key: Preference key, e.g. "preferred_return_method" or "auto_return_low_value".
        value: The value to remember, e.g. "in_store" or "true".
    """
    get_store().set_preference(merchant, key, value)
    return json.dumps({"remembered": True, "merchant": merchant, "key": key, "value": value})


@tool
def request_human_approval(purchase_id: str, reason: str) -> str:
    """Flag a purchase as needing explicit human approval before a return is
    initiated (e.g. high value or ambiguous intent). Does NOT start the return.

    Args:
        purchase_id: The purchase's id.
        reason: Short human-readable reason approval is needed, e.g.
            "$649.99 purchase exceeds $200 auto-return threshold".
    """
    store = get_store()
    purchase = store.update_purchase(purchase_id, status="pending_approval", notes=reason)
    if not purchase:
        return json.dumps({"ok": False, "error": f"No purchase with id {purchase_id}"})
    return json.dumps(
        {"ok": True, "status": "pending_approval", "id": purchase_id, "reason": reason}
    )


@tool
def initiate_return(purchase_id: str) -> str:
    """Start the return process for a purchase (calls the merchant's return API).
    Uses any remembered preferred return method for that merchant if one exists.

    Args:
        purchase_id: The purchase's id.

    Returns a JSON confirmation with a mock return request id and chosen method.
    """
    store = get_store()
    purchase = store.get_purchase(purchase_id)
    if not purchase:
        return json.dumps({"ok": False, "error": f"No purchase with id {purchase_id}"})

    policy = _lookup_policy(purchase.merchant)
    preferred = store.get_preference(purchase.merchant, "preferred_return_method")
    method = preferred or policy.preferred_method

    return_request_id = f"RET-{uuid.uuid4().hex[:8].upper()}"
    store.update_purchase(
        purchase_id,
        status="return_initiated",
        notes=f"Return started via {method}. Request ID {return_request_id}.",
    )
    return json.dumps(
        {
            "ok": True,
            "return_request_id": return_request_id,
            "method": method,
            "merchant": purchase.merchant,
            "product": purchase.product,
        }
    )


@tool
def create_calendar_reminder(purchase_id: str, note: str) -> str:
    """Create a calendar/reminder entry to follow up on a purchase (e.g. confirm
    the refund posted). Mocked for the demo — in production this calls a
    calendar API.

    Args:
        purchase_id: The purchase's id.
        note: What the reminder is for.
    """
    store = get_store()
    purchase = store.get_purchase(purchase_id)
    if not purchase:
        return json.dumps({"ok": False, "error": f"No purchase with id {purchase_id}"})
    return json.dumps(
        {
            "ok": True,
            "purchase_id": purchase_id,
            "reminder": note,
            "created_for": date.today().isoformat(),
        }
    )


@tool
def update_purchase_state(purchase_id: str, status: str, notes: str = "") -> str:
    """Update a purchase's tracked status.

    Args:
        purchase_id: The purchase's id.
        status: One of monitoring, return_ready, pending_approval, approved,
            return_initiated, refund_pending, completed.
        notes: Optional free-text note about why the status changed.
    """
    store = get_store()
    purchase = store.update_purchase(purchase_id, status=status, notes=notes or "")
    if not purchase:
        return json.dumps({"ok": False, "error": f"No purchase with id {purchase_id}"})
    return json.dumps({"ok": True, "id": purchase_id, "status": status})


ALL_TOOLS = [
    scan_receipts,
    extract_purchase,
    lookup_return_policy,
    save_purchase,
    check_deadlines,
    get_preference,
    remember_preference,
    request_human_approval,
    initiate_return,
    create_calendar_reminder,
    update_purchase_state,
]
