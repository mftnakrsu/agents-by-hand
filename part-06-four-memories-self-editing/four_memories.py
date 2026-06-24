"""
The Four Memories: typed stores the agent edits itself.
Agents from First Principles, Part 6.

Part 5 gave the agent an episodic buffer: a flat list of verbal lessons. That was
enough to carry one kind of knowledge across trials, and it exposes the next gap.
A flat buffer cannot tell three different KINDS of knowledge apart:
  - what HAPPENED       (the user opened a return at 14:02)  -- an event
  - what is TRUE        (the user is Dana, she prefers phone) -- a durable fact
  - how to DO a task    (returns after the window take a 10% fee) -- a procedure
Stuff all three into one list and retrieval gets noisy, facts get buried under
events, and a learned procedure reads like a one-off note. Worse, every tool the
agent had through Part 5 was READ-ONLY (RAG Part 19's tools only fetched); the
agent could never deliberately UPDATE its own state.

This part fixes both. Two ideas:

1. FOUR TYPED MEMORIES, by the kind of knowledge they hold (a cognitive-science
   taxonomy, used in MemGPT/Letta and others):
     WORKING     what we are doing right now      (volatile scratchpad)
     SEMANTIC    what is TRUE                      (durable facts: the user, the world)
     EPISODIC    what HAPPENED                     (an event log; this formalizes Part 5's buffer)
     PROCEDURAL  how to DO a task                  (learned rules; e.g. Part 5's promoted reflection)
   A write-ROUTER classifies each incoming item and sends it to the right store,
   and each store has its own read path.

2. MEMORY AS AN ACTION. memory_append and memory_replace become first-class TOOLS,
   declared with the Part 1 contract (typed schema, validated before firing), over
   labeled CORE blocks (user_profile, task_state). The controller calls them
   in-loop to rewrite its own persistent memory, exactly as MemGPT/Letta let an
   agent edit its core memory. The agent is no longer a read-only consumer of state.

And a placement sketch borrowed from operating systems, orthogonal to the taxonomy:
     CORE      always in context     -> the labeled blocks (user_profile, task_state)
     RECALL    recent, paged in      -> the latest episodic events
     ARCHIVAL  large, searched       -> a big store read via a black-box vector search
The ARCHIVAL read REUSES RAG retrieval AS A BLACK-BOX TOOL. We do NOT re-derive
embeddings, similarity, or vector databases here (that was RAG Parts 2-4); vector
search is demoted to one read tool the memory system calls.

CONTINUITY: same refund world and the Part 5 numbers (ORD-3300, a $200 order
returned after the 30-day window, a 10% restocking fee -> $180). Deterministic rule
router/controller offline; generate() is the real-LLM path one env flag away.

Run:
  python3 four_memories.py        # offline; no API key, no network, no deps

NOTE: SDK names and model ids move fast; only generate() would need edits.

Expected output (deterministic default path):
========================================================================
THE FOUR MEMORIES  -  typed stores the agent edits itself
========================================================================
[router] no OPENAI_API_KEY; using deterministic rule router/controller (offline default)

------------------------------------------------------------------------
THE FOUR MEMORIES (by KIND of knowledge), and the write router.
------------------------------------------------------------------------
  working    what we are doing now   (volatile scratchpad)
  semantic   what is TRUE            (durable facts: the user, the world)
  episodic   what HAPPENED           (an event log; formalizes Part 5's buffer)
  procedural how to DO a task        (learned rules; e.g. Part 5's promoted reflection)

  route -> semantic   (a durable fact about the user)
           "Hi, I'm Dana and I prefer email contact."
  route -> episodic   (an event that happened)
           'User opened a return request for ORD-3300 earlier today.'
  route -> procedural (a reusable how-to rule)
           'Returns after the 30-day window incur a 10% restocking fee; multiply the total by 0.9.'
  route -> working    (the current task focus)
           'Quoting the refund for ORD-3300 now.'

  Stores after routing:
    CORE.user_profile : 'name: Dana; prefers email'
    CORE.task_state   : 'Quoting the refund for ORD-3300 now.'
    EPISODIC          : ['User opened a return request for ORD-3300 earlier today.']
    PROCEDURAL        : ['Returns after the 30-day window incur a 10% restocking fee; multiply the total by 0.9.']

========================================================================
MEMORY AS A TOOL: the agent rewrites its own core memory in-loop (MemGPT/Letta).
Tools use the Part 1 contract: validated before they fire.
========================================================================
  memory_replace(block='user_profile', old='prefers email', new='prefers phone')
    -> replaced 'prefers email' with 'prefers phone' in user_profile
  memory_append(block='task_state', text='order ORD-3300, $200, returned after the window')
    -> appended to task_state
  memory_replace(block='preferences', old='x', new='y')
    -> [error] unknown memory block 'preferences'

  CORE.user_profile : 'name: Dana; prefers phone'
  CORE.task_state   : 'Quoting the refund for ORD-3300 now.; order ORD-3300, $200, returned after the window'
  The agent corrected a durable fact about the user with a single tool call.

========================================================================
THE MEMORY HIERARCHY (by ACCESS PATTERN), an OS-style sketch.
========================================================================
  core      always in context  -> user_profile, task_state (above)
  recall    recent, paged in   -> last episodic event: 'User opened a return request for ORD-3300 earlier today.'
  archival  large, searched    -> vector_search (black-box RAG; not re-derived here):
             query 'restocking fee returns after the window'
             -> 'Returns after the 30-day window are still refundable, minus a 10% restocking fee.' (score=0.63)

========================================================================
COMPOSING A REPLY from all four memories at once.
========================================================================
  semantic   (user_profile): name: Dana; prefers phone
  working    (task_state)  : Quoting the refund for ORD-3300 now.; order ORD-3300, $200, returned after the window
  procedural (rule)        : Returns after the 30-day window incur a 10% restocking fee; multiply the total by 0.9.
  archival   (RAG chunk)   : Returns after the 30-day window are still refundable, minus a 10% restocking fee.
  episodic   (event)       : User opened a return request for ORD-3300 earlier today.

  REPLY: Hi Dana, for ORD-3300 returned after the 30-day window your refund is
         $180.00 (the 10% restocking fee applies). We will call you by phone.

========================================================================
Done. A flat buffer cannot tell what happened from what is true from how to
act. Four typed stores + a write router separate them; memory_append and
memory_replace make memory an ACTION the agent takes, not just state it reads;
and archival is one black-box retrieval call, not a vector DB we rebuilt.
========================================================================
"""

import os
import re


# ===========================================================================
# Step 0. The four typed stores. CORE blocks (user_profile, task_state) are the
# always-in-context labeled memory the agent edits with tools. EPISODIC and
# PROCEDURAL are append logs. ARCHIVAL is the large store read via black-box search.
# ===========================================================================
CORE = {
    "user_profile": "(empty)",        # SEMANTIC: durable facts about the user
    "task_state": "(empty)",          # WORKING: what we are doing right now
}
EPISODIC = []                          # what HAPPENED: an event log
PROCEDURAL = []                        # how to DO things: learned rules

# ARCHIVAL: a large knowledge base, read ONLY via the black-box vector_search tool.
ARCHIVAL = [
    "Refunds are accepted within 30 days of purchase if the item is unused.",
    "Returns after the 30-day window are still refundable, minus a 10% restocking fee.",
    "Error E-4042 means the payment was declined by the bank.",
    "Standard shipping takes 3 to 5 business days.",
]


# ===========================================================================
# Step 1. A deterministic lexical retriever -- the BLACK-BOX archival reader. This
# stands in for RAG (Parts 2-4). We are NOT re-deriving embeddings or a vector DB;
# we just call search and treat the result as opaque. Vector search is demoted to
# one read tool the memory system uses.
# ===========================================================================
_TOKEN_RE = re.compile(r"[a-z0-9]+")
_STOP = {"the", "a", "an", "of", "to", "for", "on", "in", "is", "are", "what", "how",
         "do", "does", "and", "after", "within"}


def _toks(text):
    return {t[:-1] if len(t) > 3 and t.endswith("s") else t
            for t in _TOKEN_RE.findall(text.lower()) if t not in _STOP}


def vector_search(query):
    """ARCHIVAL read tool: returns the best-matching chunk and a score. Opaque RAG;
    the internals (embeddings, similarity, the index) are NOT this part's concern."""
    q = _toks(query)
    best, best_score = "", 0.0
    for chunk in ARCHIVAL:
        c = _toks(chunk)
        score = len(q & c) / ((len(q) * len(c)) ** 0.5) if q and c else 0.0
        if score > best_score:
            best, best_score = chunk, score
    return best, round(best_score, 2)


# ===========================================================================
# Step 2. The write ROUTER. Given an incoming item, decide WHICH kind of knowledge
# it is and route it to the matching store. A transparent rule policy offline; a
# real system swaps the body for one generate() classification call.
# ===========================================================================
def write_router(text):
    t = text.lower()
    if re.search(r"\b(i'?m|my name|prefer|i like|call me)\b", t):
        return "semantic", "a durable fact about the user"
    if re.search(r"\b(fee|policy|always|never|rule|step 1|procedure|multiply)\b", t):
        return "procedural", "a reusable how-to rule"
    if re.search(r"\b(opened|asked|clicked|requested|happened|at \d|yesterday|earlier)\b", t):
        return "episodic", "an event that happened"
    return "working", "the current task focus"


def _normalize_profile(text):
    """Extract durable facts into a compact, editable profile (so a later
    memory_replace can target a clean phrase, not a whole raw sentence)."""
    name = re.search(r"i'?m (\w+)", text, re.I)
    pref = re.search(r"prefer (\w+)", text, re.I)
    parts = []
    if name:
        parts.append(f"name: {name.group(1)}")
    if pref:
        parts.append(f"prefers {pref.group(1)}")
    return "; ".join(parts) if parts else text


def route_and_store(text):
    store, reason = write_router(text)
    if store == "semantic":
        CORE["user_profile"] = _normalize_profile(text)
    elif store == "working":
        CORE["task_state"] = text
    elif store == "episodic":
        EPISODIC.append(text)
    elif store == "procedural":
        PROCEDURAL.append(text)
    return store, reason


# ===========================================================================
# Step 3. Memory as an ACTION: memory_append and memory_replace as TOOLS, declared
# with the Part 1 contract. The controller calls these to rewrite its own core
# memory (MemGPT/Letta by hand). A read-only agent could never do this.
# ===========================================================================
def memory_append(block, text):
    if block not in CORE:
        return f"[error] unknown memory block '{block}'"          # error-as-observation (Part 2)
    CORE[block] = text if CORE[block] == "(empty)" else CORE[block] + "; " + text
    return f"appended to {block}"


def memory_replace(block, old, new):
    if block not in CORE:
        return f"[error] unknown memory block '{block}'"
    if old not in CORE[block]:
        return f"[error] '{old}' not found in {block}"
    CORE[block] = CORE[block].replace(old, new)
    return f"replaced '{old}' with '{new}' in {block}"


TOOL_SCHEMAS = {
    "memory_append": {
        "description": "append a fact to a labeled core-memory block",
        "parameters": {"block": {"type": "string", "required": True},
                       "text": {"type": "string", "required": True}},
        "fn": memory_append,
    },
    "memory_replace": {
        "description": "replace text inside a labeled core-memory block",
        "parameters": {"block": {"type": "string", "required": True},
                       "old": {"type": "string", "required": True},
                       "new": {"type": "string", "required": True}},
        "fn": memory_replace,
    },
}

_PY_TYPE = {"string": str, "number": (int, float), "boolean": bool}


def validate_call(name, args):                                    # the Part 1 validator
    if name not in TOOL_SCHEMAS:
        return False, f"unknown tool '{name}'"
    schema = TOOL_SCHEMAS[name]["parameters"]
    for arg, spec in schema.items():
        if spec.get("required") and arg not in args:
            return False, f"{name} is missing required arg '{arg}'"
    for arg, value in args.items():
        if arg not in schema:
            return False, f"{name} got unexpected arg '{arg}'"
        if not isinstance(value, _PY_TYPE[schema[arg]["type"]]):
            return False, f"{name} arg '{arg}' must be {schema[arg]['type']}"
    return True, None


def call_memory_tool(name, args):
    ok, err = validate_call(name, args)
    if not ok:
        return f"[invalid call] {err}"
    return TOOL_SCHEMAS[name]["fn"](**args)


# ===========================================================================
# Step 4. generate() -- the real LLM path (reference shape only). Offline, the rule
# router/controller is the source of truth (same device as Parts 1-5).
# ===========================================================================
def generate(prompt):
    """REAL path: ask a hosted LLM to route, decide a memory edit, or compose.
    Unused offline."""
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
    print("THE FOUR MEMORIES  -  typed stores the agent edits itself")
    print(bar)
    if os.environ.get("OPENAI_API_KEY"):
        print("[router] OPENAI_API_KEY set; the real LLM would classify/decide via generate(). "
              "Falling through to the deterministic rules so output is reproducible.")
    else:
        print("[router] no OPENAI_API_KEY; using deterministic rule router/controller (offline default)")

    # --- The taxonomy + the write router. ----------------------------------
    print("\n" + "-" * 72)
    print("THE FOUR MEMORIES (by KIND of knowledge), and the write router.")
    print("-" * 72)
    print("  working    what we are doing now   (volatile scratchpad)")
    print("  semantic   what is TRUE            (durable facts: the user, the world)")
    print("  episodic   what HAPPENED           (an event log; formalizes Part 5's buffer)")
    print("  procedural how to DO a task        (learned rules; e.g. Part 5's promoted reflection)")
    print()
    inbox = [
        "Hi, I'm Dana and I prefer email contact.",
        "User opened a return request for ORD-3300 earlier today.",
        "Returns after the 30-day window incur a 10% restocking fee; multiply the total by 0.9.",
        "Quoting the refund for ORD-3300 now.",
    ]
    for item in inbox:
        store, reason = route_and_store(item)
        print(f"  route -> {store:<10} ({reason})")
        print(f"           {item!r}")

    print("\n  Stores after routing:")
    print(f"    CORE.user_profile : {CORE['user_profile']!r}")
    print(f"    CORE.task_state   : {CORE['task_state']!r}")
    print(f"    EPISODIC          : {EPISODIC}")
    print(f"    PROCEDURAL        : {PROCEDURAL}")

    # --- Memory as an action: the agent edits its own core memory. ----------
    print("\n" + bar)
    print("MEMORY AS A TOOL: the agent rewrites its own core memory in-loop (MemGPT/Letta).")
    print("Tools use the Part 1 contract: validated before they fire.")
    print(bar)
    edits = [
        ("memory_replace", {"block": "user_profile", "old": "prefers email", "new": "prefers phone"}),
        ("memory_append", {"block": "task_state", "text": "order ORD-3300, $200, returned after the window"}),
        ("memory_replace", {"block": "preferences", "old": "x", "new": "y"}),     # unknown block -> error-as-observation
    ]
    for name, args in edits:
        result = call_memory_tool(name, args)
        argstr = ", ".join(f"{k}={v!r}" for k, v in args.items())
        print(f"  {name}({argstr})")
        print(f"    -> {result}")
    print(f"\n  CORE.user_profile : {CORE['user_profile']!r}")
    print(f"  CORE.task_state   : {CORE['task_state']!r}")
    print("  The agent corrected a durable fact about the user with a single tool call.")

    # --- The OS-style hierarchy: core / recall / archival. -----------------
    print("\n" + bar)
    print("THE MEMORY HIERARCHY (by ACCESS PATTERN), an OS-style sketch.")
    print(bar)
    print("  core      always in context  -> user_profile, task_state (above)")
    print(f"  recall    recent, paged in   -> last episodic event: {EPISODIC[-1]!r}")
    chunk, score = vector_search("restocking fee returns after the window")
    print("  archival  large, searched    -> vector_search (black-box RAG; not re-derived here):")
    print(f"             query 'restocking fee returns after the window'")
    print(f"             -> {chunk!r} (score={score})")

    # --- Reading all four memories to compose one grounded reply. ----------
    print("\n" + bar)
    print("COMPOSING A REPLY from all four memories at once.")
    print(bar)
    refund = round(200.0 * 0.9, 2)                          # procedural rule applied
    print(f"  semantic   (user_profile): {CORE['user_profile']}")
    print(f"  working    (task_state)  : {CORE['task_state']}")
    print(f"  procedural (rule)        : {PROCEDURAL[0]}")
    print(f"  archival   (RAG chunk)   : {chunk}")
    print(f"  episodic   (event)       : {EPISODIC[-1]}")
    print(f"\n  REPLY: Hi Dana, for ORD-3300 returned after the 30-day window your refund is")
    print(f"         ${refund:.2f} (the 10% restocking fee applies). We will call you by phone.")

    print("\n" + bar)
    print("Done. A flat buffer cannot tell what happened from what is true from how to")
    print("act. Four typed stores + a write router separate them; memory_append and")
    print("memory_replace make memory an ACTION the agent takes, not just state it reads;")
    print("and archival is one black-box retrieval call, not a vector DB we rebuilt.")
    print(bar)
