"""
Mock merchant return-policy table.

In production this would be `lookup_return_policy()` hitting a real policy
API / scraped database. For the hackathon demo it's a static lookup so the
agent's reasoning is deterministic and easy to narrate on camera.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ReturnPolicy:
    merchant: str
    window_days: int
    preferred_method: str  # "mail" | "in_store" | "either"
    notes: str = ""


# Merchant -> policy. Keys are lowercased merchant names.
RETURN_POLICIES: dict[str, ReturnPolicy] = {
    "amazon": ReturnPolicy(
        merchant="Amazon",
        window_days=30,
        preferred_method="mail",
        notes="Free returns via prepaid label or Amazon locker drop-off.",
    ),
    "target": ReturnPolicy(
        merchant="Target",
        window_days=90,
        preferred_method="either",
        notes="90-day standard window; electronics limited to 30 days.",
    ),
    "best buy": ReturnPolicy(
        merchant="Best Buy",
        window_days=15,
        preferred_method="in_store",
        notes="15-day standard window on most electronics; 60 for My Best Buy members.",
    ),
}


def lookup_return_policy(merchant: str) -> ReturnPolicy:
    """Look up the return policy for a merchant. Falls back to a conservative default."""
    policy = RETURN_POLICIES.get(merchant.strip().lower())
    if policy:
        return policy
    return ReturnPolicy(
        merchant=merchant,
        window_days=30,
        preferred_method="mail",
        notes="No policy on file — defaulted to 30 days.",
    )
