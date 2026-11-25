"""Offline rehearsal of the intake conversation: no Sarvam, no credits, same backend tools.

It plays the intake agent's part deterministically (the real one is the Sarvam LLM), so you can
check the backend flow + dashboard end to end and practise the demo.

  python voice/rehearse.py                       # interactive: you answer yes/no
  python voice/rehearse.py --auto                # answers yes to everything
  python voice/rehearse.py --group "O negative" --units 2 --hospital "Koramangala City"
"""
from __future__ import annotations

import argparse
import os
import sys

import httpx


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", default=os.environ.get("BACKEND_URL", "http://localhost:8000"))
    ap.add_argument("--secret", default=os.environ.get("TOOL_SECRET", "dev-tool-secret"))
    ap.add_argument("--group", default="B positive")
    ap.add_argument("--units", default=4, type=int)
    ap.add_argument("--hospital", default="City General")
    ap.add_argument("--hours", default=3, type=float)
    ap.add_argument("--component", default=None)
    ap.add_argument("--auto", action="store_true")
    a = ap.parse_args()

    c = httpx.Client(base_url=a.backend.rstrip("/"), headers={"X-Tool-Secret": a.secret}, timeout=40)

    def tool(name: str, **body) -> dict:
        r = c.post(f"/tools/{name}", json=body)
        r.raise_for_status()
        return r.json()

    def agent(text: str) -> None:
        print(f"\nAgent: {text}")

    def yes(prompt: str) -> bool:
        if a.auto:
            print("You  : yes")
            return True
        ans = input("You  : ").strip().lower()
        return ans in ("y", "yes", "haan", "ha", "ok", "sure", "go")

    print(f"You  : Need {a.units} units of {a.group}, I'm at {a.hospital}, surgery in {a.hours:g} hours.")
    r = tool("find_leads", blood_group=a.group, units=a.units, location=a.hospital, deadline_hours=a.hours,
             component=a.component)
    agent(r["say"])
    if not r["ok"]:
        sys.exit(1)
    rid = r["request_id"]
    if not yes("Shall I start calling now?"):
        agent("Okay, I won't call anyone. Say the word when you're ready.")
        return
    agent(tool("start_calls", request_id=rid, confirmed=True)["say"])
    while True:
        s = tool("get_status", request_id=rid)
        agent(s["say"])
        if s["needs_approval"]:
            if yes("Widen?"):
                agent(tool("approve_wave2", request_id=rid)["say"])
            else:
                agent("Okay, I'll stop here.")
                tool("cancel_request", request_id=rid)
                return
        if s["done"]:
            print("\nPlan steps:")
            for i, step in enumerate(s["plan"]["steps"], 1):
                print(f"  {i}. {step}")
            return


if __name__ == "__main__":
    main()
