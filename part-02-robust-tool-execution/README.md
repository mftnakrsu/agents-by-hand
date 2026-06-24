# Part 2 — When Tools Fail: retries, timeouts, and a failure taxonomy

> Part 1 gave every tool a typed contract that rejects a call that is wrong on paper; this part wraps the call that is right on paper and still throws, times out, or returns garbage at run time.

[📖 Read the essay](https://www.mefby.com/essays/robust-tool-execution) · [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/mftnakrsu/agents-by-hand/blob/main/part-02-robust-tool-execution/robust_execution.ipynb)

## What it covers
- **The failure taxonomy**: five kinds of failure, one recovery policy each. `transient` (temporary; might succeed if tried again) -> RETRY, bounded with backoff; `permanent` (will never succeed; a retry only wastes) -> FEED BACK to the model; `empty-result` (the call worked but found nothing useful) -> FEED BACK; `malformed` (arguments fail the Part 1 schema) -> FEED BACK; `unknown-tool` (not in the Part 1 action space) -> FEED BACK. "Feed back" means turning the failure into an Observation the controller reads and reasons about, not a crash.
- **Retries, backoff, and a timeout**: a robustness layer (`execute_tool`) that runs every call under a deadline and retries ONLY transient failures, bounded by a retry cap with exponential backoff. The taxonomy is what tells a transient apart from a permanent error, so a permanent failure is fed straight back instead of burning time and money on retries that cannot help.
- **Error as observation**: P19's ReAct loop and Part 1 both assumed every tool SUCCEEDS, so one throw was a stack trace and one empty result silently poisoned the answer. Here a schema-valid call that still fails returns a `ToolOutcome` the loop can read, and the loop survives a bad tool call the way it survives a good one.
- **The first side-effecting tool + idempotency guard**: `process_refund()` moves money, so it cannot be retried for free. If the refund posts and the confirmation then times out, a blind retry refunds the customer twice. An idempotency guard keyed by `order_id` records the effect before the failure point, so the retry sees it and skips re-acting. A `process_refund_unsafe` twin runs side by side to show the double-charge a missing guard produces. This is a local in-memory guard; Part 9 hardens it into durable idempotency keys that survive a process crash (seed vs harden).
- **Continuity with RAG and Part 1**: the same support-bot world (refund policy, the E-4042 error, the Acme to Globex chain) and the same deterministic-by-default runtime. The four read-only tools carry over from Part 1; the new material is the robustness layer and the side-effecting refund.

## Files
- **`robust_execution.py`** — the single runnable script: the taxonomy as exception types (`TransientError`, `ToolTimeout`, `PermanentError`), the Part 1 tools plus the side-effecting `process_refund` with its idempotency guard, fault-injection tools that drive each taxonomy branch, the `execute_tool` robustness layer (validate, deadline, classify, retry-with-backoff), the real-LLM controller shape behind generate() / build_prompt(), the deterministic controller, the robust agent loop, and worked runs: one fault-injection scenario per branch, the guarded-vs-unguarded refund side by side, and a naive baseline that dies on the first transient blip next to a robust loop that recovers.
- **`robust_execution.ipynb`** — step-by-step notebook: a markdown why before each small code step, built cell by cell.

## Run it
```bash
# from the repo root; no dependencies, no API key, no network
python3 part-02-robust-tool-execution/robust_execution.py           # runs offline
# optional: set OPENAI_API_KEY to see the real LLM-driven controller banner
```
Prefer it step by step? Open `robust_execution.ipynb` in Jupyter, or click **Open in Colab** above.

## Key idea
A schema-valid call can still fail at run time, so the layer between the loop and its tools has to expect failure. It classifies every outcome into the taxonomy, retries ONLY transients (bounded, with exponential backoff, under a per-call deadline), and feeds everything else back as an Observation rather than crashing. Side-effecting tools get one more guarantee: a retry must never act twice, so the refund is recorded keyed by `order_id` before the point where it can fail, and the retry hits the guard and returns the first result instead of refunding again. In the worked run the refund's first attempt times out after posting, the retry hits the guard, and the run finishes with exactly one refund on the ledger. This lineage traces to the standard reliability playbook: bounded retries with exponential backoff and a timeout (deadline) per call, and idempotency keys for side-effecting operations so a retry is effectively-once. Part 9 hardens the in-memory guard into durable idempotency keys that survive a process crash.

## Offline by design
The whole demo runs with no network and no API key. A deterministic rule-based controller stands in for a trained LLM router, every Thought/Action it picks is a rule you can read, and the failures are injected deterministically: the backoff delay is printed but never actually slept, a "timeout" is read from a simulated latency rather than wall-clock, and `flaky_lookup` clears on a fixed attempt, so output is reproducible. The real paths sit behind a flag: set OPENAI_API_KEY and generate() prints a banner noting the real controller would drive the loop (it still falls through to the rule policy). Real code would `time.sleep` the backoff with jitter and run the call in a thread or process it can cancel at the deadline; only generate() and those two helpers change to light up production. The taxonomy branches taken, the retries, the idempotent skip, and every Thought/Action/Observation/Finish line are identical either way.

---
[Series index](../) · [Part 3 — Planning and Decomposition →](../) (coming soon)
