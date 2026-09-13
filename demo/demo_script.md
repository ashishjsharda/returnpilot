# ReturnPilot — 5-Minute Demo Script

Before recording: `streamlit run dashboard/app.py`, click **♻️ Reset & reseed demo data**
once so the numbers are clean, and have the browser tab full-screen.

## 0:00–0:30 — Problem

> "Americans buy across dozens of merchants — Amazon, Target, Best Buy, and more.
> Every retailer has a different return window, and missing one costs real money.
> ReturnPilot is an agent that watches your purchases so you never lose money to
> an expired return window."

## 0:30–1:15 — Inbox ingestion

Show the three mock receipt emails conceptually (or open `data/mock_inbox.json`
briefly) — a $29.99 USB hub from Amazon, an $89.99 coffee maker from Target, and
a $649.99 monitor from Best Buy.

Click **📥 Ingest Receipt Inbox**. Narrate as the agent's log expands:

```
scan_receipts()       -> found 3 new emails
extract_purchase()    -> product, merchant, price, purchase date
lookup_return_policy() -> merchant return window + preferred method
save_purchase()        -> tracked with a computed return deadline
```

> "The agent just read three receipts, figured out each one's return deadline,
> and started tracking them — no manual entry."

## 1:15–2:15 — Autonomous heartbeat

Click **▶️ Simulate Daily Run**. This stands in for the daily EventBridge
trigger. Narrate the expanded log:

```
check_deadlines() -> 3 active purchases

USB Hub            12 days remaining -> no action
Coffee Maker        3 days remaining, marked "return", $89.99 < $200 threshold
                     -> auto-initiated return
Monitor              2 days remaining, $649.99 >= $200 threshold
                     -> HUMAN APPROVAL REQUIRED
```

> "That screen alone tells the whole story: cheap, already-decided item — the
> agent just handles it. Expensive item on a tight deadline — it stops and asks."

## 2:15–3:00 — Human gate

Point at the **⚠️ Pending approval** card for the Best Buy monitor — deadline,
price, and reason are right there. Click **✅ Approve Return**.

```
initiate_return()          -> return started (method: in-store)
create_calendar_reminder() -> follow-up scheduled to confirm the refund
```

> "One click, and the agent takes it from there — it even knows to send this
> one to a Best Buy store instead of mailing it back."

## 3:00–4:00 — Memory

Open the **🧠 Memory** panel and point at the remembered preference:

```
Best Buy -> preferred_return_method -> in_store
```

> "ReturnPilot remembered that I return Best Buy purchases in-store. Next time
> a Best Buy return comes up, it uses that automatically — that's real memory,
> not just a claim."

## 4:00–4:40 — Architecture

Show `diagrams/architecture.md` (rendered) and walk the loop once, fast:

> "EventBridge triggers the agent on AgentCore Runtime. The Strands agent
> reasons across three tools — a Gmail tool for receipts, a policy tool for
> return windows, and a return tool for the merchant side — with DynamoDB as
> its purchase memory, and a human-approval step for anything ambiguous or
> expensive."

## 4:40–5:00 — Close

> "Before: 'I forgot to return it and lost $179.' After: 'ReturnPilot found the
> receipt, noticed the deadline, prepared the return, and asked me once.' The
> best return is the one you never have to remember."

---

## If something breaks live

- Dashboard shows **"Live Bedrock not reachable — using local policy
  fallback"**: that's fine — the decisions shown are identical, just made by
  deterministic code instead of the live model. Say so plainly rather than
  pretending otherwise ("this run is on our local policy fallback, same
  decision logic") — judges respect honesty over a hidden failure.
- To reset mid-rehearsal: sidebar → **♻️ Reset & reseed demo data**.
