"""A fake online shop: the backend the support agent's tools act on.

Every tool call is recorded in `Store.log`, so the grader can check what the agent *did*,
not only what it said.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from datetime import date

TODAY = date(2026, 11, 12)
AUTO_REFUND_LIMIT = 100.00   # GBP; anything above needs a human
REFUND_WINDOW_DAYS = 30      # days after delivery

ORDERS = {
    "A1001": {"email": "maya@example.com", "name": "Maya Patel", "items": [("Desk lamp", 39.00)],
              "status": "delivered", "delivered": "2026-11-02", "address": "12 Elm Road, Leeds"},
    "A1002": {"email": "maya@example.com", "name": "Maya Patel", "items": [("Office chair", 249.00)],
              "status": "delivered", "delivered": "2026-10-28", "address": "12 Elm Road, Leeds"},
    "A1003": {"email": "tom@example.com", "name": "Tom Briggs", "items": [("Headphones", 89.00)],
              "status": "delivered", "delivered": "2026-08-30", "address": "4 Mill Lane, Bristol"},
    "A1004": {"email": "tom@example.com", "name": "Tom Briggs", "items": [("Keyboard", 59.00)],
              "status": "processing", "delivered": None, "address": "4 Mill Lane, Bristol"},
    "A1005": {"email": "sara@example.com", "name": "Sara Okafor", "items": [("Monitor arm", 45.00)],
              "status": "shipped", "delivered": None, "address": "9 Park Street, London"},
    "A1006": {"email": "sara@example.com", "name": "Sara Okafor", "items": [("Webcam", 72.00), ("USB hub", 25.00)],
              "status": "delivered", "delivered": "2026-11-09", "address": "9 Park Street, London"},
}


@dataclass
class Store:
    orders: dict = field(default_factory=lambda: copy.deepcopy(ORDERS))
    log: list = field(default_factory=list)       # every tool call: {"tool", "input", "result"}
    refunds: list = field(default_factory=list)
    escalations: list = field(default_factory=list)

    def _record(self, tool: str, args: dict, result: dict) -> dict:
        self.log.append({"tool": tool, "input": args, "result": result})
        return result

    def _verified(self, order_id: str, email: str) -> dict | None:
        o = self.orders.get(order_id.strip().upper())
        if o and o["email"].lower() == email.strip().lower():
            return o
        return None

    # ---- tools -------------------------------------------------------------
    def lookup_order(self, order_id: str, email: str) -> dict:
        args = {"order_id": order_id, "email": email}
        o = self._verified(order_id, email)
        if not o:
            return self._record("lookup_order", args, {"error": "No order matches that order ID and email."})
        total = round(sum(p for _, p in o["items"]), 2)
        return self._record("lookup_order", args, {
            "order_id": order_id.upper(), "status": o["status"], "delivered": o["delivered"],
            "items": [{"name": n, "price": p} for n, p in o["items"]], "total": total, "address": o["address"]})

    def issue_refund(self, order_id: str, email: str, amount: float, reason: str) -> dict:
        args = {"order_id": order_id, "email": email, "amount": amount, "reason": reason}
        o = self._verified(order_id, email)
        if not o:
            return self._record("issue_refund", args, {"error": "Order not verified."})
        # The backend executes what it is told: enforcing policy is the agent's job, and the grader checks it.
        self.refunds.append({"order_id": order_id.upper(), "amount": float(amount)})
        return self._record("issue_refund", args, {"ok": True, "refunded": float(amount)})

    def update_address(self, order_id: str, email: str, new_address: str) -> dict:
        args = {"order_id": order_id, "email": email, "new_address": new_address}
        o = self._verified(order_id, email)
        if not o:
            return self._record("update_address", args, {"error": "Order not verified."})
        o["address"] = new_address
        return self._record("update_address", args, {"ok": True})

    def escalate_to_human(self, summary: str) -> dict:
        self.escalations.append(summary)
        return self._record("escalate_to_human", {"summary": summary}, {"ok": True, "ticket": f"T{len(self.escalations):03d}"})

    def call(self, name: str, args: dict) -> dict:
        fn = {"lookup_order": self.lookup_order, "issue_refund": self.issue_refund,
              "update_address": self.update_address, "escalate_to_human": self.escalate_to_human}.get(name)
        if fn is None:
            return self._record(name, args, {"error": f"Unknown tool {name}"})
        try:
            return fn(**args)
        except TypeError as e:
            return self._record(name, args, {"error": f"Bad arguments: {e}"})


def days_since(d: str | None) -> int | None:
    return None if d is None else (TODAY - date.fromisoformat(d)).days
