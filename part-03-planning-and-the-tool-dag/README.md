# Part 3 - Planning the Work: plan-and-execute, ReWOO, and the tool DAG

> The ReAct loop from Parts 1-2 decides one step at a time, paying a fresh LLM call per hop and re-sending the whole transcript each time; this part makes the plan a first-class artifact so the model is called twice, not once per tool.

[📖 Read the essay](https://www.mefby.com/essays/planning-and-the-tool-dag) · [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/mftnakrsu/agents-by-hand/blob/main/part-03-planning-and-the-tool-dag/planners.ipynb)

## What it covers
- **The per-hop bill**: ReAct (the Parts 1-2 baseline) decides ONE step, runs it, reads the result, then decides the next. Each hop is a fresh LLM call, and each call re-sends the whole transcript so far, so a four-lookup task is five LLM calls, each longer than the last, and the model re-derives the plan from scratch every step. The fix is to stop letting the plan live only in the model's head between calls and write it down once.
- **Plan-and-Execute**: a planner writes the ordered plan once; an executor runs the steps WITHOUT calling the model again; one final call synthesizes the answer. Two LLM calls instead of one-per-hop, and model cost is decoupled from the number of tools. (It can also REPLAN when a step surprises it; that hook is Part 4.)
- **ReWOO (Reasoning WithOut Observation)**: the plan binds EVIDENCE VARIABLES (`#E1`, `#E2`, ...) so a later step can name an earlier step's result before it exists. The tools run and fill the variables in; one solver call reads the completed worksheet. Still two LLM calls, and the plan never pauses to consult the model mid-run. Here `#E2` (the acquirer "Globex") binds inside `#E2 earbuds warranty`.
- **The tool DAG (LLMCompiler-style)**: the plan is a DAG of tasks with explicit DEPENDENCIES. The executor runs it by topological LEVEL, so independent nodes share a round; only a real dependency forces a new round. The headline number is the CRITICAL-PATH DEPTH (the longest chain of dependent steps), not the step count.
- **The honest LLM-call / critical-path-depth accounting**: a `CallMeter` threads through every strategy and counts the two numbers that matter: LLM calls (the dominant cost lever) and critical-path depth (the number of sequential rounds of tool calls). The scoreboard is built from the live run, not asserted.
- **Depth, not wall-clock**: the offline runner executes everything sequentially. "Parallel" means "could run in the same round," and depth is what real concurrency would shrink. We deliberately do NOT print a fabricated speedup. (The transcript-resend cost ReAct pays is real too; we flag it here and Part 11 develops transcript economics in full.)

## Files
- **`planners.py`** — the single runnable script: the Parts 1-2 world and tools (refund policy, the Acme to Globex chain, the calculator), the `CallMeter`, the plan as data (`TaskNode` with explicit deps and `#En` evidence variables), the deterministic `rule_planner` and the real-LLM `generate()` it stands in for, the four strategies (`run_react`, `run_plan_execute`, `run_rewoo`, `run_dag`), `dag_levels` for critical-path depth, and the demo that runs all four on one task and prints the scoreboard.
- **`planners.ipynb`** — step-by-step notebook: a markdown why before each small code step, built cell by cell.

## Run it
```bash
# from the repo root; no dependencies, no API key, no network
python3 part-03-planning-and-the-tool-dag/planners.py               # runs offline
# optional: set OPENAI_API_KEY to see the real LLM planner banner (still falls through to the rule planner)
```
Prefer it step by step? Open `planners.ipynb` in Jupyter, or click **Open in Colab** above.

## Key idea
The plan does not have to live only in the model's head between calls. The task is built so the differences show: a refund summary needing the refund window from policy, the warranty on the earbuds made by the company that acquired Acme, and 18% tax on a $250 order. Four tool calls, ONE dependency chain (E2 acquirer to E3 warranty), and TWO independent branches (E1 policy, E4 tax). Every strategy returns the SAME answer; only the cost and the depth differ:

```
strategy              LLM calls  tool calls   crit-path depth
ReAct                         5           4                 4
Plan-and-Execute              2           4                 4
ReWOO                         2           4                 4
Tool DAG                      2           4                 2
```

Writing the plan down once cuts LLM calls from 5 (one per hop) to 2 (plan plus synthesize) and decouples model cost from the number of tools. ReWOO removes every mid-run model call via `#E` variable binding. The DAG additionally cuts critical-path depth from 4 to 2: the three independent lookups (E1, E2, E4) collapse into one round and only acquirer to warranty (E2 to E3) chains. We report depth, not wall-clock, because the offline runner is sequential and depth is what real concurrency would shrink. This lineage traces to ReAct (Yao et al., 2023, arXiv:2210.03629) as the baseline being beaten, the Plan-and-Execute pattern, ReWOO (Xu et al., 2023, arXiv:2305.18323), and LLMCompiler (Kim et al., 2023, arXiv:2312.04511). Cost-aware and small-model routing is toured here only in passing; it is owned later.

## Offline by design
The whole demo runs with no network and no API key. A deterministic `rule_planner` stands in for a trained LLM planner: it emits the same `TaskNode` DAG structure a single `generate()` call would return, and `compose_answer` synthesizes the final text from the filled-in evidence, so output is reproducible and every strategy provably agrees on the answer (the demo asserts it). The real path sits behind a flag: set OPENAI_API_KEY and the planner prints a banner noting the real LLM planner would emit the same plan structure, then falls through to the rule planner so output stays reproducible. Only `generate()` would need edits to light up production. The plan emitted, the bindings made, the rounds taken, and every scoreboard number are identical either way.

---
[Series index](../) · [Part 4 — Replanning and Reflection →](../) (coming soon)
