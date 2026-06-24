# Part 7 - Surviving the Long Haul: compaction and forgetting

> Run Part 6's agent long enough and two things break: the transcript it re-sends every step overflows the context window, and a store that only ever grows fills with stale and duplicate facts until the signal drowns in noise. An agent that cannot forget cannot run for long.

[📖 Read the essay](https://www.mefby.com/essays/compaction-and-forgetting) · [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/mftnakrsu/agents-by-hand/blob/main/part-07-compaction-and-forgetting/compaction_and_forgetting.ipynb)

## What it covers
- **The two long-horizon failures**: a long-lived agent breaks in two distinct ways. On the WINDOW axis, the transcript it re-sends every step keeps growing until it overflows the context window (here the live window crosses its budget at turns 4, 6, 8, 9, and 10). On the STORE axis, a semantic store that only ever grows fills with stale and duplicate facts until the useful ones are buried. Growth without forgetting is just slower failure.
- **COMPACTION, the Anthropic-style hot/warm/cold idea by hand**: when the token budget is crossed, keep the last N turns **HOT** (verbatim), fold the older SALIENT turns (tool outputs and decisions) into a **WARM** rolling summary while DROPPING chatter, and fold the oldest warm items into a single lossy **COLD** gist. The token bar drops back under budget and the run continues. Chatter turns are dropped; decisions and tool outputs survive.
- **FORGETTING, the store axis**: a memory is not equally worth keeping forever. At **READ** time, rank facts by `importance x recency x access` and surface the top few. At **WRITE** time, importance **DECAYS** with age, a **SUPERSEDING** fact retires the one it replaces (`Dana prefers email contact` -> `Dana prefers phone contact`), and when the store is over capacity the lowest-scoring memory is **EVICTED** (`Dana mentioned it is raining today` is the weakest and gets dropped when a 5th fact arrives).
- **CONSOLIDATION, a sleep-time pass**: periodically distill the raw **EPISODIC** log into durable **SEMANTIC** facts (`user.name = Dana`) and **PROCEDURAL** rules (`returns after the 30-day window: apply a 10% restocking fee`), then prune the consumed episodes. Events become knowledge: the long-horizon version of Part 6's typed stores.
- **Cashing in RAG Part 20's IOU**: RAG Part 20 kept a flat conversational buffer and noted "we will come back to summarizing older turns." This is where we come back to it.
- **Compaction is NOT condensation (the distinction)**: P20 CONDENSATION rewrites the latest QUESTION into a standalone one so retrieval works (`"what about its battery?"` -> `"what is the battery life of the earbuds?"`). COMPACTION compresses the HISTORY so the run fits the window. Different input, different output, different purpose. It is also distinct from the long-context tradeoffs of RAG Parts 11/16. Builds on Part 6's typed stores rather than rebuilding them.

## Files
- **`compaction_and_forgetting.py`** — the single runnable script: the word-count token estimator, the hot/warm/cold `compact` over a ten-turn support session, the `Fact` store with `score`/`read_top`/`add_fact` (decay, supersession, eviction), the sleep-time `consolidate` that turns the episodic log into semantic facts and procedural rules, the real-LLM `generate()` summarizer they stand in for, and the three demos.
- **`compaction_and_forgetting.ipynb`** — step-by-step notebook: a markdown why before each small code step, built cell by cell.

## Run it
```bash
# from the repo root; no dependencies, no API key, no network
python3 part-07-compaction-and-forgetting/compaction_and_forgetting.py          # runs offline
# optional: set OPENAI_API_KEY to see the real-LLM summarizer banner (still falls through to the deterministic rule compactor)
```
Prefer it step by step? Open `compaction_and_forgetting.ipynb` in Jupyter, or click **Open in Colab** above.

## Key idea
An agent that runs for a long time must do two things a one-shot pipeline never had to. First, COMPRESS the history so it still fits the window. Keep the last turns HOT verbatim, fold older decisions and tool outputs into a WARM summary, drop the chatter, and let the far past collapse into a cheap COLD gist:

```
  turn  8: window 49/40 OVER  (+ tool: calculator -> $180.00 (200 * 0.9 after)
          -> COMPACT: dropped 1 chatter turn(s), folded older decisions warm/cold; window now 39/40

  Final window state (this is all the model still sees):
    COLD : [2 earlier turns summarized]
    WARM : ['calculator -> $180.00 (200 * 0.9 after the fee).']
    HOT  : ['user: Perfect. Could you also check the earbuds warranty?', 'tool: search_products -> Globex earbuds carry a 2-year limited warranty.']
```

Second, FORGET the memories that no longer earn their place. Score each fact by `importance x recency x access`, let importance decay with age, retire a fact when a newer one supersedes it, and evict the weakest when the store is over capacity:

```
  SUPERSESSION: Dana says to use the phone instead of email.
    [retired] Dana prefers email contact
    [active] Dana prefers phone contact

  EVICTION: a 5th fact arrives but capacity is 4; the weakest is evicted.
    evicted (lowest score): Dana mentioned it is raining today
```

Then a sleep-time CONSOLIDATION pass distills the raw episodic log into durable knowledge and clears the consumed events: four raw episodes become one SEMANTIC fact (`user.name = Dana`) and one PROCEDURAL rule (`returns after the 30-day window: apply a 10% restocking fee`). This is the Anthropic context-compaction idea plus the MemGPT memory-tier idea, both by hand, over Part 6's typed stores. It is NOT P20's question condensation (rewrite the QUESTION), and NOT the P11/P16 long-context tradeoff (just buy a bigger window); compaction compresses the HISTORY, and the read/write/forget policies are territory the ever-growing RAG index never touched.

## Offline by design
The whole demo runs with no network and no API key. Tokens are estimated deterministically by **word count** (real systems use the model's tokenizer; word count is reproducible and close enough to show the mechanism), and time is a **logical clock**, so the output is reproducible: the window crosses budget on the same turns and drops back under it the same way, the same facts decay, supersede, and get evicted, and the same episodes consolidate every run. The real path sits behind a flag: set OPENAI_API_KEY and the demo prints a banner noting the real LLM would summarize via `generate()`, then falls through to the deterministic rule compactor and consolidator so output stays reproducible. Only `generate()` would need edits to light up production.

---
[Series index](../) · [Part 8 — Stopping the Runaway: budgets, loop detection, and the circuit breaker →](../) (coming soon)
