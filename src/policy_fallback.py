"""
Deterministic fallback driver — implements the EXACT same decision policy as
the Strands agent's system prompt (src/agent.py), but by calling tools
directly instead of through an LLM.

Why this exists: the dashboard needs to work the moment you run it, even
before AWS Bedrock credentials/model access are wired up. This is what runs
when build_agent() can't reach Bedrock. The moment real credentials are in
place, the dashboard switches to the live LLM-driven agent automatically —
this file is a safety net, not the intended demo path.
"""

from __future__ import annotations

import json

from src import config
from src.memory import get_store
from src.tools import (
    check_deadlines,
    create_calendar_reminder,
    extract_purchase,
    initiate_return,
    lookup_return_policy,
    request_human_approval,
    save_purchase,
    scan_receipts,
    update_purchase_state,
)


def ingest_all() -> list[str]:
    log = []
    raw = json.loads(scan_receipts())
    log.append(f"scan_receipts() -> found {raw['count']} new email(s)")
    for email in raw["emails"]:
        extracted = json.loads(extract_purchase(json.dumps(email)))
        policy = json.loads(lookup_return_policy(extracted["merchant"], extracted["purchase_date"]))
        deadline = extracted["explicit_return_deadline"] or policy["return_deadline"]
        extracted["return_deadline"] = deadline
        save_purchase(json.dumps(extracted))
        log.append(
            f"extract_purchase + lookup_return_policy + save_purchase -> "
            f"{extracted['merchant']} \"{extracted['product']}\" (${extracted['price']:.2f}), "
            f"return by {deadline}"
        )
    return log


def run_heartbeat() -> list[str]:
    log = []
    purchases = json.loads(check_deadlines(warn_within_days=5))
    log.append(f"check_deadlines() -> {len(purchases)} tracked purchase(s)")
    for p in purchases:
        if p["status"] in ("return_initiated", "completed", "pending_approval"):
            log.append(f"  {p['merchant']} \"{p['product']}\" already {p['status']} — skipping")
            continue
        if not p["deadline_approaching"]:
            log.append(f"  {p['merchant']} \"{p['product']}\" — {p['days_remaining']} days left, no action")
            continue
        if p["user_intent"] == "return" and p["price"] < config.APPROVAL_THRESHOLD_USD:
            ret = json.loads(initiate_return(p["id"]))
            create_calendar_reminder(p["id"], f"Confirm refund posted for {p['product']}")
            log.append(
                f"  {p['merchant']} \"{p['product']}\" — {p['days_remaining']} days left, marked for "
                f"return, ${p['price']:.2f} < ${config.APPROVAL_THRESHOLD_USD:.0f} threshold "
                f"-> auto-initiated return via {ret['method']} (req {ret['return_request_id']})"
            )
        else:
            reason = (
                f"${p['price']:.2f} purchase "
                + (
                    f"meets/exceeds ${config.APPROVAL_THRESHOLD_USD:.0f} auto-return threshold"
                    if p["price"] >= config.APPROVAL_THRESHOLD_USD
                    else "has ambiguous intent"
                )
            )
            request_human_approval(p["id"], reason)
            log.append(
                f"  {p['merchant']} \"{p['product']}\" — {p['days_remaining']} days left, {reason} "
                f"-> HUMAN APPROVAL REQUIRED"
            )
    return log


def decide(purchase_id: str, decision: str) -> list[str]:
    log = []
    store = get_store()
    purchase = store.get_purchase(purchase_id)
    if not purchase:
        return [f"No purchase found with id {purchase_id}"]

    if decision == "approved":
        ret = json.loads(initiate_return(purchase_id))
        create_calendar_reminder(purchase_id, f"Confirm refund posted for {purchase.product}")
        log.append(
            f"initiate_return() -> started via {ret['method']} (req {ret['return_request_id']}); "
            f"create_calendar_reminder() -> follow-up scheduled"
        )
    else:
        update_purchase_state(purchase_id, "completed", "User chose to keep the item.")
        log.append("update_purchase_state() -> marked completed (kept item, no return)")
    return log
