"""
Deterministic end-to-end smoke test that exercises the exact same tool
sequence the Strands agent is instructed to follow — WITHOUT calling an LLM.

This is what to run to prove the underlying logic is correct before you've
got live Bedrock access wired up (or any time you want a fast, free sanity
check). It calls the @tool functions directly, the way Strands would.

Run:
    python3 tests/test_agent_logic.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.memory import get_store  # noqa: E402
from src.tools import (  # noqa: E402
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

PASS = "✓"
FAIL = "✗"
failures = []


def expect(label, condition):
    mark = PASS if condition else FAIL
    print(f"  {mark} {label}")
    if not condition:
        failures.append(label)


def run():
    store = get_store()
    store.reset()
    store.set_preference("Best Buy", "preferred_return_method", "in_store")

    print("\n== Ingestion ==")
    raw = json.loads(scan_receipts())
    expect("scan_receipts finds 3 mock emails", raw["count"] == 3)

    for email in raw["emails"]:
        extracted = json.loads(extract_purchase(json.dumps(email)))
        policy = json.loads(lookup_return_policy(extracted["merchant"], extracted["purchase_date"]))
        deadline = extracted["explicit_return_deadline"] or policy["return_deadline"]
        extracted["return_deadline"] = deadline
        saved = json.loads(save_purchase(json.dumps(extracted)))
        expect(f"saved {extracted['merchant']} purchase ({extracted['product']})", saved["saved"])

    print("\n== Heartbeat: check_deadlines ==")
    statuses = {p["merchant"]: p for p in json.loads(check_deadlines(warn_within_days=5))}
    expect("Amazon USB hub NOT flagged (12 days out)", statuses["Amazon"]["deadline_approaching"] is False)
    expect("Target coffee maker IS flagged (3 days out)", statuses["Target"]["deadline_approaching"] is True)
    expect("Best Buy monitor IS flagged (2 days out)", statuses["Best Buy"]["deadline_approaching"] is True)
    expect("Best Buy price triggers approval threshold", statuses["Best Buy"]["price"] >= 200)
    expect("Target price is below approval threshold", statuses["Target"]["price"] < 200)

    print("\n== Routine auto-return path (Target, low value + marked return) ==")
    target_id = statuses["Target"]["id"]
    ret = json.loads(initiate_return(target_id))
    expect("Target return initiated", ret["ok"] is True)
    reminder = json.loads(create_calendar_reminder(target_id, "Confirm Target refund posted"))
    expect("Target calendar reminder created", reminder["ok"] is True)
    target_after = store.get_purchase(target_id)
    expect("Target status is return_initiated", target_after.status == "return_initiated")

    print("\n== Human-approval-gate path (Best Buy, high value) ==")
    bb_id = statuses["Best Buy"]["id"]
    approval = json.loads(request_human_approval(bb_id, "$649.99 exceeds $200 auto-return threshold"))
    expect("Best Buy flagged pending_approval", approval["status"] == "pending_approval")
    bb_after_flag = store.get_purchase(bb_id)
    expect("Best Buy NOT yet returned (waiting on human)", bb_after_flag.status == "pending_approval")

    # Simulate the human clicking "Approve" in the dashboard.
    bb_ret = json.loads(initiate_return(bb_id))
    expect("Best Buy return uses remembered in_store preference", bb_ret["method"] == "in_store")
    update_purchase_state(bb_id, "return_initiated", "Approved by user.")
    bb_final = store.get_purchase(bb_id)
    expect("Best Buy status is return_initiated after approval", bb_final.status == "return_initiated")

    print("\n== Re-running scan_receipts should find nothing new ==")
    raw2 = json.loads(scan_receipts())
    expect("no duplicate ingestion of already-known receipts", raw2["count"] == 0)

    print()
    if failures:
        print(f"{FAIL} {len(failures)} check(s) failed: {failures}")
        sys.exit(1)
    else:
        print(f"{PASS} All checks passed — tool chain logic is sound.")


if __name__ == "__main__":
    run()
