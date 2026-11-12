"""python -m support_evals --agent naive|claude [--only ID] [--out results/naive.md]"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .grader import grade, summarise
from .store import Store

SCENARIOS = Path(__file__).resolve().parent.parent / "scenarios" / "scenarios.json"


def run(agent_name: str, only: str | None = None, effort: str = "medium") -> list[dict]:
    scenarios = json.loads(SCENARIOS.read_text())
    results = []
    for sc in scenarios:
        if only and sc["id"] != only:
            continue
        store = Store()
        if agent_name == "naive":
            from .baselines import NaiveAgent
            agent = NaiveAgent(store)
        else:
            from .agent import ClaudeAgent
            agent = ClaudeAgent(store, effort=effort)
        replies = [agent.reply(t) for t in sc["turns"]]
        r = grade(sc, store.log, replies)
        r["transcript"] = [{"customer": t, "agent": a} for t, a in zip(sc["turns"], replies)]
        r["tool_log"] = store.log
        results.append(r)
    return results


def to_markdown(agent_name: str, results: list[dict]) -> str:
    s = summarise(results)
    lines = [f"# Results: {agent_name} agent", "",
             f"**{s['passed']}/{s['scenarios']} scenarios passed**, {s['checks_passed']}/{s['checks']} individual checks.", "",
             "| Area | Passed |", "| --- | --- |"]
    lines += [f"| {t} | {p}/{n} |" for t, (p, n) in s["by_tag"].items()]
    lines += ["", "| Scenario | Result | Failed checks |", "| --- | --- | --- |"]
    for r in results:
        failed = "; ".join(f"{c['check']} ({c['detail']})" for c in r["checks"] if not c["ok"])
        lines.append(f"| {r['id']} | {'pass' if r['passed'] else 'FAIL'} | {failed} |")
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--agent", choices=["naive", "claude"], default="naive")
    ap.add_argument("--only")
    ap.add_argument("--effort", default="medium", choices=["low", "medium", "high", "xhigh", "max"])
    ap.add_argument("--out", help="write a markdown report here")
    ap.add_argument("--json", help="write full results (transcripts and tool logs) here")
    a = ap.parse_args()
    results = run(a.agent, a.only, a.effort)
    md = to_markdown(a.agent, results)
    print(md)
    if a.out:
        Path(a.out).write_text(md)
    if a.json:
        Path(a.json).write_text(json.dumps(results, indent=1, default=str))


if __name__ == "__main__":
    main()
