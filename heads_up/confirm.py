"""One-time "Got it" links for the large-print email.

Each change gets its own random token. A token works once, only for that
change, and stops working when the event starts, so nobody can confirm for
Gloria by guessing or reusing a link.
"""
from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime

LINK_BASE = "https://heads-up.local/confirm/"  # prototype: shown in the email preview, handled in Streamlit


@dataclass
class TokenRecord:
    change_id: str
    expires_at: datetime
    used_at: datetime | None = None


@dataclass(frozen=True)
class Redemption:
    ok: bool
    reason: str               # "confirmed" | "unknown" | "expired" | "already_used"
    change_id: str | None = None


class TokenStore:
    def __init__(self) -> None:
        self._tokens: dict[str, TokenRecord] = {}

    def make(self, change_id: str, expires_at: datetime) -> str:
        token = secrets.token_urlsafe(16)  # 128 bits: can't be guessed
        self._tokens[token] = TokenRecord(change_id, expires_at)
        return token

    def link(self, token: str) -> str:
        return LINK_BASE + token

    def redeem(self, token: str, now: datetime) -> Redemption:
        record = self._tokens.get(token)
        if record is None:
            return Redemption(False, "unknown")
        if record.used_at is not None:
            return Redemption(False, "already_used", record.change_id)
        if now >= record.expires_at:
            return Redemption(False, "expired", record.change_id)
        record.used_at = now
        return Redemption(True, "confirmed", record.change_id)
