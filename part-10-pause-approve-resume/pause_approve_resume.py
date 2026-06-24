"""
Pause, Approve, Resume, Steer: human-in-the-loop.
Agents from First Principles, Part 10.

Part 9 made the agent durable: it can crash and resume without losing state or
double-charging. But it still runs start to finish on its own. Two things a real
deployment needs are missing. Some actions must WAIT for a human, a refund over a
threshold should not fire until someone approves it, and a person watching the run
may want to CORRECT it mid-flight rather than only approve or deny. The durable
agent has no way to stop, hand control to a human, and come back.

This part adds that, on top of Part 9's journal. Four moves:

1. interrupt(). When the agent reaches a gated action (a refund over the approval
   threshold), it does not call the tool. It journals a "pending_approval" event
   with a token and RAISES a serializable PendingApproval that is caught at the top
   level. Crucially this is NOT sys.exit: the exception carries the token and the
   pending action, so a notebook (or a server) catches it, persists the journal, and
   returns the token to the caller. The run is paused, not dead.

2. resume(run_id, decision). Later, a human decides. resume rehydrates the run by
   replaying the journal (Part 9), records the decision, and continues. Because the
   gated refund still carries its idempotency key, an approved resume executes it
   EXACTLY ONCE even if resume is retried.

3. STEER, not just approve/deny. The human decision is a first-class action, not a
   binary gate. An approver can APPROVE, DENY, or STEER: inject a correction (here,
   lower the refund to an amount under the threshold) that changes what the agent
   does next. Answering a clarifying question back to the user is the same mechanism.

4. Streaming progress. Because every step is a journal event, a live progress feed
   is just a read over the same log. The pause, the decision, and the resume all
   show up in the stream.

CROSS-PROCESS, honestly: a real deployment pauses in one process (the request that
hit the gate returns the token) and resumes in another (a later request, or a CLI
re-invocation, calls resume on the same journal). We model both phases in one file
by catching PendingApproval and then calling resume on the persisted world; the CLI
two-process version is the same journal read by a second script invocation.

CONTINUITY: the refund world (ORD-3300), Part 9's journal + idempotency key, frozen
timestamps + a fixed run_id for reproducibility.

Run:
  python3 pause_approve_resume.py        # offline; no API key, no network, no deps

NOTE: SDK names and model ids move fast; only generate() would need edits.

Expected output (deterministic default path):
========================================================================
PAUSE, APPROVE, RESUME, STEER  -  human-in-the-loop on a durable agent
========================================================================
[controller] no OPENAI_API_KEY; using the deterministic plan (offline default)

Approval threshold: $100. The task is a $180 refund for ORD-3300, which is over the threshold.

------------------------------------------------------------------------
RUN until the approval gate, then PAUSE (interrupt -> PendingApproval).
------------------------------------------------------------------------
    step 0 search_policy: Refunds after the window are refundable minus a 10% restocking fee.
    PAUSED: refund $180.00 exceeds the $100 threshold
    returned token 'appr-1'; the run is persisted, not dead. Ledger so far: (empty, no money moved yet)

    streaming progress from the journal:
      > run started
      > done: Refunds after the window are refundable minus a 10% restocking fee.
      > PAUSED for approval (refund $180.00 exceeds the $100 threshold); token appr-1

========================================================================
RESUME A) APPROVE: the gated refund executes (effectively-once via its key).
========================================================================
    [human] decision = approve
    step 0 search_policy: memoized -> 'Refunds after the window are refundable minus a 10% restocking fee.'
    step 1 process_refund: refunded $180.00 to ORD-3300
    finished -> Refund of $180.00 for ORD-3300 is complete.
    ledger: {'ORD-3300': 180.0}

========================================================================
RESUME B) DENY: no money moves; the run finishes with a refusal.
========================================================================
    [human] decision = deny
    step 0 search_policy: memoized -> 'Refunds after the window are refundable minus a 10% restocking fee.'
    step 1 process_refund: DENIED by approver -> no money moved
    ledger: (empty)

========================================================================
RESUME C) STEER: the approver lowers the refund to $90, under the threshold.
========================================================================
    [human] decision = steer (correction: $90.00)
    step 0 search_policy: memoized -> 'Refunds after the window are refundable minus a 10% restocking fee.'
    step 1 process_refund: STEERED by approver -> amount lowered to $90.00 (now under the $100 threshold)
    step 1 process_refund: refunded $90.00 to ORD-3300
    finished -> Refund of $90.00 for ORD-3300 is complete.
    ledger: {'ORD-3300': 90.0}

    streaming the STEER timeline (pause + decision + resume, all from the journal):
      > run started
      > done: Refunds after the window are refundable minus a 10% restocking fee.
      > PAUSED for approval (refund $180.00 exceeds the $100 threshold); token appr-1
      > human decision: steer
      > done: refunded $90.00 to ORD-3300
      > finished: Refund of $90.00 for ORD-3300 is complete.

========================================================================
Done. A durable agent can now hand control to a human and come back:
  - interrupt() raises a serializable PendingApproval (a token), NOT sys.exit
  - resume() replays the journal and acts on the decision (effectively-once)
  - the decision is a first-class action: APPROVE, DENY, or STEER a correction
  - progress streams from the same journal events that make it durable
========================================================================
"""

import copy
import os


RUN_ID = "run-aa10"
TS_BASE = "2026-07-06T09:00:"
THRESHOLD = 100.0                          # refunds over this need human approval


# ===========================================================================
# Step 1. The journal (carried from Part 9): append-only events; state is the fold
# over the log. The world bundles the durable artifacts that survive a pause.
# ===========================================================================
def new_world():
    return {"journal": [], "keystore": {}, "ledger": {}}


def append(world, etype, data):
    seq = len(world["journal"])
    world["journal"].append({"seq": seq, "run_id": RUN_ID, "ts": f"{TS_BASE}{seq:02d}Z",
                             "type": etype, "data": data})


def replay(journal):
    """Fold the log: completed steps + results, the recorded human decisions, and
    whether the run finished."""
    completed, results, decisions, finished = set(), {}, {}, False
    for e in journal:
        d, t = e["data"], e["type"]
        if t == "tool_result":
            completed.add(d["idx"]); results[d["idx"]] = d["result"]
        elif t == "approval_decision":
            decisions[d["idx"]] = {"decision": d["decision"], "correction": d.get("correction")}
        elif t == "finished":
            finished = True
    return completed, results, decisions, finished


# ===========================================================================
# Step 2. The interrupt: a serializable exception caught at the top level. NOT
# sys.exit -- it carries the token and the pending action so the caller can persist
# and hand off to a human, and a notebook stays runnable.
# ===========================================================================
class PendingApproval(Exception):
    def __init__(self, token, action, reason):
        super().__init__(f"pending approval: {reason}")
        self.token = token
        self.action = action
        self.reason = reason


# ===========================================================================
# Step 3. Tools (from Part 9): read-only search, and an idempotent side-effecting
# refund. The key makes an approved resume effectively-once.
# ===========================================================================
def exec_search(args):
    return "Refunds after the window are refundable minus a 10% restocking fee."


def exec_refund(world, order_id, amount, idem_key):
    ks = world["keystore"]
    if idem_key in ks:
        return ks[idem_key], True
    world["ledger"][order_id] = world["ledger"].get(order_id, 0.0) + amount
    result = f"refunded ${amount:.2f} to {order_id}"
    ks[idem_key] = result
    return result, False


STEPS = [
    ("search_policy", {"query": "refund policy window"}, None),
    ("process_refund", {"order_id": "ORD-3300", "amount": 180.0}, "ORD-3300:refund"),
]


# ===========================================================================
# Step 4. The run loop. At the gated step: if no decision is recorded yet, journal
# pending_approval and RAISE. If a decision exists, act on it (approve / deny /
# steer). Everything else runs as in Part 9 (memoized on replay).
# ===========================================================================
def run(world):
    if not world["journal"]:
        append(world, "run_started", {"run_id": RUN_ID})
    completed, results, decisions, finished = replay(world["journal"])
    if finished:
        return

    for idx, (tool, args, idem) in enumerate(STEPS):
        if idx in completed:
            print(f"    step {idx} {tool}: memoized -> {results[idx]!r}")
            continue

        amount = args.get("amount")
        gated = (tool == "process_refund" and amount > THRESHOLD)
        if gated:
            decision = decisions.get(idx)
            if decision is None:                       # nobody has decided yet: PAUSE
                token = f"appr-{idx}"
                action = {"tool": tool, "args": args}
                append(world, "pending_approval",
                       {"idx": idx, "token": token, "action": action,
                        "reason": f"refund ${amount:.2f} exceeds the ${THRESHOLD:.0f} threshold"})
                raise PendingApproval(token, action,
                                      f"refund ${amount:.2f} exceeds the ${THRESHOLD:.0f} threshold")
            if decision["decision"] == "deny":
                append(world, "tool_result", {"idx": idx, "tool": tool,
                                              "result": "DENIED by approver (no money moved)"})
                append(world, "finished", {"answer": "Refund denied by approver; no money moved."})
                print(f"    step {idx} {tool}: DENIED by approver -> no money moved")
                return
            if decision["decision"] == "steer":        # a correction, not a yes/no
                amount = decision["correction"]["amount"]
                args = {**args, "amount": amount}
                print(f"    step {idx} {tool}: STEERED by approver -> amount lowered to ${amount:.2f} "
                      f"(now under the ${THRESHOLD:.0f} threshold)")

        # execute (not gated, or approved, or steered under threshold)
        if tool == "process_refund":
            result, was_idem = exec_refund(world, args["order_id"], args["amount"], idem)
            tag = " (idempotent)" if was_idem else ""
        else:
            result, was_idem, tag = exec_search(args), False, ""
        append(world, "tool_result", {"idx": idx, "tool": tool, "result": result})
        print(f"    step {idx} {tool}: {result}{tag}")

    final = f"Refund of ${world['ledger'].get('ORD-3300', 0.0):.2f} for ORD-3300 is complete."
    append(world, "finished", {"answer": final})
    print(f"    finished -> {final}")


def resume(world, decision, correction=None, idx=1):
    """A human decides on a paused run. Record the decision, then re-enter run(),
    which replays the journal and acts on it. decision in {approve, deny, steer}."""
    append(world, "approval_decision", {"idx": idx, "decision": decision, "correction": correction})
    extra = f" (correction: ${correction['amount']:.2f})" if correction else ""
    print(f"    [human] decision = {decision}{extra}")
    run(world)


# ===========================================================================
# Step 5. Streaming progress: a live feed is just a read over the journal events.
# ===========================================================================
def stream(world):
    for e in world["journal"]:
        d, t = e["data"], e["type"]
        if t == "run_started":
            print("      > run started")
        elif t == "llm_decided":
            print(f"      > deciding: {d['tool']}")
        elif t == "tool_result":
            print(f"      > done: {d['result']}")
        elif t == "pending_approval":
            print(f"      > PAUSED for approval ({d['reason']}); token {d['token']}")
        elif t == "approval_decision":
            print(f"      > human decision: {d['decision']}")
        elif t == "finished":
            print(f"      > finished: {d['answer']}")


# ===========================================================================
# generate() -- the real LLM path (reference shape only). Offline, the deterministic
# plan is the source of truth (same device as Parts 1-9).
# ===========================================================================
def generate(prompt):
    """REAL path: ask a hosted LLM for the next step. Unused offline."""
    from openai import OpenAI
    client = OpenAI()
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
    )
    return resp.choices[0].message.content


def _pause(world, label):
    try:
        run(world)
        print(f"    [{label}] (completed without pausing)")
        return None
    except PendingApproval as p:
        print(f"    PAUSED: {p.reason}")
        print(f"    returned token {p.token!r}; the run is persisted, not dead. Ledger so far: "
              f"{world['ledger'] or '(empty, no money moved yet)'}")
        return p.token


# ===========================================================================
# Demo. Everything below RUNS OFFLINE.
# ===========================================================================
if __name__ == "__main__":
    bar = "=" * 72
    print(bar)
    print("PAUSE, APPROVE, RESUME, STEER  -  human-in-the-loop on a durable agent")
    print(bar)
    if os.environ.get("OPENAI_API_KEY"):
        print("[controller] OPENAI_API_KEY set; the real LLM would drive the loop via generate(). "
              "Falling through to the deterministic plan for reproducibility.")
    else:
        print("[controller] no OPENAI_API_KEY; using the deterministic plan (offline default)")
    print(f"\nApproval threshold: ${THRESHOLD:.0f}. The task is a ${STEPS[1][1]['amount']:.0f} refund "
          "for ORD-3300, which is over the threshold.")

    # --- Phase 1: run until it hits the gate, then pause. -------------------
    print("\n" + "-" * 72)
    print("RUN until the approval gate, then PAUSE (interrupt -> PendingApproval).")
    print("-" * 72)
    paused = new_world()
    token = _pause(paused, "run")
    print("\n    streaming progress from the journal:")
    stream(paused)

    # --- Phase 2: three ways a human can resolve the pause. ----------------
    print("\n" + bar)
    print("RESUME A) APPROVE: the gated refund executes (effectively-once via its key).")
    print(bar)
    wa = copy.deepcopy(paused)
    resume(wa, "approve")
    print(f"    ledger: {wa['ledger']}")

    print("\n" + bar)
    print("RESUME B) DENY: no money moves; the run finishes with a refusal.")
    print(bar)
    wb = copy.deepcopy(paused)
    resume(wb, "deny")
    print(f"    ledger: {wb['ledger'] or '(empty)'}")

    print("\n" + bar)
    print("RESUME C) STEER: the approver lowers the refund to $90, under the threshold.")
    print(bar)
    wc = copy.deepcopy(paused)
    resume(wc, "steer", correction={"amount": 90.0})
    print(f"    ledger: {wc['ledger']}")
    print("\n    streaming the STEER timeline (pause + decision + resume, all from the journal):")
    stream(wc)

    print("\n" + bar)
    print("Done. A durable agent can now hand control to a human and come back:")
    print("  - interrupt() raises a serializable PendingApproval (a token), NOT sys.exit")
    print("  - resume() replays the journal and acts on the decision (effectively-once)")
    print("  - the decision is a first-class action: APPROVE, DENY, or STEER a correction")
    print("  - progress streams from the same journal events that make it durable")
    print(bar)
