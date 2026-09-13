"""Central config, read from environment variables (see .env.example)."""

from __future__ import annotations

import os

try:
    from dotenv import load_dotenv  # optional, not a hard dependency

    load_dotenv()
except ImportError:
    pass


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


STORAGE_BACKEND = _env("RETURNPILOT_STORAGE", "local").lower()  # "local" | "dynamodb"
DYNAMODB_TABLE = _env("DYNAMODB_TABLE", "ReturnPilotPurchases")
AWS_REGION = _env("AWS_REGION", "us-east-1")
BEDROCK_MODEL_ID = _env("BEDROCK_MODEL_ID", "anthropic.claude-3-5-sonnet-20241022-v2:0")
APPROVAL_THRESHOLD_USD = float(_env("APPROVAL_THRESHOLD_USD", "200"))
LOCAL_DB_PATH = _env("RETURNPILOT_LOCAL_DB", "data/returnpilot.db")


def aws_credentials_present() -> bool:
    """Best-effort check for whether real AWS credentials are usable."""
    if os.environ.get("AWS_ACCESS_KEY_ID") and os.environ.get("AWS_SECRET_ACCESS_KEY"):
        return True
    # Could also be set via AWS_PROFILE / shared credentials file / SSO.
    if os.environ.get("AWS_PROFILE"):
        return True
    return os.path.exists(os.path.expanduser("~/.aws/credentials"))
