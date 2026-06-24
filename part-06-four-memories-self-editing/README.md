# Part 6 - The Four Memories: typed stores the agent edits itself

> Part 5 gave the agent an episodic buffer, but it is a FLAT list: it cannot tell what HAPPENED from what is TRUE from how to DO a task, and every tool through Part 5 was read-only. The agent could record lessons but never deliberately rewrite its own state.

[📖 Read the essay](https://www.mefby.com/essays/four-memories-self-editing) · [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/mftnakrsu/agents-by-hand/blob/main/part-06-four-memories-self-editing/four_memories.ipynb)

## What it covers
- **The flat-buffer failure**: Part 5's reflection buffer is one undifferentiated list. Stuff three kinds of knowledge into it and retrieval gets noisy: facts get buried under events, and a learned procedure reads like a one-off note. A flat buffer cannot separate what HAPPENED (the user opened a return) from what is TRUE (the user is Dana, she prefers email) from how to DO a task (returns after the window take a 10% fee). And worse, every tool the agent had through Part 5 was READ-ONLY (RAG Part 19's tools only fetched); the agent could never deliberately UPDATE its own state.
- **The four typed memories, by KIND of knowledge**: a cognitive-science taxonomy used in MemGPT/Letta and others. **WORKING** = what we are doing right now (a volatile scratchpad). **SEMANTIC** = what is TRUE (durable facts: the user, the world). **EPISODIC** = what HAPPENED (an event log). **PROCEDURAL** = how to DO a task (learned rules).
- **The write ROUTER**: each incoming item is classified by which kind of knowledge it is and sent to the matching store, and each store has its own read path. `"Hi, I'm Dana and I prefer email contact."` routes to semantic; `"User opened a return request for ORD-3300 earlier today."` routes to episodic; `"Returns after the 30-day window incur a 10% restocking fee; multiply the total by 0.9."` routes to procedural; `"Quoting the refund for ORD-3300 now."` routes to working.
- **Memory as an ACTION**: `memory_append` and `memory_replace` are first-class TOOLS, declared with the Part 1 contract (typed schema, validated before they fire) over labeled CORE blocks (`user_profile`, `task_state`). The controller calls them in-loop to rewrite its own persistent memory, exactly as MemGPT/Letta let an agent edit its core memory. A single `memory_replace(block='user_profile', old='prefers email', new='prefers phone')` corrects a durable fact about the user. An unknown block returns `[error] unknown memory block 'preferences'`, an error-as-observation (Part 2). The agent is no longer a read-only consumer of state.
- **The OS-style memory hierarchy, by ACCESS PATTERN**: orthogonal to the taxonomy. **CORE** = always in context (the labeled blocks). **RECALL** = recent episodic events, paged in. **ARCHIVAL** = a large store searched via a black-box vector search.
- **Archival = black-box RAG, not re-derived**: the archival read REUSES RAG retrieval AS A BLACK-BOX TOOL. We do NOT re-derive embeddings, similarity, or vector databases here (that was RAG Parts 2-4); `vector_search` is demoted to one read tool the memory system calls, and we treat its result as opaque.
- **Continuity with Part 5**: the EPISODIC store FORMALIZES Part 5's flat reflection buffer, and the PROCEDURAL store holds exactly the kind of promoted rule Part 5 learned (the restocking-fee lesson). Same refund world, same numbers (ORD-3300, a $200 order returned after the 30-day window, a 10% restocking fee -> $180.00). This part references the Part 1 tool contract that the memory tools reuse rather than re-teaching the loop.

## Files
- **`four_memories.py`** — the single runnable script: the four typed stores (CORE blocks plus EPISODIC, PROCEDURAL, and the ARCHIVAL knowledge base), the black-box `vector_search` archival reader standing in for RAG, the `write_router` and `route_and_store`, `memory_append` and `memory_replace` as tools with the Part 1 `validate_call` validator, the real-LLM `generate()` they stand in for, and the demo that routes four inputs, edits core memory in-loop, walks the core/recall/archival hierarchy, and composes one reply from all four memories.
- **`four_memories.ipynb`** — step-by-step notebook: a markdown why before each small code step, built cell by cell.

## Run it
```bash
# from the repo root; no dependencies, no API key, no network
python3 part-06-four-memories-self-editing/four_memories.py          # runs offline
# optional: set OPENAI_API_KEY to see the real-LLM banner (still falls through to the deterministic rule router/controller)
```
Prefer it step by step? Open `four_memories.ipynb` in Jupyter, or click **Open in Colab** above.

## Key idea
A flat list of lessons cannot tell three kinds of knowledge apart. Separate them by KIND into four typed stores, and put a write router in front so each incoming item lands in the right place:

```
  route -> semantic   (a durable fact about the user)
           "Hi, I'm Dana and I prefer email contact."
  route -> episodic   (an event that happened)
           'User opened a return request for ORD-3300 earlier today.'
  route -> procedural (a reusable how-to rule)
           'Returns after the 30-day window incur a 10% restocking fee; multiply the total by 0.9.'
  route -> working    (the current task focus)
           'Quoting the refund for ORD-3300 now.'
```

Then make memory an ACTION the agent takes, not just state it reads. `memory_append` and `memory_replace` are tools with the Part 1 contract, validated before they fire, and the controller calls them to rewrite its own labeled core blocks:

```
  memory_replace(block='user_profile', old='prefers email', new='prefers phone')
    -> replaced 'prefers email' with 'prefers phone' in user_profile
```

That is MemGPT/Letta by hand: the agent corrects a durable fact about the user with a single tool call. A second, OS-style axis runs orthogonal to the taxonomy: core (always in context), recall (recent episodic, paged in), and archival (large, searched). The archival read REUSES RAG retrieval as a black-box tool, so reading all four memories composes one grounded reply, `Hi Dana, for ORD-3300 returned after the 30-day window your refund is $180.00 (the 10% restocking fee applies). We will call you by phone.` The episodic store formalizes Part 5's buffer, and the procedural store holds its promoted rule.

## Offline by design
The whole demo runs with no network and no API key. A deterministic rule router and controller stand in for a trained LLM, so output is reproducible: the four inputs route to the same stores, the same tool edits fire and validate, and the unknown-block error appears the same way every run. The archival reader is a transparent lexical retriever standing in for RAG (Parts 2-4); we treat its result as opaque on purpose, because re-deriving embeddings, similarity, or a vector database is not this part's concern. The real path sits behind a flag: set OPENAI_API_KEY and the demo prints a banner noting the real LLM would classify, decide, and compose via `generate()`, then falls through to the deterministic rules so output stays reproducible. Only `generate()` would need edits to light up production.

---
[Series index](../) · [Part 7 — Compaction and Forgetting →](../) (coming soon)
