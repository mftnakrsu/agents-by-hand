"""
The Durable Agent: event journal, replay, and effectively-once.
Agents from First Principles, Part 9.

Everything so far lived in one fragile process. Pull the plug mid-run and the whole
state, every observation, every decision, the half-finished refund, is gone. Worse,
the obvious recovery is the dangerous one: just run the task again. If the refund
already posted before the crash, a naive rerun posts it a SECOND time. The agent
needs to survive a crash AND survive its own recovery.

Part 2 gave the refund tool a LOCAL idempotency guard: an in-memory dict that stops
a retry inside one run from double-acting. That dict dies with the process. This
part makes durability real with three pieces:

1. AN APPEND-ONLY EVENT JOURNAL. Every step writes an event (run_started,
   llm_decided, tool_result, finished) to a log keyed by a fixed run_id. The log is
   the source of truth, and STATE IS THE FOLD OVER THE LOG: to know what has
   happened, you replay the events, you do not trust in-memory variables. (We keep
   it in a list here and print it as JSONL; a real system appends to a JSONL file or
   SQLite so it survives the process.)

2. DETERMINISTIC REPLAY WITH STEP MEMOIZATION. On resume, fold the journal to see
   which steps already finished, and return their recorded results WITHOUT re-running
   them. Only the tail after the crash actually executes again.

3. IDEMPOTENCY KEYS for side-effecting tools. Memoization alone is not enough,
   because of the worst-case crash: the refund POSTS and the provider records it,
   but the process dies BEFORE the tool_result is journaled. On replay the journal
   has no result for that step, so memoization re-runs it. The idempotency KEY saves
   us: the refund carries a stable key, the provider remembers keys it has already
   seen (a durable keystore), and a repeat of the same key returns the original
   result instead of charging again. That is EFFECTIVELY-ONCE across a replay, and
   it hardens Part 2's local guard.

HONESTY (scope of the claims): the journal is byte-reproducible ONLY on the
deterministic path; with a real LLM you cache each decision in the journal and
replay the cached decision rather than re-generating it (best-effort, not byte
identical). "Cross-process resume" here means rerun the same script on the same
journal; it is not true inter-process messaging. The keystore models the payment
provider's own idempotency, which is what makes the guarantee real in practice.

CONTINUITY: the refund world (ORD-3300, the $180 refund from the restocking-fee
example). Frozen timestamps + a fixed run_id keep the journal reproducible.

Run:
  python3 durable_agent.py        # offline; no API key, no network, no deps

NOTE: SDK names and model ids move fast; only generate() would need edits.

Expected output (deterministic default path):
========================================================================
THE DURABLE AGENT  -  event journal, replay, and effectively-once
========================================================================
[controller] no OPENAI_API_KEY; using the deterministic plan (offline default)

------------------------------------------------------------------------
1) RUN 1 crashes after the refund posts but before it is journaled.
------------------------------------------------------------------------
    step 0 search_policy: Refunds after the window are refundable minus a 10% restocking fee.
    step 1 process_refund: effect done (ledger touched, key honored), but
    *** PROCESS KILLED before the result was journaled ***

  Journal after the crash (this is what survives on disk):
    {"data": {"run_id": "run-7f3a"}, "run_id": "run-7f3a", "seq": 0, "ts": "2026-07-05T10:00:00Z", "type": "run_started"}
    {"data": {"args": {"query": "refund policy window"}, "idx": 0, "tool": "search_policy"}, "run_id": "run-7f3a", "seq": 1, "ts": "2026-07-05T10:00:01Z", "type": "llm_decided"}
    {"data": {"idx": 0, "result": "Refunds after the window are refundable minus a 10% restocking fee.", "tool": "search_policy"}, "run_id": "run-7f3a", "seq": 2, "ts": "2026-07-05T10:00:02Z", "type": "tool_result"}
    {"data": {"args": {"amount": 180.0, "order_id": "ORD-3300"}, "idx": 1, "tool": "process_refund"}, "run_id": "run-7f3a", "seq": 3, "ts": "2026-07-05T10:00:03Z", "type": "llm_decided"}
  Ledger after the crash: ORD-3300=$180.00  (the refund DID post)
  Note: the journal has NO tool_result for step 1, so memoization alone would re-run it.

========================================================================
2) NAIVE RESTART (ignores the journal and idempotency): double charge.
========================================================================
    step 0 search_policy: re-ran from scratch
    step 1 process_refund: refunded $180.00 to ORD-3300 (no idempotency check!)
    ledger now: ORD-3300=$360.00  <- DOUBLE REFUND ($360.00). This is the bug.

========================================================================
3) DURABLE RESUME (replay the journal; the idempotency key prevents a re-charge).
========================================================================
    step 0 search_policy: memoized from journal -> 'Refunds after the window are refundable minus a 10% restocking fee.'
    step 1 process_refund: refunded $180.00 to ORD-3300 (idempotent: key already honored, no second charge)
    finished -> Refund of $180.00 for ORD-3300 is complete (processed exactly once).

  Journal after the resume:
    {"data": {"run_id": "run-7f3a"}, "run_id": "run-7f3a", "seq": 0, "ts": "2026-07-05T10:00:00Z", "type": "run_started"}
    {"data": {"args": {"query": "refund policy window"}, "idx": 0, "tool": "search_policy"}, "run_id": "run-7f3a", "seq": 1, "ts": "2026-07-05T10:00:01Z", "type": "llm_decided"}
    {"data": {"idx": 0, "result": "Refunds after the window are refundable minus a 10% restocking fee.", "tool": "search_policy"}, "run_id": "run-7f3a", "seq": 2, "ts": "2026-07-05T10:00:02Z", "type": "tool_result"}
    {"data": {"args": {"amount": 180.0, "order_id": "ORD-3300"}, "idx": 1, "tool": "process_refund"}, "run_id": "run-7f3a", "seq": 3, "ts": "2026-07-05T10:00:03Z", "type": "llm_decided"}
    {"data": {"args": {"amount": 180.0, "order_id": "ORD-3300"}, "idx": 1, "tool": "process_refund"}, "run_id": "run-7f3a", "seq": 4, "ts": "2026-07-05T10:00:04Z", "type": "llm_decided"}
    {"data": {"idx": 1, "result": "refunded $180.00 to ORD-3300", "tool": "process_refund"}, "run_id": "run-7f3a", "seq": 5, "ts": "2026-07-05T10:00:05Z", "type": "tool_result"}
    {"data": {"answer": "Refund of $180.00 for ORD-3300 is complete (processed exactly once)."}, "run_id": "run-7f3a", "seq": 6, "ts": "2026-07-05T10:00:06Z", "type": "finished"}
  Ledger after the resume: ORD-3300=$180.00  <- still ONE refund. Effectively-once.

========================================================================
Done. Durability is three things working together:
  - an append-only JOURNAL where state is the FOLD over the log (survives the crash)
  - deterministic REPLAY with step MEMOIZATION (only the tail re-runs)
  - IDEMPOTENCY KEYS so a re-run of a side effect returns the original, never doubles
Memoization handles the easy crash; the idempotency key handles the hard one
(effect done, result not yet journaled). Part 2's local guard, now effectively-once.
========================================================================
"""

import copy
import json
import os


RUN_ID = "run-7f3a"                       # a fixed run id so the journal is reproducible
TS_BASE = "2026-07-05T10:00:"             # frozen timestamps: TS_BASE + seq


# ===========================================================================
# Step 1. The event journal. Append-only events; state is the FOLD over them.
# A "world" bundles the three durable artifacts that must survive a crash:
#   journal  -- the event log (append-only)
#   keystore -- idempotency keys the provider has already honored
#   ledger   -- the real side effect (money actually moved)
# ===========================================================================
def new_world():
    return {"journal": [], "keystore": {}, "ledger": {}}


def append(world, etype, data):
    seq = len(world["journal"])
    event = {"seq": seq, "run_id": RUN_ID, "ts": f"{TS_BASE}{seq:02d}Z",
             "type": etype, "data": data}
    world["journal"].append(event)
    return event


def replay(journal):
    """Fold the log into state: which step indices completed, their recorded
    results, and whether the run already finished. This is the ONLY source of
    truth on resume; we never trust in-memory variables that died with the crash."""
    completed, results, finished = set(), {}, False
    for e in journal:
        if e["type"] == "tool_result":
            completed.add(e["data"]["idx"])
            results[e["data"]["idx"]] = e["data"]["result"]
        elif e["type"] == "finished":
            finished = True
    return completed, results, finished


def print_journal(world):
    for e in world["journal"]:
        print("    " + json.dumps(e, sort_keys=True))


# ===========================================================================
# Step 2. The tools. search_policy is read-only. process_refund is side-effecting
# and IDEMPOTENT BY KEY: the provider (the keystore) remembers keys it honored, so
# the same key never charges twice, no matter how many times it is replayed.
# ===========================================================================
def exec_search(args):
    return "Refunds after the window are refundable minus a 10% restocking fee.", False


def exec_refund(world, args, idem_key):
    ks = world["keystore"]
    if idem_key in ks:                                # the provider has seen this key
        return ks[idem_key], True                     # return the original; do NOT re-charge
    # The effect: money actually moves. The provider records the key atomically with
    # the charge (modeled here as one step), so the key survives even a crash here.
    world["ledger"][args["order_id"]] = world["ledger"].get(args["order_id"], 0.0) + args["amount"]
    result = f"refunded ${args['amount']:.2f} to {args['order_id']}"
    ks[idem_key] = result
    return result, False


# The plan: (tool, args, idempotency_key). The refund's key is stable across runs.
STEPS = [
    ("search_policy", {"query": "refund policy window"}, None),
    ("process_refund", {"order_id": "ORD-3300", "amount": 180.0}, "ORD-3300:refund:180.00"),
]
FINAL_ANSWER = "Refund of $180.00 for ORD-3300 is complete (processed exactly once)."


# ===========================================================================
# Step 3. The durable run loop. Replay the journal to skip completed steps
# (memoization); execute only the tail. The crash is simulated as a kill AFTER a
# step's effect but BEFORE its tool_result is journaled -- the case memoization
# alone cannot cover.
# ===========================================================================
def run_durable(world, crash_after=None, label="run"):
    if not world["journal"]:
        append(world, "run_started", {"run_id": RUN_ID})
    completed, results, finished = replay(world["journal"])
    if finished:
        print(f"    [{label}] journal shows the run already finished; nothing to do.")
        return results
    for idx, (tool, args, idem) in enumerate(STEPS):
        if idx in completed:                          # MEMOIZED: do not re-run
            print(f"    step {idx} {tool}: memoized from journal -> {results[idx]!r}")
            continue
        append(world, "llm_decided", {"idx": idx, "tool": tool, "args": args})
        if tool == "process_refund":
            result, was_idem = exec_refund(world, args, idem)
        else:
            result, was_idem = exec_search(args)
        if crash_after == idx:                        # *** the kill ***
            print(f"    step {idx} {tool}: effect done (ledger touched, key honored), but")
            print(f"    *** PROCESS KILLED before the result was journaled ***")
            return results
        tag = " (idempotent: key already honored, no second charge)" if was_idem else ""
        append(world, "tool_result", {"idx": idx, "tool": tool, "result": result})
        print(f"    step {idx} {tool}: {result}{tag}")
    append(world, "finished", {"answer": FINAL_ANSWER})
    print(f"    finished -> {FINAL_ANSWER}")
    return results


def run_naive(world):
    """A restart that ignores the journal and idempotency entirely: just do the plan
    again. This is the dangerous recovery: the refund posts a SECOND time."""
    for idx, (tool, args, idem) in enumerate(STEPS):
        if tool == "process_refund":
            world["ledger"][args["order_id"]] = world["ledger"].get(args["order_id"], 0.0) + args["amount"]
            print(f"    step {idx} {tool}: refunded ${args['amount']:.2f} to {args['order_id']} "
                  "(no idempotency check!)")
        else:
            print(f"    step {idx} {tool}: re-ran from scratch")


def ledger_str(world):
    return ", ".join(f"{k}=${v:.2f}" for k, v in world["ledger"].items()) or "(empty)"


# ===========================================================================
# generate() -- the real LLM path (reference shape only). On the real path each
# decision is CACHED into the journal and replayed from there, not re-generated.
# ===========================================================================
def generate(prompt):
    """REAL path: ask a hosted LLM for the next step; cache the decision in the
    journal so replay is faithful. Unused offline."""
    from openai import OpenAI
    client = OpenAI()
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
    )
    return resp.choices[0].message.content


# ===========================================================================
# Demo. Everything below RUNS OFFLINE.
# ===========================================================================
if __name__ == "__main__":
    bar = "=" * 72
    print(bar)
    print("THE DURABLE AGENT  -  event journal, replay, and effectively-once")
    print(bar)
    if os.environ.get("OPENAI_API_KEY"):
        print("[controller] OPENAI_API_KEY set; the real LLM path caches each decision in the "
              "journal and replays it. Falling through to the deterministic plan for reproducibility.")
    else:
        print("[controller] no OPENAI_API_KEY; using the deterministic plan (offline default)")

    # --- 1. A run that crashes mid-refund. ---------------------------------
    print("\n" + "-" * 72)
    print("1) RUN 1 crashes after the refund posts but before it is journaled.")
    print("-" * 72)
    world = new_world()
    run_durable(world, crash_after=1, label="run-1")
    print(f"\n  Journal after the crash (this is what survives on disk):")
    print_journal(world)
    print(f"  Ledger after the crash: {ledger_str(world)}  (the refund DID post)")
    print("  Note: the journal has NO tool_result for step 1, so memoization alone would re-run it.")

    # --- 2. The dangerous recovery: a naive restart. -----------------------
    print("\n" + bar)
    print("2) NAIVE RESTART (ignores the journal and idempotency): double charge.")
    print(bar)
    naive = copy.deepcopy(world)                       # same post-crash world (ledger has 1 refund)
    run_naive(naive)
    print(f"    ledger now: {ledger_str(naive)}  <- DOUBLE REFUND ($360.00). This is the bug.")

    # --- 3. The durable resume: replay + memoization + idempotency key. ----
    print("\n" + bar)
    print("3) DURABLE RESUME (replay the journal; the idempotency key prevents a re-charge).")
    print(bar)
    resumed = copy.deepcopy(world)                     # same post-crash world (ledger has 1 refund)
    run_durable(resumed, crash_after=None, label="resume")
    print(f"\n  Journal after the resume:")
    print_journal(resumed)
    print(f"  Ledger after the resume: {ledger_str(resumed)}  <- still ONE refund. Effectively-once.")

    print("\n" + bar)
    print("Done. Durability is three things working together:")
    print("  - an append-only JOURNAL where state is the FOLD over the log (survives the crash)")
    print("  - deterministic REPLAY with step MEMOIZATION (only the tail re-runs)")
    print("  - IDEMPOTENCY KEYS so a re-run of a side effect returns the original, never doubles")
    print("Memoization handles the easy crash; the idempotency key handles the hard one")
    print("(effect done, result not yet journaled). Part 2's local guard, now effectively-once.")
    print(bar)
