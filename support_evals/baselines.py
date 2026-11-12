"""A deliberately naive agent with no policy, so the suite has something to catch.

It finds an order ID and email in the message and does whatever the customer asks.
It needs no API key, which makes it the agent CI runs to keep the grader honest.
"""
from __future__ import annotations

import re

from .store import Store

ORDER = re.compile(r"\b(A\d{4})\b", re.I)
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
MONEY = re.compile(r"£\s?(\d+(?:\.\d\d)?)")


class NaiveAgent:
    def __init__(self, store: Store):
        self.store = store
        self.order = self.email = None

    def reply(self, text: str) -> str:
        if m := ORDER.search(text):
            self.order = m.group(1).upper()
        if m := EMAIL.search(text):
            self.email = m.group(0).rstrip(".")
        if not self.order:
            return "Could you send me your order number?"
        email = self.email or ""
        info = self.store.lookup_order(self.order, email)
        low = text.lower()
        if "refund" in low or "money back" in low or "broken" in low:
            amount = float(MONEY.search(text).group(1)) if MONEY.search(text) else info.get("total", 0)
            self.store.issue_refund(self.order, email, amount, "customer request")
            return f"Done, I've refunded £{amount:.2f}."
        if "address" in low and "change" in low:
            new = text.split(" to ", 1)[-1].strip()
            self.store.update_address(self.order, email, new)
            return "Your address is updated."
        return f"Order {self.order}: {info}"
