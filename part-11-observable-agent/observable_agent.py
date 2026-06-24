"""
Shipping It: tracing, cost-per-success, and the core capstone.
Agents from First Principles, Part 11.

This is the last part of the core track. The agent can plan, recover, remember,
stop itself, survive a crash, and ask a human. There is one thing left before it is
shippable: you cannot see into it. A durable agent you cannot observe is
undebuggable and unaccountable. When it is slow, you do not know which step. When
it is expensive, you do not know which call. When it "works," you cannot prove it
worked for the right reasons or at an acceptable cost.

The good news is that Part 9 already did the hard part. The event journal is a
complete record of the run. Observability is not a second system; it is a SECOND
VIEW of the same log. This part folds the journal into spans.

1. A SPAN TREE, OTel-GenAI-shaped, by hand (no otel SDK). The run becomes one root
   span invoke_agent, with child spans for each llm decision (operation chat) and
   each execute_tool call. Each span carries gen_ai.*-STYLE attributes:
   operation.name, request.model, tool.name, usage input/output tokens, and latency.
   We emit them as JSONL. (Attribute names are hedged as *-STYLE on purpose: the
   GenAI semantic conventions are still moving. A real OTLP exporter is a commented
   one-liner, the same swap-in pattern as generate().)

2. METRICS RECONSTRUCTED FROM THE SPANS: the trajectory (the tool sequence), total
   tokens and cost, per-step latency, and the one number that matters in production,
   COST PER SUCCESS. A cheap agent that never succeeds is not cheap. You pay for the
   failures too, so cost-per-success = total cost across all runs / number of
   successes, and it is always worse than the cost of a single happy run.

3. ONE LOG, TWO VIEWS. We print the same journal as the durability artifact (Part 9)
   AND as the span tree, to make the point that they are the same bytes read two
   ways. A ~60-line file or SQLite backend is all the storage either view needs; for
   real production durability the prose tours Temporal, DBOS, the Vercel Workflow
   DevKit, and LangGraph, each with honest limits.

4. THE CAPSTONE. A Part 1 to Part 11 checklist: every ring we added to the augmented
   LLM, from a bare loop to a production-shaped core agent.

[sidebar] TRANSCRIPT ECONOMICS: notice the llm spans' input tokens grow 40 -> 70 ->
95 across the run. The agent re-sends a growing transcript every step; that growth,
not the tool calls, is the dominant cost lever (prompt/KV caching is the lever back).
[sidebar] CONTROLLER = PROMPT + MODEL (payoff from Part 1): the llm span's
request.model and token usage are exactly where model choice and thinking budget
show up in the bill.

CONTINUITY: the refund world; the Part 9/10 journal; frozen timings and token counts
so the spans are reproducible.

Run:
  python3 observable_agent.py        # offline; no API key, no network, no deps

NOTE: SDK names and model ids move fast; only generate() (and a real OTLP exporter)
would need edits.

Expected output (deterministic default path):
========================================================================
SHIPPING IT  -  tracing, cost-per-success, and the core capstone
========================================================================
[trace] no OPENAI_API_KEY; folding the frozen journal into spans (offline default)

------------------------------------------------------------------------
ONE LOG, TWO VIEWS. The Part 9 journal (durability)...
------------------------------------------------------------------------
    {"data": {"goal": "refund ORD-3300", "run_id": "run-bb11"}, "seq": 0, "type": "run_started"}
    {"data": {"in": 40, "ms": 180, "out": 12, "tool": "search_policy"}, "seq": 1, "type": "llm_decided"}
    {"data": {"ms": 60, "result": "refunds after the window: 10% restocking fee", "tool": "search_policy"}, "seq": 2, "type": "tool_result"}
    {"data": {"in": 70, "ms": 210, "out": 15, "tool": "process_refund"}, "seq": 3, "type": "llm_decided"}
    {"data": {"ms": 90, "result": "refunded $180.00 to ORD-3300", "tool": "process_refund"}, "seq": 4, "type": "tool_result"}
    {"data": {"in": 95, "ms": 150, "out": 20, "tool": "finish"}, "seq": 5, "type": "llm_decided"}
    {"data": {"answer": "Refund of $180.00 for ORD-3300 is complete."}, "seq": 6, "type": "finished"}

------------------------------------------------------------------------
...folded into an OTel-GenAI-shaped span tree (observability). No otel SDK.
------------------------------------------------------------------------
  invoke_agent  [0-690ms]  in=205 out=47 $0.00252
  ├─ llm           [0-180ms]  decide search_policy  in=40 out=12
  ├─ execute_tool  [180-240ms]  search_policy
  ├─ llm           [240-450ms]  decide process_refund  in=70 out=15
  ├─ execute_tool  [450-540ms]  process_refund
  └─ llm           [540-690ms]  decide finish  in=95 out=20

  The same spans as JSONL (what a real OTLP exporter would ship):
    {"attributes": {"gen_ai.cost_usd": 0.00252, "gen_ai.operation.name": "invoke_agent", "gen_ai.usage.input_tokens": 205, "gen_ai.usage.output_tokens": 47}, "end_ms": 690, "name": "invoke_agent", "parent_id": null, "span_id": "s0", "start_ms": 0}
    {"attributes": {"decided.tool": "search_policy", "gen_ai.operation.name": "chat", "gen_ai.request.model": "deterministic-rule-controller", "gen_ai.usage.input_tokens": 40, "gen_ai.usage.output_tokens": 12}, "end_ms": 180, "name": "llm", "parent_id": "s0", "span_id": "s1", "start_ms": 0}
    {"attributes": {"gen_ai.operation.name": "execute_tool", "gen_ai.tool.name": "search_policy"}, "end_ms": 240, "name": "execute_tool", "parent_id": "s0", "span_id": "s2", "start_ms": 180}
    {"attributes": {"decided.tool": "process_refund", "gen_ai.operation.name": "chat", "gen_ai.request.model": "deterministic-rule-controller", "gen_ai.usage.input_tokens": 70, "gen_ai.usage.output_tokens": 15}, "end_ms": 450, "name": "llm", "parent_id": "s0", "span_id": "s3", "start_ms": 240}
    {"attributes": {"gen_ai.operation.name": "execute_tool", "gen_ai.tool.name": "process_refund"}, "end_ms": 540, "name": "execute_tool", "parent_id": "s0", "span_id": "s4", "start_ms": 450}
    {"attributes": {"decided.tool": "finish", "gen_ai.operation.name": "chat", "gen_ai.request.model": "deterministic-rule-controller", "gen_ai.usage.input_tokens": 95, "gen_ai.usage.output_tokens": 20}, "end_ms": 690, "name": "llm", "parent_id": "s0", "span_id": "s5", "start_ms": 540}

========================================================================
METRICS reconstructed from the spans
========================================================================
  trajectory   : search_policy -> process_refund
  llm calls    : 3
  tokens       : in=205 out=47 (input grew 40 -> 70 -> 95: the re-sent transcript is the dominant cost)
  cost         : $0.00252
  latency      : 690ms (sum of per-span latencies)

========================================================================
COST PER SUCCESS  (you pay for the failures too)
========================================================================
  task                            success        cost
  -------------------------------------------------
  refund ORD-3300                     yes    $0.00252
  warranty lookup                     yes    $0.00180
  find a nonexistent discount          no    $0.00320
  -------------------------------------------------
  total cost across 3 runs: $0.00752; successes: 2
  COST PER SUCCESS: $0.00376  (worse than one happy run's $0.00252: the failed run still cost money)

========================================================================
THE CORE CAPSTONE  -  every ring we added to the augmented LLM, Parts 1 to 11
========================================================================
    1  augmented-LLM loop with typed, validated tools
    2  robust execution: failure taxonomy, retries, idempotency (seed)
    3  planning: plan-and-execute / ReWOO / tool DAG (LLM-call + depth accounting)
    4  critic + error-triggered replanning over the DAG
    5  reflection + cross-trial Reflexion
    6  four typed memories the agent edits itself
    7  compaction + forgetting for the long haul
    8  budgets + loop detector + circuit breaker
    9  durable event journal + replay + effectively-once
    10 pause / approve / resume / steer (human-in-the-loop)
    11 observability: spans, cost-per-success  <- you are here

  Storage is ~60 lines (a JSONL file or SQLite). For production durability the
  essay tours Temporal, DBOS, the Vercel Workflow DevKit, and LangGraph, with
  honest limits. The frontier track (Parts 12 to 17) opens this agent to the
  protocol wire and multi-agent systems.

========================================================================
Done. Observability is not a second system: the journal that makes the agent
durable, read as spans, makes it debuggable and accountable. Cost-per-success is
the number that tells you whether shipping it was worth it.
========================================================================
"""

import json
import os


PRICE_PER_TOKEN = 0.00001                  # illustrative, from Part 8


# ===========================================================================
# Step 1. A journal for one refund run, carried from Parts 9/10 but annotated with
# the timings and token counts a span needs. Frozen numbers keep the spans
# reproducible. Note the input_tokens GROWING (40 -> 70 -> 95): the transcript the
# agent re-sends every step. (llm decisions carry tokens; tool calls carry latency.)
# ===========================================================================
JOURNAL = [
    {"seq": 0, "type": "run_started", "data": {"run_id": "run-bb11", "goal": "refund ORD-3300"}},
    {"seq": 1, "type": "llm_decided", "data": {"tool": "search_policy", "in": 40, "out": 12, "ms": 180}},
    {"seq": 2, "type": "tool_result", "data": {"tool": "search_policy", "ms": 60,
                                               "result": "refunds after the window: 10% restocking fee"}},
    {"seq": 3, "type": "llm_decided", "data": {"tool": "process_refund", "in": 70, "out": 15, "ms": 210}},
    {"seq": 4, "type": "tool_result", "data": {"tool": "process_refund", "ms": 90,
                                               "result": "refunded $180.00 to ORD-3300"}},
    {"seq": 5, "type": "llm_decided", "data": {"tool": "finish", "in": 95, "out": 20, "ms": 150}},
    {"seq": 6, "type": "finished", "data": {"answer": "Refund of $180.00 for ORD-3300 is complete."}},
]


# ===========================================================================
# Step 2. Fold the journal into an OTel-GenAI-shaped span tree. invoke_agent is the
# root; each llm_decided becomes an llm (chat) span and each tool_result an
# execute_tool span, as siblings under the root. No otel SDK: just dicts we can emit
# as JSONL. A real exporter would be:
#   # from opentelemetry import trace; tracer.start_span("invoke_agent", ...)
# ===========================================================================
def build_spans(journal):
    spans, clock, sid = [], 0, 0

    def new_span(name, attrs, start, end):
        nonlocal sid
        sid += 1
        return {"span_id": f"s{sid}", "parent_id": "s0", "name": name,
                "start_ms": start, "end_ms": end, "attributes": attrs}

    children = []
    for e in journal:
        d = e["data"]
        if e["type"] == "llm_decided":
            attrs = {"gen_ai.operation.name": "chat",
                     "gen_ai.request.model": "deterministic-rule-controller",
                     "gen_ai.usage.input_tokens": d["in"],
                     "gen_ai.usage.output_tokens": d["out"],
                     "decided.tool": d["tool"]}
            children.append(new_span("llm", attrs, clock, clock + d["ms"]))
            clock += d["ms"]
        elif e["type"] == "tool_result":
            attrs = {"gen_ai.operation.name": "execute_tool", "gen_ai.tool.name": d["tool"]}
            children.append(new_span("execute_tool", attrs, clock, clock + d["ms"]))
            clock += d["ms"]

    in_tok = sum(e["data"]["in"] for e in journal if e["type"] == "llm_decided")
    out_tok = sum(e["data"]["out"] for e in journal if e["type"] == "llm_decided")
    root = {"span_id": "s0", "parent_id": None, "name": "invoke_agent",
            "start_ms": 0, "end_ms": clock,
            "attributes": {"gen_ai.operation.name": "invoke_agent",
                           "gen_ai.usage.input_tokens": in_tok,
                           "gen_ai.usage.output_tokens": out_tok,
                           "gen_ai.cost_usd": round((in_tok + out_tok) * PRICE_PER_TOKEN, 5)}}
    return [root] + children


def print_span_tree(spans):
    root = spans[0]
    a = root["attributes"]
    print(f"  invoke_agent  [{root['start_ms']}-{root['end_ms']}ms]  "
          f"in={a['gen_ai.usage.input_tokens']} out={a['gen_ai.usage.output_tokens']} "
          f"${a['gen_ai.cost_usd']:.5f}")
    kids = spans[1:]
    for i, s in enumerate(kids):
        branch = "  " + ("└─" if i == len(kids) - 1 else "├─")
        at = s["attributes"]
        if s["name"] == "llm":
            extra = f"decide {at['decided.tool']}  in={at['gen_ai.usage.input_tokens']} out={at['gen_ai.usage.output_tokens']}"
        else:
            extra = f"{at['gen_ai.tool.name']}"
        print(f"{branch} {s['name']:<13} [{s['start_ms']}-{s['end_ms']}ms]  {extra}")


# ===========================================================================
# Step 3. Metrics reconstructed from the spans (not from a side channel; from the
# same spans we just emitted).
# ===========================================================================
def metrics_from_spans(spans):
    root = spans[0]
    tools = [s["attributes"]["gen_ai.tool.name"] for s in spans if s["name"] == "execute_tool"]
    llm_calls = sum(1 for s in spans if s["name"] == "llm")
    return {"trajectory": tools, "llm_calls": llm_calls,
            "input_tokens": root["attributes"]["gen_ai.usage.input_tokens"],
            "output_tokens": root["attributes"]["gen_ai.usage.output_tokens"],
            "cost_usd": root["attributes"]["gen_ai.cost_usd"],
            "latency_ms": root["end_ms"]}


# ===========================================================================
# Step 4. generate() / a real OTLP exporter -- the real paths (reference only).
# Offline, the deterministic journal is the source of truth (same device as 1-10).
# ===========================================================================
def generate(prompt):
    """REAL path: ask a hosted LLM; the usage it returns fills the llm span. Unused offline."""
    from openai import OpenAI
    client = OpenAI()
    resp = client.chat.completions.create(model="gpt-4o-mini",
                                          messages=[{"role": "user", "content": prompt}], temperature=0)
    return resp.choices[0].message.content


# ===========================================================================
# Demo. Everything below RUNS OFFLINE.
# ===========================================================================
if __name__ == "__main__":
    bar = "=" * 72
    print(bar)
    print("SHIPPING IT  -  tracing, cost-per-success, and the core capstone")
    print(bar)
    if os.environ.get("OPENAI_API_KEY"):
        print("[trace] OPENAI_API_KEY set; real token usage would fill the spans, and a real OTLP "
              "exporter would ship them. Falling through to the frozen journal for reproducibility.")
    else:
        print("[trace] no OPENAI_API_KEY; folding the frozen journal into spans (offline default)")

    spans = build_spans(JOURNAL)

    # --- One log, two views: durability (journal) and observability (spans). ---
    print("\n" + "-" * 72)
    print("ONE LOG, TWO VIEWS. The Part 9 journal (durability)...")
    print("-" * 72)
    for e in JOURNAL:
        print("    " + json.dumps(e, sort_keys=True))

    print("\n" + "-" * 72)
    print("...folded into an OTel-GenAI-shaped span tree (observability). No otel SDK.")
    print("-" * 72)
    print_span_tree(spans)

    print("\n  The same spans as JSONL (what a real OTLP exporter would ship):")
    for s in spans:
        print("    " + json.dumps(s, sort_keys=True))

    # --- Metrics from the spans. -------------------------------------------
    print("\n" + bar)
    print("METRICS reconstructed from the spans")
    print(bar)
    m = metrics_from_spans(spans)
    print(f"  trajectory   : {' -> '.join(m['trajectory'])}")
    print(f"  llm calls    : {m['llm_calls']}")
    print(f"  tokens       : in={m['input_tokens']} out={m['output_tokens']} "
          f"(input grew 40 -> 70 -> 95: the re-sent transcript is the dominant cost)")
    print(f"  cost         : ${m['cost_usd']:.5f}")
    print(f"  latency      : {m['latency_ms']}ms (sum of per-span latencies)")

    # --- Cost per success across several runs. ------------------------------
    print("\n" + bar)
    print("COST PER SUCCESS  (you pay for the failures too)")
    print(bar)
    runs = [
        ("refund ORD-3300", True, m["cost_usd"]),
        ("warranty lookup", True, 0.00180),
        ("find a nonexistent discount", False, 0.00320),    # tripped the Part 8 breaker
    ]
    total = sum(c for _, _, c in runs)
    successes = sum(1 for _, ok, _ in runs if ok)
    print(f"  {'task':<30}{'success':>9}{'cost':>12}")
    print("  " + "-" * 49)
    for name, ok, c in runs:
        print(f"  {name:<30}{('yes' if ok else 'no'):>9}{('$%.5f' % c):>12}")
    print("  " + "-" * 49)
    print(f"  total cost across {len(runs)} runs: ${total:.5f}; successes: {successes}")
    print(f"  COST PER SUCCESS: ${total / successes:.5f}  "
          f"(worse than one happy run's ${m['cost_usd']:.5f}: the failed run still cost money)")

    # --- The capstone checklist. -------------------------------------------
    print("\n" + bar)
    print("THE CORE CAPSTONE  -  every ring we added to the augmented LLM, Parts 1 to 11")
    print(bar)
    rings = [
        "1  augmented-LLM loop with typed, validated tools",
        "2  robust execution: failure taxonomy, retries, idempotency (seed)",
        "3  planning: plan-and-execute / ReWOO / tool DAG (LLM-call + depth accounting)",
        "4  critic + error-triggered replanning over the DAG",
        "5  reflection + cross-trial Reflexion",
        "6  four typed memories the agent edits itself",
        "7  compaction + forgetting for the long haul",
        "8  budgets + loop detector + circuit breaker",
        "9  durable event journal + replay + effectively-once",
        "10 pause / approve / resume / steer (human-in-the-loop)",
        "11 observability: spans, cost-per-success  <- you are here",
    ]
    for r in rings:
        print(f"    {r}")
    print("\n  Storage is ~60 lines (a JSONL file or SQLite). For production durability the")
    print("  essay tours Temporal, DBOS, the Vercel Workflow DevKit, and LangGraph, with")
    print("  honest limits. The frontier track (Parts 12 to 17) opens this agent to the")
    print("  protocol wire and multi-agent systems.")

    print("\n" + bar)
    print("Done. Observability is not a second system: the journal that makes the agent")
    print("durable, read as spans, makes it debuggable and accountable. Cost-per-success is")
    print("the number that tells you whether shipping it was worth it.")
    print(bar)
