# Part 11 - Shipping It: tracing, cost-per-success, and the core capstone

> This is the last part of the core track. The agent can plan, recover, remember, stop itself, survive a crash, and ask a human. One thing is left before it is shippable: you cannot see into it. A durable agent you cannot observe is undebuggable and unaccountable. When it is slow, you do not know which step; when it is expensive, you do not know which call; when it "works," you cannot prove it worked for the right reasons or at an acceptable cost. The good news is Part 9 already did the hard part: observability is not a second system, it is a second view of the same log.

[📖 Read the essay](https://www.mefby.com/essays/observable-agent) · [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/mftnakrsu/agents-by-hand/blob/main/part-11-observable-agent/observable_agent.ipynb)

## What it covers
- **The cant-see-into-it failure**: the agent from Parts 1 to 10 can plan, recover, remember, throttle itself, survive a crash, and pause for a human, but it is opaque. You cannot tell which step is slow, which call is expensive, or whether a "success" succeeded for the right reasons at an acceptable cost. Durability (Part 9) buys you a complete record of the run; it does not, on its own, make the run debuggable or accountable.
- **A hand-rolled OTel-GenAI-shaped span tree, folded from the journal, no SDK**: the run becomes one root span `invoke_agent` `[0-690ms]` over child spans for each llm decision (operation `chat`) and each `execute_tool` call, as siblings under the root: `llm decide search_policy [0-180ms]`, `execute_tool search_policy [180-240ms]`, `llm decide process_refund [240-450ms]`, `execute_tool process_refund [450-540ms]`, `llm decide finish [540-690ms]`. Each span carries `gen_ai.*`-STYLE attributes (`operation.name`, `request.model`, `tool.name`, `usage` input/output tokens, latency) and is emitted as JSONL. The attribute names are hedged as *-STYLE on purpose: the [OpenTelemetry GenAI semantic conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/) are still evolving. A real OTLP exporter is a commented one-liner, the same swap-in pattern as `generate()`. No otel SDK, so the offline bar holds.
- **Metrics reconstructed from the spans, ending in cost-per-success**: from the same spans we just emitted, not a side channel, we read the trajectory `search_policy -> process_refund` (finish is an llm decision, not a tool), llm calls 3, tokens `in=205 out=47`, cost `$0.00252`, and per-step latency totalling `690ms`. The one number that matters in production is COST PER SUCCESS: a cheap agent that never succeeds is not cheap, and you pay for the failures too. Across 3 runs (refund ORD-3300 `yes $0.00252`, warranty lookup `yes $0.00180`, find a nonexistent discount `no $0.00320` after tripping the Part 8 breaker) total cost is `$0.00752` over 2 successes, so cost-per-success is `$0.00376`, always worse than one happy run's `$0.00252` because the failed run still cost money.
- **One log, two views**: the script prints the same journal as the durability artifact (Part 9) AND as the span tree, to make the point that they are the same bytes read two ways. Observability is a second view of the same log, not a second system bolted on beside it.
- **The Part 1 to 11 capstone**: a checklist of every ring we added to the augmented LLM, from a bare loop with typed tools (1) through robust execution (2), planning over a tool DAG (3), critic and replanning (4), reflection and Reflexion (5), four self-edited memories (6), compaction and forgetting (7), budgets and the circuit breaker (8), the durable journal (9), pause/approve/resume/steer (10), to observability and cost-per-success (11). This is the whole core agent in one frame.
- **The ~60-line backend plus a production-durability tour**: storage for either view is a ~60-line JSONL file or SQLite. For real production durability the prose tours Temporal, DBOS, the Vercel Workflow DevKit, and LangGraph, each with honest limits. The frontier track (Parts 12 to 17) then opens this agent to the protocol wire and multi-agent systems.
- **Two sidebars**: TRANSCRIPT ECONOMICS notices the llm spans' input tokens grow `40 -> 70 -> 95` across the run, the re-sent transcript is the dominant cost lever, and prompt/KV caching is the lever back. CONTROLLER = PROMPT + MODEL (the payoff from Part 1) points out that the llm span's `request.model` and token usage are exactly where model choice and thinking budget show up in the bill.

## Files
- **`observable_agent.py`** — the single runnable script: the `PRICE_PER_TOKEN` from Part 8, the frozen Part 9/10 `JOURNAL` for the `run-bb11` refund run annotated with the timings and growing token counts a span needs, `build_spans` folding each `llm_decided` into an `llm` (chat) span and each `tool_result` into an `execute_tool` span under one `invoke_agent` root, `print_span_tree` and the JSONL emit (what a real OTLP exporter would ship), `metrics_from_spans` reconstructing trajectory / llm calls / tokens / cost / latency from those same spans, the cost-per-success table over three runs, the Part 1 to 11 capstone checklist, the real-LLM `generate()` they stand in for, and the offline demo that prints one log as two views.
- **`observable_agent.ipynb`** — step-by-step notebook: a markdown why before each small code step, built cell by cell.

## Run it
```bash
# from the repo root; no dependencies, no API key, no network
python3 part-11-observable-agent/observable_agent.py   # runs offline
# optional: set OPENAI_API_KEY to see the real-LLM banner; it still falls through to the frozen journal
```
Prefer it step by step? Open `observable_agent.ipynb` in Jupyter, or click **Open in Colab** above.

## Key idea
Observability is not a second system. The Part 9 event journal is already a complete record of the run, so observability is a SECOND VIEW of the same log. Fold the journal into an OTel-GenAI-shaped span tree: one root `invoke_agent` span over an `llm` (chat) span for each decision and an `execute_tool` span for each call, each carrying `gen_ai.*`-STYLE attributes, emitted as JSONL. No otel SDK:

```
  invoke_agent  [0-690ms]  in=205 out=47 $0.00252
  ├─ llm           [0-180ms]  decide search_policy  in=40 out=12
  ├─ execute_tool  [180-240ms]  search_policy
  ├─ llm           [240-450ms]  decide process_refund  in=70 out=15
  ├─ execute_tool  [450-540ms]  process_refund
  └─ llm           [540-690ms]  decide finish  in=95 out=20
```

Then read the metrics back off those spans, ending in the one number production cares about. A cheap agent that never succeeds is not cheap, because you pay for the failures too:

```
  total cost across 3 runs: $0.00752; successes: 2
  COST PER SUCCESS: $0.00376  (worse than one happy run's $0.00252: the failed run still cost money)
```

Shipping a core agent is four things made visible from one log: a span tree folded from the durable journal (no new system), metrics reconstructed from those same spans, cost-per-success as the number that says whether shipping it was worth it, and a capstone showing every ring from Parts 1 to 11. It does not re-teach the loop; it reads the durable journal as the trace that makes the agent debuggable and accountable.

## Offline by design
The whole demo runs with no network and no API key. It REUSES Part 9's journal (referenced, not rebuilt): the `run_id` is fixed (`run-bb11`), the timings and token counts are frozen by sequence number, and the spans are derived deterministically, so the journal is byte-reproducible and the same output prints every run. The cost numbers use the illustrative `PRICE_PER_TOKEN` from Part 8. The span attributes are hedged as `gen_ai.*`-STYLE because the OpenTelemetry GenAI semantic conventions are still evolving; a real OTLP exporter sits behind a commented one-liner, exactly like the real-LLM path. Set `OPENAI_API_KEY` and the demo prints a banner, then falls through to the frozen journal so output stays reproducible. Only `generate()` (and that exporter) would need edits to light up production.

---
[Series index](../) · [Part 12 — the frontier track begins →](../) (coming soon, frontier track begins)
