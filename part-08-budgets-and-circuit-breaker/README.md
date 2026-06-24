# Part 8 - Stopping the Runaway: budgets, loop detection, and the circuit breaker

> Every part so far made the agent more capable. This one makes it safe to leave running. The loop ends only on finish() or a single max_steps cap, but a real controller does not always converge: it can get STUCK re-issuing the same search forever, or WANDER with plausible never-ending progress that quietly runs up a bill. An agent that does not know when to give up is a liability.

[📖 Read the essay](https://www.mefby.com/essays/budgets-and-circuit-breaker) · [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/mftnakrsu/agents-by-hand/blob/main/part-08-budgets-and-circuit-breaker/budget_circuit_breaker.ipynb)

## What it covers
- **The never-gives-up failure**: the ReAct loop from Part 1 ends only when the controller calls finish() or it hits a single max_steps cap (RAG Part 19's one guard). That is not enough for two reasons. It cannot tell a run that is making PROGRESS from one SPINNING in place, and it ignores the dimensions that actually cost money: tokens, dollars, and time. Run a real controller and it shows up in two shapes a step cap cannot tell apart: a STUCK agent re-issuing the identical search, and a WANDERING agent making steady, plausible, never-ending progress. There are documented incidents of unbounded agent loops burning a serious amount of money before anyone noticed.
- **The multi-dimensional `BudgetMeter`**: one number cannot capture "too expensive." The meter tracks steps, estimated tokens, estimated USD, and (simulated) wall-clock, each with its own ceiling, checked BEFORE every step. `exceeded()` returns the FIRST dimension over its limit, so the first to cross stops the run (here: **4 steps | 600 tokens | $0.02 | 12s**, charging **80 tokens | $0.0008 | ~1.2s** per step).
- **The `LoopDetector` (formalizing RAG P19's note)**: repeating the identical `(action, args)` is the signature of a stuck agent. The detector counts repeats and flags a loop at a threshold (**3 identical actions**). This turns RAG Part 19's informal "if the agent runs the same search twice, stop" remark into a real, reusable check.
- **The graceful `CircuitBreaker`**: when the budget is exceeded OR a loop is detected, the breaker trips: closed -> tripped -> graceful-finish. Crucially, tripping does NOT crash. It returns the best PARTIAL result the agent has, plus the reason it stopped, so the caller gets something useful and an explanation instead of a hang or a stack trace.
- **Owned here, reused later**: these are not throwaway demos. The `BudgetMeter` is reused by **Part 13** to cap a code-execution sandbox, and the `CircuitBreaker` by **Part 14** to stop a runaway supervisor. We build them carefully here because later parts depend on them.
- **Honesty about the numbers**: wall-clock is **SIMULATED** (a fixed per-step estimate), not measured, so the run is reproducible; the cost numbers are illustrative per-token estimates, not a real price sheet; and the runaway-cost framing is generalized ("documented incidents of unbounded loops burning a serious amount of money") with no fabricated specific dollar figure.

## Files
- **`budget_circuit_breaker.py`** — the single runnable script: the multi-dimensional `BudgetMeter` (`charge_step`/`exceeded`/`snapshot`), the `LoopDetector` keyed on `(action, args)`, the `CircuitBreaker` (closed -> tripped), the two non-converging controllers (`stuck_controller`, `wandering_controller`) that never call finish(), the guarded `run_agent` loop with its pre-step budget guard and post-action loop check, the `_graceful_partial` finish, the real-LLM `generate()` they stand in for, and the three demos.
- **`budget_circuit_breaker.ipynb`** — step-by-step notebook: a markdown why before each small code step, built cell by cell.

## Run it
```bash
# from the repo root; no dependencies, no API key, no network
python3 part-08-budgets-and-circuit-breaker/budget_circuit_breaker.py          # runs offline
# optional: set OPENAI_API_KEY to see the real-LLM controller banner (still falls through to the deterministic controllers)
```
Prefer it step by step? Open `budget_circuit_breaker.ipynb` in Jupyter, or click **Open in Colab** above.

## Key idea
A single max_steps cap cannot tell a stuck run from an expensive one. With no guards, a stuck agent re-issues the same search and never stops; only a demo cap cuts it off:

```
    step 8: search_policy('discount code for ORD-9999') -> (no discount code on file)  (x8)    [steps 8 | tokens 640 | $0.0064 | ~9.6s]
    [demo cap] cut off at 8 steps; an unguarded agent would not stop on its own.
    final meter: steps 8 | tokens 640 | $0.0064 | ~9.6s
    -> RUNAWAY (no guards): 8 steps and still not done.
```

Turn the guards on and the LOOP DETECTOR catches the identical action at the threshold, well before the budget would, and the breaker trips to a graceful partial result:

```
    BREAKER TRIPPED: loop detected: identical action repeated 3 times
    breaker: tripped (loop detected: identical action repeated 3 times)
    final meter: steps 3 | tokens 240 | $0.0024 | ~3.6s  (well under budget; the loop caught it first)
```

A WANDERING agent never repeats, so there is no loop to catch; the multi-dimensional BUDGET is what stops it, the first dimension to cross its ceiling ending the run before step 5:

```
    BREAKER TRIPPED before step 5: step budget (4) reached
    breaker: tripped (step budget (4) reached)
    final meter: steps 4 | tokens 320 | $0.0032 | ~4.8s
    -> Stopped gracefully after 4 steps (step budget (4) reached). Partial result: could not complete 'Audit every policy clause'; returning what was gathered instead of looping or crashing.
```

A MULTI-DIMENSIONAL budget (steps, tokens, cost, time) stops the first to cross; a LOOP DETECTOR catches the identical-action signature (formalizing P19's note); a CIRCUIT BREAKER trips to a GRACEFUL partial result, never a crash or a spin. This GENERALIZES RAG Part 19's single max_steps and informal loop remark into real, reusable safety machinery; it does not re-teach the ReAct loop, it guards it. It builds on Part 5's recovery and limits theme.

## Offline by design
The whole demo runs with no network and no API key. The controllers are deterministic, tokens and cost are estimated by fixed per-step constants, and wall-clock is a **simulated** per-step estimate rather than a measured time, so the output is reproducible: the stuck run hits the loop threshold at the same step 3 every time, the wandering run trips the step budget before the same step 5, and the meter reads the same numbers each run. The real path sits behind a flag: set OPENAI_API_KEY and the demo prints a banner noting the real LLM would drive the loop via `generate()`, then falls through to the deterministic controllers so output stays reproducible. Only `generate()` would need edits to light up production.

---
[Series index](../) · [Part 9 — coming soon](../) (coming soon)
