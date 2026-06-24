# Part 12 - Tools as a Protocol: a minimal MCP server and host by hand

> The frontier track begins. The core agent can plan, recover, remember, throttle itself, survive a crash, pause for a human, and be observed end to end. But its tools are still a hardcoded Python dict baked into one process: Part 1's `TOOL_SCHEMAS`. That dict cannot be shared with another agent, swapped at deploy time, or DISCOVERED by a host that did not import it. Every integration is bespoke wiring. The Model Context Protocol turns "what tools do you have and how do I call them" into a wire protocol: a SERVER advertises capabilities, a HOST discovers and calls them over JSON-RPC, and the agent's action space is assembled at run time from whatever servers it connects to, not hardcoded at author time.

[📖 Read the essay](https://www.mefby.com/essays/mcp-by-hand) · [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/mftnakrsu/agents-by-hand/blob/main/part-12-mcp-by-hand/mcp_server_and_host.ipynb)

## What it covers
- **The hardcoded-dict failure**: the agent from Parts 1 to 11 calls tools through a Python dict (`TOOL_SCHEMAS`) baked into the same process. It cannot share that dict with another agent, swap it at deploy time, or be handed tools by a host that never imported it. Every new integration is one-off wiring, and the action space is frozen at author time.
- **An MCP server and host, both built by hand, stdlib only**: no SDK. The SERVER answers JSON-RPC requests and the HOST drives it. The default transport is an IN-PROCESS shim (the host calls `server.handle(request)` directly), but every message is a real JSON-RPC frame printed verbatim, so you read the exact bytes that would cross a socket.
- **The initialize handshake and capability negotiation**: the host sends `initialize` (id 1) with `protocolVersion "2025-06-18"` and `clientInfo`; the server replies with its `protocolVersion`, `serverInfo`, and `capabilities`. The support-server advertises `tools`, `resources`, and `prompts`; the catalog-server advertises only `tools`. The host connects only on a version it understands and reads the capability set to know what the server can do.
- **tools/list and tools/call, plus the three primitives**: `tools/list` (id 2) returns the schemas, the host discovers `['search_policy', 'process_refund']`. The three MCP server PRIMITIVES are then exercised in turn: `tools/call` (id 3) runs `search_policy` -> "Refunds are accepted within 30 days; after the window a 10% restocking fee applies."; `resources/read` (id 4) fetches `file:///policies/refund.md` -> "Refunds within 30 days; 10% restocking fee after."; `prompts/get` (id 5) returns the `refund_decision` template -> "Decide the refund for {order}, citing the policy."
- **Discovered schemas drive Part 1's validator (over the wire)**: the JSON `inputSchema` returned by `tools/list` is fed STRAIGHT INTO Part 1's validator and controller, replacing the hardcoded dict. `{"order_id": "ORD-3300", "amount": 180.0}` -> OK; `{"order_id": "ORD-3300"}` -> REJECTED: missing required arg `amount`; `{"order_id": "ORD-3300", "amount": "lots"}` -> REJECTED: arg `amount` must be number. The schema was not hardcoded; it arrived from the wire. Part 1's guarantee, over MCP.
- **Multiplexing N servers into one palette**: connect a second server and the agent's palette becomes the union of both: `search_policy` and `process_refund` (support-server) plus `search_products` (catalog-server). A multi-hop task uses `search_products` from catalog transparently alongside `process_refund` from support, on one run-time-assembled palette.
- **In-process shim default vs the illustrative stdio path**: the verified default is the in-process shim. The real deployment runs the server as a SEPARATE PROCESS over stdio, shown as a LABELED, ILLUSTRATIVE CLI transcript (two local processes, no network, same frames crossing a pipe), explicitly marked "not executed here", not a frozen verified run.
- **The skills / progressive-disclosure sidebar**: a host wired to many servers can be handed hundreds of tools. Rather than stuffing them all into the prompt, it can disclose them progressively (names first, full schema only when the model reaches for a tool), which pairs naturally with MCP's discovery calls.

## Files
- **`mcp_server_and_host.py`** — the single runnable script: the support-bot tool bodies (`search_policy`, `process_refund`, `search_products`) and the schemas behind them, the MCP server's `handle()` answering `initialize` / `tools/list` / `tools/call` / `resources/read` / `prompts/get`, the in-process JSON-RPC shim that prints every frame verbatim, the host that does the handshake, discovers tools, and feeds the discovered `inputSchema` into Part 1's validator/controller, the multiplexer that unions two servers into one palette, and the labeled illustrative stdio transcript. The real-LLM and real-stdio paths sit one flag away.
- **`mcp_server_and_host.ipynb`** — step-by-step notebook: a markdown why before each small code step, built cell by cell.

## Run it
```bash
# from the repo root; no dependencies, no API key, no network
python3 part-12-mcp-by-hand/mcp_server_and_host.py   # runs offline
```
Prefer it step by step? Open `mcp_server_and_host.ipynb` in Jupyter, or click **Open in Colab** above.

## Key idea
Tools stop being a hardcoded dict and become a discovered, schema-described capability set spoken over a protocol. A SERVER advertises tools, resources, and prompts; a HOST does the `initialize` handshake (negotiating `protocolVersion` and capabilities), calls `tools/list`, and reads the JSON `inputSchema` straight off the wire:

```
  --> {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
  <-- {"jsonrpc": "2.0", "id": 2, "result": {"tools": [search_policy, process_refund]}}
  [host] discovered tools: ['search_policy', 'process_refund']
```

That discovered schema feeds Part 1's validator unchanged, so the same guarantee now holds over MCP instead of over an imported dict:

```
  validate {"order_id": "ORD-3300", "amount": 180.0} -> OK
  validate {"order_id": "ORD-3300"}                   -> REJECTED: missing required arg 'amount'
  validate {"order_id": "ORD-3300", "amount": "lots"} -> REJECTED: arg 'amount' must be number
```

And one host MULTIPLEXES many servers into a single, run-time-assembled palette, so a multi-hop task pulls `search_products` from the catalog-server and `process_refund` from the support-server transparently. This does not re-teach the loop; it replaces the hardcoded wiring of every prior part with a standardized protocol the action space is assembled from at run time.

## Offline by design
The whole demo runs with no network, no API key, and no dependencies. The default transport is an in-process JSON-RPC shim: the host calls `server.handle()` directly, the tools are deterministic, and every frame is a real JSON-RPC message printed verbatim, so the same output prints every run. The real deployment runs the server as a subprocess over stdio; that path is a clearly LABELED illustrative transcript (the same frames crossing a pipe between two OS processes), marked "not executed here" rather than a frozen verified run. The `protocolVersion` is pinned to `2025-06-18`. The MCP spec and SDK shapes move fast, so check the current spec; only the transport and `protocolVersion` strings would need edits to light up the real stdio (and real-LLM) paths.

---
[Series index](../) · [Part 13 — The Code-Running Tool: sandboxed execution and computer-use →](../) (coming soon, frontier track)
