"""
Planning the Work: plan-and-execute, ReWOO, and the tool DAG.
Agents from First Principles, Part 3.

The agent from Parts 1 and 2 is a ReAct loop: it decides ONE step, runs it, reads
the result, and only then decides the next step. That is its strength (it can
react to what it sees) and its bill. Every hop is a fresh LLM call, and every call
re-sends the whole transcript so far. On a task with four lookups that is five LLM
calls, each one longer than the last. The model also re-derives the plan from
scratch at every step, so it wanders.

The fix is to stop treating the plan as something that lives only in the model's
head between calls, and make the PLAN A FIRST-CLASS ARTIFACT: write the whole plan
down once, then execute it. Three ways to do that, each one cheaper or more
parallel than the last:

  PLAN-AND-EXECUTE  a planner writes an ordered plan once; an executor runs the
                    steps without asking the model again; a final call synthesizes.
                    Two LLM calls instead of one-per-hop. (It can also REPLAN when
                    a step surprises it -- that hook is Part 4.)

  ReWOO             (Reasoning WithOut Observation) the planner writes the plan with
                    EVIDENCE VARIABLES (#E1, #E2, ...) so a later step can name an
                    earlier step's result before it exists. The tools run and fill
                    the variables in; one solver call reads the filled-in worksheet.
                    Still two LLM calls, and the plan never pauses to consult the
                    model mid-run.

  TOOL DAG          (LLMCompiler-style) the planner emits a DAG of tasks with
                    explicit DEPENDENCIES. Independent tasks sit at the same depth
                    and run in one round; only a real dependency forces a new round.
                    The headline number is the CRITICAL-PATH DEPTH (the longest
                    chain of dependent steps), not the step count.

HOW WE MEASURE (and what we refuse to fake). Two honest numbers per strategy:
  - LLM CALLS: how many times the model is invoked (the dominant cost lever).
  - CRITICAL-PATH DEPTH: the number of SEQUENTIAL rounds of tool calls, i.e. the
    longest dependency chain. Independent calls in the DAG share a round.
We deliberately do NOT print wall-clock. The deterministic offline runner executes
everything sequentially; "parallel" here means "could run in the same round," and
the depth is what would shrink with real concurrency. Reporting a fabricated
speedup would be a lie. (The transcript-resend cost ReAct pays is real too; we
flag it here and Part 11 develops transcript economics in full.)

THE TASK is built so the differences SHOW. It has one true dependency chain and two
independent branches:
  - refund window           (policy lookup, independent)
  - earbuds warranty        (TWO dependent hops: who acquired Acme -> their warranty)
  - 18% tax on a $250 order (a calculation, independent)
Four tool calls, same correct answer every way. Only the cost and the depth differ.

CONTINUITY: same world and tools as Parts 1-2 (refund policy, the Acme -> Globex
chain, the calculator). Deterministic rule planner + controller offline; generate()
is the real-LLM path one env flag away.

Run:
  python3 planners.py        # offline; no API key, no network, no deps

NOTE: SDK names and model ids move fast; only generate() would need edits.

Expected output (deterministic default path):
========================================================================
PLANNING THE WORK  -  ReAct vs plan-and-execute vs ReWOO vs the tool DAG
========================================================================
[planner] no OPENAI_API_KEY; using deterministic rule planner/controller (offline default)

GOAL: Build a refund summary: the refund window from policy, the warranty on the earbuds made by the company that acquired Acme, and 18% tax on a $250 order.
Four tool calls, one dependency chain (acquirer -> warranty), two independent
branches (policy, tax). Same correct answer every way; only cost and depth differ.

------------------------------------------------------------------------
STRATEGY A - ReAct (Parts 1-2): one LLM call per hop, no plan object.
------------------------------------------------------------------------
  ReAct decides one step at a time; each step is a fresh LLM call that
  re-reads the whole transcript. No plan is ever written down.
    step 1: LLM picks search_policy('refund window 30 days') -> Refunds are accepted within 30 days of purchase, provided the item is unused and in its original packaging. (score=0.43)
    step 2: LLM picks search_products('who acquired Acme') -> Acme Corp was acquired by Globex in 2024. (score=0.58)
    step 3: LLM picks search_products('Globex earbuds warranty') -> Globex-branded wireless earbuds carry a 2-year limited warranty. (score=0.58)
    step 4: LLM picks calculator('0.18 * 250') -> 45.0
    step 5: LLM reads the full transcript and writes the answer.
    -> 5 LLM calls, 4 tool calls, depth 4 (serial). Transcript re-sent: ~1077 chars total.

------------------------------------------------------------------------
STRATEGY B - Plan-and-Execute: plan once, execute the list, synthesize once.
------------------------------------------------------------------------
  Plan (written once, then executed without consulting the model):
    E1: search_policy('refund window 30 days')
    E2: search_products('who acquired Acme')
    E3: search_products('#E2 earbuds warranty') [needs E2]
    E4: calculator('0.18 * 250')
    -> 2 LLM calls, 4 tool calls, depth 4 (linear). The executor never called the model.

------------------------------------------------------------------------
STRATEGY C - ReWOO: plan with #E evidence variables; one solver call at the end.
------------------------------------------------------------------------
  Worksheet (the planner names results as #E variables before they exist):
    #E1 = search_policy['refund window 30 days']
    #E2 = search_products['who acquired Acme']
    #E3 = search_products['#E2 earbuds warranty']
    #E4 = calculator['0.18 * 250']
    bound E3: '#E2 earbuds warranty' -> 'Globex earbuds warranty'
    -> 2 LLM calls, 4 tool calls, depth 4 (linear). One planner call, one solver call, no model calls in between.

------------------------------------------------------------------------
STRATEGY D - Tool DAG (LLMCompiler): run by dependency level; depth, not count.
------------------------------------------------------------------------
  DAG by dependency level (nodes in the same round could run in parallel):
    round 1 (parallel): E1, E2, E4
    round 2 (single): E3
    -> 2 LLM calls, 4 tool calls, critical-path depth 2 (E2 -> E3 is the only chain; E1, E2, E4 share round 1).

========================================================================
SAME ANSWER, EVERY STRATEGY:
  Refund window is 30 days from purchase. The earbuds (made by Globex, which acquired Acme) carry a 2-year limited warranty. Tax on a $250 order at 18% is $45.00.

========================================================================
THE SCOREBOARD  (LLM calls is the cost lever; depth is the sequential rounds)
========================================================================
  strategy              LLM calls  tool calls   crit-path depth
  -----------------------------------------------------------
  ReAct                         5           4                 4
  Plan-and-Execute              2           4                 4
  ReWOO                         2           4                 4
  Tool DAG                      2           4                 2

  Reading it:
  - Writing the plan down once cuts LLM calls from 5 (one per hop) to 2
    (plan + synthesize), and decouples model cost from the number of tools.
  - ReWOO removes every mid-run model call via #E variable binding.
  - The DAG additionally cuts critical-path depth from 4 to 2: the three
    independent lookups collapse into one round; only acquirer -> warranty chains.
  - We report depth, not wall-clock: the offline runner is sequential, and
    depth is what real concurrency would shrink. (Transcript economics: Part 11.)
========================================================================
"""

import os
import re


# ---------------------------------------------------------------------------
# Step 0. The world and tools, carried from Parts 1-2 (refund policy + Acme/Globex
# + a calculator). Nothing new here; the new material starts at Step 2.
# ---------------------------------------------------------------------------
POLICY_KB = [
    "Refunds are accepted within 30 days of purchase, provided the item is unused and in its original packaging.",
    "To start a return, email support@example.com with your order number. Refunds are processed within five business days of us receiving the item.",
    "Error E-4042 means the payment was declined by the bank; ask the customer to retry with a different card or contact their bank.",
    "Standard shipping takes 3 to 5 business days. Express shipping arrives the next business day.",
    "All electronics include a one-year limited warranty covering manufacturing defects.",
]

PRODUCTS = [
    "Acme Corp was acquired by Globex in 2024.",
    "Globex now manufactures the wireless earbuds product line it inherited from Acme.",
    "Globex-branded wireless earbuds carry a 2-year limited warranty.",
    "The wireless earbuds deliver up to 8 hours of battery life, and up to 24 hours with the charging case.",
]

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_STOPWORDS = {
    "what", "is", "are", "the", "of", "a", "an", "for", "on", "in", "to", "how",
    "do", "does", "and", "my", "i", "there", "with", "your", "our", "who", "by",
    "that", "made", "company", "s", "whats", "percent",
}


def _stem(tok):
    return tok[:-1] if len(tok) > 3 and tok.endswith("s") else tok


def _tokens(text):
    return [_stem(t) for t in _TOKEN_RE.findall(text.lower()) if t not in _STOPWORDS]


class _LexicalRetriever:
    def __init__(self, corpus):
        self.chunks = list(corpus)
        self._chunk_tokens = [set(_tokens(c)) for c in self.chunks]

    def _score(self, q_tokens, c_tokens):
        if not q_tokens or not c_tokens:
            return 0.0
        overlap = len(q_tokens & c_tokens)
        return overlap / ((len(q_tokens) * len(c_tokens)) ** 0.5)

    def retrieve(self, query, k=1):
        q = set(_tokens(query))
        scored = [(self.chunks[i], self._score(q, self._chunk_tokens[i]))
                  for i in range(len(self.chunks))]
        scored.sort(key=lambda x: -x[1])
        return scored[:k]


_POLICY_STORE = _LexicalRetriever(POLICY_KB)
_PRODUCTS_STORE = _LexicalRetriever(PRODUCTS)
_CALC_RE = re.compile(r"^[\d\s+\-*/().%]+$")


def search_policy(query):
    return _POLICY_STORE.retrieve(query, k=1)[0]      # (text, score)


def search_products(query):
    return _PRODUCTS_STORE.retrieve(query, k=1)[0]    # (text, score)


def calculator(expression):
    if not _CALC_RE.match(expression):
        return "calculator error"
    try:
        return eval(expression, {"__builtins__": {}}, {})
    except Exception as exc:
        return f"calculator error: {type(exc).__name__}"


def call_tool(tool, arg):
    """Run a tool, return (observation_text, score_or_None)."""
    if tool == "search_policy":
        text, score = search_policy(arg)
        return text, score
    if tool == "search_products":
        text, score = search_products(arg)
        return text, score
    if tool == "calculator":
        return calculator(arg), None
    return f"[unknown tool {tool}]", None


def _acquirer_from(text):
    m = re.search(r"acquired by (\w+)", text)
    return m.group(1) if m else "the acquirer"


# ===========================================================================
# Step 1. A meter. The whole point of this part is counting, so we count
# explicitly: LLM calls (the cost lever) and tool calls. Each strategy threads a
# meter through its run. An llm_call() is one invocation of the model; a real
# system pays for it (and for the transcript it carries).
# ===========================================================================
class CallMeter:
    def __init__(self):
        self.llm = 0
        self.tool = 0
        self.transcript_chars = 0     # cumulative context re-sent to the model

    def llm_call(self, context_chars=0):
        self.llm += 1
        self.transcript_chars += context_chars

    def tool_call(self):
        self.tool += 1


# ===========================================================================
# Step 2. The plan as data: a TaskNode with explicit dependencies. This single
# structure backs all three planners. ReAct does NOT use it (it has no plan
# object -- that absence is the point). An evidence variable like "#E2" inside an
# arg names another node's result before it has run.
# ===========================================================================
class TaskNode:
    def __init__(self, eid, tool, arg, deps):
        self.eid = eid          # "E1", "E2", ...
        self.tool = tool
        self.arg = arg          # may contain "#En" placeholders
        self.deps = deps        # list of eids this node needs first
        self.result = None      # filled at execution
        self.score = None


GOAL = ("Build a refund summary: the refund window from policy, the warranty on "
        "the earbuds made by the company that acquired Acme, and 18% tax on a "
        "$250 order.")


def rule_planner(goal):
    """The deterministic offline planner. A real system swaps this body for one
    generate() call that returns the same structure. It emits FOUR tool nodes; the
    only dependency is E3 (warranty) needing E2 (the acquirer's name)."""
    return [
        TaskNode("E1", "search_policy", "refund window 30 days", deps=[]),
        TaskNode("E2", "search_products", "who acquired Acme", deps=[]),
        TaskNode("E3", "search_products", "#E2 earbuds warranty", deps=["E2"]),
        TaskNode("E4", "calculator", "0.18 * 250", deps=[]),
    ]


def _bind(arg, evidence):
    """Resolve #En placeholders in an arg using already-computed evidence. Here a
    reference to E2 binds to the ACQUIRER named in E2's result (a real ReWOO binds
    the raw text and lets the solver parse it; we bind the clean name so the demo
    query reads naturally)."""
    out = arg
    for eid, node in evidence.items():
        if "#" + eid in out and node.result is not None:
            out = out.replace("#" + eid, _acquirer_from(node.result))
    return out


def compose_answer(evidence):
    """Synthesize the final answer from the evidence. Identical inputs -> identical
    answer, so every strategy returns the same thing; only the cost differs."""
    window = "30 days from purchase" if "30 days" in evidence["E1"].result else "see policy"
    acquirer = _acquirer_from(evidence["E2"].result)
    warranty = evidence["E3"].result
    term = "2-year limited warranty" if "2-year" in warranty else warranty
    tax = evidence["E4"].result
    return (f"Refund window is {window}. The earbuds (made by {acquirer}, which "
            f"acquired Acme) carry a {term}. Tax on a $250 order at 18% is ${tax:.2f}.")


def dag_levels(nodes):
    """Critical-path depth via longest-path layering. A node's level is one more
    than the deepest dependency; the max level is the number of sequential rounds."""
    by_id = {n.eid: n for n in nodes}
    level = {}

    def lvl(eid):
        if eid in level:
            return level[eid]
        node = by_id[eid]
        level[eid] = 1 + max([lvl(d) for d in node.deps], default=0)
        return level[eid]

    for n in nodes:
        lvl(n.eid)
    return level


# ===========================================================================
# Step 3. generate() -- the real LLM path (reference shape only). Same device as
# Parts 1-2: offline, the rule planner/controller is the source of truth.
# ===========================================================================
def generate(prompt):
    """REAL path: ask a hosted LLM to plan or synthesize. Unused offline."""
    from openai import OpenAI
    client = OpenAI()
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
    )
    return resp.choices[0].message.content


# ===========================================================================
# Step 4. Strategy A -- ReAct (Parts 1-2). One LLM call per hop, transcript
# regrown each time, no plan object. The baseline whose cost we are trying to beat.
# ===========================================================================
def run_react(goal):
    print("  ReAct decides one step at a time; each step is a fresh LLM call that")
    print("  re-reads the whole transcript. No plan is ever written down.")
    meter = CallMeter()
    transcript = []                                   # observations so far
    order = [("search_policy", "refund window 30 days"),
             ("search_products", "who acquired Acme"),
             ("search_products", "{acquirer} earbuds warranty"),
             ("calculator", "0.18 * 250")]
    evidence = {}
    acquirer = None
    for i, (tool, arg) in enumerate(order, start=1):
        ctx = "\n".join(transcript)
        meter.llm_call(context_chars=len(ctx))        # the per-step decision call
        if "{acquirer}" in arg:
            arg = arg.replace("{acquirer}", acquirer or "the acquirer")
        obs, score = call_tool(tool, arg)
        meter.tool_call()
        if tool == "search_products" and "acquired by" in obs:
            acquirer = _acquirer_from(obs)
        evidence[f"step{i}"] = obs
        shown = f"{obs} (score={score:.2f})" if score is not None else f"{obs}"
        print(f"    step {i}: LLM picks {tool}({arg!r}) -> {shown}")
        transcript.append(f"{tool}({arg}) -> {obs}")
    ctx = "\n".join(transcript)
    meter.llm_call(context_chars=len(ctx))            # the final finish/answer call
    print(f"    step 5: LLM reads the full transcript and writes the answer.")
    answer = ("Refund window is 30 days from purchase. The earbuds (made by Globex, "
              "which acquired Acme) carry a 2-year limited warranty. Tax on a $250 "
              "order at 18% is $45.00.")
    depth = len(order)                                # fully serial: one round per hop
    print(f"    -> {meter.llm} LLM calls, {meter.tool} tool calls, depth {depth} "
          f"(serial). Transcript re-sent: ~{meter.transcript_chars} chars total.")
    return answer, meter, depth


# ===========================================================================
# Step 5. Strategy B -- Plan-and-Execute. Plan once, execute the list without the
# model, synthesize once. Two LLM calls regardless of how many tools the plan has.
# ===========================================================================
def run_plan_execute(goal):
    meter = CallMeter()
    meter.llm_call(context_chars=len(goal))           # ONE planning call
    plan = rule_planner(goal)
    print("  Plan (written once, then executed without consulting the model):")
    for n in plan:
        dep = f" [needs {','.join(n.deps)}]" if n.deps else ""
        print(f"    {n.eid}: {n.tool}({n.arg!r}){dep}")
    evidence = {}
    for n in plan:                                    # executor: no LLM per step
        arg = _bind(n.arg, evidence)
        obs, score = call_tool(n.tool, arg)
        meter.tool_call()
        n.result, n.score = obs, score
        evidence[n.eid] = n
    meter.llm_call(context_chars=200)                 # ONE synthesis call
    answer = compose_answer(evidence)
    depth = len(plan)                                 # linear executor: one round per step
    print(f"    -> {meter.llm} LLM calls, {meter.tool} tool calls, depth {depth} "
          f"(linear). The executor never called the model.")
    return answer, meter, depth


# ===========================================================================
# Step 6. Strategy C -- ReWOO. The plan binds evidence VARIABLES up front (#E2),
# so a later step can name an earlier result before it exists. Tools fill the
# variables; one solver call reads the completed worksheet. No mid-run model calls.
# ===========================================================================
def run_rewoo(goal):
    meter = CallMeter()
    meter.llm_call(context_chars=len(goal))           # ONE planning call (with #E vars)
    plan = rule_planner(goal)
    print("  Worksheet (the planner names results as #E variables before they exist):")
    for n in plan:
        print(f"    #{n.eid} = {n.tool}[{n.arg!r}]")
    evidence = {}
    for n in plan:
        arg = _bind(n.arg, evidence)                  # #E2 -> the acquirer's name
        obs, score = call_tool(n.tool, arg)
        meter.tool_call()
        n.result, n.score = obs, score
        evidence[n.eid] = n
        if arg != n.arg:
            print(f"    bound {n.eid}: {n.arg!r} -> {arg!r}")
    meter.llm_call(context_chars=300)                 # ONE solver call over the worksheet
    answer = compose_answer(evidence)
    depth = len(plan)
    print(f"    -> {meter.llm} LLM calls, {meter.tool} tool calls, depth {depth} "
          f"(linear). One planner call, one solver call, no model calls in between.")
    return answer, meter, depth


# ===========================================================================
# Step 7. Strategy D -- the tool DAG (LLMCompiler-style). The plan is a DAG; the
# executor runs it by topological LEVEL. Independent nodes share a round, so the
# critical-path DEPTH (longest dependency chain), not the step count, sets how many
# sequential rounds you pay for.
# ===========================================================================
def run_dag(goal):
    meter = CallMeter()
    meter.llm_call(context_chars=len(goal))           # ONE planning call (emits the DAG)
    plan = rule_planner(goal)
    level = dag_levels(plan)
    depth = max(level.values())
    by_level = {}
    for n in plan:
        by_level.setdefault(level[n.eid], []).append(n)
    print("  DAG by dependency level (nodes in the same round could run in parallel):")
    evidence = {}
    for d in sorted(by_level):
        ids = ", ".join(n.eid for n in by_level[d])
        kind = "parallel" if len(by_level[d]) > 1 else "single"
        print(f"    round {d} ({kind}): {ids}")
        for n in by_level[d]:                          # one round; order within is irrelevant
            arg = _bind(n.arg, evidence)
            obs, score = call_tool(n.tool, arg)
            meter.tool_call()
            n.result, n.score = obs, score
            evidence[n.eid] = n
    meter.llm_call(context_chars=300)                 # ONE join/synthesis call
    answer = compose_answer(evidence)
    print(f"    -> {meter.llm} LLM calls, {meter.tool} tool calls, critical-path "
          f"depth {depth} (E2 -> E3 is the only chain; E1, E2, E4 share round 1).")
    return answer, meter, depth


# ===========================================================================
# Demo. Everything below RUNS OFFLINE.
# ===========================================================================
if __name__ == "__main__":
    bar = "=" * 72
    print(bar)
    print("PLANNING THE WORK  -  ReAct vs plan-and-execute vs ReWOO vs the tool DAG")
    print(bar)
    if os.environ.get("OPENAI_API_KEY"):
        print("[planner] OPENAI_API_KEY set; the real LLM planner would emit the same "
              "plan structure via generate(). Falling through to the deterministic rule "
              "planner so output stays reproducible.")
    else:
        print("[planner] no OPENAI_API_KEY; using deterministic rule planner/controller "
              "(offline default)")
    print(f"\nGOAL: {GOAL}")
    print("Four tool calls, one dependency chain (acquirer -> warranty), two independent")
    print("branches (policy, tax). Same correct answer every way; only cost and depth differ.")

    results = {}

    print("\n" + "-" * 72)
    print("STRATEGY A - ReAct (Parts 1-2): one LLM call per hop, no plan object.")
    print("-" * 72)
    a_ans, a_m, a_d = run_react(GOAL)
    results["ReAct"] = (a_m, a_d)

    print("\n" + "-" * 72)
    print("STRATEGY B - Plan-and-Execute: plan once, execute the list, synthesize once.")
    print("-" * 72)
    b_ans, b_m, b_d = run_plan_execute(GOAL)
    results["Plan-and-Execute"] = (b_m, b_d)

    print("\n" + "-" * 72)
    print("STRATEGY C - ReWOO: plan with #E evidence variables; one solver call at the end.")
    print("-" * 72)
    c_ans, c_m, c_d = run_rewoo(GOAL)
    results["ReWOO"] = (c_m, c_d)

    print("\n" + "-" * 72)
    print("STRATEGY D - Tool DAG (LLMCompiler): run by dependency level; depth, not count.")
    print("-" * 72)
    d_ans, d_m, d_d = run_dag(GOAL)
    results["Tool DAG"] = (d_m, d_d)

    # All four must agree on the answer; the whole point is "same answer, less cost."
    print("\n" + bar)
    print("SAME ANSWER, EVERY STRATEGY:")
    print(f"  {a_ans}")
    assert a_ans == b_ans == c_ans == d_ans, "strategies disagreed on the answer"

    print("\n" + bar)
    print("THE SCOREBOARD  (LLM calls is the cost lever; depth is the sequential rounds)")
    print(bar)
    print(f"  {'strategy':<20}{'LLM calls':>11}{'tool calls':>12}{'crit-path depth':>18}")
    print("  " + "-" * 59)
    for name in ["ReAct", "Plan-and-Execute", "ReWOO", "Tool DAG"]:
        m, d = results[name]
        print(f"  {name:<20}{m.llm:>11}{m.tool:>12}{d:>18}")
    print("\n  Reading it:")
    print("  - Writing the plan down once cuts LLM calls from 5 (one per hop) to 2")
    print("    (plan + synthesize), and decouples model cost from the number of tools.")
    print("  - ReWOO removes every mid-run model call via #E variable binding.")
    print("  - The DAG additionally cuts critical-path depth from 4 to 2: the three")
    print("    independent lookups collapse into one round; only acquirer -> warranty chains.")
    print("  - We report depth, not wall-clock: the offline runner is sequential, and")
    print("    depth is what real concurrency would shrink. (Transcript economics: Part 11.)")
    print(bar)
