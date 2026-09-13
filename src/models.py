"""Core data model for ReturnPilot."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import date, datetime
from typing import Optional


def _parse_date(value) -> date:
    if isinstance(value, date):
        return value
    return datetime.fromisoformat(value).date()


@dataclass
class Purchase:
    id: str
    merchant: str
    product: str
    category: str
    price: float
    purchase_date: str          # ISO date string
    return_deadline: str        # ISO date string
    source_email_subject: str = ""
    user_intent: Optional[str] = None    # None | "return" | "keep"
    status: str = "monitoring"           # monitoring | return_ready | pending_approval
                                          # | approved | return_initiated | refund_pending | completed
    notes: str = ""

    def days_remaining(self, as_of: Optional[date] = None) -> int:
        today = as_of or date.today()
        return (_parse_date(self.return_deadline) - today).days

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Purchase":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})
