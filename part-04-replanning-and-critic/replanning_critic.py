"""
Surviving a Broken Plan: the critic and error-triggered replanning.
Agents from First Principles, Part 4.

Part 3 made the plan a first-class artifact: write the whole DAG down once, then
execute it cheaply. That is a real win, and it buys a new failure. A plan written
up front is a bet that the world will still look the way it did when you planned.
The instant the world disagrees, a committed plan is a liability, and the DAG
executor from Part 3 charges ahead and executes it anyway.

The break we inject is the realistic one: a SKU is DISCONTINUED. The plan was built
to quote a price and warranty for SKU-ACME-EB, but mid-run that product turns out to
be retired and replaced by SKU-GLX-EB. Part 2 already taught us to classify the
failure: a discontinued SKU is a PERMANENT error (retrying the same call cannot
help). Part 2 fed that error back as an observation. That is necessary and NOT
sufficient here, because the agent is now committed to a plan that names a dead SKU
in three places. Knowing the step failed is not the same as being able to do
something about a plan you already wrote.

Two mechanisms fix it, one before execution and one during:

1. A PROSPECTIVE CRITIC. Before a single tool fires, check the plan for the
   structural mistakes a planner makes: an UNKNOWN TOOL (not in the registry), an
   UNSATISFIABLE DEP (a step that needs a node that does not exist), a DEPENDENCY
   CYCLE (a step that transitively needs itself), and a REDUNDANT step (two nodes
   with the identical tool and argument). A bad plan is rejected before it wastes a
   single call. This is the plan-time analog of Part 1's pre-flight argument validator.

2. An ERROR-TRIGGERED REPLANNER. When a step fails in a way that invalidates the
   rest of the plan, do not abandon the run and do not start over. Revise ONLY THE
   REMAINING SUBGRAPH: rewrite the not-yet-run steps to target the replacement,
   keep every completed step MEMOIZED (so it is never re-run), and continue. An
   honest REPLAN BUDGET caps how many times this can happen, so a plan that keeps
   breaking trips out instead of looping forever (the circuit breaker is Part 8).

The contrast we show: a BLIND executor (Part 3, no critic, no replanner) hits the
discontinued SKU, dutifully feeds back the permanent error, and still cannot
produce a valid quote, because it has no way to revise the committed plan. The
CRITIC + REPLANNER executor clears the plan up front, hits the same failure, rewrites
only the dead tail to the replacement SKU, reuses the memoized lookup, and finishes
with a correct quote.

REUSE, not rebuild: the TaskNode, the dependency DAG, and topological execution come
straight from Part 3. This part adds the critic and the replanner around them.

CONTINUITY: same Acme -> Globex world (the acquisition retires the Acme earbuds in
favor of the Globex line). Deterministic rule critic/planner offline; generate() is
the real-LLM path one env flag away.

Run:
  python3 replanning_critic.py        # offline; no API key, no network, no deps

NOTE: SDK names and model ids move fast; only generate() would need edits.

Expected output (deterministic default path):
========================================================================
SURVIVING A BROKEN PLAN  -  the prospective critic and the replanner
========================================================================
[planner] no OPENAI_API_KEY; using deterministic rule planner/critic (offline default)

GOAL: Quote the price, warranty, and tax-included total for the Acme earbuds (SKU-ACME-EB).

------------------------------------------------------------------------
THE CRITIC: catch a bad plan BEFORE it wastes a single tool call.
------------------------------------------------------------------------
  Critiquing a planner's first draft (it has four kinds of mistake):
      - B2: redundant, identical to B1 (get_price('SKU-GLX-EB'))
      - B3: unknown tool 'search_web' (not in the registry)
      - B4: depends on 'B9', which is not in the plan
      - dependency cycle detected (a step transitively depends on itself)
  -> rejected; the planner is asked to try again before anything runs.

  The same critic on the real quote plan:
  plan:  E1=lookup_status('SKU-ACME-EB') | E2=get_price('SKU-ACME-EB') | E3=get_warranty('SKU-ACME-EB') | E4=calculator('#E2 * 1.18')
  levels: E1@L1, E2@L1, E3@L1, E4@L2
  critic: no problems found; cleared for execution.

========================================================================
BLIND EXECUTOR (Part 3 DAG, no critic, no replanner): the world disagrees.
========================================================================
    E1: lookup_status('SKU-ACME-EB') -> SKU-ACME-EB: discontinued, replaced by SKU-GLX-EB
    E2: get_price('SKU-ACME-EB') -> PermanentError: SKU-ACME-EB is discontinued (replaced by SKU-GLX-EB)
         fed back as an observation (Part 2), but the plan still names a dead SKU
    E3: get_warranty('SKU-ACME-EB') -> PermanentError: SKU-ACME-EB is discontinued (replaced by SKU-GLX-EB)
         fed back as an observation (Part 2), but the plan still names a dead SKU
    E4: calculator('#E2 * 1.18') -> calculator error: cannot evaluate (missing input?)
    QUOTE: INCOMPLETE -- price=unavailable, warranty=unavailable, total=uncomputable.
    -> The executor knew the SKU was dead and still could not revise the committed plan.

========================================================================
CRITIC + REPLANNER: clear the plan, hit the failure, rewrite only the tail.
========================================================================
    critic: no problems found; plan cleared for execution.
    E1: lookup_status('SKU-ACME-EB') -> SKU-ACME-EB: discontinued, replaced by SKU-GLX-EB
    E2: get_price('SKU-ACME-EB') -> PermanentError: SKU-ACME-EB is discontinued (replaced by SKU-GLX-EB)
         REPLAN #1: rewrite remaining ['E2', 'E3'] to SKU-GLX-EB; memoized ['E1'] stay (not re-run).
    E2: get_price('SKU-GLX-EB') -> $79.00
    E3: get_warranty('SKU-GLX-EB') -> 2-year limited warranty
    E4: calculator('79.0 * 1.18') -> $93.22
    QUOTE: SKU-GLX-EB (replaces discontinued SKU-ACME-EB): price $79.00, 2-year limited warranty, total with tax $93.22.
    -> Completed with 1 replan(s); the dead tail was rewritten, the lookup reused.

========================================================================
Done. An up-front plan is a bet on a world that can change under you:
  - a prospective CRITIC rejects a structurally broken plan before it runs
  - an error-triggered REPLANNER revises only the remaining subgraph on failure
  - completed steps are MEMOIZED (never re-run); a replan BUDGET stops the loop
Feeding an error back (Part 2) says the step failed; replanning is how a
committed plan does something about it.
========================================================================
"""

import os
import re


# ===========================================================================
# Step 0. The world: a tiny product catalog where one SKU is discontinued and
# points at its replacement. This is the Acme -> Globex acquisition made concrete:
# the Acme earbuds are retired in favor of the Globex line.
# ===========================================================================
CATALOG = {
    "SKU-ACME-EB": {"status": "discontinued", "replacement": "SKU-GLX-EB"},
    "SKU-GLX-EB": {"status": "active", "price": 79.0, "warranty": "2-year limited warranty"},
}


class DiscontinuedError(Exception):
    """A PERMANENT error (Part 2's taxonomy): retrying the same SKU cannot help.
    Carries the replacement so the replanner knows where to point the dead tail."""

    def __init__(self, sku, replacement):
        super().__init__(f"{sku} is discontinued (replaced by {replacement})")
        self.sku = sku
        self.replacement = replacement


# ===========================================================================
# Step 1. The tools. lookup_status reports whether a SKU is live; get_price and
# get_warranty REFUSE a discontinued SKU by raising the permanent error.
# ===========================================================================
def lookup_status(sku):
    rec = CATALOG.get(sku, {"status": "unknown"})
    if rec["status"] == "discontinued":
        return f"{sku}: discontinued, replaced by {rec['replacement']}"
    return f"{sku}: {rec['status']}"


def get_price(sku):
    rec = CATALOG.get(sku, {"status": "unknown"})
    if rec.get("status") == "discontinued":
        raise DiscontinuedError(sku, rec["replacement"])
    return rec.get("price")


def get_warranty(sku):
    rec = CATALOG.get(sku, {"status": "unknown"})
    if rec.get("status") == "discontinued":
        raise DiscontinuedError(sku, rec["replacement"])
    return rec.get("warranty")


_CALC_RE = re.compile(r"^[\d\s+\-*/().]+$")


def calculator(expression):
    if not _CALC_RE.match(expression):
        return "calculator error: cannot evaluate (missing input?)"
    try:
        return eval(expression, {"__builtins__": {}}, {})
    except Exception as exc:
        return f"calculator error: {type(exc).__name__}"


REGISTRY = {
    "lookup_status": lookup_status,
    "get_price": get_price,
    "get_warranty": get_warranty,
    "calculator": calculator,
}


# ===========================================================================
# Step 2. The plan as data -- carried verbatim from Part 3. A TaskNode has an id,
# a tool, an argument (which may carry an #En reference to another node's result),
# and explicit dependencies. We do not rebuild the DAG machinery; we reuse it.
# ===========================================================================
class TaskNode:
    def __init__(self, eid, tool, arg, deps):
        self.eid = eid
        self.tool = tool
        self.arg = arg
        self.deps = deps
        self.result = None


def topo_order(plan):
    """Stable topological order: a node appears after all its dependencies."""
    by_id = {n.eid: n for n in plan}
    done, order = set(), []

    def visit(n):
        if n.eid in done:
            return
        for d in n.deps:
            if d in by_id:
                visit(by_id[d])
        done.add(n.eid)
        order.append(n)

    for n in plan:
        visit(n)
    return order


def dag_levels(plan):
    by_id = {n.eid: n for n in plan}
    level = {}

    def lvl(eid):
        if eid in level:
            return level[eid]
        level[eid] = 1 + max([lvl(d) for d in by_id[eid].deps if d in by_id], default=0)
        return level[eid]

    for n in plan:
        lvl(n.eid)
    return level


def _bind_arg(arg, memo):
    """Resolve #En references using already-computed results (Part 3's binding)."""
    out = arg
    for eid, value in memo.items():
        token = "#" + eid
        if token in out and not isinstance(value, dict):
            out = out.replace(token, f"{value}")
    return out


GOAL = "Quote the price, warranty, and tax-included total for the Acme earbuds (SKU-ACME-EB)."


def rule_planner(sku):
    """Plan a quote for `sku`. E4 (the total) depends on E2 (the price)."""
    return [
        TaskNode("E1", "lookup_status", sku, deps=[]),
        TaskNode("E2", "get_price", sku, deps=[]),
        TaskNode("E3", "get_warranty", sku, deps=[]),
        TaskNode("E4", "calculator", "#E2 * 1.18", deps=["E2"]),
    ]


# ===========================================================================
# Step 3. The PROSPECTIVE CRITIC. Before any tool fires, check the plan for the
# structural mistakes a planner makes. Returns a list of problems; an empty list
# means the plan is cleared for execution. This is the plan-time analog of Part 1's
# pre-flight argument validator.
# ===========================================================================
def _has_cycle(plan):
    by_id = {n.eid: n for n in plan}
    color = {}                                  # 0 unseen, 1 on-stack, 2 done

    def dfs(eid):
        if eid not in by_id:
            return False
        color[eid] = 1
        for d in by_id[eid].deps:
            if color.get(d, 0) == 1:
                return True
            if color.get(d, 0) == 0 and dfs(d):
                return True
        color[eid] = 2
        return False

    return any(color.get(n.eid, 0) == 0 and dfs(n.eid) for n in plan)


def critic(plan, registry):
    problems = []
    ids = {n.eid for n in plan}
    seen = {}
    for n in plan:
        if n.tool not in registry:
            problems.append(f"{n.eid}: unknown tool '{n.tool}' (not in the registry)")
        for d in n.deps:
            if d not in ids:
                problems.append(f"{n.eid}: depends on '{d}', which is not in the plan")
        key = (n.tool, n.arg)
        if key in seen:
            problems.append(f"{n.eid}: redundant, identical to {seen[key]} ({n.tool}({n.arg!r}))")
        else:
            seen[key] = n.eid
    if _has_cycle(plan):
        problems.append("dependency cycle detected (a step transitively depends on itself)")
    return problems


# ===========================================================================
# Step 4. generate() -- the real LLM path (reference shape only). Offline, the
# rule planner/critic is the source of truth (same device as Parts 1-3).
# ===========================================================================
def generate(prompt):
    """REAL path: ask a hosted LLM to plan, critique, or replan. Unused offline."""
    from openai import OpenAI
    client = OpenAI()
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
    )
    return resp.choices[0].message.content


def _fmt(value):
    if isinstance(value, float):
        return f"${value:.2f}"
    return f"{value}"


# ===========================================================================
# Step 5. The BLIND executor (Part 3, unchanged): no critic, no replanner. It
# feeds the permanent error back (Part 2) but cannot revise a committed plan.
# ===========================================================================
def run_blind(plan):
    memo = {}
    for n in topo_order(plan):
        arg = _bind_arg(n.arg, memo)
        try:
            result = REGISTRY[n.tool](arg)
            memo[n.eid] = result
            print(f"    {n.eid}: {n.tool}({arg!r}) -> {_fmt(result)}")
        except DiscontinuedError as exc:
            print(f"    {n.eid}: {n.tool}({arg!r}) -> PermanentError: {exc}")
            print(f"         fed back as an observation (Part 2), but the plan still names a dead SKU")
    price = memo.get("E2")
    warranty = memo.get("E3")
    total = memo.get("E4")
    print("    QUOTE: INCOMPLETE -- "
          f"price={'unavailable' if price is None else _fmt(price)}, "
          f"warranty={'unavailable' if warranty is None else warranty}, "
          f"total={'uncomputable' if not isinstance(total, (int, float)) else _fmt(total)}.")
    print("    -> The executor knew the SKU was dead and still could not revise the committed plan.")
    return memo


# ===========================================================================
# Step 6. The CRITIC + REPLANNER executor. Clear the plan first, then execute the
# DAG; on a plan-invalidating failure, revise ONLY the remaining tail, keep
# completed nodes memoized, and continue under a replan budget.
# ===========================================================================
def run_with_replanning(plan, max_replans=2):
    problems = critic(plan, REGISTRY)
    if problems:
        print("    critic REJECTED the plan before execution:")
        for p in problems:
            print(f"      - {p}")
        return None
    print("    critic: no problems found; plan cleared for execution.")

    order = topo_order(plan)
    memo = {}
    replans = 0
    i = 0
    while i < len(order):
        n = order[i]
        if n.eid in memo:                         # already completed: memoized, skip
            i += 1
            continue
        arg = _bind_arg(n.arg, memo)
        try:
            result = REGISTRY[n.tool](arg)
            memo[n.eid] = result
            print(f"    {n.eid}: {n.tool}({arg!r}) -> {_fmt(result)}")
            i += 1
        except DiscontinuedError as exc:
            if replans >= max_replans:
                print(f"    {n.eid}: DiscontinuedError again; replan budget ({max_replans}) "
                      "exhausted -> stop (the circuit breaker is Part 8).")
                return None
            replans += 1
            tail = order[i:]                       # the not-yet-completed subgraph
            revised = [m.eid for m in tail if exc.sku in m.arg]
            for m in tail:
                if exc.sku in m.arg:
                    m.arg = m.arg.replace(exc.sku, exc.replacement)
            kept = [e for e in memo]               # completed nodes stay put
            print(f"    {n.eid}: {n.tool}({arg!r}) -> PermanentError: {exc}")
            print(f"         REPLAN #{replans}: rewrite remaining {revised} to {exc.replacement}; "
                  f"memoized {kept} stay (not re-run).")
            # do not advance i: retry this node with its revised argument
    price, warranty, total = memo["E2"], memo["E3"], memo["E4"]
    final_sku = order[1].arg                       # E2's (possibly revised) SKU
    print(f"    QUOTE: {final_sku} (replaces discontinued SKU-ACME-EB): price {_fmt(price)}, "
          f"{warranty}, total with tax {_fmt(total)}.")
    print(f"    -> Completed with {replans} replan(s); the dead tail was rewritten, the lookup reused.")
    return memo


# ===========================================================================
# Demo. Everything below RUNS OFFLINE.
# ===========================================================================
if __name__ == "__main__":
    bar = "=" * 72
    print(bar)
    print("SURVIVING A BROKEN PLAN  -  the prospective critic and the replanner")
    print(bar)
    if os.environ.get("OPENAI_API_KEY"):
        print("[planner] OPENAI_API_KEY set; the real LLM would plan/critique/replan via "
              "generate(). Falling through to the deterministic rules so output is reproducible.")
    else:
        print("[planner] no OPENAI_API_KEY; using deterministic rule planner/critic (offline default)")
    print(f"\nGOAL: {GOAL}")

    # --- The prospective critic, on a deliberately broken plan. -------------
    print("\n" + "-" * 72)
    print("THE CRITIC: catch a bad plan BEFORE it wastes a single tool call.")
    print("-" * 72)
    bad_plan = [
        TaskNode("B1", "get_price", "SKU-GLX-EB", deps=[]),
        TaskNode("B2", "get_price", "SKU-GLX-EB", deps=[]),          # redundant with B1
        TaskNode("B3", "search_web", "earbuds review", deps=[]),     # unknown tool
        TaskNode("B4", "calculator", "#B9 * 2", deps=["B9"]),        # depends on missing B9
        TaskNode("B5", "get_warranty", "SKU-GLX-EB", deps=["B6"]),   # B5 <-> B6 cycle
        TaskNode("B6", "lookup_status", "SKU-GLX-EB", deps=["B5"]),
    ]
    print("  Critiquing a planner's first draft (it has four kinds of mistake):")
    for p in critic(bad_plan, REGISTRY):
        print(f"      - {p}")
    print("  -> rejected; the planner is asked to try again before anything runs.")

    print("\n  The same critic on the real quote plan:")
    good_plan = rule_planner("SKU-ACME-EB")
    lv = dag_levels(good_plan)
    print("  plan:  " + " | ".join(f"{n.eid}={n.tool}({n.arg!r})" for n in good_plan))
    print("  levels: " + ", ".join(f"{eid}@L{lv[eid]}" for eid in sorted(lv)))
    gp = critic(good_plan, REGISTRY)
    print(f"  critic: {'no problems found; cleared for execution.' if not gp else gp}")

    # --- Blind executor: knows the SKU is dead, still cannot recover. -------
    print("\n" + bar)
    print("BLIND EXECUTOR (Part 3 DAG, no critic, no replanner): the world disagrees.")
    print(bar)
    run_blind(rule_planner("SKU-ACME-EB"))

    # --- Critic + replanner: revise only the dead tail, reuse the rest. -----
    print("\n" + bar)
    print("CRITIC + REPLANNER: clear the plan, hit the failure, rewrite only the tail.")
    print(bar)
    run_with_replanning(rule_planner("SKU-ACME-EB"))

    print("\n" + bar)
    print("Done. An up-front plan is a bet on a world that can change under you:")
    print("  - a prospective CRITIC rejects a structurally broken plan before it runs")
    print("  - an error-triggered REPLANNER revises only the remaining subgraph on failure")
    print("  - completed steps are MEMOIZED (never re-run); a replan BUDGET stops the loop")
    print("Feeding an error back (Part 2) says the step failed; replanning is how a")
    print("committed plan does something about it.")
    print(bar)
