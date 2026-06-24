# Part 9 - The Durable Agent: event journal, replay, and effectively-once

> Everything so far lived in one fragile process. Pull the plug mid-run and every observation, every decision, the half-finished refund is gone. Worse, the obvious recovery is the dangerous one: just run the task again, and if the refund already posted, a naive rerun posts it a second time. The agent has to survive a crash AND survive its own recovery.

[📖 Read the essay](https://www.mefby.com/essays/durable-agent) · [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/mftnakrsu/agents-by-hand/blob/main/part-09-durable-agent/durable_agent.ipynb)

## What it covers
- **The fragile-process + dangerous-recovery failure**: the whole agent state lived in memory, so a crash mid-run loses it all, including the half-finished refund. The natural fix, rerun the task, is exactly the wrong one: if the refund already posted to ORD-3300 before the crash, a naive restart posts it AGAIN, taking the ledger from $180.00 to $360.00 (a double refund). Crash-safety and recovery-safety are the same problem.
- **The append-only event journal where state is the fold over the log**: every step writes an event (`run_started`, `llm_decided`, `tool_result`, `finished`) to a log keyed by a fixed `run_id` with frozen timestamps. The log is the source of truth, and STATE IS THE FOLD OVER THE LOG: to know what happened you replay the events, you never trust in-memory variables that died with the crash. Kept in a list and printed as JSONL here; a real system appends to a JSONL file or SQLite so it survives the process.
- **Deterministic replay with step memoization**: on resume, fold the journal to see which steps already finished, and return their recorded results WITHOUT re-running them. Only the tail after the crash actually executes again. In the worked run, step 0's policy lookup is memoized straight from the journal; only step 1 is re-attempted.
- **Idempotency keys for effectively-once**: side-effecting tools carry a stable key (`ORD-3300:refund:180.00`). The provider (a durable keystore) remembers keys it has already honored, so a repeat of the same key returns the original result instead of charging again. That is EFFECTIVELY-ONCE across a replay: the durable resume re-attempts the refund but reports `idempotent: key already honored, no second charge`, and the ledger stays at $180.00.
- **The hard-crash case memoization alone cannot cover**: the crash is deliberately placed at the worst spot, AFTER the refund effect and keystore write but BEFORE the `tool_result` is journaled. The journal then has NO result for that step, so memoization would re-run it. Only the idempotency KEY saves the day, because the provider already remembers the key. Memoization handles the easy crash; the key handles the hard one.
- **Hardening Part 2's local guard**: Part 2 gave the refund tool a LOCAL idempotency guard, an in-memory dict that stops a retry inside one run from double-acting. That dict dies with the process. This part makes the same guarantee durable, so it holds across a crash and a separate recovery run (seed vs harden), building on Part 8's limits theme.
- **The journal is reused later**: the append-only event journal built here is REUSED by **Part 10** (pause and resume) and **Part 11** (spans). We build it carefully because later parts depend on it.

## Files
- **`durable_agent.py`** — the single runnable script: the `world` bundling the three durable artifacts (`journal`, `keystore`, `ledger`), `append`/`replay`/`print_journal` (replay is the fold over the log), the read-only `search_policy` and the side-effecting `process_refund` that is idempotent by key, the `STEPS` plan with the refund's stable key, the durable `run_durable` loop with its crash injection (kill after the effect, before the `tool_result`) and step memoization, the dangerous `run_naive` restart, the real-LLM `generate()` they stand in for, and the three demos (crash, naive double-charge, durable resume).
- **`durable_agent.ipynb`** — step-by-step notebook: a markdown why before each small code step, built cell by cell.

## Run it
```bash
# from the repo root; no dependencies, no API key, no network
python3 part-09-durable-agent/durable_agent.py          # runs offline
# optional: set OPENAI_API_KEY to see the real-LLM banner (the real path caches each decision in the journal and replays it; still falls through to the deterministic plan)
```
Prefer it step by step? Open `durable_agent.ipynb` in Jupyter, or click **Open in Colab** above.

## Key idea
A process can die at any instant, so the agent's state cannot live only in memory: it lives in an append-only JOURNAL, and the current state is the FOLD over that log. On resume you replay the journal, memoize the steps that already finished, and execute only the tail. That alone covers the easy crash, but not the worst one: the refund POSTS and the provider records it, then the process dies BEFORE the `tool_result` is journaled, so the journal has no result and memoization would re-run the charge. The fix is an idempotency KEY: the side effect carries a stable key, the provider (a durable keystore) remembers keys it has honored, and a repeat returns the original result instead of charging again.

With no journal and no key, the dangerous recovery doubles the charge:

```
    step 1 process_refund: refunded $180.00 to ORD-3300 (no idempotency check!)
    ledger now: ORD-3300=$360.00  <- DOUBLE REFUND ($360.00). This is the bug.
```

Replay the journal and the idempotency key holds the line: step 0 is memoized, step 1 is re-attempted but recognized, and the ledger stays at one refund:

```
    step 0 search_policy: memoized from journal -> 'Refunds after the window are refundable minus a 10% restocking fee.'
    step 1 process_refund: refunded $180.00 to ORD-3300 (idempotent: key already honored, no second charge)
    finished -> Refund of $180.00 for ORD-3300 is complete (processed exactly once).
  Ledger after the resume: ORD-3300=$180.00  <- still ONE refund. Effectively-once.
```

Durability is three things working together: an append-only JOURNAL where state is the FOLD over the log (survives the crash), deterministic REPLAY with step MEMOIZATION (only the tail re-runs), and IDEMPOTENCY KEYS so a re-run of a side effect returns the original, never doubles. This is an orthogonal durability layer the always-in-memory agents had no need for; it does not re-teach the loop or the tool contract, it makes them crash-safe. It hardens Part 2's local guard into effectively-once and builds on Part 8's limits theme.

## Offline by design
The whole demo runs with no network and no API key. The plan is deterministic, the `run_id` is fixed (`run-7f3a`), and timestamps are frozen by sequence number, so the journal is byte-reproducible and the same JSONL prints every run. One honesty note on scope: that byte-for-byte reproducibility holds ONLY on the deterministic path. With a real LLM you CACHE each decision into the journal and replay the cached decision rather than re-generating it (best-effort, not byte identical), which is why the re-decided step shows two `llm_decided` events for the same index: the decision is re-made on resume, the EFFECT is not. "Cross-process resume" here means rerun the same script on the same journal, not true inter-process messaging, and the keystore models the payment provider's own idempotency, which is what makes the guarantee real in practice. The real path sits behind a flag: set OPENAI_API_KEY and the demo prints a banner, then falls through to the deterministic plan so output stays reproducible. Only `generate()` would need edits to light up production.

---
[Series index](../) · [Part 10 — Pause and Resume →](../) (coming soon)
