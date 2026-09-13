# ReturnPilot

**Your AI agent that makes sure you never lose money to an expired return window.**

Built for the [Agents for Humans Hackathon](https://agentsforhumans.devpost.com/) (Everyday
Agents track) using the [AWS Strands Agents SDK](https://aws.amazon.com/blogs/opensource/introducing-strands-agents-an-open-source-ai-agents-sdk/).

> Before: *"I forgot to return it and lost $179."*
> After: *"ReturnPilot found the receipt, noticed the deadline, prepared the return, and asked me once."*

## What it does

Every morning, ReturnPilot wakes up, checks the purchases it's tracking, and
figures out which ones are approaching their return deadline. Cheap items
you've already decided to return get handled automatically. Anything
expensive or ambiguous gets a single approval request instead of silent
action. It remembers your preferences (e.g. "Best Buy returns go in-store")
so it needs to ask less over time.

See `diagrams/architecture.md` for the full architecture and how each part
of the agent loop maps to a file in this repo, and `demo/demo_script.md` for
the exact demo walkthrough.

## Quick start

```bash
python3 -m venv .venv && source .venv/bin/activate   # optional but recommended
pip install -r requirements.txt

cp .env.example .env    # fill in AWS credentials / Bedrock region if you have them

python3 scripts/build_mock_inbox.py    # generate mock receipt emails (dates relative to today)
python3 tests/test_agent_logic.py      # deterministic smoke test of the full tool chain, no LLM needed

streamlit run dashboard/app.py         # the demo dashboard
```

Open the URL Streamlit prints (defaults to http://localhost:8501). Click
**Ingest Receipt Inbox**, then **Simulate Daily Run**, then work the
**Pending approval** card that appears for the high-value item.

## Running with real AWS Bedrock

By default the dashboard runs against a **local policy fallback** (deterministic
code, not an LLM) so it works immediately with zero AWS setup — useful for
development and rehearsing the demo. To use the actual Strands agent + Claude
on Bedrock:

1. In `.env`, set `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` (or configure
   the AWS CLI / an `AWS_PROFILE` instead and leave those blank).
2. In the [Bedrock console](https://console.aws.amazon.com/bedrock/), under
   **Model access**, make sure the Claude model referenced by
   `BEDROCK_MODEL_ID` in `.env` is enabled for your account/region.
3. Restart the dashboard (or click **🔁 Reconnect to Bedrock** in the sidebar).
   The sidebar will show "Strands agent ready" once it's live.

To use real DynamoDB instead of local SQLite, set `RETURNPILOT_STORAGE=dynamodb`
in `.env` — the table is created automatically (on-demand billing) on first run.

## Project structure

```
src/
  agent.py            Strands Agent + system prompt (the decision policy)
  tools.py             @tool functions: scan_receipts, extract_purchase,
                        lookup_return_policy, save_purchase, check_deadlines,
                        request_human_approval, initiate_return,
                        create_calendar_reminder, update_purchase_state,
                        get_preference, remember_preference
  memory.py            Storage abstraction — DynamoDB (real) or SQLite (local)
  models.py            Purchase data model
  return_policies.py   Mock merchant return-window table
  policy_fallback.py   Deterministic driver (no LLM) — dashboard's safety net
  config.py            Env-based configuration

dashboard/app.py       Streamlit demo dashboard (ingest, heartbeat, approval gate, memory)
scripts/
  build_mock_inbox.py  Generates data/mock_inbox.json with dates relative to today
  run_heartbeat.py      CLI / Lambda-shaped entry point for a real scheduled run
  seed_data.py           Alternate: seed purchases directly, skipping ingestion
tests/test_agent_logic.py  Deterministic end-to-end smoke test (no LLM required)
diagrams/architecture.md   Architecture diagram + agent loop
demo/demo_script.md        5-minute demo script
```

## Why a local fallback exists

The dashboard and CLI always try the live Strands/Bedrock agent first. If
Bedrock isn't reachable (no credentials yet, model access not enabled), they
fall back to `src/policy_fallback.py`, which makes the *exact same decisions*
by calling the tools directly instead of through an LLM. This means the demo
never hard-fails on AWS plumbing — and `tests/test_agent_logic.py` exercises
that same tool chain as a fast, free correctness check independent of any
live model call.

## License

MIT — see `LICENSE`.
