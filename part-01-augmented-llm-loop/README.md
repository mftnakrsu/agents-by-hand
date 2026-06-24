# Part 1 — The Augmented LLM: a real loop with typed tools

> The smallest building block of agent reasoning: a model call ringed by tools with a typed contract, wrapped in an explicit stop condition.

[📖 Read the essay](https://www.mefby.com/essays/augmented-llm-loop) · [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/mftnakrsu/agents-by-hand/blob/main/part-01-augmented-llm-loop/augmented_llm_loop.ipynb)

## What it covers
- **The Augmented LLM primitive** (after Anthropic's "Building Effective Agents"): a single model call wrapped in tools and memory, nested in the smallest loop with an explicit stop condition. This is the foundational block everything else builds on.
- **The agent ladder**: three rungs for the same question, rising power and rising cost. Reach for the lowest rung that works: (1) ONE AUGMENTED CALL (single round, tools available, then answer); (2) FIXED WORKFLOW (hardcoded sequence, author-time routing); (3) FULL AGENT (reason/act/observe loop, runtime routing, model decides next step). This part names the primitive that Part 19 of the RAG series used without naming.
- **The tool contract**: every tool declares a JSON schema (name, typed parameters, descriptions). A validator runs BEFORE any tool fires, rejecting an unknown tool or malformed argument and turning it into an Observation the loop recovers from, instead of a crash. This is the layer Part 19 lacked and the same contract a real LLM SDK is handed for tool calling.
- **Continuity with RAG**: the corpus is the support-bot world from the RAG series (refund policy, the E-4042 error, Acme to Globex acquisition, earbuds warranty chain). The multi-hop question is the same one RAG Part 10 toured in prose and Part 19 ran. Retrieval is no longer the pipeline; it is two tools (search_policy, search_products) in the action space, alongside calculator and finish.

## Files
- **`augmented_llm_loop.py`** — the single runnable script: two tiny corpora, four tools with typed schemas, the real-LLM controller shape behind generate() / build_augmented_prompt(), the deterministic rule_based controller, the augmented loop, and three worked runs showing the tool contract in action and all three rungs of the ladder.
- **`augmented_llm_loop.ipynb`** — step-by-step notebook: a markdown why before each small code step, built cell by cell.

## Run it
```bash
# from the repo root; no dependencies, no API key, no network
python3 part-01-augmented-llm-loop/augmented_llm_loop.py             # runs offline
# optional, for the REAL embedder path: pip install sentence-transformers && RAG_REAL_EMBED=1 …
# optional: set OPENAI_API_KEY to see the real LLM-driven controller banner
```
Prefer it step by step? Open `augmented_llm_loop.ipynb` in Jupyter, or click **Open in Colab** above.

## Key idea
Every agent step is another model call, and that cost is not known in advance because the model decides how many cycles it will take. This part names a primitive: the smallest loop with tools and a stop condition. The ladder shows when to use it (rung 1: one call, fastest) versus when you need routing power (rung 2: fixed workflow, author chooses steps) versus when the model must route (rung 3: agent loop, model chooses next step at runtime). The tool contract is what bridges offline demos to real systems. This lineage traces to Anthropic's "Building Effective Agents" (the augmented-LLM primitive and the workflow-vs-agent distinction) and ReAct (Yao et al., 2023, arXiv:2210.03629).

## Offline by design
The whole demo runs with no network and no API key. A deterministic rule-based controller stands in for a trained LLM router, every Thought/Action it picks is a rule you can read, and a deterministic lexical retriever stands in for sentence-transformers, so output is reproducible. The real paths sit behind flags: set OPENAI_API_KEY and generate() prints a banner noting the real controller would drive the loop (it still falls through to the rule policy); set RAG_REAL_EMBED=1 with sentence-transformers installed for the dense retriever. The tools chosen, the hops taken, and every Thought/Action/Observation/Finish line are identical either way.

---
[Series index](../) · [Part 2 — When Tools Fail →](../) (coming soon)
