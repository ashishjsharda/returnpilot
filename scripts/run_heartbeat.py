"""
CLI entry point for a single ReturnPilot run — this is what a real EventBridge
rule would invoke on a schedule (directly, or wrapped as a Lambda handler;
`handler()` below is Lambda-shaped for that purpose).

Usage:
    python3 scripts/run_heartbeat.py ingest      # scan inbox, save new purchases
    python3 scripts/run_heartbeat.py heartbeat   # run the daily deadline check
    python3 scripts/run_heartbeat.py both        # ingest then heartbeat (default)
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.agent import build_agent, run_daily_heartbeat, run_ingestion  # noqa: E402


def main(mode: str = "both") -> None:
    agent = build_agent()

    if mode in ("ingest", "both"):
        print("=== Ingesting receipt inbox ===")
        print(run_ingestion(agent))
        print()

    if mode in ("heartbeat", "both"):
        print("=== Running daily heartbeat ===")
        print(run_daily_heartbeat(agent))


def handler(event=None, context=None):
    """AWS Lambda handler shape, for EventBridge -> Lambda -> ReturnPilot."""
    mode = (event or {}).get("mode", "both")
    main(mode)
    return {"statusCode": 200, "mode": mode}


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else "both"
    main(arg)
