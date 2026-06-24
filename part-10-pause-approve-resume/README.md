# Part 10 - Pause, Approve, Resume, Steer: human-in-the-loop

> Part 9's durable agent survives a crash, but it still runs start to finish on its own. Some actions must WAIT for a human: a $180 refund over the $100 threshold should not fire until someone approves it. And a person watching the run may want to CORRECT it mid-flight, not just approve or deny. The agent needs a way to stop, hand control to a human, and come back later, in a different process.

[📖 Read the essay](https://www.mefby.com/essays/pause-approve-resume) · [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/mftnakrsu/agents-by-hand/blob/main/part-10-pause-approve-resume/pause_approve_resume.ipynb)

## What it covers
- **The cant-stop-and-come-back failure**: the durable agent runs to completion on its own, with no way to halt at a sensitive action and wait for a human. A refund of $180.00 for ORD-3300 is over the $100 threshold, so it must not fire until someone approves it, yet the loop has no place to pause. Crash-safety (Part 9) is not the same as the ability to stop, hand off, and resume.
- **`interrupt()` raising a serializable `PendingApproval`, caught at the top level, NOT `sys.exit`**: at a gated action the agent does not call the tool. It journals a `pending_approval` event with a token (`appr-1`) and RAISES a `PendingApproval` carrying the token + the pending action. The top level catches it, persists the journal, and returns the token. The run is PAUSED, not dead, and a notebook or server stays runnable, because nothing called `sys.exit`. The ledger is still empty: no money has moved.
- **`resume(run_id, decision)` replaying the journal + acting on the decision effectively-once**: later a human decides. `resume` rehydrates the run by replaying the journal (Part 9), records an `approval_decision` event, and re-enters the loop. Step 0's policy lookup is memoized straight from the journal; only the gated step is acted on. Because the refund keeps its idempotency key, an APPROVED resume executes EXACTLY ONCE even if `resume` is retried, ending `refunded $180.00 to ORD-3300` with ledger `{'ORD-3300': 180.0}`.
- **STEER as a first-class action, beyond approve/deny**: the human decision is not a binary gate. An approver can APPROVE, DENY, or STEER, injecting a correction that changes what the agent does next. DENY journals `DENIED by approver -> no money moved` and the ledger stays empty. STEER lowers the refund to $90.00, now under the threshold, so the agent prints the correction and then `refunded $90.00 to ORD-3300`, ledger `{'ORD-3300': 90.0}`. Answering a clarifying question back to the user is the same mechanism.
- **Streaming progress from journal events**: because every step is a journal event, a live progress feed is just a read over the same log. The pause stream shows `run started`, `done` (the policy), and `PAUSED for approval (... token appr-1)`. The STEER timeline streams the full arc: run started, done (search), PAUSED, `human decision: steer`, done (refund $90), and finished.
- **The cross-process, two-invocation model**: a real deployment pauses in one process (the request that hit the gate returns the token) and resumes in another (a later request, or a CLI re-invocation, calls `resume` on the same journal). This file models both phases in one script by catching `PendingApproval` then calling `resume` on the persisted world; the CLI two-process version is the same journal read by a second invocation.

## Files
- **`pause_approve_resume.py`** — the single runnable script: the Part 9 `journal` (with `append`/`replay` where state is the fold over the log) and the `world` bundling `journal`/`keystore`/`ledger`, the serializable `PendingApproval` exception, the read-only `exec_search` and the idempotent `exec_refund`, the `STEPS` plan with the gated refund's stable key, the `run` loop that journals `pending_approval` and RAISES at the gate (or acts on approve/deny/steer when a decision exists), `resume` recording the decision and re-entering the loop, `stream` reading progress off the journal, the real-LLM `generate()` they stand in for, and the demos (pause, then APPROVE / DENY / STEER resumes).
- **`pause_approve_resume.ipynb`** — step-by-step notebook: a markdown why before each small code step, built cell by cell.

## Run it
```bash
# from the repo root; no dependencies, no API key, no network
python3 part-10-pause-approve-resume/pause_approve_resume.py   # runs offline
# optional: set OPENAI_API_KEY to see the real-LLM banner; it still falls through to the deterministic plan
```
Prefer it step by step? Open `pause_approve_resume.ipynb` in Jupyter, or click **Open in Colab** above.

## Key idea
Some actions are too sensitive to run unattended, so the agent must be able to PAUSE at a gate and come back. At the gated step the loop journals a `pending_approval` event with a token and RAISES a serializable `PendingApproval`, caught at the top level, never `sys.exit`. The exception carries the token and the pending action, so the caller persists the journal and returns the token. The run is paused, not dead, and no money has moved:

```
    step 0 search_policy: Refunds after the window are refundable minus a 10% restocking fee.
    PAUSED: refund $180.00 exceeds the $100 threshold
    returned token 'appr-1'; the run is persisted, not dead. Ledger so far: (empty, no money moved yet)
```

Later a human decides, and `resume` replays the journal (step 0 memoized) and acts on the decision. The decision is a first-class action, not a yes/no gate. STEER injects a correction that lowers the refund under the threshold, and the gated step proceeds with the corrected amount:

```
    step 1 process_refund: STEERED by approver -> amount lowered to $90.00 (now under the $100 threshold)
    step 1 process_refund: refunded $90.00 to ORD-3300
    finished -> Refund of $90.00 for ORD-3300 is complete.
    ledger: {'ORD-3300': 90.0}
```

Human-in-the-loop is four things working together: an `interrupt()` that raises a serializable `PendingApproval` token (NOT `sys.exit`) so the run pauses without dying, a `resume()` that replays the journal and acts on the decision effectively-once, a decision that is a first-class action (APPROVE, DENY, or STEER a correction), and progress that streams from the same journal events that make the agent durable. It does not re-teach the loop or the tool contract; it adds the control-handoff layer on top of Part 9.

## Offline by design
The whole demo runs with no network and no API key. It REUSES Part 9's journal + idempotency key (referenced, not rebuilt): the plan is deterministic, the `run_id` is fixed (`run-aa10`), and timestamps are frozen by sequence number, so the journal is byte-reproducible and the same output prints every run. The keystore models the payment provider's own idempotency, which is what makes the approved-resume "effectively-once" guarantee real. "Cross-process resume" here means catch `PendingApproval`, persist, then call `resume` on the same journal; the genuine two-process version is the same journal read by a second CLI invocation. The real LLM path sits behind a flag: set `OPENAI_API_KEY` and the demo prints a banner, then falls through to the deterministic plan so output stays reproducible. Only `generate()` would need edits to light up production.

---
[Series index](../) · [Part 11 — Spans and Traces →](../) (coming soon)
