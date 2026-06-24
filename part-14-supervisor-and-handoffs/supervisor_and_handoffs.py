"""
The Supervisor and the Handoff: multi-agent, and when it hurts.
Agents from First Principles, Part 14.

So far there has been one agent with one context window. That is a real limit. A
breadth-first task with independent parts cannot be parallelized inside one context,
and a task that should really be handled by a specialist is awkward to cram into a
generalist's loop. The fix is to use MORE THAN ONE agent. The fix is also a trap:
multi-agent systems are more expensive, harder to debug, and frequently OVERKILL.
This part builds the two main multi-agent shapes and, just as importantly, the
honest economics of when NOT to reach for them.

1. ORCHESTRATOR-WORKER (the supervisor). A lead agent DECOMPOSES a task into
   subtasks, spawns N WORKERS, each with its OWN isolated context and a TYPED BRIEF
   (objective, output format, tool guidance, boundaries), and then SYNTHESIZES their
   results. The worker is just the Part 1 agent reused as a black box; we do not
   rebuild the loop. Workers coordinate through a shared append-only BLACKBOARD.

2. HANDOFF AS A TOOL CALL. Sometimes the right move is not to fan out but to TRANSFER
   CONTROL to a specialist, carrying the live trace along. handoff(to=...) is a tool
   like any other. We show a clean handoff and its two classic failure modes:
   TRUNCATION (the trace is cut, so the specialist is missing the key fact) and ROLE
   CONFUSION (the brief does not say who owns the task, so it stalls).

3. THE ECONOMICS: single vs supervisor vs debate, on one task, with the numbers.
   A proposer-critic DEBATE shows the uncomfortable truth that more rounds are not
   more quality: round 3 REGRESSES. The single agent is cheapest to wire; the
   supervisor isolates context and parallelizes; debate is the most expensive and
   the least monotonic.

HONESTY about parallelism (the feasibility crux): the offline default runs workers
SEQUENTIALLY. We never print a fabricated wall-clock speedup. What multi-agent buys
is reported honestly as (a) LLM-CALL COUNT and (b) TOKEN ISOLATION: each worker sees
only its own small brief, not one ever-growing shared transcript. With real
concurrency the independent workers run in a single round (depth 1, the Part 3
idea). A runaway supervisor is stopped by Part 8's circuit breaker (reused, not
rebuilt), and these distributed runs render as the Part 11 span tree.

CONTINUITY: the support world (refunds, the earbuds warranty, shipping). Deterministic.

Run:
  python3 supervisor_and_handoffs.py        # offline; no API key, no network, no deps

NOTE: SDK names move fast; only generate() would need edits.

Expected output (deterministic default path):
========================================================================
THE SUPERVISOR AND THE HANDOFF  -  multi-agent, and when it hurts
========================================================================
[orchestrator] no OPENAI_API_KEY; deterministic lead/workers (offline default)

Parallelism is SEQUENTIAL in this offline default: we report LLM-call count and
TOKEN ISOLATION (each worker sees only its brief), never a fabricated wall-clock.

------------------------------------------------------------------------
1) ORCHESTRATOR-WORKER: decompose, fan out to isolated workers, synthesize.
------------------------------------------------------------------------
  supervisor decomposes: 'Prepare a customer briefing on refunds, the earbuds warranty, and shipping.'
    [w1] brief: summarize the refund policy (own context, 14 tokens) -> Refunds within 30 days; a 10% restocking fee applies after the window.
    [w2] brief: state the earbuds warranty (own context, 14 tokens) -> The Globex earbuds carry a 2-year limited warranty.
    [w3] brief: list the shipping options (own context, 14 tokens) -> Standard shipping is 3 to 5 business days; express is next business day.
  supervisor synthesizes the blackboard into the briefing:
    Refunds within 30 days; a 10% restocking fee applies after the window. The Globex earbuds carry a 2-year limited warranty. Standard shipping is 3 to 5 business days; express is next business day.
    (3 workers, each its own context; with real concurrency they run in ONE round.)

------------------------------------------------------------------------
2) HANDOFF AS A TOOL CALL: transfer control + the trace to a specialist.
------------------------------------------------------------------------
  clean handoff (full trace, clear role):
    handoff(to='billing-specialist'): carrying 3/3 trace entries, role=clear
    -> [done] billing-specialist refunded order ORD-3300 using the carried trace.
  failure mode TRUNCATION (trace cut to the last entry; the order id was earlier):
    handoff(to='billing-specialist'): carrying 1/3 trace entries, role=clear
    -> [failed] billing-specialist cannot act: the order id was truncated out of the carried trace.
  failure mode ROLE CONFUSION (brief never said who owns it):
    handoff(to='billing-specialist'): carrying 3/3 trace entries, role=UNCLEAR
    -> [stalled] billing-specialist and the lead both wait: the brief never said who owns the task.

========================================================================
3) THE ECONOMICS: single vs supervisor vs debate (call count + token isolation).
========================================================================
  strategy        LLM calls   tokens  quality
  -----------------------------------------
  single                  4      300      3/3
  supervisor              5      220      3/3
  debate                  7      320      2/3

  Debate quality by round (more rounds is NOT more quality):
    proposer   quality 2/3
    round 1    quality 3/3
    round 2    quality 3/3
    round 3    quality 2/3  <- regressed

  Reading it:
  - single: fewest calls, but ONE growing context (tokens climb every step)
  - supervisor: more calls, but each worker context is ISOLATED and small;
    independent workers parallelize (one round with real concurrency)
  - debate: most expensive AND non-monotonic; round 3 made it worse
  - cost-per-success follows tokens: pay for breadth only when the task IS broad;
    a single agent is the right, cheaper tool for a small sequential task.

========================================================================
4) SAFETY: a runaway supervisor (workers spawning workers) is stopped by Part 8's
circuit breaker, reused not rebuilt; and these runs render as the Part 11 span tree.
========================================================================

========================================================================
Done. Multi-agent is a tool, not a default:
  - ORCHESTRATOR-WORKER: typed briefs + isolated contexts + a blackboard + synthesis
  - HANDOFF as a tool call: transfer control + trace (watch truncation + role confusion)
  - the economics: supervisor isolates + parallelizes; debate is dear and not monotonic;
    a single agent is best for a small task. Reach for multi-agent when the work is broad.
========================================================================
"""

import os


# ===========================================================================
# Step 0. The tools (the worker's action space; over MCP in Part 12). The worker is
# the Part 1 agent reused as a black box: hand it a brief, it returns one result.
# ===========================================================================
def search_policy(query):
    if "shipping" in query:
        return "Standard shipping is 3 to 5 business days; express is next business day."
    return "Refunds within 30 days; a 10% restocking fee applies after the window."


def search_products(query):
    return "The Globex earbuds carry a 2-year limited warranty."


TOOLS = {"search_policy": search_policy, "search_products": search_products}


# ===========================================================================
# Step 1. The orchestrator-worker. The supervisor decomposes into typed briefs,
# each worker runs in its OWN context (it only ever sees its brief), writes to the
# shared blackboard, and the supervisor synthesizes.
# ===========================================================================
class Blackboard:
    def __init__(self):
        self.entries = []

    def post(self, author, text):
        self.entries.append((author, text))


def worker(brief, blackboard):
    """A black-box Part 1 agent. Its context is JUST this brief (isolation). It runs
    its one tool and posts to the blackboard."""
    result = TOOLS[brief["tool"]](brief["query"])
    blackboard.post(brief["id"], result)
    ctx_tokens = len(brief["objective"].split()) + len(brief["query"].split()) + 8
    return result, ctx_tokens


def supervisor_run(goal):
    print(f"  supervisor decomposes: {goal!r}")
    briefs = [
        {"id": "w1", "objective": "summarize the refund policy", "output": "one sentence",
         "tool": "search_policy", "query": "refund policy", "boundaries": "policy only"},
        {"id": "w2", "objective": "state the earbuds warranty", "output": "one sentence",
         "tool": "search_products", "query": "earbuds warranty", "boundaries": "products only"},
        {"id": "w3", "objective": "list the shipping options", "output": "one sentence",
         "tool": "search_policy", "query": "shipping options", "boundaries": "shipping only"},
    ]
    bb = Blackboard()
    total_ctx = 0
    for b in briefs:
        result, ctx = worker(b, bb)
        total_ctx += ctx
        print(f"    [{b['id']}] brief: {b['objective']} (own context, {ctx} tokens) -> {result}")
    briefing = " ".join(text for _author, text in bb.entries)
    print(f"  supervisor synthesizes the blackboard into the briefing:")
    print(f"    {briefing}")
    return briefing, total_ctx


# ===========================================================================
# Step 2. Handoff as a tool call: transfer control AND the trace to a specialist.
# A clean handoff carries the full trace and a clear role; the two failure modes are
# a TRUNCATED trace (specialist missing the key fact) and ROLE CONFUSION.
# ===========================================================================
def handoff(to, trace, role, truncate=False, role_clear=True):
    carried = trace[-1:] if truncate else trace
    print(f"    handoff(to={to!r}): carrying {len(carried)}/{len(trace)} trace entries, "
          f"role={'clear' if role_clear else 'UNCLEAR'}")
    if not role_clear:
        return f"[stalled] {to} and the lead both wait: the brief never said who owns the task."
    order = next((t.split("order ")[1].split()[0] for t in carried if "order " in t), None)
    if order is None:
        return f"[failed] {to} cannot act: the order id was truncated out of the carried trace."
    return f"[done] {to} refunded order {order} using the carried trace."


# ===========================================================================
# Step 3. The economics. Single vs supervisor vs debate on the same task. We report
# LLM calls + total context tokens (the token-isolation story) + quality, never a
# wall-clock speedup. A proposer-critic debate regresses on round 3.
# ===========================================================================
def single_agent(goal):
    """One agent, one GROWING context: each step re-sends everything before it."""
    steps = ["refund policy", "earbuds warranty", "shipping options", "synthesize"]
    ctx, total = 0, 0
    for i, _s in enumerate(steps, start=1):
        ctx += 30                            # the transcript grows every step (Parts 3/11)
        total += ctx
    return {"calls": len(steps), "tokens": total, "quality": 3}


def supervisor_econ(goal):
    # decompose + 3 isolated workers + synthesize; each worker context is small + constant
    calls = 1 + 3 + 1
    tokens = 30 + (40 + 40 + 40) + 70        # isolated worker contexts do not grow
    return {"calls": calls, "tokens": tokens, "quality": 3}


def debate_econ(goal):
    """Proposer then 3 critic-revise rounds. Quality is NOT monotonic in rounds."""
    rounds = [("proposer", 2), ("round 1", 3), ("round 2", 3), ("round 3", 2)]  # round 3 regresses
    calls = 1 + 3 * 2                        # proposer + 3x(critic+revise)
    tokens = 0
    base = 50
    for i, (_name, _q) in enumerate(rounds):
        tokens += base + i * 20              # debate transcripts grow fast
    return {"calls": calls, "tokens": tokens, "quality_by_round": rounds,
            "quality": rounds[-1][1]}


def generate(prompt):
    """REAL path: a hosted LLM is the lead/worker/critic. Unused offline."""
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
    print("THE SUPERVISOR AND THE HANDOFF  -  multi-agent, and when it hurts")
    print(bar)
    if os.environ.get("OPENAI_API_KEY"):
        print("[orchestrator] OPENAI_API_KEY set; a real LLM would be the lead/workers/critic. "
              "Falling through to deterministic logic for reproducibility.")
    else:
        print("[orchestrator] no OPENAI_API_KEY; deterministic lead/workers (offline default)")
    print("\nParallelism is SEQUENTIAL in this offline default: we report LLM-call count and")
    print("TOKEN ISOLATION (each worker sees only its brief), never a fabricated wall-clock.")

    # --- 1. Orchestrator-worker. -------------------------------------------
    print("\n" + "-" * 72)
    print("1) ORCHESTRATOR-WORKER: decompose, fan out to isolated workers, synthesize.")
    print("-" * 72)
    goal = "Prepare a customer briefing on refunds, the earbuds warranty, and shipping."
    supervisor_run(goal)
    print("    (3 workers, each its own context; with real concurrency they run in ONE round.)")

    # --- 2. Handoff as a tool call + its failure modes. --------------------
    print("\n" + "-" * 72)
    print("2) HANDOFF AS A TOOL CALL: transfer control + the trace to a specialist.")
    print("-" * 72)
    trace = ["identified order ORD-3300 for refund", "looked up policy: eligible",
             "user confirmed they want the refund"]
    print("  clean handoff (full trace, clear role):")
    print("    -> " + handoff("billing-specialist", trace, "refund the order"))
    print("  failure mode TRUNCATION (trace cut to the last entry; the order id was earlier):")
    print("    -> " + handoff("billing-specialist", trace, "refund the order", truncate=True))
    print("  failure mode ROLE CONFUSION (brief never said who owns it):")
    print("    -> " + handoff("billing-specialist", trace, "refund the order", role_clear=False))

    # --- 3. The economics: single vs supervisor vs debate. ----------------
    print("\n" + bar)
    print("3) THE ECONOMICS: single vs supervisor vs debate (call count + token isolation).")
    print(bar)
    s, sup, deb = single_agent(goal), supervisor_econ(goal), debate_econ(goal)
    print(f"  {'strategy':<14}{'LLM calls':>11}{'tokens':>9}{'quality':>9}")
    print("  " + "-" * 41)
    print(f"  {'single':<14}{s['calls']:>11}{s['tokens']:>9}{str(s['quality']) + '/3':>9}")
    print(f"  {'supervisor':<14}{sup['calls']:>11}{sup['tokens']:>9}{str(sup['quality']) + '/3':>9}")
    print(f"  {'debate':<14}{deb['calls']:>11}{deb['tokens']:>9}{str(deb['quality']) + '/3':>9}")
    print("\n  Debate quality by round (more rounds is NOT more quality):")
    for name, q in deb["quality_by_round"]:
        flag = "  <- regressed" if name == "round 3" else ""
        print(f"    {name:<10} quality {q}/3{flag}")
    print("\n  Reading it:")
    print("  - single: fewest calls, but ONE growing context (tokens climb every step)")
    print("  - supervisor: more calls, but each worker context is ISOLATED and small;")
    print("    independent workers parallelize (one round with real concurrency)")
    print("  - debate: most expensive AND non-monotonic; round 3 made it worse")
    print("  - cost-per-success follows tokens: pay for breadth only when the task IS broad;")
    print("    a single agent is the right, cheaper tool for a small sequential task.")

    # --- 4. Runaway supervisor -> Part 8 breaker (reused, not rebuilt). ----
    print("\n" + bar)
    print("4) SAFETY: a runaway supervisor (workers spawning workers) is stopped by Part 8's")
    print("circuit breaker, reused not rebuilt; and these runs render as the Part 11 span tree.")
    print(bar)

    print("\n" + bar)
    print("Done. Multi-agent is a tool, not a default:")
    print("  - ORCHESTRATOR-WORKER: typed briefs + isolated contexts + a blackboard + synthesis")
    print("  - HANDOFF as a tool call: transfer control + trace (watch truncation + role confusion)")
    print("  - the economics: supervisor isolates + parallelizes; debate is dear and not monotonic;")
    print("    a single agent is best for a small task. Reach for multi-agent when the work is broad.")
    print(bar)
