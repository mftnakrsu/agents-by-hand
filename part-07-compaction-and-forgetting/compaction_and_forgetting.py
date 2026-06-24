"""
Surviving the Long Haul: compaction and forgetting.
Agents from First Principles, Part 7.

Part 6 gave the agent typed stores it can write to. Run it long enough and two
things break. First, the transcript it re-sends every step keeps growing until it
overflows the context window. Second, a store that only ever grows fills with stale
and duplicate facts until the signal drowns in noise. An agent that cannot forget
cannot run for long.

This part adds the two operations a long-lived agent needs: compress the history so
it still fits, and forget the memories that no longer earn their place.

RAG Part 20 left an IOU here: it kept a flat conversational buffer and noted "we
will come back to summarizing older turns." This is where we come back to it. But
be precise about what is different, because it is easy to conflate two operations:
  - P20 CONDENSATION rewrites the latest QUESTION into a standalone one so retrieval
    works ("what about its battery?" -> "what is the battery life of the earbuds?").
  - COMPACTION compresses the HISTORY so the run fits the window. Different input,
    different output, different purpose.

Three mechanisms:

1. COMPACTION (the window axis), the Anthropic-style hot/warm/cold idea by hand.
   When the token budget is crossed, keep the last N turns HOT (verbatim), fold the
   middle into a WARM rolling summary that keeps decisions and tool outputs and
   drops chatter, and fold the oldest WARM into a single COLD broad summary. The
   token bar drops back under budget and the run continues.

2. FORGETTING (the store axis). A memory is not equally worth keeping forever.
   READ time: rank by importance x recency x access, surface the top few. WRITE
   time: importance DECAYS with age, a SUPERSEDING fact retires the one it replaces,
   and when the store is over capacity the lowest-scoring memory is EVICTED.

3. CONSOLIDATION (a sleep-time pass). Periodically distill the raw EPISODIC log into
   durable SEMANTIC facts and PROCEDURAL rules, then prune the consumed episodes.
   This is the long-horizon version of Part 6's stores: events become knowledge.

CONTINUITY: same world (Dana, ORD-3300, the 10% restocking fee, the Globex earbuds).
Tokens are estimated deterministically by word count, and time is a logical clock,
so the demo is reproducible. generate() is the real-LLM summarizer one flag away.

Run:
  python3 compaction_and_forgetting.py        # offline; no API key, no network, no deps

NOTE: SDK names and model ids move fast; only generate() would need edits.

Expected output (deterministic default path):
========================================================================
SURVIVING THE LONG HAUL  -  compaction and forgetting
========================================================================
[summarizer] no OPENAI_API_KEY; using deterministic rule compactor (offline default)

NOT the same as RAG P20 condensation: P20 rewrites the QUESTION into a standalone
one; COMPACTION compresses the HISTORY to fit the window. Different operations.

------------------------------------------------------------------------
COMPACTION: keep the last turns HOT, fold the middle into a WARM summary.
------------------------------------------------------------------------
  turn  1: window 11/40 ok  (+ user: Hi, I'm Dana, I'd like to ask about or)
  turn  2: window 20/40 ok  (+ tool: search_policy -> refunds within 30 day)
  turn  3: window 29/40 ok  (+ user: Oh interesting, thanks for checking th)
  turn  4: window 41/40 OVER  (+ user: It has actually been about 40 days sin)
          -> COMPACT: dropped 1 chatter turn(s), folded older decisions warm/cold; window now 29/40
  turn  5: window 40/40 ok  (+ tool: search_policy -> after the window, a 1)
  turn  6: window 49/40 OVER  (+ user: Got it, that seems fair enough I suppo)
          -> COMPACT: dropped 2 chatter turn(s), folded older decisions warm/cold; window now 28/40
  turn  7: window 39/40 ok  (+ user: So what would my refund be on the $200)
  turn  8: window 49/40 OVER  (+ tool: calculator -> $180.00 (200 * 0.9 after)
          -> COMPACT: dropped 1 chatter turn(s), folded older decisions warm/cold; window now 39/40
  turn  9: window 48/40 OVER  (+ user: Perfect. Could you also check the earb)
          -> COMPACT: dropped 1 chatter turn(s), folded older decisions warm/cold; window now 37/40
  turn 10: window 47/40 OVER  (+ tool: search_products -> Globex earbuds carr)
          -> COMPACT: dropped 0 chatter turn(s), folded older decisions warm/cold; window now 32/40

  Final window state (this is all the model still sees):
    COLD : [2 earlier turns summarized]
    WARM : ['calculator -> $180.00 (200 * 0.9 after the fee).']
    HOT  : ['user: Perfect. Could you also check the earbuds warranty?', 'tool: search_products -> Globex earbuds carry a 2-year limited warranty.']

========================================================================
FORGETTING: score by importance x recency x access; decay, supersede, evict.
========================================================================
  Read-time ranking at t=0 (importance x recency x access):
    0.90  the user is Dana
    0.70  Dana's order is ORD-3300 ($200)
    0.60  Dana prefers email contact
    0.20  Dana mentioned it is raining today

  At t=6, importance has decayed with age; 'name' was accessed twice:
    0.38  the user is Dana
    0.25  Dana's order is ORD-3300 ($200)
    0.21  Dana prefers email contact
    0.07  Dana mentioned it is raining today

  SUPERSESSION: Dana says to use the phone instead of email.
    [retired] Dana prefers email contact
    [active] Dana prefers phone contact

  EVICTION: a 5th fact arrives but capacity is 4; the weakest is evicted.
    evicted (lowest score): Dana mentioned it is raining today
  Active store now:
    0.60  Dana prefers phone contact
    0.38  the user is Dana
    0.25  Dana's order is ORD-3300 ($200)
    0.15  Dana clicked a promo email once

========================================================================
CONSOLIDATION: a sleep-time pass turns raw episodes into durable knowledge.
========================================================================
  Raw episodic log (what happened):
    t1: user asked whether a return after the window is allowed
    t2: tool said after the window a 10% restocking fee applies
    t3: user accepted the $180.00 refund on the $200 order
    t4: user confirmed their name is Dana

  After the sleep-time consolidation pass:
    -> SEMANTIC facts   : ['user.name = Dana']
    -> PROCEDURAL rules : ['returns after the 30-day window: apply a 10% restocking fee']
    -> episodic log pruned: 4 raw events distilled and cleared

========================================================================
Done. An agent that runs for a long time must do two things a one-shot pipeline
never had to: COMPRESS the history so it still fits the window (hot/warm/cold,
distinct from P20's question condensation), and FORGET the memories that no
longer earn their place (decay, supersession, eviction), distilling raw episodes
into durable facts and rules. Growth without forgetting is just slower failure.
========================================================================
"""

import os


def est_tokens(text):
    """A deterministic token estimate: word count. Real systems use the model's
    tokenizer; word count is reproducible and close enough to show the mechanism."""
    return len(text.split())


# ===========================================================================
# Step 1. COMPACTION. A long support session, turn by turn. Each turn is
# (role, text, salient): salient turns (tool outputs, decisions) survive a
# compaction; chatter does not. When the running token total crosses the BUDGET,
# we keep the last HOT_N turns verbatim and fold the rest into a warm summary.
# ===========================================================================
BUDGET = 40          # token budget for the live window (small, to trigger compaction)
HOT_N = 2            # keep the last N turns verbatim

SESSION = [
    ("user", "Hi, I'm Dana, I'd like to ask about order ORD-3300.", False),
    ("tool", "search_policy -> refunds within 30 days of purchase.", True),
    ("user", "Oh interesting, thanks for checking that for me.", False),
    ("user", "It has actually been about 40 days since I bought it.", False),
    ("tool", "search_policy -> after the window, a 10% restocking fee applies.", True),
    ("user", "Got it, that seems fair enough I suppose.", False),
    ("user", "So what would my refund be on the $200 order?", False),
    ("tool", "calculator -> $180.00 (200 * 0.9 after the fee).", True),
    ("user", "Perfect. Could you also check the earbuds warranty?", False),
    ("tool", "search_products -> Globex earbuds carry a 2-year limited warranty.", True),
]


def render(role, text):
    return f"{role}: {text}"


def cold_gist(n):
    """The COLD tier is a single lossy line: how many older turns were summarized
    away. A real system would keep a short paraphrase here; the point is that the
    far past costs almost nothing to carry."""
    return f"[{n} earlier turns summarized]" if n else ""


def window_tokens(hot, warm, cold_n):
    t = est_tokens(cold_gist(cold_n))
    t += sum(est_tokens(w) for w in warm)
    t += sum(est_tokens(render(r, x)) for r, x, _ in hot)
    return t


def compact(hot, warm, cold_n):
    """Keep the last HOT_N turns verbatim; fold older SALIENT turns into the warm
    summary and drop chatter; then fold the OLDEST warm items into the cold gist
    until the window is back under budget. Guarantees window <= BUDGET (as long as
    the hot turns alone fit). Returns (hot, warm, cold_n, dropped)."""
    keep = hot[-HOT_N:]
    dropped = 0
    for role, text, salient in hot[:-HOT_N]:
        if salient:
            warm.append(text)                          # a decision/tool output: keep it
        else:
            dropped += 1                               # chatter: drop it
    while window_tokens(keep, warm, cold_n) > BUDGET and warm:
        warm.pop(0)                                    # oldest warm decision -> cold gist
        cold_n += 1
    return keep, warm, cold_n, dropped


def run_compaction():
    hot, warm, cold_n = [], [], 0
    for i, (role, text, salient) in enumerate(SESSION, start=1):
        hot.append((role, text, salient))
        tokens = window_tokens(hot, warm, cold_n)
        flag = "OVER" if tokens > BUDGET else "ok"
        print(f"  turn {i:>2}: window {tokens:>2}/{BUDGET} {flag}  (+ {render(role, text)[:44]})")
        if tokens > BUDGET:
            hot, warm, cold_n, dropped = compact(hot, warm, cold_n)
            after = window_tokens(hot, warm, cold_n)
            print(f"          -> COMPACT: dropped {dropped} chatter turn(s), folded older "
                  f"decisions warm/cold; window now {after}/{BUDGET}")
    print("\n  Final window state (this is all the model still sees):")
    if cold_n:
        print(f"    COLD : {cold_gist(cold_n)}")
    print(f"    WARM : {warm}")
    print(f"    HOT  : {[render(r, x) for r, x, _ in hot]}")


# ===========================================================================
# Step 2. FORGETTING. A semantic store where each fact carries importance, the
# time it was last touched, and an access count. Reads rank by a score; writes
# decay importance, supersede old facts, and evict the weakest when over capacity.
# ===========================================================================
CAPACITY = 4         # the store holds at most this many active facts
HALF_LIFE = 4.0      # logical time units for recency to halve


class Fact:
    def __init__(self, key, text, importance, created):
        self.key = key
        self.text = text
        self.importance = importance
        self.last_touch = created
        self.access = 0
        self.superseded = False


def recency(fact, now):
    return 0.5 ** ((now - fact.last_touch) / HALF_LIFE)


def score(fact, now):
    return fact.importance * recency(fact, now) * (1 + 0.1 * fact.access)


def read_top(store, now, k=3):
    active = [f for f in store if not f.superseded]
    ranked = sorted(active, key=lambda f: -score(f, now))
    return ranked[:k]


def add_fact(store, key, text, importance, now, supersedes=None):
    if supersedes:
        for f in store:
            if f.key == supersedes and not f.superseded:
                f.superseded = True
    store.append(Fact(key, text, importance, now))
    # Evict the lowest-scoring active fact if over capacity.
    active = [f for f in store if not f.superseded]
    if len(active) > CAPACITY:
        victim = min(active, key=lambda f: score(f, now))
        victim.superseded = True
        return victim
    return None


def run_forgetting():
    now = 0
    store = []
    add_fact(store, "name", "the user is Dana", 0.9, now)
    add_fact(store, "contact", "Dana prefers email contact", 0.6, now)
    add_fact(store, "order", "Dana's order is ORD-3300 ($200)", 0.7, now)
    add_fact(store, "chitchat", "Dana mentioned it is raining today", 0.2, now)

    print("  Read-time ranking at t=0 (importance x recency x access):")
    for f in read_top(store, now, k=4):
        print(f"    {score(f, now):.2f}  {f.text}")

    now = 6                                            # time passes; recency decays
    store[0].access += 2                               # 'name' got read a couple of times
    print(f"\n  At t={now}, importance has decayed with age; 'name' was accessed twice:")
    for f in read_top(store, now, k=4):
        print(f"    {score(f, now):.2f}  {f.text}")

    print("\n  SUPERSESSION: Dana says to use the phone instead of email.")
    add_fact(store, "contact", "Dana prefers phone contact", 0.6, now, supersedes="contact")
    for f in store:
        if f.key == "contact":
            tag = "retired" if f.superseded else "active"
            print(f"    [{tag}] {f.text}")

    print("\n  EVICTION: a 5th fact arrives but capacity is 4; the weakest is evicted.")
    victim = add_fact(store, "promo", "Dana clicked a promo email once", 0.15, now)
    print(f"    evicted (lowest score): {victim.text}")
    print("  Active store now:")
    for f in read_top(store, now, k=9):
        print(f"    {score(f, now):.2f}  {f.text}")


# ===========================================================================
# Step 3. CONSOLIDATION (a sleep-time pass). Distill the raw episodic log into
# durable semantic facts and procedural rules, then prune the consumed episodes.
# Events become knowledge: the long-horizon version of Part 6's stores.
# ===========================================================================
EPISODIC_LOG = [
    "t1: user asked whether a return after the window is allowed",
    "t2: tool said after the window a 10% restocking fee applies",
    "t3: user accepted the $180.00 refund on the $200 order",
    "t4: user confirmed their name is Dana",
]


def consolidate(episodic):
    semantic, procedural = [], []
    for event in episodic:
        low = event.lower()
        if "name is" in low:
            semantic.append("user.name = Dana")
        if "restocking fee" in low:
            procedural.append("returns after the 30-day window: apply a 10% restocking fee")
    # de-duplicate while preserving order
    semantic = list(dict.fromkeys(semantic))
    procedural = list(dict.fromkeys(procedural))
    return semantic, procedural


def run_consolidation():
    print("  Raw episodic log (what happened):")
    for e in EPISODIC_LOG:
        print(f"    {e}")
    semantic, procedural = consolidate(EPISODIC_LOG)
    print("\n  After the sleep-time consolidation pass:")
    print(f"    -> SEMANTIC facts   : {semantic}")
    print(f"    -> PROCEDURAL rules : {procedural}")
    print(f"    -> episodic log pruned: {len(EPISODIC_LOG)} raw events distilled and cleared")


# ===========================================================================
# generate() -- the real LLM summarizer (reference shape only). Offline, the rule
# compactor/consolidator is the source of truth (same device as Parts 1-6).
# ===========================================================================
def generate(prompt):
    """REAL path: ask a hosted LLM to summarize history or consolidate. Unused offline."""
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
    print("SURVIVING THE LONG HAUL  -  compaction and forgetting")
    print(bar)
    if os.environ.get("OPENAI_API_KEY"):
        print("[summarizer] OPENAI_API_KEY set; the real LLM would summarize via generate(). "
              "Falling through to the deterministic rules so output is reproducible.")
    else:
        print("[summarizer] no OPENAI_API_KEY; using deterministic rule compactor (offline default)")

    print("\nNOT the same as RAG P20 condensation: P20 rewrites the QUESTION into a standalone")
    print("one; COMPACTION compresses the HISTORY to fit the window. Different operations.")

    print("\n" + "-" * 72)
    print("COMPACTION: keep the last turns HOT, fold the middle into a WARM summary.")
    print("-" * 72)
    run_compaction()

    print("\n" + bar)
    print("FORGETTING: score by importance x recency x access; decay, supersede, evict.")
    print(bar)
    run_forgetting()

    print("\n" + bar)
    print("CONSOLIDATION: a sleep-time pass turns raw episodes into durable knowledge.")
    print(bar)
    run_consolidation()

    print("\n" + bar)
    print("Done. An agent that runs for a long time must do two things a one-shot pipeline")
    print("never had to: COMPRESS the history so it still fits the window (hot/warm/cold,")
    print("distinct from P20's question condensation), and FORGET the memories that no")
    print("longer earn their place (decay, supersession, eviction), distilling raw episodes")
    print("into durable facts and rules. Growth without forgetting is just slower failure.")
    print(bar)
