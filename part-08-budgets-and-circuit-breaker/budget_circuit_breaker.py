"""
Stopping the Runaway: budgets, loop detection, and the circuit breaker.
Agents from First Principles, Part 8.

Every part so far made the agent more capable. This one makes it safe to leave
running. The loop from Part 1 ends only when the controller calls finish() or it
hits a single max_steps cap (RAG Part 19's one guard). A real controller does not
always converge: it can get stuck re-issuing the SAME search forever, or it can
make steady, plausible, never-ending progress that quietly runs up a large bill.
There are documented incidents of unbounded agent loops burning a serious amount
of money before anyone noticed. An agent that does not know when to give up is a
liability.

A single step cap is not enough, for two reasons. It does not distinguish a run
that is making progress from one spinning in place, and it ignores the dimensions
that actually cost money: tokens, dollars, and time. This part adds three guards:

1. A MULTI-DIMENSIONAL BUDGET. A BudgetMeter tracks steps, estimated tokens,
   estimated USD, and (simulated) wall-clock, each with its own ceiling, checked
   BEFORE every step. The first dimension to cross its ceiling stops the run. One
   number cannot capture "too expensive."

2. A LOOP DETECTOR. Repeating the identical (action, args) is the signature of a
   stuck agent. The detector counts repeats and flags a loop at a threshold. This
   FORMALIZES the informal note from RAG Part 19 ("if the agent runs the same
   search twice, stop") into a real, reusable check.

3. A CIRCUIT BREAKER. When the budget is exceeded or a loop is detected, the
   breaker trips: closed -> tripped -> graceful-finish. Crucially, tripping does
   not crash. It returns the best PARTIAL result the agent has, plus the reason it
   stopped, so the caller gets something useful and an explanation.

These are not throwaway demos. The BudgetMeter is reused by Part 13 (to cap a
code-execution sandbox) and the circuit breaker by Part 14 (to stop a runaway
supervisor). We build them carefully here because later parts depend on them.

HONESTY: wall-clock is SIMULATED (a fixed per-step estimate), not measured, so the
run is reproducible; the cost numbers are illustrative per-token estimates, not a
real price sheet. We do not fabricate a specific runaway dollar incident.

CONTINUITY: same support world. Deterministic controllers offline; generate() is
the real-LLM path one env flag away.

Run:
  python3 budget_circuit_breaker.py        # offline; no API key, no network, no deps

NOTE: SDK names and model ids move fast; only generate() would need edits.

Expected output (deterministic default path):
========================================================================
STOPPING THE RUNAWAY  -  budgets, loop detection, and the circuit breaker
========================================================================
[controller] no OPENAI_API_KEY; using deterministic controllers (offline default)

Budget ceilings: 4 steps | 600 tokens | $0.02 | 12s (simulated). Loop threshold: 3 identical actions.

------------------------------------------------------------------------
1) NO GUARDS: a stuck agent re-issues the same search and never stops.
------------------------------------------------------------------------
    step 1: search_policy('discount code for ORD-9999') -> (no discount code on file)    [steps 1 | tokens 80 | $0.0008 | ~1.2s]
    step 2: search_policy('discount code for ORD-9999') -> (no discount code on file)  (x2)    [steps 2 | tokens 160 | $0.0016 | ~2.4s]
    step 3: search_policy('discount code for ORD-9999') -> (no discount code on file)  (x3)    [steps 3 | tokens 240 | $0.0024 | ~3.6s]
    step 4: search_policy('discount code for ORD-9999') -> (no discount code on file)  (x4)    [steps 4 | tokens 320 | $0.0032 | ~4.8s]
    step 5: search_policy('discount code for ORD-9999') -> (no discount code on file)  (x5)    [steps 5 | tokens 400 | $0.0040 | ~6.0s]
    step 6: search_policy('discount code for ORD-9999') -> (no discount code on file)  (x6)    [steps 6 | tokens 480 | $0.0048 | ~7.2s]
    step 7: search_policy('discount code for ORD-9999') -> (no discount code on file)  (x7)    [steps 7 | tokens 560 | $0.0056 | ~8.4s]
    step 8: search_policy('discount code for ORD-9999') -> (no discount code on file)  (x8)    [steps 8 | tokens 640 | $0.0064 | ~9.6s]
    [demo cap] cut off at 8 steps; an unguarded agent would not stop on its own.
    final meter: steps 8 | tokens 640 | $0.0064 | ~9.6s
    -> RUNAWAY (no guards): 8 steps and still not done.

------------------------------------------------------------------------
2) GUARDS ON: the loop detector catches the identical action at the threshold.
------------------------------------------------------------------------
    step 1: search_policy('discount code for ORD-9999') -> (no discount code on file)    [steps 1 | tokens 80 | $0.0008 | ~1.2s]
    step 2: search_policy('discount code for ORD-9999') -> (no discount code on file)  (x2)    [steps 2 | tokens 160 | $0.0016 | ~2.4s]
    step 3: search_policy('discount code for ORD-9999') -> (no discount code on file)  (x3)    [steps 3 | tokens 240 | $0.0024 | ~3.6s]
    BREAKER TRIPPED: loop detected: identical action repeated 3 times
    breaker: tripped (loop detected: identical action repeated 3 times)
    final meter: steps 3 | tokens 240 | $0.0024 | ~3.6s  (well under budget; the loop caught it first)
    -> Stopped gracefully after 3 steps (loop detected: identical action repeated 3 times). Partial result: could not complete 'Find a discount code for ORD-9999'; returning what was gathered instead of looping or crashing.

------------------------------------------------------------------------
3) GUARDS ON: a wandering agent never repeats, so the BUDGET stops it.
------------------------------------------------------------------------
    step 1: search_policy('policy clause 1') -> clause text for 'policy clause 1'    [steps 1 | tokens 80 | $0.0008 | ~1.2s]
    step 2: search_policy('policy clause 2') -> clause text for 'policy clause 2'    [steps 2 | tokens 160 | $0.0016 | ~2.4s]
    step 3: search_policy('policy clause 3') -> clause text for 'policy clause 3'    [steps 3 | tokens 240 | $0.0024 | ~3.6s]
    step 4: search_policy('policy clause 4') -> clause text for 'policy clause 4'    [steps 4 | tokens 320 | $0.0032 | ~4.8s]
    BREAKER TRIPPED before step 5: step budget (4) reached
    breaker: tripped (step budget (4) reached)
    final meter: steps 4 | tokens 320 | $0.0032 | ~4.8s
    -> Stopped gracefully after 4 steps (step budget (4) reached). Partial result: could not complete 'Audit every policy clause'; returning what was gathered instead of looping or crashing.

========================================================================
Done. A single max_steps cap cannot tell a stuck run from an expensive one.
  - a MULTI-DIMENSIONAL budget (steps, tokens, cost, time) stops the first to cross
  - a LOOP DETECTOR catches the identical-action signature (formalizes P19's note)
  - a CIRCUIT BREAKER trips to a GRACEFUL partial result, never a crash or a spin
Owned here, reused later: the BudgetMeter in Part 13, the breaker in Part 14.
========================================================================
"""

import os


# ===========================================================================
# Step 1. The BudgetMeter: multi-dimensional, checked before every step. Each
# dimension has a ceiling; exceeded() returns the FIRST one over its limit (or
# None). One number ("max steps") cannot express "too many tokens" or "too costly."
# ===========================================================================
USD_PER_TOKEN = 0.00001        # an illustrative per-token price, not a real sheet
TOKENS_PER_STEP = 80           # an illustrative per-step token estimate
WALL_PER_STEP = 1.2            # SIMULATED seconds per step (not measured)


class BudgetMeter:
    def __init__(self, max_steps, max_tokens, max_usd, max_wall):
        self.max_steps, self.max_tokens = max_steps, max_tokens
        self.max_usd, self.max_wall = max_usd, max_wall
        self.steps = self.tokens = 0
        self.usd = self.wall = 0.0

    def charge_step(self):
        self.steps += 1
        self.tokens += TOKENS_PER_STEP
        self.usd += TOKENS_PER_STEP * USD_PER_TOKEN
        self.wall += WALL_PER_STEP

    def exceeded(self):
        if self.steps >= self.max_steps:
            return f"step budget ({self.max_steps})"
        if self.tokens >= self.max_tokens:
            return f"token budget ({self.max_tokens})"
        if self.usd >= self.max_usd:
            return f"cost budget (${self.max_usd:.2f})"
        if self.wall >= self.max_wall:
            return f"time budget ({self.max_wall:.0f}s)"
        return None

    def snapshot(self):
        return (f"steps {self.steps} | tokens {self.tokens} | "
                f"${self.usd:.4f} | ~{self.wall:.1f}s")


# ===========================================================================
# Step 2. The LoopDetector: count identical (action, args) and flag a loop at a
# threshold. This formalizes RAG Part 19's informal "saw the same search twice"
# note into a reusable check. (Alternating A-B-A-B cycles are a natural extension;
# we key on exact repeats here.)
# ===========================================================================
class LoopDetector:
    def __init__(self, threshold=3):
        self.threshold = threshold
        self.counts = {}

    def record(self, action_key):
        self.counts[action_key] = self.counts.get(action_key, 0) + 1
        n = self.counts[action_key]
        return (n >= self.threshold), n


# ===========================================================================
# Step 3. The CircuitBreaker: closed -> tripped -> graceful-finish. It does not
# raise. When it trips it records WHY, and the agent returns its best partial
# result instead of crashing or looping.
# ===========================================================================
class CircuitBreaker:
    def __init__(self):
        self.state = "closed"
        self.reason = None

    def trip(self, reason):
        self.state = "tripped"
        self.reason = reason


# ===========================================================================
# Step 4. Two controllers that DO NOT converge, the two failure shapes a single
# step cap cannot tell apart.
#   stuck    : re-issues the IDENTICAL search every step (loop detector catches it)
#   wandering: a DIFFERENT plausible search every step, forever (budget catches it)
# Neither ever calls finish() -- that is the bug we are guarding against.
# ===========================================================================
def stuck_controller(goal, steps):
    return ("Look up the discount code again.",
            "search_policy", {"query": "discount code for ORD-9999"})


def wandering_controller(goal, steps):
    n = len(steps) + 1
    return (f"Audit policy clause {n}.",
            "search_policy", {"query": f"policy clause {n}"})


def search_policy(query):
    if "discount code" in query:
        return "(no discount code on file)"          # empty-ish: re-searching cannot help
    return f"clause text for '{query}'"


# ===========================================================================
# Step 5. The guarded agent loop. Before every step: ask the breaker whether the
# budget is exceeded. After choosing an action: ask the loop detector. Either trips
# the breaker, which ends the run with a graceful PARTIAL result.
# ===========================================================================
def run_agent(goal, controller, ceilings, guards=True, loop_threshold=3,
              hard_cap=10, trace=True):
    meter = BudgetMeter(*ceilings)
    detector = LoopDetector(threshold=loop_threshold)
    breaker = CircuitBreaker()
    steps = []

    def log(msg):
        if trace:
            print(msg)

    while True:
        # --- pre-step budget guard -----------------------------------------
        if guards:
            over = meter.exceeded()
            if over:
                breaker.trip(f"{over} reached")
                log(f"    BREAKER TRIPPED before step {meter.steps + 1}: {breaker.reason}")
                break
        else:
            if meter.steps >= hard_cap:
                log(f"    [demo cap] cut off at {hard_cap} steps; an unguarded agent would "
                    "not stop on its own.")
                break

        thought, tool, args = controller(goal, steps)
        if tool == "finish":
            log(f"    finish -> {args.get('answer')}")
            return args.get("answer"), meter, breaker

        # --- loop detection on (action, args) ------------------------------
        key = (tool, tuple(sorted(args.items())))
        is_loop, count = detector.record(key)

        meter.charge_step()
        obs = search_policy(args["query"])
        steps.append((tool, args, obs))
        rep = f"  (x{count})" if count > 1 else ""
        log(f"    step {meter.steps}: {tool}({args['query']!r}) -> {obs}{rep}    [{meter.snapshot()}]")

        if guards and is_loop:
            breaker.trip(f"loop detected: identical action repeated {count} times")
            log(f"    BREAKER TRIPPED: {breaker.reason}")
            break

    # --- graceful finish: return the best partial result + the reason ------
    partial = _graceful_partial(goal, steps, breaker)
    return partial, meter, breaker


def _graceful_partial(goal, steps, breaker):
    if breaker.state != "tripped":
        return f"RUNAWAY (no guards): {len(steps)} steps and still not done."
    seen = len(steps)
    return (f"Stopped gracefully after {seen} steps ({breaker.reason}). "
            f"Partial result: could not complete '{goal}'; returning what was gathered "
            "instead of looping or crashing.")


# ===========================================================================
# generate() -- the real LLM controller path (reference shape only). Offline, the
# deterministic controllers are the source of truth (same device as Parts 1-7).
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


# ===========================================================================
# Demo. Everything below RUNS OFFLINE.
# ===========================================================================
if __name__ == "__main__":
    bar = "=" * 72
    print(bar)
    print("STOPPING THE RUNAWAY  -  budgets, loop detection, and the circuit breaker")
    print(bar)
    if os.environ.get("OPENAI_API_KEY"):
        print("[controller] OPENAI_API_KEY set; the real LLM would drive the loop via generate(). "
              "Falling through to the deterministic controllers so output is reproducible.")
    else:
        print("[controller] no OPENAI_API_KEY; using deterministic controllers (offline default)")

    CEILINGS = (4, 600, 0.02, 12.0)        # max_steps, max_tokens, max_usd, max_wall
    print(f"\nBudget ceilings: {CEILINGS[0]} steps | {CEILINGS[1]} tokens | "
          f"${CEILINGS[2]:.2f} | {CEILINGS[3]:.0f}s (simulated). Loop threshold: 3 identical actions.")

    # --- 1. The runaway: no guards. ----------------------------------------
    print("\n" + "-" * 72)
    print("1) NO GUARDS: a stuck agent re-issues the same search and never stops.")
    print("-" * 72)
    ans, meter, br = run_agent("Find a discount code for ORD-9999", stuck_controller,
                               CEILINGS, guards=False, hard_cap=8)
    print(f"    final meter: {meter.snapshot()}")
    print(f"    -> {ans}")

    # --- 2. The loop detector trips the breaker. ---------------------------
    print("\n" + "-" * 72)
    print("2) GUARDS ON: the loop detector catches the identical action at the threshold.")
    print("-" * 72)
    ans, meter, br = run_agent("Find a discount code for ORD-9999", stuck_controller,
                               CEILINGS, guards=True, loop_threshold=3)
    print(f"    breaker: {br.state} ({br.reason})")
    print(f"    final meter: {meter.snapshot()}  (well under budget; the loop caught it first)")
    print(f"    -> {ans}")

    # --- 3. The budget trips the breaker (no loop to catch). ---------------
    print("\n" + "-" * 72)
    print("3) GUARDS ON: a wandering agent never repeats, so the BUDGET stops it.")
    print("-" * 72)
    ans, meter, br = run_agent("Audit every policy clause", wandering_controller,
                               CEILINGS, guards=True, loop_threshold=3)
    print(f"    breaker: {br.state} ({br.reason})")
    print(f"    final meter: {meter.snapshot()}")
    print(f"    -> {ans}")

    print("\n" + bar)
    print("Done. A single max_steps cap cannot tell a stuck run from an expensive one.")
    print("  - a MULTI-DIMENSIONAL budget (steps, tokens, cost, time) stops the first to cross")
    print("  - a LOOP DETECTOR catches the identical-action signature (formalizes P19's note)")
    print("  - a CIRCUIT BREAKER trips to a GRACEFUL partial result, never a crash or a spin")
    print("Owned here, reused later: the BudgetMeter in Part 13, the breaker in Part 14.")
    print(bar)
