"""
ReturnPilot dashboard — the demo's centerpiece: ingest receipts, simulate the
daily heartbeat, and work the human-approval gate for high-value returns.

Run from the project root:
    streamlit run dashboard/app.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import streamlit as st  # noqa: E402

from src import config, policy_fallback  # noqa: E402
from src.agent import build_agent, run_approval_decision, run_daily_heartbeat, run_ingestion  # noqa: E402
from src.memory import get_store  # noqa: E402

st.set_page_config(page_title="ReturnPilot", page_icon="🔄", layout="wide")

STATUS_LABELS = {
    "monitoring": "🕒 Monitoring",
    "pending_approval": "⚠️ Awaiting approval",
    "return_initiated": "📦 Return initiated",
    "completed": "✅ Completed",
    "return_ready": "🟢 Return ready",
}


# ---------------------------------------------------------------------------
# Agent connection (lazy, cached in session_state; falls back to the
# deterministic policy driver if Bedrock isn't reachable yet)
#
# Credentials come from the sidebar text inputs below (kept only in this
# browser session's server-side memory — never written to .env, disk, or
# git) so nothing secret needs to live in a file that could end up in the
# public hackathon repo. If those fields are left blank, build_agent() falls
# back to the standard boto3 credential chain (.env / ~/.aws / AWS_PROFILE)
# for local CLI use instead.
# ---------------------------------------------------------------------------

def get_agent():
    if "agent" not in st.session_state:
        try:
            st.session_state.agent = build_agent(
                aws_access_key_id=st.session_state.get("aws_access_key_id_input") or None,
                aws_secret_access_key=st.session_state.get("aws_secret_access_key_input") or None,
                aws_session_token=st.session_state.get("aws_session_token_input") or None,
                region_name=st.session_state.get("aws_region_input") or None,
                model_id=st.session_state.get("bedrock_model_id_input") or None,
            )
            st.session_state.agent_build_error = None
        except Exception as exc:  # noqa: BLE001
            st.session_state.agent = None
            st.session_state.agent_build_error = str(exc)
    return st.session_state.agent


def run_with_fallback(live_fn, fallback_fn, *args):
    """Try the live Strands/Bedrock agent; fall back to deterministic policy
    logic (same decisions, no LLM) if Bedrock isn't reachable. Always returns
    (text_or_loglines, used_live: bool, error: str | None)."""
    agent = get_agent()
    if agent is not None:
        try:
            result = live_fn(agent, *args)
            return result, True, None
        except Exception as exc:  # noqa: BLE001
            err = str(exc)
    else:
        err = st.session_state.get("agent_build_error", "Bedrock agent unavailable")
    return fallback_fn(*args), False, err


# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------

st.title("🔄 ReturnPilot")
st.caption("Your AI agent that makes sure you never lose money to an expired return window.")

with st.sidebar:
    with st.expander("🔑 AWS credentials (this session only)", expanded="agent" not in st.session_state):
        st.caption(
            "Kept in this browser session's memory only — never written to "
            "`.env`, never saved to disk, never committed. Safe to use even "
            "with a public repo. Leave blank to fall back to `.env` / "
            "`~/.aws/credentials` instead (for local CLI runs)."
        )
        st.text_input("AWS Access Key ID", key="aws_access_key_id_input")
        st.text_input("AWS Secret Access Key", type="password", key="aws_secret_access_key_input")
        st.text_input("AWS Session Token (optional)", type="password", key="aws_session_token_input")
        st.text_input("AWS Region", value=config.AWS_REGION, key="aws_region_input")
        st.text_input("Bedrock Model ID / ARN", value=config.BEDROCK_MODEL_ID, key="bedrock_model_id_input")
        if st.button("🔌 Connect / Reconnect to Bedrock", use_container_width=True):
            st.session_state.pop("agent", None)
            st.session_state.pop("agent_build_error", None)
            st.rerun()

    st.subheader("Status")
    st.write(f"**Storage:** `{config.STORAGE_BACKEND}`")
    st.write(f"**Auto-approve under:** ${config.APPROVAL_THRESHOLD_USD:.0f}")

    agent_probe = get_agent()
    if agent_probe is not None and not st.session_state.get("agent_build_error"):
        st.success("Strands agent ready")
    else:
        st.warning("Live Bedrock not reachable — using local policy fallback")
        with st.expander("Why?"):
            st.code(st.session_state.get("agent_build_error", "unknown"))
            st.caption(
                "Fill in your AWS credentials above and make sure the Claude "
                "model is enabled in Bedrock, then click Connect/Reconnect."
            )

    st.divider()
    if st.button("♻️ Reset & reseed demo data"):
        import scripts.build_mock_inbox as build_mock_inbox

        build_mock_inbox.build()
        get_store().reset()
        get_store().set_preference("Best Buy", "preferred_return_method", "in_store")
        st.session_state.pop("last_log", None)
        st.rerun()


# ---------------------------------------------------------------------------
# Action buttons
# ---------------------------------------------------------------------------

col1, col2 = st.columns(2)
with col1:
    ingest_clicked = st.button("📥 Ingest Receipt Inbox", use_container_width=True)
with col2:
    heartbeat_clicked = st.button("▶️ Simulate Daily Run", use_container_width=True)

if ingest_clicked:
    result, used_live, err = run_with_fallback(run_ingestion, policy_fallback.ingest_all)
    st.session_state.last_log = ("Ingestion", result, used_live, err)

if heartbeat_clicked:
    result, used_live, err = run_with_fallback(run_daily_heartbeat, policy_fallback.run_heartbeat)
    st.session_state.last_log = ("Daily heartbeat", result, used_live, err)

if "last_log" in st.session_state:
    label, result, used_live, err = st.session_state.last_log
    mode = "🧠 Live Strands agent (Bedrock)" if used_live else "⚙️ Local policy fallback"
    with st.expander(f"{label} — {mode}", expanded=True):
        if isinstance(result, list):
            st.code("\n".join(result))
        else:
            st.write(result)
        if err and not used_live:
            st.caption(f"(Bedrock fallback reason: {err[:200]})")


# ---------------------------------------------------------------------------
# Pending approvals — the human gate
# ---------------------------------------------------------------------------

store = get_store()
pending = store.list_purchases(status="pending_approval")

if pending:
    st.subheader("⚠️ Pending approval")
    for p in pending:
        with st.container(border=True):
            st.markdown(f"**{p.merchant} — {p.product}** · ${p.price:.2f}")
            st.caption(f"Return deadline: {p.return_deadline}  ·  {p.notes}")
            c1, c2 = st.columns(2)
            if c1.button("✅ Approve Return", key=f"approve-{p.id}", use_container_width=True):
                result, used_live, err = run_with_fallback(
                    run_approval_decision, policy_fallback.decide, p.id, "approved"
                )
                st.session_state.last_log = ("Approval decision", result, used_live, err)
                st.rerun()
            if c2.button("🚫 Keep Item", key=f"keep-{p.id}", use_container_width=True):
                result, used_live, err = run_with_fallback(
                    run_approval_decision, policy_fallback.decide, p.id, "keep"
                )
                st.session_state.last_log = ("Approval decision", result, used_live, err)
                st.rerun()


# ---------------------------------------------------------------------------
# Tracked purchases
# ---------------------------------------------------------------------------

st.subheader("📦 Tracked purchases")
purchases = store.list_purchases()
if not purchases:
    st.info("No purchases tracked yet — click **Ingest Receipt Inbox** to scan the mock inbox.")
else:
    rows = []
    for p in purchases:
        days = p.days_remaining()
        rows.append(
            {
                "Merchant": p.merchant,
                "Product": p.product,
                "Price": f"${p.price:.2f}",
                "Days left": days,
                "Status": STATUS_LABELS.get(p.status, p.status),
                "Intent": p.user_intent or "—",
            }
        )
    st.dataframe(rows, use_container_width=True, hide_index=True)


# ---------------------------------------------------------------------------
# Memory
# ---------------------------------------------------------------------------

st.subheader("🧠 Memory — learned preferences")
prefs = store.list_preferences()
if not prefs:
    st.caption("Nothing remembered yet.")
else:
    st.dataframe(
        [{"Merchant": p["merchant"], "Preference": p["key"], "Value": p["value"]} for p in prefs],
        use_container_width=True,
        hide_index=True,
    )

st.divider()
st.caption("“The best return is the one you never have to remember.” — ReturnPilot")
