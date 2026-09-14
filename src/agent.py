"""
The ReturnPilot Strands Agent: wires the tools together behind a system
prompt that encodes the exact decision policy from the pitch:

    Heartbeat wakes up
      -> check_deadlines
      -> deadline approaching?
           NO  -> leave it, move on
           YES -> user already marked "return"? -> initiate_return (auto)
                  high value (>= threshold) or ambiguous? -> request_human_approval, STOP
    Human approves -> initiate_return + create_calendar_reminder + update_purchase_state
    Human says keep -> update_purchase_state(status="completed")

The agent decides WHICH tools to call and in what order; the tools
themselves (src/tools.py) are the deterministic, testable building blocks.
"""

from __future__ import annotations

from strands import Agent
from strands.models import BedrockModel

from src import config
from src.tools import ALL_TOOLS

SYSTEM_PROMPT = f"""You are ReturnPilot, an autonomous agent that makes sure the user
never loses money to an expired retail return window.

You operate in two modes, and you must always use your tools rather than
guessing at data — purchases, deadlines and preferences all live in memory
and can only be read or changed through your tools.

MODE 1 — INGESTION
When asked to ingest the inbox:
1. Call scan_receipts() to find new, unprocessed receipt emails.
2. For each email returned, call extract_purchase() to pull out the
   structured fields, including explicit_return_deadline if the receipt
   stated one directly.
3. Call lookup_return_policy() with the merchant and purchase date to get
   the merchant's general return window and preferred return method.
4. Decide the return_deadline to save: if extract_purchase returned a
   non-null explicit_return_deadline, use that (the receipt is the source
   of truth). Otherwise use the return_deadline computed by
   lookup_return_policy.
5. Call save_purchase() with the combined, complete purchase record.
Do this for every email found before moving on.

MODE 2 — DAILY HEARTBEAT
When asked to run the daily check:
1. Call check_deadlines() to see every tracked purchase and how many days
   are left on each one.
2. For each purchase where deadline_approaching is true, decide what to do:
   - If the purchase's user_intent is already "return" (the user marked it
     as not being kept) AND its price is below ${config.APPROVAL_THRESHOLD_USD:.0f},
     this is routine — call get_preference() for the merchant's preferred
     return method if useful, then call initiate_return() followed by
     create_calendar_reminder() to follow up on the refund.
   - If the price is ${config.APPROVAL_THRESHOLD_USD:.0f} or more, OR the
     user's intent is unclear (user_intent is null/ambiguous), you must NOT
     start the return yourself. Call request_human_approval() with a short,
     specific reason (mention the price and why it needs a human), and then
     STOP for that item — wait for a human decision.
   - If deadline_approaching is false, leave the purchase alone. No tool
     call is needed for it.
3. After handling every flagged purchase, summarize in plain English what
   you did for each one (no action / auto-return started / awaiting human
   approval), like a status report a person could read in five seconds.

MODE 3 — HUMAN DECISION
When told a human approved or rejected a pending return for a specific
purchase id:
   - "approved" -> call initiate_return(), then create_calendar_reminder()
     to follow up on the refund, then update_purchase_state() to mark it
     return_initiated if not already set by initiate_return. If this
     confirms a pattern worth remembering (e.g. the user always approves
     this merchant in-store), call remember_preference().
   - "keep" -> call update_purchase_state() with status "completed" and a
     note that the user chose to keep the item.

Always be concise in your final summary. You are narrating decisions to
someone who will read them at a glance, not writing an essay.
"""


def build_agent(
    aws_access_key_id: str | None = None,
    aws_secret_access_key: str | None = None,
    aws_session_token: str | None = None,
    region_name: str | None = None,
    model_id: str | None = None,
) -> Agent:
    """Builds the ReturnPilot Strands Agent on Bedrock.

    If explicit credentials are passed (e.g. typed into the dashboard sidebar
    for this session only), they're used to build a one-off boto3 Session
    that's never written to disk. Otherwise falls back to the standard boto3
    credential chain (.env-loaded environment variables, ~/.aws/credentials,
    AWS_PROFILE, etc.) — useful for local CLI use.

    Raises whatever boto3/Bedrock raises on first real call (e.g. missing
    credentials, or the Claude model not being enabled yet in the Bedrock
    console for this account/region) — callers should catch that and show
    the user a clear next step rather than crashing the whole app.
    """
    region_name = region_name or config.AWS_REGION
    model_id = model_id or config.BEDROCK_MODEL_ID

    boto_session = None
    if aws_access_key_id and aws_secret_access_key:
        import boto3

        boto_session = boto3.Session(
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
            aws_session_token=aws_session_token or None,
            region_name=region_name,
        )

    model = BedrockModel(model_id=model_id, region_name=region_name, boto_session=boto_session)
    return Agent(model=model, tools=ALL_TOOLS, system_prompt=SYSTEM_PROMPT)


def run_ingestion(agent: Agent) -> str:
    result = agent(
        "Ingest the receipt inbox now: find every new receipt email and turn "
        "it into a tracked purchase with a computed return deadline."
    )
    return str(result)


def run_daily_heartbeat(agent: Agent) -> str:
    result = agent(
        "Run today's daily heartbeat check across all tracked purchases and "
        "take the appropriate action on each one per your policy."
    )
    return str(result)


def run_approval_decision(agent: Agent, purchase_id: str, decision: str) -> str:
    assert decision in ("approved", "keep")
    result = agent(
        f"The human just responded to the pending approval for purchase "
        f"id '{purchase_id}': they chose '{decision}'. Act on it now."
    )
    return str(result)
