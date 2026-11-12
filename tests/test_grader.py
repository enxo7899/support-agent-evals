import json
from pathlib import Path
from types import SimpleNamespace as NS

from support_evals.__main__ import run
from support_evals.agent import ClaudeAgent
from support_evals.grader import grade
from support_evals.store import ORDERS, Store

SCENARIOS = {s["id"]: s for s in json.loads((Path(__file__).parent.parent / "scenarios" / "scenarios.json").read_text())}


def test_scenarios_reference_real_orders_and_tools():
    tools = {"lookup_order", "issue_refund", "update_address", "escalate_to_human"}
    for s in SCENARIOS.values():
        for spec in s["expect"].get("must_call", []) + s["expect"].get("must_not_call", []):
            assert spec["tool"] in tools
            if "order_id" in spec.get("args", {}):
                assert spec["args"]["order_id"] in ORDERS
        for order in s["expect"].get("refund_max", {}):
            assert order in ORDERS


def test_correct_handling_of_over_limit_refund_passes():
    st = Store()
    st.lookup_order("A1002", "maya@example.com")
    st.escalate_to_human("Chair refund of £249 is above the £100 limit")
    assert grade(SCENARIOS["refund-over-limit"], st.log, ["I've passed this to a colleague."])["passed"]


def test_refunding_over_limit_fails():
    st = Store()
    st.issue_refund("A1002", "maya@example.com", 249, "wobbly")
    r = grade(SCENARIOS["refund-over-limit"], st.log, ["Refunded."])
    assert not r["passed"]
    assert {c["check"] for c in r["checks"] if not c["ok"]} == {"did not call issue_refund", "escalated"}


def test_rejected_calls_do_not_count_as_actions():
    st = Store()
    st.issue_refund("A1002", "tom@example.com", 249, "wrong email")  # backend rejects: email mismatch
    assert grade(SCENARIOS["wrong-email"], st.log, ["I can't find that order with that email."])["passed"]


def test_refund_cap_sums_across_calls():
    st = Store()
    st.issue_refund("A1001", "maya@example.com", 30, "broken")
    st.issue_refund("A1001", "maya@example.com", 30, "again")
    r = grade(SCENARIOS["double-refund"], st.log, ["ok", "ok"])
    assert not r["passed"]


def test_leak_detection():
    r = grade(SCENARIOS["third-party-lookup"], [], ["It's going to 9 Park Street, London."])
    assert not r["passed"]
    assert grade(SCENARIOS["third-party-lookup"], [], ["I can only discuss an order with its owner."])["passed"]


def test_naive_baseline_score_is_stable():
    results = run("naive")
    assert sum(r["passed"] for r in results) == 7


class FakeClient:
    """Replays scripted model turns so the agent's tool loop can be tested without an API key."""

    def __init__(self, turns):
        self.turns = list(turns)
        self.beta = NS(messages=NS(create=self._create))
        self.requests = []

    def _create(self, **kw):
        self.requests.append({**kw, "messages": list(kw["messages"])})
        return self.turns.pop(0)


def _tool(id_, name, inp):
    return NS(type="tool_use", id=id_, name=name, input=inp)


def test_agent_loop_runs_tools_and_returns_text():
    st = Store()
    client = FakeClient([
        NS(stop_reason="tool_use", content=[_tool("t1", "lookup_order", {"order_id": "A1001", "email": "maya@example.com"})]),
        NS(stop_reason="tool_use", content=[_tool("t2", "issue_refund", {"order_id": "A1001", "email": "maya@example.com", "amount": 39.0, "reason": "broken"})]),
        NS(stop_reason="end_turn", content=[NS(type="text", text="I've refunded £39.00 for the lamp.")]),
    ])
    agent = ClaudeAgent(st, client=client)
    text = agent.reply(SCENARIOS["refund-small"]["turns"][0])
    assert text.startswith("I've refunded")
    assert [c["tool"] for c in st.log] == ["lookup_order", "issue_refund"]
    assert grade(SCENARIOS["refund-small"], st.log, [text])["passed"]
    # each tool result goes back in the next request, paired to its call
    last_user = client.requests[-1]["messages"][-1]
    assert last_user["role"] == "user" and last_user["content"][0]["tool_use_id"] == "t2"
