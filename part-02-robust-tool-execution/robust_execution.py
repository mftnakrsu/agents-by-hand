"""
When Tools Fail: retries, timeouts, and a failure taxonomy.
Agents from First Principles, Part 2.

Part 1 gave every tool a CONTRACT: a typed schema and a validator that rejects an
unknown tool or a malformed argument BEFORE the call fires. That closes the door
on calls that are wrong on paper. It does nothing about the call that is right on
paper and still goes wrong at run time.

A schema-valid tool can still:
  - THROW           a network blip, a 500, a rate limit, a bug in the tool;
  - TIME OUT        the dependency is up but slower than your deadline;
  - RETURN GARBAGE  an empty result, or a payload that passes every type check
                    and still means "I found nothing."
RAG Part 19, and Part 1 here, assumed every tool SUCCEEDS: the loop took whatever
a tool returned as ground truth and marched on. One throw and the whole run is a
stack trace; one empty result silently poisons the answer.

This part wraps tool execution in a layer that EXPECTS failure. Three ideas:

1. A FAILURE TAXONOMY. Not every failure is the same, and the right response
   depends on the KIND. Five categories, one recovery policy each:
     transient      temporary; might work next time   -> RETRY (bounded, backoff)
     permanent      will never work; retrying wastes   -> FEED BACK to the model
     empty-result   call worked, found nothing useful  -> FEED BACK to the model
     malformed      bad arguments (Part 1's validator) -> FEED BACK to the model
     unknown-tool   not in the action space (Part 1)   -> FEED BACK to the model
   "Feed back" means: turn the failure into an OBSERVATION the controller reads
   and reasons about, instead of a crash. The loop survives a bad tool call the
   way it survives a good one.

2. RETRIES with bounded exponential BACKOFF and a TIMEOUT, applied ONLY to
   transient failures. Retrying a permanent error just burns time and money; the
   taxonomy is what tells the two apart.

3. The first SIDE-EFFECTING tool: process_refund(). A read-only tool can be
   retried for free. A tool that MOVES MONEY cannot: if the refund posts and then
   the confirmation times out, a blind retry refunds the customer twice. The fix
   is an IDEMPOTENCY GUARD: the tool records what it did keyed by the order id, so
   a second attempt for the same order returns the first result instead of acting
   again. (A local in-memory guard here; Part 9 hardens it into durable
   idempotency keys that survive a process crash -- effectively-once across a
   replay. This part is the seed; Part 9 is the hardening.)

CONTINUITY: same world as Part 1 (refund policy, the E-4042 error, the
Acme -> Globex chain) and the same deterministic-by-default runtime -- the
controller is a readable rule policy offline, with generate() one env flag away.

Run:
  python3 robust_execution.py        # offline; no API key, no network, no deps

NOTE: SDK names and model ids move fast; only generate() would need edits to light
up the real LLM path.

Expected output (deterministic default path):
========================================================================
WHEN TOOLS FAIL  -  a failure taxonomy, retries, and an idempotent tool
========================================================================
[controller] no OPENAI_API_KEY; using deterministic rule-based controller (offline default)

------------------------------------------------------------------------
THE FAILURE TAXONOMY: five kinds of failure, one recovery policy each.
------------------------------------------------------------------------
  transient     temporary; might succeed if tried again   -> RETRY (bounded, backoff)
  permanent     will never succeed; a retry only wastes    -> FEED BACK to the model
  empty-result  the call worked but found nothing useful   -> FEED BACK to the model
  malformed     arguments fail the schema (Part 1)         -> FEED BACK to the model
  unknown-tool  not in the action space (Part 1)           -> FEED BACK to the model
  "Feed back" = turn the failure into an Observation the controller reads, not a crash.

========================================================================
FAULT INJECTION: drive each branch through the same execute_tool wrapper
(deadline 2.0s, up to 2 retries, backoff x2).
========================================================================

  SCENARIO: flaky-then-succeeds (transient that clears on retry)
    call: flaky_lookup({"query": "today's order count"})
    attempt 1 -> TransientError: temporary upstream failure (HTTP 503)
      transient -> retry 1/2 after 0.5s backoff
    attempt 2 -> TransientError: temporary upstream failure (HTTP 503)
      transient -> retry 2/2 after 1.0s backoff
    attempt 3 -> OK: the dependency recovered and returned the data (score=0.91)
    disposition: RECOVERED, usable result after 3 attempt(s)  [category: ok]

  SCENARIO: timeout (slower than the deadline, every attempt)
    call: slow_lookup({"query": "today's order count"})
    attempt 1 -> ToolTimeout: exceeded the 2.0s deadline (simulated latency ~5.0s)
      transient -> retry 1/2 after 0.5s backoff
    attempt 2 -> ToolTimeout: exceeded the 2.0s deadline (simulated latency ~5.0s)
      transient -> retry 2/2 after 1.0s backoff
    attempt 3 -> ToolTimeout: exceeded the 2.0s deadline (simulated latency ~5.0s)
      transient -> retries exhausted (2); give up and feed back as an Observation
    disposition: GAVE UP gracefully after 3 attempts; error fed back as an Observation  [category: transient]

  SCENARIO: exception (permanent error: retrying cannot help)
    call: broken_lookup({"query": "today's order count"})
    attempt 1 -> PermanentError: 404: index 'archive' does not exist
      permanent -> FEED BACK to the model
    disposition: fed back as an Observation; not retried  [category: permanent]

  SCENARIO: empty-result (the call worked, found nothing)
    call: empty_lookup({"query": "today's order count"})
    attempt 1 -> returned, but EMPTY
      empty-result -> FEED BACK to the model
    disposition: fed back as an Observation; not retried  [category: empty-result]

  SCENARIO: unknown-tool (the model invented a tool)
    call: search_web({"query": "today's order count"})
    pre-flight -> unknown-tool: unknown tool 'search_web' (not in the action space)
    disposition: fed back as an Observation; not retried  [category: unknown-tool]

  SCENARIO: malformed (missing the required argument)
    call: flaky_lookup({"q": "today's order count"})
    pre-flight -> malformed: flaky_lookup is missing required arg 'query'
    disposition: fed back as an Observation; not retried  [category: malformed]

========================================================================
THE SIDE-EFFECTING TOOL: a retry must NOT refund the customer twice.
Same transient (refund posts, ack times out), once WITHOUT a guard, once WITH.
========================================================================

  NO GUARD  process_refund_unsafe(ORD-5510, $80.00):
    attempt 1 -> TransientError: refund posted to the gateway, but the confirmation timed out
      transient -> retry 1/2 after 0.5s backoff
    attempt 2 -> OK: refunded $80.00 to ORD-5510
    ledger: 2 refunds posted for ORD-5510 -> $160.00 charged back. DOUBLE REFUND.

  GUARDED   process_refund(ORD-5510, $80.00):
    attempt 1 -> TransientError: refund posted to the gateway, but the confirmation timed out
      transient -> retry 1/2 after 0.5s backoff
    attempt 2 -> OK: already refunded $80.00 to ORD-5510 (idempotent skip; no double-charge)
    ledger: 1 refund recorded for ORD-5510 -> $80.00. Exactly once.
    The retry hit the guard and skipped re-acting. (Part 9 makes the guard durable so it
    survives a process crash, not just this in-memory dict.)

========================================================================
THE ROBUST AGENT: a transient failure mid-run no longer derails it.
GOAL: Process the approved $49.99 refund for order ORD-7788.
========================================================================

  Naive baseline (Part 1 style: call the tool directly, no wrapper):
    process_refund(...) raised TransientError: refund posted to the gateway, but the confirmation timed out
    -> uncaught, the whole run dies on the first transient blip.

  Robust loop (every call through execute_tool):
  Step 1
    Thought: Before moving money, confirm refunds are allowed by policy.
    Action: search_policy({"query": "refund window 30 days"})
    attempt 1 -> OK: Refunds are accepted within 30 days of purchase, provided the item is...
    Observation: Refunds are accepted within 30 days of purchase, provided the item is unused and in its original packaging. (score=0.43)
  Step 2
    Thought: Policy allows the refund; issue it for ORD-7788.
    Action: process_refund({"order_id": "ORD-7788", "amount": 49.99})
    attempt 1 -> TransientError: refund posted to the gateway, but the confirmation timed out
      transient -> retry 1/2 after 0.5s backoff
    attempt 2 -> OK: already refunded $49.99 to ORD-7788 (idempotent skip; no double-charge)
    Observation: already refunded $49.99 to ORD-7788 (idempotent skip; no double-charge)  (resolved after 2 attempts)
  Step 3
    Thought: The refund is recorded exactly once; finish.
    Action: finish({"answer": "Refund of $49.99 for ORD-7788 is complete (processed once, despite a transient gateway timeout)."})
  ANSWER: Refund of $49.99 for ORD-7788 is complete (processed once, despite a transient gateway timeout).
  (3 steps; the refund's first attempt timed out after posting, the retry hit the
   idempotency guard, and the run finished with exactly one refund on the ledger.)

========================================================================
Done. The layer between the loop and its tools:
  - classify every failure (transient / permanent / empty / malformed / unknown)
  - retry ONLY transients, bounded, with backoff; feed everything else back
  - guard side-effecting tools so a retry never acts twice
A schema-valid call can still fail; now a failure is an Observation, not a crash.
========================================================================
"""

import os
import re


# ---------------------------------------------------------------------------
# Step 0. The world, carried verbatim from Part 1 (refund policy + Acme/Globex).
# A single-file read stays self-contained: the two corpora and the lexical
# retriever are the same ones Part 1 used, so nothing here is new -- the new
# material starts at Step 2.
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
    "that", "made", "company", "s", "whats",
}


def _stem(tok):
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
        denom = (len(q_tokens) * len(c_tokens)) ** 0.5
        return overlap / denom

    def retrieve(self, query, k=1):
        q_tokens = set(_tokens(query))
        scored = [(self.chunks[i], self._score(q_tokens, self._chunk_tokens[i]))
                  for i in range(len(self.chunks))]
        scored.sort(key=lambda x: -x[1])
        return scored[:k]


_POLICY_STORE = _LexicalRetriever(POLICY_KB)
_PRODUCTS_STORE = _LexicalRetriever(PRODUCTS)


# ===========================================================================
# Step 1. The taxonomy as exceptions. A tool signals HOW it failed by the TYPE
# it raises, exactly as real code reads an HTTP status or a driver error code
# and decides "retry this" vs "give up on this." Two families:
#   TransientError  -> might clear on a retry          (503, rate limit, timeout)
#   PermanentError  -> will not clear; a retry wastes  (404, bad request, auth)
# A timeout is just a particular transient, so ToolTimeout extends TransientError.
# ===========================================================================
class ToolError(Exception):
    """Base class for a tool failure the wrapper knows how to classify."""


class TransientError(ToolError):
    """Temporary: retrying with backoff may succeed."""


class ToolTimeout(TransientError):
    """The dependency was too slow for the deadline. A kind of transient."""


class PermanentError(ToolError):
    """Will never succeed for this call: do not retry; feed it back instead."""


# The five categories the wrapper resolves a call into, and the one-line policy
# for each. OK is the sixth, happy outcome. These strings are what the trace and
# the figure label.
OK = "ok"
TRANSIENT = "transient"
PERMANENT = "permanent"
EMPTY = "empty-result"
MALFORMED = "malformed"
UNKNOWN = "unknown-tool"

RECOVERY = {
    TRANSIENT: "RETRY (bounded, backoff)",
    PERMANENT: "FEED BACK to the model",
    EMPTY: "FEED BACK to the model",
    MALFORMED: "FEED BACK to the model",
    UNKNOWN: "FEED BACK to the model",
}


# ===========================================================================
# Step 2. The tools. The four read-only tools from Part 1, plus the FIRST
# side-effecting tool: process_refund(). Read-only tools are safe to retry for
# free. process_refund moves money, so it cannot be -- which is the whole point
# of Step 4.
# ===========================================================================
def search_policy(query):
    """Retrieve the single best chunk from the POLICY index."""
    return _POLICY_STORE.retrieve(query, k=1)[0]      # (text, score)


def search_products(query):
    """Retrieve the single best chunk from the PRODUCTS index."""
    return _PRODUCTS_STORE.retrieve(query, k=1)[0]    # (text, score)


_CALC_RE = re.compile(r"^[\d\s+\-*/().%]+$")


def calculator(expression):
    """Evaluate simple arithmetic."""
    if not _CALC_RE.match(expression):
        return "calculator error: expression contains unsupported characters"
    try:
        return eval(expression, {"__builtins__": {}}, {})
    except Exception as exc:
        return f"calculator error: {type(exc).__name__}"


def finish(answer):
    """Terminate the loop with the final answer."""
    return answer


# --- The side-effecting tool, with a local idempotency guard. --------------
# _REFUND_LEDGER is the guard's memory: order_id -> the refund we recorded. The
# guard is the first line of process_refund: if an order is already in the
# ledger, return the recorded result WITHOUT issuing a second refund.
_REFUND_LEDGER = {}     # order_id -> {"amount": float}      (guarded path)
_REFUND_CALLS = {}      # order_id -> attempt count          (deterministic fault)


def process_refund(order_id, amount):
    """Issue a refund for an order. SIDE-EFFECTING and idempotent.

    The failure we simulate is the realistic one: the refund POSTS to the
    gateway, then the confirmation times out before we hear back. A blind retry
    would refund twice. The guard prevents that: the effect is recorded keyed by
    order_id, so the retry sees it and skips re-acting.
    """
    if order_id in _REFUND_LEDGER:                    # IDEMPOTENCY GUARD
        prior = _REFUND_LEDGER[order_id]
        return (f"already refunded ${prior['amount']:.2f} to {order_id} "
                "(idempotent skip; no double-charge)")
    # Record the effect, keyed by the order id, BEFORE the point where we can
    # fail -- so a retry can recognize it. (Part 9 makes this record durable.)
    _REFUND_LEDGER[order_id] = {"amount": amount}
    _REFUND_CALLS[order_id] = _REFUND_CALLS.get(order_id, 0) + 1
    if _REFUND_CALLS[order_id] == 1:                  # first attempt: ack is lost
        raise TransientError("refund posted to the gateway, but the confirmation timed out")
    return f"refunded ${amount:.2f} to {order_id}"


# The UNSAFE twin: identical, but with NO guard. Used once, side by side, to show
# what a blind retry does to a side-effecting tool. Never used in the agent loop.
_UNSAFE_LEDGER = []     # appends one entry per successful POST (duplicates show up)
_UNSAFE_CALLS = {}


def process_refund_unsafe(order_id, amount):
    """A refund tool with no idempotency guard. Double-acts under retry."""
    _UNSAFE_CALLS[order_id] = _UNSAFE_CALLS.get(order_id, 0) + 1
    _UNSAFE_LEDGER.append({"order_id": order_id, "amount": amount})   # the effect
    if _UNSAFE_CALLS[order_id] == 1:
        raise TransientError("refund posted to the gateway, but the confirmation timed out")
    return f"refunded ${amount:.2f} to {order_id}"


# --- Fault-injection tools: a controlled way to make each taxonomy branch fire.
# Each one stands in for a real tool whose dependency misbehaves in one specific
# way. flaky_lookup clears on a retry; slow_lookup blows the deadline; broken_lookup
# is a hard permanent error; empty_lookup succeeds but finds nothing.
_FLAKY_STATE = {}


def flaky_lookup(query):
    """Transient: fails the first two calls (HTTP 503), then recovers."""
    _FLAKY_STATE["n"] = _FLAKY_STATE.get("n", 0) + 1
    if _FLAKY_STATE["n"] <= 2:
        raise TransientError("temporary upstream failure (HTTP 503)")
    return ("the dependency recovered and returned the data", 0.91)


def slow_lookup(query):
    """Too slow for the deadline on every attempt -> times out every time."""
    return ("(a result that never arrives in time)", 0.90)


slow_lookup.latency = 5.0      # simulated seconds; the wrapper's deadline is 2.0


def broken_lookup(query):
    """Permanent: the index does not exist. Retrying cannot fix it."""
    raise PermanentError("404: index 'archive' does not exist")


def empty_lookup(query):
    """The call SUCCEEDS but finds nothing useful. Not an error -- an empty result."""
    return ("", 0.0)


# ===========================================================================
# Step 3. The tool registry (the Part 1 contract), now with the refund tool.
# TOOL_SCHEMAS is the agent's real ACTION SPACE. The fault tools live in a
# separate registry used only by the standalone fault-injection demo, so the
# controller never sees them.
# ===========================================================================
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
    "process_refund": {
        "description": "issue a refund for an order (side-effecting; idempotent by order id)",
        "parameters": {"order_id": {"type": "string", "required": True},
                       "amount": {"type": "number", "required": True}},
        "fn": process_refund,
    },
    "finish": {
        "description": "return the final answer and stop",
        "parameters": {"answer": {"type": "string", "required": True}},
        "fn": finish,
    },
}

_FAULT_TOOLS = {
    "flaky_lookup": {
        "description": "a lookup whose upstream fails transiently then recovers",
        "parameters": {"query": {"type": "string", "required": True}},
        "fn": flaky_lookup,
    },
    "slow_lookup": {
        "description": "a lookup slower than the deadline",
        "parameters": {"query": {"type": "string", "required": True}},
        "fn": slow_lookup,
    },
    "broken_lookup": {
        "description": "a lookup against an index that does not exist",
        "parameters": {"query": {"type": "string", "required": True}},
        "fn": broken_lookup,
    },
    "empty_lookup": {
        "description": "a lookup that succeeds but finds nothing",
        "parameters": {"query": {"type": "string", "required": True}},
        "fn": empty_lookup,
    },
    "process_refund_unsafe": {
        "description": "a refund tool with NO idempotency guard",
        "parameters": {"order_id": {"type": "string", "required": True},
                       "amount": {"type": "number", "required": True}},
        "fn": process_refund_unsafe,
    },
}

_PY_TYPE = {"string": str, "number": (int, float), "boolean": bool}


# --- Part 1's validator, now also returning the taxonomy CATEGORY of a bad call.
def validate_call(name, args, registry):
    """Return (ok, error_message, category). category is None when ok."""
    if name not in registry:
        return False, f"unknown tool '{name}' (not in the action space)", UNKNOWN
    schema = registry[name]["parameters"]
    for arg_name, spec in schema.items():
        if spec.get("required") and arg_name not in args:
            return False, f"{name} is missing required arg '{arg_name}'", MALFORMED
    for arg_name, value in args.items():
        if arg_name not in schema:
            return False, f"{name} got unexpected arg '{arg_name}'", MALFORMED
        expected = schema[arg_name]["type"]
        if not isinstance(value, _PY_TYPE[expected]):
            got = type(value).__name__
            return False, f"{name} arg '{arg_name}' must be {expected}, got {got}", MALFORMED
    return True, None, None


# ===========================================================================
# Step 4. execute_tool(): the robustness layer. Validate (Part 1), then invoke
# under a deadline, classifying every outcome into the taxonomy and applying its
# recovery policy. Transient failures are retried with bounded exponential
# backoff; everything else is fed straight back to the model as an Observation.
# The return value is always a ToolOutcome the loop can read -- never a crash.
# ===========================================================================
MAX_RETRIES = 2          # so up to 3 attempts total (1 try + 2 retries)
BASE_DELAY = 0.5         # seconds before the first retry
BACKOFF = 2.0            # each retry waits BACKOFF x longer: 0.5, 1.0, 2.0, ...
DEFAULT_TIMEOUT = 2.0    # per-call deadline, in (simulated) seconds
EMPTY_THRESHOLD = 0.1    # a retrieval score below this counts as "found nothing"


class ToolOutcome:
    """The resolved result of a tool call: which category it landed in, the
    observation text the loop should read, how many attempts it took, and whether
    it produced a usable result."""

    def __init__(self, category, observation, attempts):
        self.category = category
        self.observation = observation
        self.attempts = attempts
        self.usable = (category == OK)


def _backoff_delay(attempt):
    return BASE_DELAY * (BACKOFF ** (attempt - 1))    # 0.5, 1.0, 2.0, ...


def _sleep(seconds):
    """Offline: we PRINT the planned backoff but do not actually wait, so the
    demo is fast and reproducible. Real code would time.sleep(seconds) here, with
    a little random jitter so a fleet of clients does not retry in lockstep."""
    return None


def _invoke_with_timeout(fn, args, timeout):
    """Enforce a deadline. Real code would run fn in a thread/process and cancel
    it at the deadline (e.g. concurrent.futures .result(timeout=...)). Offline we
    read a simulated latency so a "timeout" is deterministic, not wall-clock."""
    latency = getattr(fn, "latency", 0.0)
    if latency > timeout:
        raise ToolTimeout(f"exceeded the {timeout:.1f}s deadline (simulated latency ~{latency:.1f}s)")
    return fn(**args)


def _unwrap(value):
    if isinstance(value, tuple):                      # a retriever's (text, score)
        return value[0], value[1]
    return value, None


def _obs_text(value):
    text, score = _unwrap(value)
    return f"{text} (score={score:.2f})" if score is not None else f"{text}"


def _short(value, n=72):
    t = _obs_text(value)
    return t if len(t) <= n else t[: n - 3] + "..."


def execute_tool(name, args, registry, timeout=DEFAULT_TIMEOUT, trace=None):
    """Run one tool call robustly. Returns a ToolOutcome; never raises."""
    def emit(line):
        if trace is not None:
            trace.append(line)

    # 1. Pre-flight: the Part 1 contract. Unknown tool / malformed args are not
    #    retried -- a retry would fail identically. Feed them back at once.
    ok, err, cat = validate_call(name, args, registry)
    if not ok:
        emit(f"    pre-flight -> {cat}: {err}")
        return ToolOutcome(cat, f"[{cat}] {err}", attempts=0)

    fn = registry[name]["fn"]
    # 2. Invoke under a deadline, retrying ONLY transient failures.
    for attempt in range(1, MAX_RETRIES + 2):
        try:
            value = _invoke_with_timeout(fn, args, timeout)
        except PermanentError as exc:
            emit(f"    attempt {attempt} -> PermanentError: {exc}")
            emit(f"      {PERMANENT} -> {RECOVERY[PERMANENT]}")
            return ToolOutcome(PERMANENT, f"[{PERMANENT}] {exc}", attempt)
        except TransientError as exc:
            kind = type(exc).__name__
            if attempt <= MAX_RETRIES:
                delay = _backoff_delay(attempt)
                emit(f"    attempt {attempt} -> {kind}: {exc}")
                emit(f"      {TRANSIENT} -> retry {attempt}/{MAX_RETRIES} after {delay:.1f}s backoff")
                _sleep(delay)
                continue
            emit(f"    attempt {attempt} -> {kind}: {exc}")
            emit(f"      {TRANSIENT} -> retries exhausted ({MAX_RETRIES}); give up and feed back as an Observation")
            return ToolOutcome(TRANSIENT, f"[{TRANSIENT}, gave up after {attempt} attempts] {exc}", attempt)

        # 3. Succeeded without raising -- but "succeeded" is not "found something."
        if _is_empty(value):
            emit(f"    attempt {attempt} -> returned, but EMPTY")
            emit(f"      {EMPTY} -> {RECOVERY[EMPTY]}")
            return ToolOutcome(EMPTY, f"[{EMPTY}] the call succeeded but found nothing useful", attempt)
        emit(f"    attempt {attempt} -> OK: {_short(value)}")
        return ToolOutcome(OK, _obs_text(value), attempt)


def _is_empty(value):
    text, score = _unwrap(value)
    if score is not None:
        return (not str(text).strip()) or score < EMPTY_THRESHOLD
    return not str(text).strip()


# ===========================================================================
# Step 5. generate() -- the REAL LLM controller path (reference shape only).
# Identical pattern to Part 1: the offline controller in Step 6 is the source of
# truth; generate() shows what a hosted model would be handed.
# ===========================================================================
def _render_schemas():
    lines = []
    for name, s in TOOL_SCHEMAS.items():
        params = ", ".join(f"{p}: {spec['type']}" for p, spec in s["parameters"].items())
        lines.append(f"  {name}({params}) -- {s['description']}")
    return "\n".join(lines)


SYSTEM = """You are an augmented LLM that can call tools. Solve the goal step by
step. At each step output exactly:
  Thought: <reasoning>
  Action: <tool>(<json args>)
A tool result may come back as an error observation (transient, permanent,
empty-result, malformed, unknown-tool). Read it and adapt: a transient error was
already retried for you; a permanent or empty result means try another approach.
Action space:
{schemas}
Call finish(...) as soon as you can answer the goal."""


def build_prompt(goal, transcript):
    history = transcript if transcript else "(no steps yet)"
    return (SYSTEM.format(schemas=_render_schemas())
            + f"\n\nGoal: {goal}\n\nTranscript so far:\n{history}\n\nNext step:")


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
# Step 6. The deterministic controller -- the offline source of truth. Same
# device as Part 1: a readable rule policy. This part's task is a refund, so the
# rules route a refund goal: confirm the policy, then issue the refund, then
# finish.
# ===========================================================================
_ORDER_RE = re.compile(r"ORD-\d+")
_AMOUNT_RE = re.compile(r"\$\s*(\d+(?:\.\d+)?)")


def controller(goal, steps):
    """Return the next (thought, tool, args) for the refund task."""
    n = len(steps)
    order = _ORDER_RE.search(goal)
    amount = _AMOUNT_RE.search(goal)
    order_id = order.group(0) if order else "ORD-0000"
    amt = float(amount.group(1)) if amount else 0.0

    if n == 0:
        return ("Before moving money, confirm refunds are allowed by policy.",
                "search_policy", {"query": "refund window 30 days"})
    if n == 1:
        return (f"Policy allows the refund; issue it for {order_id}.",
                "process_refund", {"order_id": order_id, "amount": amt})
    return ("The refund is recorded exactly once; finish.",
            "finish", {"answer": f"Refund of ${amt:.2f} for {order_id} is complete "
                                 "(processed once, despite a transient gateway timeout)."})


# ===========================================================================
# Step 7. The agent loop, now driving every tool call through execute_tool so a
# failure becomes an Observation instead of a crash.
# ===========================================================================
def run_agent(goal, registry, max_steps=6):
    steps = []                                        # (thought, tool, args, obs)
    for step in range(1, max_steps + 1):
        thought, tool, args = controller(goal, steps)
        print(f"  Step {step}")
        print(f"    Thought: {thought}")
        print(f"    Action: {tool}({_json_args(args)})")

        if tool == "finish":
            ok, err, _cat = validate_call(tool, args, registry)
            if not ok:
                print(f"      [invalid finish] {err}")
                steps.append((thought, tool, args, f"[invalid] {err}"))
                continue
            return args["answer"], step

        trace = []
        outcome = execute_tool(tool, args, registry, trace=trace)
        for line in trace:
            print(line)
        note = "" if outcome.attempts <= 1 else f"  (resolved after {outcome.attempts} attempts)"
        print(f"    Observation: {outcome.observation}{note}")
        steps.append((thought, tool, args, outcome.observation))

    return "Stopped: did not converge within the step budget.", max_steps


def _json_args(args):
    parts = [f'"{k}": ' + (f'"{v}"' if isinstance(v, str) else str(v)) for k, v in args.items()]
    return "{" + ", ".join(parts) + "}"


def _reset_state():
    """Clear all fault/refund state so each demo section is independent of the
    order the others ran in (keeps the output deterministic)."""
    _FLAKY_STATE.clear()
    _REFUND_LEDGER.clear()
    _REFUND_CALLS.clear()
    _UNSAFE_LEDGER.clear()
    _UNSAFE_CALLS.clear()


# ===========================================================================
# Demo. Everything below RUNS OFFLINE.
# ===========================================================================
def _run_scenario(title, name, args, registry):
    print(f"\n  SCENARIO: {title}")
    print(f"    call: {name}({_json_args(args)})")
    trace = []
    outcome = execute_tool(name, args, registry, trace=trace)
    for line in trace:
        print(line)
    if outcome.category == OK:
        disp = f"RECOVERED, usable result after {outcome.attempts} attempt(s)"
    elif outcome.category == TRANSIENT:
        disp = f"GAVE UP gracefully after {outcome.attempts} attempts; error fed back as an Observation"
    else:
        disp = "fed back as an Observation; not retried"
    print(f"    disposition: {disp}  [category: {outcome.category}]")


if __name__ == "__main__":
    line = "=" * 72
    print(line)
    print("WHEN TOOLS FAIL  -  a failure taxonomy, retries, and an idempotent tool")
    print(line)

    if os.environ.get("OPENAI_API_KEY"):
        print("[controller] OPENAI_API_KEY set; the real LLM controller would drive "
              "generate(build_prompt(...)). Falling through to the deterministic policy "
              "so output stays reproducible.")
    else:
        print("[controller] no OPENAI_API_KEY; using deterministic rule-based "
              "controller (offline default)")

    # --- The taxonomy reference. -------------------------------------------
    print("\n" + "-" * 72)
    print("THE FAILURE TAXONOMY: five kinds of failure, one recovery policy each.")
    print("-" * 72)
    print("  transient     temporary; might succeed if tried again   -> RETRY (bounded, backoff)")
    print("  permanent     will never succeed; a retry only wastes    -> FEED BACK to the model")
    print("  empty-result  the call worked but found nothing useful   -> FEED BACK to the model")
    print("  malformed     arguments fail the schema (Part 1)         -> FEED BACK to the model")
    print("  unknown-tool  not in the action space (Part 1)           -> FEED BACK to the model")
    print('  "Feed back" = turn the failure into an Observation the controller reads, not a crash.')

    # --- Fault injection: one scenario per branch of the taxonomy. ---------
    print("\n" + line)
    print("FAULT INJECTION: drive each branch through the same execute_tool wrapper")
    print(f"(deadline {DEFAULT_TIMEOUT:.1f}s, up to {MAX_RETRIES} retries, backoff x{BACKOFF:.0f}).")
    print(line)
    _reset_state()
    _run_scenario("flaky-then-succeeds (transient that clears on retry)",
                  "flaky_lookup", {"query": "today's order count"}, _FAULT_TOOLS)
    _run_scenario("timeout (slower than the deadline, every attempt)",
                  "slow_lookup", {"query": "today's order count"}, _FAULT_TOOLS)
    _run_scenario("exception (permanent error: retrying cannot help)",
                  "broken_lookup", {"query": "today's order count"}, _FAULT_TOOLS)
    _run_scenario("empty-result (the call worked, found nothing)",
                  "empty_lookup", {"query": "today's order count"}, _FAULT_TOOLS)
    _run_scenario("unknown-tool (the model invented a tool)",
                  "search_web", {"query": "today's order count"}, _FAULT_TOOLS)
    _run_scenario("malformed (missing the required argument)",
                  "flaky_lookup", {"q": "today's order count"}, _FAULT_TOOLS)

    # --- The side-effecting tool: why a retry needs an idempotency guard. ---
    print("\n" + line)
    print("THE SIDE-EFFECTING TOOL: a retry must NOT refund the customer twice.")
    print("Same transient (refund posts, ack times out), once WITHOUT a guard, once WITH.")
    print(line)

    _reset_state()
    print("\n  NO GUARD  process_refund_unsafe(ORD-5510, $80.00):")
    trace = []
    execute_tool("process_refund_unsafe", {"order_id": "ORD-5510", "amount": 80.0},
                 _FAULT_TOOLS, trace=trace)
    for ln in trace:
        print(ln)
    print(f"    ledger: {len(_UNSAFE_LEDGER)} refunds posted for ORD-5510 -> "
          f"${sum(e['amount'] for e in _UNSAFE_LEDGER):.2f} charged back. DOUBLE REFUND.")

    _reset_state()
    print("\n  GUARDED   process_refund(ORD-5510, $80.00):")
    trace = []
    execute_tool("process_refund", {"order_id": "ORD-5510", "amount": 80.0},
                 TOOL_SCHEMAS, trace=trace)
    for ln in trace:
        print(ln)
    print(f"    ledger: {len(_REFUND_LEDGER)} refund recorded for ORD-5510 -> "
          f"${_REFUND_LEDGER['ORD-5510']['amount']:.2f}. Exactly once.")
    print("    The retry hit the guard and skipped re-acting. (Part 9 makes the guard "
          "durable so it")
    print("    survives a process crash, not just this in-memory dict.)")

    # --- The whole thing in the loop. --------------------------------------
    print("\n" + line)
    print("THE ROBUST AGENT: a transient failure mid-run no longer derails it.")
    print("GOAL: Process the approved $49.99 refund for order ORD-7788.")
    print(line)

    _reset_state()
    print("\n  Naive baseline (Part 1 style: call the tool directly, no wrapper):")
    try:
        process_refund("ORD-7788", 49.99)
    except ToolError as exc:
        print(f"    process_refund(...) raised {type(exc).__name__}: {exc}")
        print("    -> uncaught, the whole run dies on the first transient blip.")

    _reset_state()
    print("\n  Robust loop (every call through execute_tool):")
    answer, steps_taken = run_agent("Process the approved $49.99 refund for order ORD-7788.",
                                    TOOL_SCHEMAS)
    print(f"  ANSWER: {answer}")
    print(f"  ({steps_taken} steps; the refund's first attempt timed out after posting, the "
          "retry hit the")
    print("   idempotency guard, and the run finished with exactly one refund on the ledger.)")

    print("\n" + line)
    print("Done. The layer between the loop and its tools:")
    print("  - classify every failure (transient / permanent / empty / malformed / unknown)")
    print("  - retry ONLY transients, bounded, with backoff; feed everything else back")
    print("  - guard side-effecting tools so a retry never acts twice")
    print("A schema-valid call can still fail; now a failure is an Observation, not a crash.")
    print(line)
