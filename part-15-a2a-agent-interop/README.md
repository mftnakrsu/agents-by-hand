# Part 15 - Agent to Agent: A2A delegation across boundaries

> Part 14's handoff transfers control to a specialist that lives in YOUR process: you import it, you call it. Real organizations are not one process. The billing agent is owned by another team, runs on another host, behind another deploy, and you cannot import it. A2A (the Agent-to-Agent protocol) is how one agent DISCOVERS and DELEGATES to a peer across an organizational boundary, and decides whether to TRUST it. MCP (Part 12) was VERTICAL, an agent reaching down to its tools; A2A is HORIZONTAL, an agent reaching across to a peer. Same JSON-RPC plumbing, opposite direction.

[📖 Read the essay](https://www.mefby.com/essays/a2a-agent-interop) · [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/mftnakrsu/agents-by-hand/blob/main/part-15-a2a-agent-interop/a2a_delegation.ipynb)

## What it covers
- **Why handoffs stop at the process boundary**: Part 14's `handoff` works because the specialist lives in YOUR process; you import it and call it. A real billing agent is owned by another team, on another host, behind another deploy. You cannot import it, so the handoff has nowhere to land. A2A is the move that crosses the boundary: discover a peer, delegate to it over the wire, and decide whether to trust it.
- **Agent Cards: discovery is just fetching a document**: a peer publishes a public description at a well-known URL, `/.well-known/agent-card.json`: its `name`, the `skills` it offers, the input/output modes it speaks, and how to AUTHENTICATE. The support agent discovers `billing-agent` and prints `skills=['process_refund'], auth=['bearer']`. Discovery is nothing more than fetching this card.
- **Delegation over JSON-RPC with a task lifecycle**: the support agent sends `tasks/send` (JSON-RPC id 1) for `process_refund {order_id ORD-3300, amount 180.0}`. An A2A task has a LIFECYCLE, `submitted -> working -> completed`, and returns its result as an ARTIFACT: `refund of $180.00 issued for ORD-3300 (ref BILL-ORD-3300)`. The literal request and response frames are printed.
- **A tiny registry to locate peers**: a `Registry` keyed by each peer's well-known URL is how the support agent looks up where the billing agent lives before it can fetch a card or delegate a task.
- **Trust, an allowlist, and an untrusted annotation (kept thin)**: discovering a peer is NOT trusting it. Before delegating, the support agent checks the peer against an ALLOWLIST. `billing-agent` is allowlisted, so delegation proceeds; a rogue `refund-bot-9000` (`auth=['none']`) claiming the same skill is `NOT on the allowlist -> delegation REFUSED`, result `None`, and any output from outside the allowlist is tagged UNTRUSTED. This touchpoint stays DELIBERATELY THIN; the deep treatment (injection through a delegated result, the lethal trifecta) is Part 16.
- **MCP = vertical vs A2A = horizontal, one transport**: MCP (Part 12) is agent -> TOOLS (`initialize` / `tools-list` / `tools-call`); A2A is agent -> AGENT (`agent-card` / `tasks-send` plus a task lifecycle). Both ride JSON-RPC; A2A adds discovery via Agent Cards and a trust boundary between peers.
- **Reused, not rebuilt**: the JSON-RPC transport is Part 12's in-process shim, reused as a reference rather than rebuilt, now pointed sideways at a peer instead of down at a tool. These cross-boundary delegations render as the Part 11 span tree (forward-ref).

## Files
- **`a2a_delegation.py`** — the single runnable script: two Agent Cards (`BILLING_CARD` and the unvetted `ROGUE_CARD`), the `A2AAgent` that serves `agent/getCard` and runs `tasks/send` through the `submitted -> working -> completed` lifecycle returning an artifact, the tiny `Registry` keyed by well-known URL, and the `SupportAgent` (the A2A client) that discovers a card, checks it against an allowlist, and delegates a task over JSON-RPC, all wired into the four-act demo (agent card + discovery, allowlisted delegation, the refused rogue peer, MCP vs A2A). The real-LLM backend that would drive the delegation decisions sits one flag away behind `generate()`.
- **`a2a_delegation.ipynb`** — step-by-step notebook: a markdown why before each small code step, built cell by cell.

## Run it
```bash
# from the repo root; no dependencies, no API key, no network
python3 part-15-a2a-agent-interop/a2a_delegation.py   # runs offline
```
Prefer it step by step? Open `a2a_delegation.ipynb` in Jupyter, or click **Open in Colab** above.

## Key idea
A handoff transfers control to a specialist inside your own process; it has nowhere to land when the specialist is a billing agent owned by another team on another host. A2A crosses that boundary with the same JSON-RPC plumbing as MCP, only pointed sideways at a peer instead of down at a tool:

```
  MCP (Part 12):   agent -> TOOLS    (vertical)     initialize / tools-list / tools-call
  A2A (this part): agent -> AGENT    (horizontal)   agent-card / tasks-send + a task lifecycle
```

A peer publishes an AGENT CARD at `/.well-known/agent-card.json` (name, skills, auth); DISCOVERY is fetching it. DELEGATION is a JSON-RPC `tasks/send` task with a `submitted -> working -> completed` lifecycle whose result comes back as an artifact. A REGISTRY locates peers, and an ALLOWLIST decides which to trust: `billing-agent` is allowlisted and delegates cleanly, while the unvetted `refund-bot-9000` is REFUSED. Discovery is not trust: any result from outside the allowlist is tagged UNTRUSTED. That trust boundary stays thin here; Part 16 goes deep.

## Offline by design
The whole demo runs with no network, no API key, and no dependencies. The deterministic default is the in-process JSON-RPC shim (Part 12 reused): the registry holds both peers in memory, `agent/getCard` returns the literal Agent Card, and `tasks/send` walks the fixed `submitted -> working -> completed` lifecycle and returns the same artifact every run, so the printed frames are reproducible. The trust check is a plain allowlist membership test, so the rogue peer is refused identically each time. Set `OPENAI_API_KEY` and a real LLM would drive the support agent's delegation decisions, but the demo falls through to the deterministic logic for reproducibility. Only `generate()` and the transport would need edits to light up the real network path. The A2A spec and field names move fast, so check the current spec; only the transport and protocol strings would change.

---
[Series index](../) · [Part 16 — Securing the Agent: the lethal trifecta and untrusted tools (coming soon, frontier track) →](../)
