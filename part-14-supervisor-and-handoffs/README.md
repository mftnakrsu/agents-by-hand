# Part 14 - The Supervisor and the Handoff: multi-agent, and when it hurts

> So far there has been one agent with one context window. That is a real limit. A breadth-first task with independent parts cannot be parallelized inside one context, and a task that should really be handled by a specialist is awkward to cram into a generalist's loop. The fix is to use MORE THAN ONE agent. The fix is also a trap: multi-agent systems are more expensive, harder to debug, and frequently OVERKILL. This part builds the two main multi-agent shapes (orchestrator-worker and handoff-as-a-tool) and, just as importantly, the honest economics of when NOT to reach for them.

[📖 Read the essay](https://www.mefby.com/essays/supervisor-and-handoffs) · [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/mftnakrsu/agents-by-hand/blob/main/part-14-supervisor-and-handoffs/supervisor_and_handoffs.ipynb)

## What it covers
- **The one-context limit, and why one more agent is the move**: every part from 1 to 13 had ONE agent with ONE context window. That cannot parallelize breadth-first work with independent parts, and it is overkill when the right move is to hand off to a specialist. The answer is more than one agent, in two shapes: the supervisor and the handoff. Both are a trap if reached for by default, so this part also builds the honest economics of when NOT to.
- **Orchestrator-worker (the supervisor): decompose, fan out, synthesize**: a lead agent DECOMPOSES the briefing into 3 TYPED BRIEFS (objective, output format, tool guidance, boundaries), spawns N WORKERS each in its OWN isolated context (14 tokens each), and SYNTHESIZES. Worker w1 (refund policy) posts `Refunds within 30 days; a 10% restocking fee applies after the window.`; w2 (warranty) posts `The Globex earbuds carry a 2-year limited warranty.`; w3 (shipping) posts `Standard shipping is 3 to 5 business days; express is next business day.` Workers coordinate through a shared append-only BLACKBOARD, then the supervisor stitches the three into one briefing. The worker is the Part 1 agent reused as a BLACK BOX; the ReAct loop is never rebuilt.
- **Handoff as a tool call, and its two failure modes**: sometimes the move is not to fan out but to TRANSFER CONTROL to a specialist, carrying the live trace. `handoff(to=...)` is a tool like any other. Clean (3/3 trace, role clear) -> `[done] billing-specialist refunded order ORD-3300 using the carried trace.` TRUNCATION (trace cut to the last entry, the order id was earlier, 1/3 trace) -> `[failed] billing-specialist cannot act: the order id was truncated out of the carried trace.` ROLE CONFUSION (3/3 trace but role UNCLEAR) -> `[stalled] billing-specialist and the lead both wait: the brief never said who owns the task.`
- **The single-vs-supervisor-vs-debate economics, with debate regressing**: on one task, single = 4 LLM calls / 300 tokens / 3/3; supervisor = 5 / 220 / 3/3; debate = 7 / 320 / 2/3. A proposer-critic DEBATE shows the uncomfortable truth that more rounds is NOT more quality: proposer 2/3, round 1 3/3, round 2 3/3, round 3 2/3 (REGRESSED). Single is fewest calls but ONE growing context; supervisor is more calls but ISOLATED small contexts that parallelize; debate is the most expensive AND non-monotonic.
- **The honesty that parallelism is sequential-in-default**: the offline default runs workers SEQUENTIALLY. We never print a fabricated wall-clock speedup. What multi-agent buys is reported as (a) LLM-CALL COUNT and (b) TOKEN ISOLATION: each worker sees only its own small brief, not one ever-growing shared transcript. With real concurrency the independent workers run in ONE round (depth 1, the Part 3 idea).
- **Reused, not rebuilt**: the worker is the Part 1 agent as a black box (no ReAct re-derivation), and a runaway supervisor (workers spawning workers) is stopped by Part 8's circuit breaker, reused not rebuilt. These distributed runs render as the Part 11 span tree (forward-ref).

## Files
- **`supervisor_and_handoffs.py`** — the single runnable script: the support world (refunds, the earbuds warranty, shipping) and its two tools, the `Blackboard` (append-only) plus the black-box `worker` and the `supervisor_run` that decomposes into 3 typed briefs / fans out to isolated contexts / synthesizes, the `handoff` tool with its clean / truncation / role-confusion paths, and the economics (`single_agent` with one growing context, `supervisor_econ` with isolated small contexts, `debate_econ` whose round 3 regresses), all wired into the four-act demo. The real-LLM lead/worker/critic backend sits one flag away behind `generate()`.
- **`supervisor_and_handoffs.ipynb`** — step-by-step notebook: a markdown why before each small code step, built cell by cell.

## Run it
```bash
# from the repo root; no dependencies, no API key, no network
python3 part-14-supervisor-and-handoffs/supervisor_and_handoffs.py   # runs offline
```
Prefer it step by step? Open `supervisor_and_handoffs.ipynb` in Jupyter, or click **Open in Colab** above.

## Key idea
One agent with one context window cannot parallelize breadth-first work and is overkill when the move is to hand off to a specialist. Multi-agent fixes both, in two shapes: the SUPERVISOR decomposes a task into typed briefs, fans out to workers each in an isolated context, and synthesizes a blackboard; the HANDOFF transfers control AND the live trace to a specialist. But multi-agent is a tool, not a default, and the economics say so:

```
  strategy        LLM calls   tokens  quality
  -----------------------------------------
  single                  4      300      3/3   (one GROWING context)
  supervisor              5      220      3/3   (ISOLATED small contexts, parallelizable)
  debate                  7      320      2/3   (most expensive AND non-monotonic)

  debate by round: proposer 2/3, round 1 3/3, round 2 3/3, round 3 2/3  <- regressed
```

Parallelism here is SEQUENTIAL by default: we report call count and token isolation, never a fabricated wall-clock. With real concurrency the independent workers run in ONE round (depth 1, Part 3); a runaway supervisor is stopped by Part 8's circuit breaker, reused not rebuilt. Reach for multi-agent when the work is BROAD; a single agent is the right, cheaper tool for a small sequential task.

## Offline by design
The whole demo runs with no network, no API key, and no dependencies. The deterministic default is the lead and the workers: the supervisor decomposes into three fixed typed briefs, each worker runs its one tool in a context that is JUST its brief, and the synthesis is a join over the blackboard, so the same output prints every run. The economics are computed, not timed: single accumulates one growing transcript, supervisor sums small isolated worker contexts, and debate grows fast while round 3 regresses, so we report LLM-call count and token isolation, never a wall-clock speedup that sequential execution could not honestly claim. Set `OPENAI_API_KEY` and a real LLM would be the lead / worker / critic, but the demo falls through to the deterministic logic for reproducibility. Only `generate()` would need edits to light up the real path.

---
[Series index](../) · [Part 15 — Evaluating agents: trajectory and outcome (coming soon, frontier track) →](../)
