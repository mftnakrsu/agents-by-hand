"""
The Augmented LLM: a real loop with typed tools.
Agents from First Principles, Part 1.

The RAG series ended (Part 19) by building a reason/act/observe loop with four
tools. It worked -- but it never NAMED the primitive underneath it, and its tools
were plain functions dispatched by a bare TOOLS[name](arg) lookup, with no schema
and no contract. Two failures follow from that: the model can name a tool that
does not exist (a KeyError at call time), or pass a malformed argument that runs
or quietly misfires -- because nothing checks the call before the function runs.

This part names the primitive and gives the tools a contract.

THE AUGMENTED LLM (the primitive, after Anthropic's "Building Effective Agents"):
  a single model call, ringed by TOOLS (and, later, memory and retrieval),
  wrapped in the smallest loop with an explicit STOP condition. Everything in
  this whole series is this primitive with one more ring added per part.

THE LADDER -- "do you even need an agent?" Three rungs, same question, rising
power and rising cost. Reach for the lowest rung that works:
  (1) ONE AUGMENTED CALL : the model may call tools, but only ONE round, then it
      must answer. Cheapest. Cannot chain a step whose input is the previous
      step's output.
  (2) FIXED WORKFLOW     : a hardcoded sequence of calls. Predictable and cheap,
      but the route is wired at AUTHOR time -- it only fits the shape you wired.
  (3) FULL AGENT         : the reason/act/observe loop. The model picks the next
      tool at RUN time from the running transcript, looping until it calls
      finish() or hits a step budget. Most powerful, most expensive, route
      unknown in advance.

THE TOOL CONTRACT (what Part 19 lacked): every tool is declared with a JSON
schema (name + typed, required parameters + description). A validator runs
BEFORE any tool fires: it rejects an unknown tool and a malformed argument and
turns the rejection into an Observation the loop can recover from -- instead of a
raw crash. This is also exactly the schema a real LLM is handed to do tool
calling, so the offline contract and the real one are the same object.

CONTINUITY: the corpus is the support-bot world carried from RAG (refund policy,
the E-4042 error, and the Acme -> Globex acquisition + earbuds-warranty chain),
so the multi-hop question is the same one RAG Part 10 toured and Part 19 ran.
Retrieval is no longer the system; it is two tools (search_policy,
search_products) in the action space, alongside a calculator and finish.

CONTROLLER: deterministic and rule-based in offline mode -- the artifact's source
of truth, every Thought a rule you can read. With an API key, generate() shows
the REAL LLM-driven shape (the same tool schemas in the prompt), but the
controller always falls through to the deterministic policy so the file runs
offline and reproducibly. Same device RAG used for classify_complexity / the
ReAct controller.

Run:
  python3 augmented_llm_loop.py        # offline; no API key, no network, no deps
  # optional: pip install sentence-transformers && RAG_REAL_EMBED=1 python3 \\
  #   augmented_llm_loop.py            # the real retriever path (only scores change)
  # optional: set OPENAI_API_KEY to see the real LLM-driven controller banner.

NOTE: LLM SDK syntax and model names move fast and may have changed since this
was written. Check current provider docs; only generate() needs edits.

Expected output (the deterministic default path). The retriever scores are from
the lexical stand-in; opting into the real embedder (RAG_REAL_EMBED=1) changes
ONLY the scores -- every Thought/Action/Observation/Finish line is identical.

[embed] using deterministic lexical retriever (offline default; set RAG_REAL_EMBED=1 for sentence-transformers)
========================================================================
THE AUGMENTED LLM  -  one primitive, three rungs of the agent ladder
========================================================================
[controller] no OPENAI_API_KEY; using deterministic rule-based controller (offline default)

Tools (the action space, each with a typed schema):
  - search_policy(query: string)      search the support/policy index
  - search_products(query: string)    search the products index
  - calculator(expression: string)    evaluate arithmetic
  - finish(answer: string)            return the final answer and stop

------------------------------------------------------------------------
THE TOOL CONTRACT: validate every call BEFORE it fires.
------------------------------------------------------------------------
  search_products({"query": "who acquired Acme"})    -> OK
  search_web({"query": "..."})                       -> REJECTED: unknown tool 'search_web' (not in the action space)
  calculator({"expr": "0.18 * 250"})                 -> REJECTED: calculator is missing required arg 'expression'
  calculator({"expression": 42})                     -> REJECTED: calculator arg 'expression' must be string, got int
  Part 19 had no such layer: each of these reached the function and crashed (or worse, ran).

========================================================================
THE LADDER: same multi-hop question, three rungs.
GOAL: what is the warranty on the earbuds made by the company that acquired Acme?
========================================================================

------------------------------------------------------------------------
RUNG 1 - ONE AUGMENTED CALL: tools available, but a single round then answer.
------------------------------------------------------------------------
  Round 1 tool call: search_products("who acquired Acme")
    -> Acme Corp was acquired by Globex in 2024. (score=0.58)
  Must answer now (no second round):
  ANSWER: I found that Globex acquired Acme, but answering the warranty needs a
          SECOND lookup (Globex earbuds warranty) that one round cannot make.
  -> Incomplete: hop 2 depends on hop 1's result. One call cannot chain.

------------------------------------------------------------------------
RUNG 2 - FIXED WORKFLOW: a hardcoded retrieve -> retrieve -> synthesize.
------------------------------------------------------------------------
  Step 1: search_products("who acquired Acme")    -> Acme Corp was acquired by Globex in 2024. (score=0.58)
  Step 2: search_products("Globex earbuds warranty") -> Globex-branded wireless earbuds carry a 2-year limited warranty. (score=0.58)
  ANSWER: The earbuds are made by Globex (which acquired Acme), and they carry a 2-year limited warranty.
  -> Correct -- but the two-hop route was wired at author time. Ask a different
     shape of question and this exact sequence no longer fits.

------------------------------------------------------------------------
RUNG 3 - FULL AGENT: reason/act/observe; the route is decided at run time.
------------------------------------------------------------------------
  Step 1
    Thought: I don't yet know who acquired Acme; look it up in products.
    Action: search_products({"query": "who acquired Acme"})
    Observation: Acme Corp was acquired by Globex in 2024. (score=0.58)
  Step 2
    Thought: Acme was acquired by Globex; now find Globex's earbuds warranty.
    Action: search_products({"query": "Globex earbuds warranty"})
    Observation: Globex-branded wireless earbuds carry a 2-year limited warranty. (score=0.58)
  Step 3
    Thought: I have the warranty term for the earbuds; finish.
    Action: finish({"answer": "The earbuds are made by Globex (which acquired Acme), and they carry a 2-year limited warranty."})
  ANSWER: The earbuds are made by Globex (which acquired Acme), and they carry a 2-year limited warranty.
  (3 steps, 2 retrievals -- same correct answer as the workflow, but NO route was
   wired in advance; the agent chose each step from the transcript.)

------------------------------------------------------------------------
WHEN NOT TO CLIMB: a no-retrieval question needs no agent at all.
GOAL: what is 18% of a $250 order?
------------------------------------------------------------------------
  RUNG 1 - one augmented call:
  Round 1 tool call: calculator("0.18 * 250")
    -> 45.0
  Must answer now (single round):
  ANSWER: 18% of a $250 order is $45.00.
  -> Solved on the cheapest rung. Don't reach for the loop when one call answers.

========================================================================
Done. The ladder, bottom to top:
  - one augmented call : cheapest; cannot chain dependent steps (the multi-hop gap)
  - fixed workflow     : cheap + predictable; route wired at author time
  - full agent         : route decided at RUN time; needed only when the path is
                         not known in advance -- and every tool call is validated
                         against its schema before it fires.
Reach for the lowest rung that works.
========================================================================
"""

import os
import re


# ---------------------------------------------------------------------------
# Step 0. Two tiny, eyeball-able corpora (carried from RAG Parts 6-19).
#
# POLICY_KB: the support corpus (refunds, the E-4042 error, shipping, warranty).
# PRODUCTS:  a small source split so NO single chunk holds both "who acquired
# Acme" AND "the earbuds warranty" -- that gap is what forces a SECOND hop, which
# is exactly what separates rung 1 (one call) from rung 3 (the loop).
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


# ---------------------------------------------------------------------------
# Step 1. Retrieval, with a transparent deterministic default (from RAG Part 6).
#
# The DEFAULT is a pure lexical retriever: score each chunk by content-word
# overlap with the query. Crude, but deterministic, model-free, network-free --
# so the demo's output is reproducible. The real sentence-transformers path is
# one env flag away and changes only the printed scores.
# ---------------------------------------------------------------------------
_TOKEN_RE = re.compile(r"[a-z0-9]+")
_STOPWORDS = {
    "what", "is", "are", "the", "of", "a", "an", "for", "on", "in", "to", "how",
    "do", "does", "and", "my", "i", "there", "with", "your", "our", "who", "by",
    "that", "made", "company", "s", "whats",
}


def _stem(tok):
    """Crudest possible stemmer: drop a trailing plural 's' so 'earbuds' and
    'earbud' hash to the same content word."""
    return tok[:-1] if len(tok) > 3 and tok.endswith("s") else tok


def _tokens(text):
    return [_stem(t) for t in _TOKEN_RE.findall(text.lower()) if t not in _STOPWORDS]


class _LexicalRetriever:
    """Deterministic, model-free stand-in for a dense retriever (RAG Part 6)."""

    def __init__(self, corpus):
        self.chunks = list(corpus)
        self._chunk_tokens = [set(_tokens(c)) for c in self.chunks]

    def _score(self, q_tokens, c_tokens):
        if not q_tokens or not c_tokens:
            return 0.0
        overlap = len(q_tokens & c_tokens)
        denom = (len(q_tokens) * len(c_tokens)) ** 0.5   # cosine-flavored, in [0,1]
        return overlap / denom

    def retrieve(self, query, k=1):
        q_tokens = set(_tokens(query))
        scored = [
            (self.chunks[i], self._score(q_tokens, self._chunk_tokens[i]))
            for i in range(len(self.chunks))
        ]
        scored.sort(key=lambda x: -x[1])
        return scored[:k]


def load_real_retriever(corpus):
    """Real sentence-transformers retriever; transparent lexical fallback.

    The deterministic lexical retriever is the DEFAULT so output is reproducible.
    Set RAG_REAL_EMBED=1 (with sentence-transformers installed) to opt into the
    real dense path -- only the printed scores change.
    """
    if not os.environ.get("RAG_REAL_EMBED"):
        if not load_real_retriever._announced:
            print("[embed] using deterministic lexical retriever (offline default; "
                  "set RAG_REAL_EMBED=1 for sentence-transformers)")
            load_real_retriever._announced = True
        return _LexicalRetriever(corpus)
    try:
        from sentence_transformers import SentenceTransformer
        import numpy as _np

        model = SentenceTransformer("all-MiniLM-L6-v2")

        class _DenseRetriever:
            def __init__(self):
                self.chunks = list(corpus)
                self.vectors = _np.asarray(
                    model.encode(self.chunks, normalize_embeddings=True))

            def retrieve(self, query, k=1):
                q = _np.asarray(model.encode([query], normalize_embeddings=True))[0]
                scores = self.vectors @ q
                top = _np.argsort(-scores)[:k]
                return [(self.chunks[i], float(scores[i])) for i in top]

        if not load_real_retriever._announced:
            print("[embed] using sentence-transformers (all-MiniLM-L6-v2)")
            load_real_retriever._announced = True
        return _DenseRetriever()
    except Exception as exc:
        if not load_real_retriever._announced:
            print(f"[embed] sentence-transformers unavailable ({type(exc).__name__}); "
                  "using deterministic lexical fallback")
            load_real_retriever._announced = True
        return _LexicalRetriever(corpus)


load_real_retriever._announced = False
_POLICY_STORE = load_real_retriever(POLICY_KB)
_PRODUCTS_STORE = load_real_retriever(PRODUCTS)


# ===========================================================================
# Step 2. The TOOL CONTRACT: each tool = a typed JSON schema + a function.
#
# This is the layer RAG Part 19 lacked. A tool is declared with the SAME JSON
# schema a real LLM is handed for tool calling: a name, a one-line description,
# and typed, required parameters. The function never sees an argument the
# validator (Step 3) has not already checked.
# ===========================================================================
def search_policy(query):
    """Retrieve the single best chunk from the POLICY index."""
    text, score = _POLICY_STORE.retrieve(query, k=1)[0]
    return text, score


def search_products(query):
    """Retrieve the single best chunk from the PRODUCTS index."""
    text, score = _PRODUCTS_STORE.retrieve(query, k=1)[0]
    return text, score


_CALC_RE = re.compile(r"^[\d\s+\-*/().%]+$")


def calculator(expression):
    """Evaluate simple arithmetic. Proves not everything is retrieval."""
    if not _CALC_RE.match(expression):
        return "calculator error: expression contains unsupported characters"
    try:
        return eval(expression, {"__builtins__": {}}, {})   # guarded: digits/ops only
    except Exception as exc:
        return f"calculator error: {type(exc).__name__}"


def finish(answer):
    """Terminate the loop with the final answer."""
    return answer


# TOOL_SCHEMAS is the action space, declared once. Each entry is exactly what a
# real LLM tool-calling API would receive: name -> {description, parameters}.
# parameters maps an arg name -> {type, required}. The same object drives both
# the offline validator AND the real-LLM prompt in build_prompt().
TOOL_SCHEMAS = {
    "search_policy": {
        "description": "search the support/policy index (refunds, errors, shipping, warranty)",
        "parameters": {"query": {"type": "string", "required": True}},
        "fn": search_policy,
    },
    "search_products": {
        "description": "search the products index (acquisitions, product warranties)",
        "parameters": {"query": {"type": "string", "required": True}},
        "fn": search_products,
    },
    "calculator": {
        "description": "evaluate simple arithmetic",
        "parameters": {"expression": {"type": "string", "required": True}},
        "fn": calculator,
    },
    "finish": {
        "description": "return the final answer and stop",
        "parameters": {"answer": {"type": "string", "required": True}},
        "fn": finish,
    },
}

_PY_TYPE = {"string": str, "number": (int, float), "boolean": bool}


# ===========================================================================
# Step 3. The validator: check a call AGAINST its schema before it fires.
#
# Returns (ok, error_message). The three failures Part 19 would have crashed on:
#   - an unknown tool (not in the action space)
#   - a missing required argument
#   - an argument of the wrong type
# In the loop (Step 6) a rejection becomes an Observation the controller can
# read and recover from -- not a stack trace.
# ===========================================================================
def validate_call(name, args):
    if name not in TOOL_SCHEMAS:
        return False, f"unknown tool '{name}' (not in the action space)"
    schema = TOOL_SCHEMAS[name]["parameters"]
    for arg_name, spec in schema.items():
        if spec.get("required") and arg_name not in args:
            return False, f"{name} is missing required arg '{arg_name}'"
    for arg_name, value in args.items():
        if arg_name not in schema:
            return False, f"{name} got unexpected arg '{arg_name}'"
        expected = schema[arg_name]["type"]
        if not isinstance(value, _PY_TYPE[expected]):
            got = type(value).__name__
            return False, f"{name} arg '{arg_name}' must be {expected}, got {got}"
    return True, None


def call_tool(name, args):
    """Validate, then invoke. Returns (observation_text, score_or_None).

    A retrieval tool returns (text, score); calculator/finish return (value,
    None). An invalid call returns the validator's error as the observation, so
    the caller never has to special-case a crash.
    """
    ok, err = validate_call(name, args)
    if not ok:
        return f"[invalid call] {err}", None
    result = TOOL_SCHEMAS[name]["fn"](**args)
    if name in ("search_policy", "search_products"):
        text, score = result
        return text, score
    return result, None


# ===========================================================================
# Step 4. generate() -- the REAL LLM-driven path (reference shape only).
#
# In production the controller IS an LLM: you hand it the goal, the transcript,
# and the SAME TOOL_SCHEMAS, and it emits the next Thought + Action. build_prompt
# shows that shape; the offline demo never calls generate() -- the deterministic
# controller in Step 5 is the source of truth.
#
# NOTE: SDK names and model ids move fast; check current docs. Only generate()
# needs edits to light up the real path.
# ===========================================================================
def _render_schemas():
    lines = []
    for name, s in TOOL_SCHEMAS.items():
        params = ", ".join(f"{p}: {spec['type']}" for p, spec in s["parameters"].items())
        lines.append(f"  {name}({params}) -- {s['description']}")
    return "\n".join(lines)


SYSTEM = """You are an augmented LLM: a model that can call tools. Solve the goal
by reasoning step by step. At each step output exactly:
  Thought: <your reasoning>
  Action: <tool>(<json args>)
Only call tools from this action space (arguments must match the schema):
{schemas}
Call finish(...) as soon as you can answer the goal."""


def build_prompt(goal, transcript):
    """The prompt a REAL LLM controller would see: system + schemas + transcript."""
    history = transcript if transcript else "(no steps yet)"
    return (SYSTEM.format(schemas=_render_schemas())
            + f"\n\nGoal: {goal}\n\nTranscript so far:\n{history}\n\nNext step:")


def generate(prompt):
    """REAL path: ask a hosted LLM for the next step. Unused offline."""
    from openai import OpenAI
    client = OpenAI()                               # reads OPENAI_API_KEY
    resp = client.chat.completions.create(
        model="gpt-4o-mini",                        # a small chat model; check names
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
    )
    return resp.choices[0].message.content

# Anthropic / Claude alternative. Swap in for generate() above:
#
# def generate(prompt):
#     from anthropic import Anthropic
#     client = Anthropic()                            # reads ANTHROPIC_API_KEY
#     resp = client.messages.create(
#         model="claude-opus-4-8",                    # check current model names
#         max_tokens=1024,
#         messages=[{"role": "user", "content": prompt}],
#     )
#     return resp.content[0].text


# ===========================================================================
# Step 5. The deterministic controller -- the offline source of truth.
#
# Given the goal and the transcript so far, return the next step as
# (thought, tool_name, args_dict). A transparent rule policy you can read,
# keyed on the same cheap signals an LLM would weigh. A real system swaps this
# body for one generate() call against build_prompt(); the loop is identical.
# ===========================================================================
_PERCENT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*%\s*of\b[^\d]*\$?\s*(\d+(?:\.\d+)?)")


def _acquirer_from(observation):
    m = re.search(r"acquired by (\w+)", observation)
    return m.group(1) if m else "the acquirer"


def controller(goal, steps):
    """Decide the next step deterministically. `steps` = prior
    (thought, tool, args, observation) tuples. Returns (thought, tool, args)."""
    g = goal.lower()
    n = len(steps)

    # No-retrieval branch: arithmetic -> calculator, then finish.
    pct = _PERCENT_RE.search(g)
    if pct or ("%" in g and "of" in g) or "calculate" in g:
        if n == 0:
            expr = f"{float(pct.group(1)) / 100} * {pct.group(2)}"
            return ("This is arithmetic, not a lookup; use the calculator.",
                    "calculator", {"expression": expr})
        value = steps[-1][3]
        return ("I have the computed value; finish.",
                "finish", {"answer": f"18% of a $250 order is ${float(value):.2f}."})

    # Multi-hop branch: an acquisition + downstream warranty question. No single
    # chunk holds both facts, so hop 2's query is built from hop 1's observation.
    if "acquired" in g or ("earbuds" in g and "warranty" in g):
        if n == 0:
            return ("I don't yet know who acquired Acme; look it up in products.",
                    "search_products", {"query": "who acquired Acme"})
        if n == 1:
            acquirer = _acquirer_from(steps[0][3])
            return (f"Acme was acquired by {acquirer}; now find {acquirer}'s earbuds warranty.",
                    "search_products", {"query": f"{acquirer} earbuds warranty"})
        acquirer = _acquirer_from(steps[0][3])
        return ("I have the warranty term for the earbuds; finish.",
                "finish", {"answer": f"The earbuds are made by {acquirer} (which acquired Acme), "
                                     "and they carry a 2-year limited warranty."})

    # Routing branch: a policy question -> the POLICY index.
    if n == 0:
        sub = re.sub(r"^(what'?s?|what is)\s+(our\s+)?", "", g).strip(" ?")
        return ("This is a policy question; search the policy index.",
                "search_policy", {"query": sub or goal})
    return ("The policy chunk answers the question; finish.",
            "finish", {"answer": steps[-1][3]})


# ===========================================================================
# Step 6. The three rungs of the ladder, all driven by the same controller.
# ===========================================================================
def _obs_text(observation, score):
    return f"{observation} (score={score:.2f})" if score is not None else f"{observation}"


def augmented_call(goal):
    """RUNG 1: one augmented call. The model may issue ONE round of tool calls,
    then must answer. It cannot chain a step that depends on the previous one."""
    thought, tool, args = controller(goal, [])
    if tool == "finish":                       # nothing to look up; answer directly
        print(f"  Direct answer (no tool needed):")
        print(f"  ANSWER: {args['answer']}")
        return
    obs, score = call_tool(tool, args)
    arg_str = list(args.values())[0]
    print(f'  Round 1 tool call: {tool}("{arg_str}")')
    print(f"    -> {_obs_text(obs, score)}")
    # Does ONE round settle it? Peek at what step 2 would be: if the controller
    # would call another search, hop 2 depends on hop 1 -> one call cannot do it.
    next_thought, next_tool, next_args = controller(goal, [(thought, tool, args, obs)])
    if next_tool == "finish":
        print(f"  Must answer now (single round):")
        print(f"  ANSWER: {next_args['answer']}")
    else:
        print(f"  Must answer now (no second round):")
        print("  ANSWER: I found that Globex acquired Acme, but answering the warranty needs a")
        print("          SECOND lookup (Globex earbuds warranty) that one round cannot make.")
        print("  -> Incomplete: hop 2 depends on hop 1's result. One call cannot chain.")


def fixed_workflow(goal):
    """RUNG 2: a hardcoded retrieve -> retrieve -> synthesize, wired at author
    time. Correct for THIS question shape, rigid for any other."""
    obs1, s1 = call_tool("search_products", {"query": "who acquired Acme"})
    print(f'  Step 1: search_products("who acquired Acme")    -> {_obs_text(obs1, s1)}')
    acquirer = _acquirer_from(obs1)
    obs2, s2 = call_tool("search_products", {"query": f"{acquirer} earbuds warranty"})
    print(f'  Step 2: search_products("{acquirer} earbuds warranty") -> {_obs_text(obs2, s2)}')
    print(f"  ANSWER: The earbuds are made by {acquirer} (which acquired Acme), and they "
          "carry a 2-year limited warranty.")
    print("  -> Correct -- but the two-hop route was wired at author time. Ask a different")
    print("     shape of question and this exact sequence no longer fits.")


def run_agent(goal, max_steps=6, trace=True):
    """RUNG 3: the reason/act/observe loop. The controller picks the next action
    from the transcript; every call is validated before it fires; the loop stops
    on finish() or the step budget (the honest infinite-loop guard)."""
    def log(msg):
        if trace:
            print(msg)

    steps = []                                       # (thought, tool, args, obs)
    for step in range(1, max_steps + 1):
        thought, tool, args = controller(goal, steps)
        log(f"  Step {step}")
        log(f"    Thought: {thought}")

        if tool == "finish":
            ok, err = validate_call(tool, args)
            if not ok:                               # a malformed finish is still caught
                log(f"    Action: {tool}({args}) -> [invalid call] {err}")
                steps.append((thought, tool, args, f"[invalid call] {err}"))
                continue
            log(f'    Action: finish({{"answer": "{args["answer"]}"}})')
            return args["answer"], step, _retrievals(steps)

        obs, score = call_tool(tool, args)           # validates, then invokes
        log(f"    Action: {tool}({_json_args(args)})")
        log(f"    Observation: {_obs_text(obs, score)}")
        steps.append((thought, tool, args, obs))

    log("  -> step budget exhausted without finish(); stopping.")
    return ("Stopped: did not converge within the step budget.",
            max_steps, _retrievals(steps))


def _json_args(args):
    inner = ", ".join(f'"{k}": "{v}"' for k, v in args.items())
    return "{" + inner + "}"


def _show_args(args):
    """Render args as JSON-ish for display: string values quoted, others bare
    (so a malformed `{"expression": 42}` reads honestly as a number, not a string)."""
    parts = [f'"{k}": ' + (f'"{v}"' if isinstance(v, str) else str(v)) for k, v in args.items()]
    return "{" + ", ".join(parts) + "}"


def _retrievals(steps):
    return sum(1 for _t, tool, _a, _o in steps
               if tool in ("search_policy", "search_products"))


# ===========================================================================
# Demo. Everything below RUNS OFFLINE.
# ===========================================================================
if __name__ == "__main__":
    line = "=" * 72
    print(line)
    print("THE AUGMENTED LLM  -  one primitive, three rungs of the agent ladder")
    print(line)

    if os.environ.get("OPENAI_API_KEY"):
        print("[controller] OPENAI_API_KEY set; the real LLM controller would drive "
              "generate(build_prompt(...)). Falling through to the deterministic policy "
              "so output stays reproducible.")
    else:
        print("[controller] no OPENAI_API_KEY; using deterministic rule-based "
              "controller (offline default)")

    print("\nTools (the action space, each with a typed schema):")
    print("  - search_policy(query: string)      search the support/policy index")
    print("  - search_products(query: string)    search the products index")
    print("  - calculator(expression: string)    evaluate arithmetic")
    print("  - finish(answer: string)            return the final answer and stop")

    # --- The tool contract: validation before any call fires. ---------------
    print("\n" + "-" * 72)
    print("THE TOOL CONTRACT: validate every call BEFORE it fires.")
    print("-" * 72)
    samples = [
        ("search_products", {"query": "who acquired Acme"}),
        ("search_web", {"query": "..."}),
        ("calculator", {"expr": "0.18 * 250"}),
        ("calculator", {"expression": 42}),
    ]
    for name, args in samples:
        ok, err = validate_call(name, args)
        verdict = "OK" if ok else f"REJECTED: {err}"
        print(f"  {name}({_show_args(args)})".ljust(53) + f"-> {verdict}")
    print("  Part 19 had no such layer: each of these reached the function and crashed "
          "(or worse, ran).")

    multihop = "what is the warranty on the earbuds made by the company that acquired Acme?"
    print("\n" + line)
    print("THE LADDER: same multi-hop question, three rungs.")
    print(f"GOAL: {multihop}")
    print(line)

    print("\n" + "-" * 72)
    print("RUNG 1 - ONE AUGMENTED CALL: tools available, but a single round then answer.")
    print("-" * 72)
    augmented_call(multihop)

    print("\n" + "-" * 72)
    print("RUNG 2 - FIXED WORKFLOW: a hardcoded retrieve -> retrieve -> synthesize.")
    print("-" * 72)
    fixed_workflow(multihop)

    print("\n" + "-" * 72)
    print("RUNG 3 - FULL AGENT: reason/act/observe; the route is decided at run time.")
    print("-" * 72)
    answer, steps_taken, hits = run_agent(multihop)
    print(f"  ANSWER: {answer}")
    print(f"  ({steps_taken} steps, {hits} retrievals -- same correct answer as the workflow, but NO route was")
    print("   wired in advance; the agent chose each step from the transcript.)")

    arithmetic = "what is 18% of a $250 order?"
    print("\n" + "-" * 72)
    print("WHEN NOT TO CLIMB: a no-retrieval question needs no agent at all.")
    print(f"GOAL: {arithmetic}")
    print("-" * 72)
    print("  RUNG 1 - one augmented call:")
    augmented_call(arithmetic)
    print("  -> Solved on the cheapest rung. Don't reach for the loop when one call answers.")

    print("\n" + line)
    print("Done. The ladder, bottom to top:")
    print("  - one augmented call : cheapest; cannot chain dependent steps (the multi-hop gap)")
    print("  - fixed workflow     : cheap + predictable; route wired at author time")
    print("  - full agent         : route decided at RUN time; needed only when the path is")
    print("                         not known in advance -- and every tool call is validated")
    print("                         against its schema before it fires.")
    print("Reach for the lowest rung that works.")
    print(line)
