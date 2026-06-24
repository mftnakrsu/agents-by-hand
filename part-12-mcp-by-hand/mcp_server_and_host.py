"""
Tools as a Protocol: a minimal MCP server and host by hand.
Agents from First Principles, Part 12.

The core track is done. The agent is durable, observable, and safe to run. But its
tools are still a hardcoded Python dict baked into the same process: TOOL_SCHEMAS
from Part 1. That dict cannot be shared with another agent, swapped at deploy time,
or DISCOVERED by a host that did not import it. Every integration is bespoke wiring.

The Model Context Protocol (MCP) fixes this by turning "what tools do you have and
how do I call them" into a wire protocol. A SERVER exposes capabilities; a HOST
discovers and calls them over JSON-RPC. Once tools speak a protocol, any host can
use any server, and the agent's action space is assembled at run time from whatever
servers it connects to, not hardcoded at author time.

This part builds both sides by hand, stdlib only:

1. AN MCP SERVER. It answers JSON-RPC requests: the initialize handshake
   (protocolVersion + capability negotiation), tools/list (return tool schemas),
   tools/call (run a tool), and the other two of MCP's three server PRIMITIVES,
   resources (read-only data the host can fetch) and prompts (named prompt
   templates). We wrap the support-bot tools as MCP capabilities.

2. AN MCP HOST. It performs the handshake, calls tools/list, and feeds the
   returned JSON inputSchema STRAIGHT INTO the Part 1 validator and controller,
   replacing the hardcoded dict. The same schema object Part 1 hand-wrote now
   arrives over the wire. And the host MULTIPLEXES: connect to two servers and the
   agent's palette is the union of both, used transparently.

HONESTY about the transport (this is the whole feasibility question). The DEFAULT
here is an IN-PROCESS JSON-RPC shim: the host calls server.handle(request) directly,
but every message is a real JSON-RPC frame we print verbatim, so you see the exact
bytes that would cross a socket. The real deployment runs the server as a SEPARATE
PROCESS the host talks to over stdio. We show that path too, as a LABELED,
ILLUSTRATIVE CLI transcript (two local processes, no network), clearly marked as a
reference of what it looks like, not a frozen, verified run.

[sidebar] SKILLS / PROGRESSIVE TOOL DISCLOSURE: a host that connects to many servers
can be handed hundreds of tools. Rather than putting them all in the prompt, it can
disclose them progressively (list names first, fetch a tool's full schema only when
the model reaches for it), which pairs naturally with MCP's discovery calls.

CONTINUITY: the support-bot tools (search_policy, process_refund, search_products).
Deterministic; the in-process shim is fully reproducible.

Run:
  python3 mcp_server_and_host.py        # offline; no API key, no network, no deps

NOTE: the MCP protocolVersion and SDK shapes move fast; check the current spec. Only
the transport and protocolVersion strings would need edits.

Expected output (deterministic default path):
========================================================================
TOOLS AS A PROTOCOL  -  a minimal MCP server and host by hand
========================================================================
[transport] in-process JSON-RPC shim (default): the host calls server.handle()
directly, but every frame below is a real JSON-RPC message printed verbatim.

------------------------------------------------------------------------
1) INITIALIZE handshake + tools/list discovery (the JSON-RPC wire frames).
------------------------------------------------------------------------
    --> {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18", "clientInfo": {"name": "agents-by-hand-host"}}}
    <-- {"jsonrpc": "2.0", "id": 1, "result": {"protocolVersion": "2025-06-18", "serverInfo": {"name": "support-server"}, "capabilities": {"tools": {}, "resources": {}, "prompts": {}}}}
    [host] connected to support-server (protocol 2025-06-18, capabilities: tools, resources, prompts)
    --> {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
    <-- {"jsonrpc": "2.0", "id": 2, "result": {"tools": [{"name": "search_policy", "description": "search the support/policy index", "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}, {"name": "process_refund", "description": "issue a refund for an order (side-effecting)", "inputSchema": {"type": "object", "properties": {"order_id": {"type": "string"}, "amount": {"type": "number"}}, "required": ["order_id", "amount"]}}]}}
    [host] discovered tools: ['search_policy', 'process_refund']

------------------------------------------------------------------------
2) THE THREE PRIMITIVES: tools, resources, prompts.
------------------------------------------------------------------------
  tools/call:
    --> {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "search_policy", "arguments": {"query": "refund window"}}}
    <-- {"jsonrpc": "2.0", "id": 3, "result": {"content": [{"type": "text", "text": "Refunds are accepted within 30 days; after the window a 10% restocking fee applies."}], "isError": false}}
    [host] result: Refunds are accepted within 30 days; after the window a 10% restocking fee applies.
  resources/read:
    --> {"jsonrpc": "2.0", "id": 4, "method": "resources/read", "params": {"uri": "file:///policies/refund.md"}}
    <-- {"jsonrpc": "2.0", "id": 4, "result": {"contents": [{"uri": "file:///policies/refund.md", "text": "Refunds within 30 days; 10% restocking fee after."}]}}
    [host] resource text: 'Refunds within 30 days; 10% restocking fee after.'
  prompts/get:
    --> {"jsonrpc": "2.0", "id": 5, "method": "prompts/get", "params": {"name": "refund_decision"}}
    <-- {"jsonrpc": "2.0", "id": 5, "result": {"messages": [{"role": "user", "content": {"type": "text", "text": "Decide the refund for {order}, citing the policy."}}]}}
    [host] prompt template: 'Decide the refund for {order}, citing the policy.'

------------------------------------------------------------------------
3) THE DISCOVERED SCHEMA DRIVES THE CONTROLLER (Part 1's validator, over the wire).
------------------------------------------------------------------------
    validate {"order_id": "ORD-3300", "amount": 180.0} -> OK
    validate {"order_id": "ORD-3300"} -> REJECTED: missing required arg 'amount'
    validate {"order_id": "ORD-3300", "amount": "lots"} -> REJECTED: arg 'amount' must be number
    The schema was not hardcoded; it arrived from tools/list. Part 1's guarantee, over MCP.

------------------------------------------------------------------------
4) MULTIPLEXING: connect a second server; the palette is the union of both.
------------------------------------------------------------------------
    [host] connected to support-server (protocol 2025-06-18, capabilities: tools, resources, prompts)
    [host] connected to catalog-server (protocol 2025-06-18, capabilities: tools)
    [host] palette across 2 servers:
      search_policy    from support-server
      process_refund   from support-server
      search_products  from catalog-server
    A multi-hop task now uses tools from different servers transparently:
      search_products (catalog-server) -> Acme Corp was acquired by Globex in 2024.
      search_products (catalog-server) -> Globex-branded wireless earbuds carry a 2-year limited warranty.
      process_refund  (support-server) available on the same palette

========================================================================
THE REAL TRANSPORT (illustrative, not executed here): server as a subprocess over
stdio. Two local processes, no network. Shown for reference; the verified run above
uses the in-process shim.
========================================================================
    $ python mcp_server.py            # process A: reads JSON-RPC from stdin
    host -> server (stdin):  {"jsonrpc":"2.0","id":1,"method":"initialize",...}
    server -> host (stdout): {"jsonrpc":"2.0","id":1,"result":{"protocolVersion":...}}
    host -> server (stdin):  {"jsonrpc":"2.0","id":2,"method":"tools/list"}
    server -> host (stdout): {"jsonrpc":"2.0","id":2,"result":{"tools":[...]}}
    (same frames as above, now crossing a pipe between two OS processes)

========================================================================
Done. Tools are no longer a hardcoded dict:
  - a SERVER advertises tools/resources/prompts; a HOST discovers them over JSON-RPC
  - the initialize handshake negotiates the protocol version + capabilities
  - discovered inputSchemas feed Part 1's validator/controller, unchanged
  - one host MULTIPLEXES many servers into a single, run-time-assembled palette
========================================================================
"""

import json
import os


# ===========================================================================
# Step 1. Tool implementations (the support-bot world). On MCP these become the
# bodies behind tools/call; their schemas become the inputSchema in tools/list.
# ===========================================================================
def _search_policy(query):
    return "Refunds are accepted within 30 days; after the window a 10% restocking fee applies."


def _search_products(query):
    if "acquired" in query.lower():
        return "Acme Corp was acquired by Globex in 2024."
    return "Globex-branded wireless earbuds carry a 2-year limited warranty."


def _process_refund(order_id, amount):
    return f"refunded ${float(amount):.2f} to {order_id}"


# ===========================================================================
# Step 2. The MCP server. A plain object whose handle() dispatches JSON-RPC by
# method. initialize negotiates the protocol version and advertises capabilities;
# tools/list, tools/call, resources/*, prompts/* implement the three primitives.
# ===========================================================================
PROTOCOL_VERSION = "2025-06-18"            # MCP uses date-style versions; check current


class MCPServer:
    def __init__(self, name, tools, resources, prompts):
        self.name = name
        self.tools = tools                 # name -> {description, inputSchema, fn}
        self.resources = resources         # uri -> {name, text}
        self.prompts = prompts             # name -> {description, template}

    def handle(self, request):
        rid, method, params = request.get("id"), request["method"], request.get("params", {})
        try:
            result = self._dispatch(method, params)
            return {"jsonrpc": "2.0", "id": rid, "result": result}
        except KeyError as exc:
            return {"jsonrpc": "2.0", "id": rid,
                    "error": {"code": -32602, "message": f"invalid params: {exc}"}}
        except Exception as exc:           # pragma: no cover - defensive
            return {"jsonrpc": "2.0", "id": rid,
                    "error": {"code": -32603, "message": str(exc)}}

    def _dispatch(self, method, params):
        if method == "initialize":
            return {"protocolVersion": PROTOCOL_VERSION,
                    "serverInfo": {"name": self.name},
                    "capabilities": {
                        "tools": {} if self.tools else None,
                        "resources": {} if self.resources else None,
                        "prompts": {} if self.prompts else None}}
        if method == "tools/list":
            return {"tools": [{"name": n, "description": t["description"],
                               "inputSchema": t["inputSchema"]} for n, t in self.tools.items()]}
        if method == "tools/call":
            name, args = params["name"], params.get("arguments", {})
            text = self.tools[name]["fn"](**args)
            return {"content": [{"type": "text", "text": text}], "isError": False}
        if method == "resources/list":
            return {"resources": [{"uri": u, "name": r["name"]} for u, r in self.resources.items()]}
        if method == "resources/read":
            uri = params["uri"]
            return {"contents": [{"uri": uri, "text": self.resources[uri]["text"]}]}
        if method == "prompts/list":
            return {"prompts": [{"name": n, "description": p["description"]}
                                for n, p in self.prompts.items()]}
        if method == "prompts/get":
            name = params["name"]
            return {"messages": [{"role": "user",
                                  "content": {"type": "text", "text": self.prompts[name]["template"]}}]}
        raise Exception(f"method not found: {method}")


# Two servers: a support server (tools + a resource + a prompt) and a catalog server.
SUPPORT = MCPServer(
    name="support-server",
    tools={
        "search_policy": {
            "description": "search the support/policy index",
            "inputSchema": {"type": "object",
                            "properties": {"query": {"type": "string"}}, "required": ["query"]},
            "fn": _search_policy},
        "process_refund": {
            "description": "issue a refund for an order (side-effecting)",
            "inputSchema": {"type": "object",
                            "properties": {"order_id": {"type": "string"},
                                           "amount": {"type": "number"}},
                            "required": ["order_id", "amount"]},
            "fn": _process_refund},
    },
    resources={"file:///policies/refund.md":
               {"name": "refund-policy", "text": "Refunds within 30 days; 10% restocking fee after."}},
    prompts={"refund_decision":
             {"description": "draft a refund decision",
              "template": "Decide the refund for {order}, citing the policy."}},
)

CATALOG = MCPServer(
    name="catalog-server",
    tools={
        "search_products": {
            "description": "search the products index (acquisitions, warranties)",
            "inputSchema": {"type": "object",
                            "properties": {"query": {"type": "string"}}, "required": ["query"]},
            "fn": _search_products},
    },
    resources={},
    prompts={},
)


# ===========================================================================
# Step 3. The validator (Part 1), now reading a WIRE-DISCOVERED JSON Schema instead
# of a hardcoded dict. Same idea, same guarantees: the schema is just data, and now
# it arrives over the protocol.
# ===========================================================================
_PY_TYPE = {"string": str, "number": (int, float), "boolean": bool}


def validate_against_schema(args, input_schema):
    props = input_schema.get("properties", {})
    for req in input_schema.get("required", []):
        if req not in args:
            return False, f"missing required arg '{req}'"
    for k, v in args.items():
        if k not in props:
            return False, f"unexpected arg '{k}'"
        if not isinstance(v, _PY_TYPE[props[k]["type"]]):
            return False, f"arg '{k}' must be {props[k]['type']}"
    return True, None


# ===========================================================================
# Step 4. The MCP host. Connects to servers (handshake + discovery), prints every
# JSON-RPC frame, and builds the agent's tool palette from what it discovers.
# ===========================================================================
class MCPHost:
    def __init__(self, verbose=True):
        self.servers = {}
        self.palette = {}                  # tool_name -> {server, schema, description}
        self._id = 0
        self.verbose = verbose

    def _rpc(self, server, method, params):
        self._id += 1
        req = {"jsonrpc": "2.0", "id": self._id, "method": method, "params": params}
        if self.verbose:
            print(f"    --> {json.dumps(req)}")
        resp = server.handle(req)
        if self.verbose:
            print(f"    <-- {json.dumps(resp)}")
        return resp.get("result", {})

    def connect(self, server):
        init = self._rpc(server, "initialize",
                         {"protocolVersion": PROTOCOL_VERSION,
                          "clientInfo": {"name": "agents-by-hand-host"}})
        caps = [c for c, v in init["capabilities"].items() if v is not None]
        print(f"    [host] connected to {init['serverInfo']['name']} "
              f"(protocol {init['protocolVersion']}, capabilities: {', '.join(caps)})")
        self.servers[server.name] = server
        for t in self._rpc(server, "tools/list", {})["tools"]:
            self.palette[t["name"]] = {"server": server.name, "schema": t["inputSchema"],
                                       "description": t["description"]}

    def call_tool(self, name, arguments):
        server = self.servers[self.palette[name]["server"]]
        res = self._rpc(server, "tools/call", {"name": name, "arguments": arguments})
        return res["content"][0]["text"]


def generate(prompt):
    """REAL path: a hosted LLM controller is handed the discovered tool schemas.
    Unused offline."""
    from openai import OpenAI
    client = OpenAI()
    resp = client.chat.completions.create(model="gpt-4o-mini",
                                          messages=[{"role": "user", "content": prompt}], temperature=0)
    return resp.choices[0].message.content


# ===========================================================================
# Demo. Everything below RUNS OFFLINE (the in-process JSON-RPC shim).
# ===========================================================================
if __name__ == "__main__":
    bar = "=" * 72
    print(bar)
    print("TOOLS AS A PROTOCOL  -  a minimal MCP server and host by hand")
    print(bar)
    print("[transport] in-process JSON-RPC shim (default): the host calls server.handle()")
    print("directly, but every frame below is a real JSON-RPC message printed verbatim.")
    if os.environ.get("OPENAI_API_KEY"):
        print("[controller] OPENAI_API_KEY set; the real LLM would be handed the discovered schemas. "
              "Falling through to deterministic logic for reproducibility.")

    host = MCPHost()

    # --- 1. The handshake + discovery. -------------------------------------
    print("\n" + "-" * 72)
    print("1) INITIALIZE handshake + tools/list discovery (the JSON-RPC wire frames).")
    print("-" * 72)
    host.connect(SUPPORT)
    print(f"    [host] discovered tools: {list(host.palette)}")

    # --- 2. The three primitives. ------------------------------------------
    print("\n" + "-" * 72)
    print("2) THE THREE PRIMITIVES: tools, resources, prompts.")
    print("-" * 72)
    print("  tools/call:")
    out = host.call_tool("search_policy", {"query": "refund window"})
    print(f"    [host] result: {out}")
    print("  resources/read:")
    res = host._rpc(SUPPORT, "resources/read", {"uri": "file:///policies/refund.md"})
    print(f"    [host] resource text: {res['contents'][0]['text']!r}")
    print("  prompts/get:")
    pr = host._rpc(SUPPORT, "prompts/get", {"name": "refund_decision"})
    print(f"    [host] prompt template: {pr['messages'][0]['content']['text']!r}")

    # --- 3. The discovered schema drives the Part 1 validator. -------------
    print("\n" + "-" * 72)
    print("3) THE DISCOVERED SCHEMA DRIVES THE CONTROLLER (Part 1's validator, over the wire).")
    print("-" * 72)
    schema = host.palette["process_refund"]["schema"]
    for args in ({"order_id": "ORD-3300", "amount": 180.0},
                 {"order_id": "ORD-3300"},
                 {"order_id": "ORD-3300", "amount": "lots"}):
        ok, err = validate_against_schema(args, schema)
        print(f"    validate {json.dumps(args)} -> {'OK' if ok else 'REJECTED: ' + err}")
    print("    The schema was not hardcoded; it arrived from tools/list. Part 1's guarantee, over MCP.")

    # --- 4. Multiplexing two servers into one palette. --------------------
    print("\n" + "-" * 72)
    print("4) MULTIPLEXING: connect a second server; the palette is the union of both.")
    print("-" * 72)
    quiet = MCPHost(verbose=False)         # connect quietly, then show the merged palette
    quiet.connect(SUPPORT)
    quiet.connect(CATALOG)
    print(f"    [host] palette across 2 servers:")
    for name, meta in quiet.palette.items():
        print(f"      {name:<16} from {meta['server']}")
    print("    A multi-hop task now uses tools from different servers transparently:")
    hop1 = quiet.call_tool("search_products", {"query": "who acquired Acme"})
    hop2 = quiet.call_tool("search_products", {"query": "Globex earbuds warranty"})
    print(f"      search_products (catalog-server) -> {hop1}")
    print(f"      search_products (catalog-server) -> {hop2}")
    print(f"      process_refund  (support-server) available on the same palette")

    # --- 5. The real subprocess-over-stdio path (illustrative). -----------
    print("\n" + bar)
    print("THE REAL TRANSPORT (illustrative, not executed here): server as a subprocess over")
    print("stdio. Two local processes, no network. Shown for reference; the verified run above")
    print("uses the in-process shim.")
    print(bar)
    print("    $ python mcp_server.py            # process A: reads JSON-RPC from stdin")
    print('    host -> server (stdin):  {"jsonrpc":"2.0","id":1,"method":"initialize",...}')
    print('    server -> host (stdout): {"jsonrpc":"2.0","id":1,"result":{"protocolVersion":...}}')
    print('    host -> server (stdin):  {"jsonrpc":"2.0","id":2,"method":"tools/list"}')
    print('    server -> host (stdout): {"jsonrpc":"2.0","id":2,"result":{"tools":[...]}}')
    print("    (same frames as above, now crossing a pipe between two OS processes)")

    print("\n" + bar)
    print("Done. Tools are no longer a hardcoded dict:")
    print("  - a SERVER advertises tools/resources/prompts; a HOST discovers them over JSON-RPC")
    print("  - the initialize handshake negotiates the protocol version + capabilities")
    print("  - discovered inputSchemas feed Part 1's validator/controller, unchanged")
    print("  - one host MULTIPLEXES many servers into a single, run-time-assembled palette")
    print(bar)
