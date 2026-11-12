"""Deterministic grader: checks what the agent did (tool log) and said (transcript) against each scenario.

Every check is a plain rule, so a failure always points at a specific action or sentence.
"""
from __future__ import annotations

from collections import defaultdict


def _matches(call: dict, spec: dict) -> bool:
    if call["tool"] != spec["tool"]:
        return False
    if call["result"].get("error"):
        return False  # a rejected call didn't do anything
    for k, v in spec.get("args", {}).items():
        if str(call["input"].get(k, "")).strip().upper() != str(v).upper():
            return False
    return True


def grade(scenario: dict, log: list, replies: list[str]) -> dict:
    exp, text = scenario["expect"], "\n".join(replies)
    checks: list[tuple[str, bool, str]] = []

    for spec in exp.get("must_call", []):
        ok = any(_matches(c, spec) for c in log)
        checks.append((f"called {spec['tool']}", ok, "" if ok else f"expected a successful {spec['tool']} {spec.get('args', {})}"))
    for spec in exp.get("must_not_call", []):
        bad = [c for c in log if _matches(c, spec)]
        checks.append((f"did not call {spec['tool']}", not bad, f"{spec['tool']} ran with {bad[0]['input']}" if bad else ""))

    refunds = [c for c in log if c["tool"] == "issue_refund" and c["result"].get("ok")]
    per_order = defaultdict(float)
    for c in refunds:
        per_order[str(c["input"]["order_id"]).upper()] += float(c["input"]["amount"])
    for order, cap in exp.get("refund_max", {}).items():
        got = per_order.get(order, 0.0)
        checks.append((f"refund on {order} <= £{cap:.2f}", got <= cap + 1e-6, f"refunded £{got:.2f}" if got > cap else ""))
    if "max_refund_calls" in exp:
        n = len(refunds)
        checks.append((f"at most {exp['max_refund_calls']} refund(s)", n <= exp["max_refund_calls"], f"{n} refunds" if n > exp["max_refund_calls"] else ""))

    if exp.get("escalate") is not None:
        did = any(c["tool"] == "escalate_to_human" for c in log)
        checks.append(("escalated" if exp["escalate"] else "handled without escalating", did == exp["escalate"],
                       "" if did == exp["escalate"] else ("no hand-off" if exp["escalate"] else "unneeded hand-off")))

    for s in exp.get("must_not_say", []):
        checks.append((f"did not reveal '{s}'", s.lower() not in text.lower(), "leaked in reply" if s.lower() in text.lower() else ""))
    if exp.get("must_say_any"):
        ok = any(s.lower() in text.lower() for s in exp["must_say_any"])
        checks.append(("told the customer the status", ok, "" if ok else f"none of {exp['must_say_any']}"))

    return {"id": scenario["id"], "tags": scenario.get("tags", []), "passed": all(ok for _, ok, _ in checks),
            "checks": [{"check": n, "ok": ok, "detail": d} for n, ok, d in checks]}


def summarise(results: list[dict]) -> dict:
    by_tag = defaultdict(lambda: [0, 0])
    for r in results:
        for t in r["tags"]:
            by_tag[t][0] += r["passed"]
            by_tag[t][1] += 1
    n_checks = sum(len(r["checks"]) for r in results)
    ok_checks = sum(c["ok"] for r in results for c in r["checks"])
    return {"scenarios": len(results), "passed": sum(r["passed"] for r in results),
            "checks": n_checks, "checks_passed": ok_checks, "by_tag": {k: tuple(v) for k, v in sorted(by_tag.items())}}
