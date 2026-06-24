# Part 4 - Surviving a Broken Plan: the critic and error-triggered replanning

> Part 3 made the plan a first-class artifact, which buys a new failure: an up-front plan is a bet that the world will not change, and the instant a SKU goes discontinued mid-run, the Part 3 DAG executor charges ahead and runs the dead plan anyway.

[📖 Read the essay](https://www.mefby.com/essays/replanning-and-critic) · [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/mftnakrsu/agents-by-hand/blob/main/part-04-replanning-and-critic/replanning_critic.ipynb)

## What it covers
- **An up-front plan is a bet**: writing the whole DAG down once (Part 3) is a real win, and it commits you to a world that can change under you. The moment that world disagrees, a committed plan is a liability, and the Part 3 executor has no way to revise it. The break we inject is the realistic one: SKU-ACME-EB is DISCONTINUED mid-run, replaced by SKU-GLX-EB (the Acme to Globex acquisition made concrete), and a discontinued SKU is a PERMANENT error in Part 2's taxonomy, so retrying the same call cannot help.
- **The prospective critic and its four checks**: before a single tool fires, check the plan for the structural mistakes a planner makes: an UNKNOWN TOOL (not in the registry), an UNSATISFIABLE DEP (a step that needs a node not in the plan), a DEPENDENCY CYCLE (a step that transitively needs itself), and a REDUNDANT step (two nodes with the identical tool and argument). A bad plan is rejected before it wastes a single call. This is the plan-time analog of Part 1's pre-flight argument validator.
- **Error-triggered partial replanning over the remaining subgraph**: when a step fails in a way that invalidates the rest of the plan, do not abandon the run and do not start over. Revise ONLY THE REMAINING SUBGRAPH, rewriting the not-yet-run steps to target the replacement SKU while leaving the rest of the DAG (and Part 3's topological execution) intact.
- **Step memoization**: every completed step stays MEMOIZED across the replan, so the lookup that already ran is reused, never re-run. Feeding an error back (Part 2) tells the agent the step failed; replanning is how a committed plan actually does something about it.
- **The replan budget**: an honest budget (max 2 here) caps how many times a single run may replan, so a plan that keeps breaking trips out instead of looping forever.
- **Seed here, harden in Part 8**: the replan budget is the seed of resilience; the full circuit breaker (the general mechanism that stops a degenerating run) is owned by Part 8.
- **Reuse of Part 3's DAG**: the `TaskNode`, the dependency DAG, and topological execution come straight from Part 3 unchanged. This part adds the critic and the replanner around them; it does not rebuild the DAG, re-teach the ReAct loop or the tool contract, or re-derive the retry taxonomy.

## Files
- **`replanning_critic.py`** — the single runnable script: the tiny discontinued-SKU catalog and `DiscontinuedError` (a Part 2 permanent error carrying its replacement), the tools that refuse a dead SKU, Part 3's `TaskNode` / `topo_order` / `dag_levels` reused verbatim, the prospective `critic` and its four checks, the real-LLM `generate()` it stands in for, the BLIND executor (`run_blind`, Part 3 with no critic or replanner) and the `run_with_replanning` executor, and the demo that critiques a deliberately broken plan, clears the real one, then runs both executors against the same failure.
- **`replanning_critic.ipynb`** — step-by-step notebook: a markdown why before each small code step, built cell by cell.

## Run it
```bash
# from the repo root; no dependencies, no API key, no network
python3 part-04-replanning-and-critic/replanning_critic.py          # runs offline
# optional: set OPENAI_API_KEY to see the real LLM planner banner (still falls through to the rule planner/critic)
```
Prefer it step by step? Open `replanning_critic.ipynb` in Jupyter, or click **Open in Colab** above.

## Key idea
Two mechanisms fix a broken plan, one before execution and one during. The prospective CRITIC runs on the plan as data: on a deliberately broken first draft it reports four problems before anything executes, then clears the real quote plan. The BLIND executor (Part 3, no critic, no replanner) shows why feeding an error back is necessary but not sufficient: it learns the SKU is dead, dutifully feeds the permanent error back as an observation, and still produces nothing usable, because it cannot revise a plan that names a dead SKU in three places:

```
QUOTE: INCOMPLETE -- price=unavailable, warranty=unavailable, total=uncomputable.
```

The CRITIC + REPLANNER executor hits the same failure and recovers. On the first `DiscontinuedError` it rewrites only the not-yet-run tail to the replacement SKU, keeps the already-completed lookup memoized, and continues under the replan budget:

```
REPLAN #1: rewrite remaining ['E2', 'E3'] to SKU-GLX-EB; memoized ['E1'] stay (not re-run).
```

The revised tail then resolves to $79.00 and a 2-year limited warranty, E4's calculator runs on the bound price (E4 carries no SKU, so it is not in the revised tail), and the run finishes with a valid quote and 1 replan. Knowing a step failed (Part 2) and being able to revise the committed plan (Part 4) are different things; the replanner is the second. This lineage traces to Plan-and-Execute's replan hook (flagged in Part 3), LLMCompiler-style DAG execution (Kim et al., 2023, arXiv:2312.04511) for the subgraph we revise, and the self-correction line developed further in Part 5.

## Offline by design
The whole demo runs with no network and no API key. A deterministic rule planner and a deterministic rule critic stand in for a trained LLM: the planner emits the same `TaskNode` DAG a single `generate()` call would return, and the critic's four checks and the replanner's tail-rewrite are plain rules you can read, so output is reproducible and the discontinued-SKU failure fires the same way every run. The real path sits behind a flag: set OPENAI_API_KEY and the planner prints a banner noting the real LLM would plan, critique, and replan via `generate()`, then falls through to the deterministic rules so output stays reproducible. Only `generate()` would need edits to light up production. The four critic problems reported, the plan cleared, the replan triggered, the memoized step reused, and every quote line are identical either way.

---
[Series index](../) · [Part 5 — Learning from Failure: in-loop reflection and Reflexion →](../) (coming soon)
