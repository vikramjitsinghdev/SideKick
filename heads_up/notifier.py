"""Where calls, emails and family messages go.

The prototype uses SimulatedNotifier: everything lands in an outbox that the
Streamlit app shows as the call screen, email preview and family message.
A Gmail or Twilio notifier can replace it later with the same three methods.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class OutboxItem:
    at: datetime
    channel: str          # "call" | "email" | "family_message"
    to: str
    body: str
    meta: dict = field(default_factory=dict)


class SimulatedNotifier:
    def __init__(self) -> None:
        self.outbox: list[OutboxItem] = []

    def call(self, at: datetime, to: str, script: str, attempt: int) -> OutboxItem:
        item = OutboxItem(at, "call", to, script, {"attempt": attempt})
        self.outbox.append(item)
        return item

    def email(self, at: datetime, to: str, subject: str, body: str, link: str) -> OutboxItem:
        item = OutboxItem(at, "email", to, body, {"subject": subject, "link": link})
        self.outbox.append(item)
        return item

    def family_message(self, at: datetime, to: str, body: str) -> OutboxItem:
        item = OutboxItem(at, "family_message", to, body)
        self.outbox.append(item)
        return item

    def question_to_gloria(self, at: datetime, to: str, body: str) -> OutboxItem:
        """'Ask Gloria' decisions: tell her about the text instead of editing anything."""
        item = OutboxItem(at, "question", to, body)
        self.outbox.append(item)
        return item
