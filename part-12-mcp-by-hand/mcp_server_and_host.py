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

1. AN MCP SERVER. It answers JSON-RPC requests: server/discover (which protocol
   versions and capabilities it supports), tools/list (return tool schemas),
   tools/call (run a tool), and the other two of MCP's three server PRIMITIVES,
   resources (read-only data the host can fetch) and prompts (named prompt
   templates). We wrap the support-bot tools as MCP capabilities. There is NO
   handshake: since the 2026-07-28 revision MCP is stateless, and every request
   carries io.modelcontextprotocol/protocolVersion and .../clientCapabilities in its
   _meta. A request in a version the server does not speak is refused with -32022
   (Unsupported protocol version), listing the versions it does support.

2. AN MCP HOST. It optionally calls server/discover, calls tools/list, and feeds the
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

NOTE: written against the MCP 2026-07-28 revision. The first version of this part
used 2025-06-18, where every connection opened with an initialize request and an
initialized notification; 2026-07-28 removed that handshake (and protocol-level
sessions). The spec moves fast; check the current one. Only the transport and the
protocolVersion strings would need edits.

Expected output (deterministic default path):
========================================================================
TOOLS AS A PROTOCOL  -  a minimal MCP server and host by hand
========================================================================
[transport] in-process JSON-RPC shim (default): the host calls server.handle()
directly, but every frame below is a real JSON-RPC message printed verbatim.

------------------------------------------------------------------------
1) DISCOVERY WITHOUT A HANDSHAKE: server/discover (optional) + tools/list.
------------------------------------------------------------------------
    --> {"jsonrpc": "2.0", "id": 1, "method": "server/discover", "params": {"_meta": {"io.modelcontextprotocol/protocolVersion": "2026-07-28", "io.modelcontextprotocol/clientInfo": {"name": "agents-by-hand-host", "version": "0.1.0"}, "io.modelcontextprotocol/clientCapabilities": {}}}}
    <-- {"jsonrpc": "2.0", "id": 1, "result": {"resultType": "complete", "supportedVersions": ["2026-07-28"], "capabilities": {"tools": {}, "resources": {}, "prompts": {}}, "_meta": {"io.modelcontextprotocol/serverInfo": {"name": "support-server", "version": "0.1.0"}}, "ttlMs": 3600000, "cacheScope": "public"}}
    [host] support-server speaks ['2026-07-28'], capabilities: tools, resources, prompts
    --> {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {"_meta": {...}}}
    <-- {"jsonrpc": "2.0", "id": 2, "result": {"resultType": "complete", "tools": [{"name": "search_policy", "description": "search the support/policy index", "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}, {"name": "process_refund", "description": "issue a refund for an order (side-effecting)", "inputSchema": {"type": "object", "properties": {"order_id": {"type": "string"}, "amount": {"type": "number"}}, "required": ["order_id", "amount"]}}], "ttlMs": 300000, "cacheScope": "public"}}
    [host] discovered tools: ['search_policy', 'process_refund']  (cache 300000 ms, public)

------------------------------------------------------------------------
2) THE THREE PRIMITIVES: tools, resources, prompts.
------------------------------------------------------------------------
  tools/call:
    --> {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "search_policy", "arguments": {"query": "refund window"}, "_meta": {...}}}
    <-- {"jsonrpc": "2.0", "id": 3, "result": {"resultType": "complete", "content": [{"type": "text", "text": "Refunds are accepted within 30 days; after the window a 10% restocking fee applies."}], "isError": false}}
    [host] result: Refunds are accepted within 30 days; after the window a 10% restocking fee applies.
  resources/read:
    --> {"jsonrpc": "2.0", "id": 4, "method": "resources/read", "params": {"uri": "file:///policies/refund.md", "_meta": {...}}}
    <-- {"jsonrpc": "2.0", "id": 4, "result": {"resultType": "complete", "contents": [{"uri": "file:///policies/refund.md", "text": "Refunds within 30 days; 10% restocking fee after."}], "ttlMs": 300000, "cacheScope": "public"}}
    [host] resource text: 'Refunds within 30 days; 10% restocking fee after.'
  prompts/get:
    --> {"jsonrpc": "2.0", "id": 5, "method": "prompts/get", "params": {"name": "refund_decision", "_meta": {...}}}
    <-- {"jsonrpc": "2.0", "id": 5, "result": {"resultType": "complete", "messages": [{"role": "user", "content": {"type": "text", "text": "Decide the refund for {order}, citing the policy."}}]}}
    [host] prompt template: 'Decide the refund for {order}, citing the policy.'

------------------------------------------------------------------------
3) VERSION MISMATCH: a host still pinned to the old revision is refused.
------------------------------------------------------------------------
    --> {"jsonrpc": "2.0", "id": 6, "method": "tools/list", "params": {"_meta": {"io.modelcontextprotocol/protocolVersion": "2025-06-18", ...}}}
    <-- {"jsonrpc": "2.0", "id": 6, "error": {"code": -32022, "message": "Unsupported protocol version", "data": {"supported": ["2026-07-28"], "requested": "2025-06-18"}}}
    [host] error -32022: retry with one of ['2026-07-28']

------------------------------------------------------------------------
4) THE DISCOVERED SCHEMA DRIVES THE CONTROLLER (Part 1's validator, over the wire).
------------------------------------------------------------------------
    validate {"order_id": "ORD-3300", "amount": 180.0} -> OK
    validate {"order_id": "ORD-3300"} -> REJECTED: missing required arg 'amount'
    validate {"order_id": "ORD-3300", "amount": "lots"} -> REJECTED: arg 'amount' must be number
    The schema was not hardcoded; it arrived from tools/list. Part 1's guarantee, over MCP.

------------------------------------------------------------------------
5) MULTIPLEXING: connect a second server; the palette is the union of both.
------------------------------------------------------------------------
    [host] discovered support-server (protocol 2026-07-28, capabilities: tools, resources, prompts)
    [host] discovered catalog-server (protocol 2026-07-28, capabilities: tools)
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
    host -> server (stdin):  {"jsonrpc":"2.0","id":1,"method":"server/discover","params":{"_meta":{...}}}
    server -> host (stdout): {"jsonrpc":"2.0","id":1,"result":{"resultType":"complete","supportedVersions":["2026-07-28"],...}}
    host -> server (stdin):  {"jsonrpc":"2.0","id":2,"method":"tools/list","params":{"_meta":{...}}}
    server -> host (stdout): {"jsonrpc":"2.0","id":2,"result":{"resultType":"complete","tools":[...],...}}
    (same frames as above, now crossing a pipe between two OS processes)

========================================================================
Done. Tools are no longer a hardcoded dict:
  - a SERVER advertises tools/resources/prompts; a HOST discovers them over JSON-RPC
  - no handshake: every request carries its protocol version + capabilities in _meta
  - server/discover (optional) advertises versions + capabilities; a mismatch is -32022
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
# method. There is NO handshake (MCP 2026-07-28 is stateless): every request carries
# its protocol version and the client's capabilities in params._meta, and the server
# checks them on every call, remembering nothing between requests. server/discover
# advertises versions + capabilities; tools/list, tools/call, resources/*, prompts/*
# implement the three primitives. Every result carries resultType "complete", and
# cacheable results carry ttlMs + cacheScope hints.
# ===========================================================================
PROTOCOL_VERSION = "2026-07-28"            # MCP uses date-style versions; check current
SUPPORTED_VERSIONS = [PROTOCOL_VERSION]
MCP = "io.modelcontextprotocol/"           # reserved _meta key prefix
LIST_CACHE = {"ttlMs": 300000, "cacheScope": "public"}      # tools/list, resources/read, ...
DISCOVER_CACHE = {"ttlMs": 3600000, "cacheScope": "public"}  # server/discover: an hour


class MCPError(Exception):
    def __init__(self, code, message, data=None):
        super().__init__(message)
        self.code, self.message, self.data = code, message, data


class MCPServer:
    def __init__(self, name, tools, resources, prompts):
        self.name = name
        self.tools = tools                 # name -> {description, inputSchema, fn}
        self.resources = resources         # uri -> {name, text}
        self.prompts = prompts             # name -> {description, template}

    def handle(self, request):
        rid, method, params = request.get("id"), request["method"], request.get("params", {})
        try:
            self._check_meta(params.get("_meta", {}))
            result = self._dispatch(method, params)
            return {"jsonrpc": "2.0", "id": rid, "result": {"resultType": "complete", **result}}
        except MCPError as exc:
            error = {"code": exc.code, "message": exc.message}
            if exc.data is not None:
                error["data"] = exc.data
            return {"jsonrpc": "2.0", "id": rid, "error": error}
        except KeyError as exc:
            return {"jsonrpc": "2.0", "id": rid,
                    "error": {"code": -32602, "message": f"invalid params: {exc}"}}
        except Exception as exc:           # pragma: no cover - defensive
            return {"jsonrpc": "2.0", "id": rid,
                    "error": {"code": -32603, "message": str(exc)}}

    def _check_meta(self, meta):
        # Stateless: the version and client capabilities arrive with EVERY request.
        if MCP + "protocolVersion" not in meta or MCP + "clientCapabilities" not in meta:
            raise MCPError(-32602, "missing required _meta fields")
        requested = meta[MCP + "protocolVersion"]
        if requested not in SUPPORTED_VERSIONS:
            # version negotiation: refuse, and say what we do speak
            raise MCPError(-32022, "Unsupported protocol version",
                           {"supported": SUPPORTED_VERSIONS, "requested": requested})

    def _capabilities(self):
        caps = {"tools": self.tools, "resources": self.resources, "prompts": self.prompts}
        return {c: {} for c, offered in caps.items() if offered}

    def _dispatch(self, method, params):
        if method == "server/discover":
            return {"supportedVersions": SUPPORTED_VERSIONS,
                    "capabilities": self._capabilities(),
                    "_meta": {MCP + "serverInfo": {"name": self.name, "version": "0.1.0"}},
                    **DISCOVER_CACHE}
        if method == "tools/list":
            return {"tools": [{"name": n, "description": t["description"],
                               "inputSchema": t["inputSchema"]} for n, t in self.tools.items()],
                    **LIST_CACHE}
        if method == "tools/call":
            name, args = params["name"], params.get("arguments", {})
            text = self.tools[name]["fn"](**args)
            return {"content": [{"type": "text", "text": text}], "isError": False}
        if method == "resources/list":
            return {"resources": [{"uri": u, "name": r["name"]} for u, r in self.resources.items()],
                    **LIST_CACHE}
        if method == "resources/read":
            uri = params["uri"]
            return {"contents": [{"uri": uri, "text": self.resources[uri]["text"]}], **LIST_CACHE}
        if method == "prompts/list":
            return {"prompts": [{"name": n, "description": p["description"]}
                                for n, p in self.prompts.items()], **LIST_CACHE}
        if method == "prompts/get":
            name = params["name"]
            return {"messages": [{"role": "user",
                                  "content": {"type": "text", "text": self.prompts[name]["template"]}}]}
        raise MCPError(-32601, "Method not found")


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
# Step 4. The MCP host. No handshake: it stamps every request's _meta with the
# protocol version + its capabilities, optionally asks server/discover first, calls
# tools/list, prints every JSON-RPC frame, and builds the agent's tool palette from
# what it discovers.
# ===========================================================================
def request_meta(version=PROTOCOL_VERSION):
    return {MCP + "protocolVersion": version,                          # required
            MCP + "clientInfo": {"name": "agents-by-hand-host", "version": "0.1.0"},
            MCP + "clientCapabilities": {}}                            # required; we offer nothing extra


def show_frame(req, meta_view):
    """The request as printed. The _meta is identical on every request, so after the
    first frame we elide it: "full" prints it, "elide" shows {...}, "version" keeps
    only the protocol version (for the mismatch demo)."""
    if meta_view == "full":
        return json.dumps(req)
    shown = "{...}"
    if meta_view == "version":
        key = MCP + "protocolVersion"
        shown = "{" + f"{json.dumps(key)}: {json.dumps(req['params']['_meta'][key])}, ...}}"
    elided = {**req, "params": {**req["params"], "_meta": "@META@"}}
    return json.dumps(elided).replace('"@META@"', shown)


class MCPHost:
    def __init__(self, verbose=True):
        self.servers = {}
        self.palette = {}                  # tool_name -> {server, schema, description}
        self._id = 0
        self.verbose = verbose

    def _rpc(self, server, method, params, version=PROTOCOL_VERSION, meta_view="elide"):
        self._id += 1
        req = {"jsonrpc": "2.0", "id": self._id, "method": method,
               "params": {**params, "_meta": request_meta(version)}}
        if self.verbose:
            print(f"    --> {show_frame(req, meta_view)}")
        resp = server.handle(req)
        if self.verbose:
            print(f"    <-- {json.dumps(resp)}")
        return resp.get("result", resp.get("error"))

    def discover(self, server, meta_view="elide"):
        """Optional for the host (every server must answer it): versions + capabilities."""
        return self._rpc(server, "server/discover", {}, meta_view=meta_view)

    def list_tools(self, server):
        self.servers[server.name] = server
        res = self._rpc(server, "tools/list", {})
        for t in res["tools"]:
            self.palette[t["name"]] = {"server": server.name, "schema": t["inputSchema"],
                                       "description": t["description"]}
        return res

    def connect(self, server):
        d = self.discover(server)
        print(f"    [host] discovered {d['_meta'][MCP + 'serverInfo']['name']} "
              f"(protocol {d['supportedVersions'][0]}, capabilities: {', '.join(d['capabilities'])})")
        self.list_tools(server)

    def call_tool(self, name, arguments):
        server = self.servers[self.palette[name]["server"]]
        res = self._rpc(server, "tools/call", {"name": name, "arguments": arguments})
        return res["content"][0]["text"]


def generate(prompt):
    """REAL path: a hosted LLM controller is handed the discovered tool schemas.
    Unused offline."""
    from openai import OpenAI
    client = OpenAI()
    resp = client.chat.completions.create(model="gpt-6-luna",
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

    # --- 1. Discovery, no handshake. ---------------------------------------
    print("\n" + "-" * 72)
    print("1) DISCOVERY WITHOUT A HANDSHAKE: server/discover (optional) + tools/list.")
    print("-" * 72)
    d = host.discover(SUPPORT, meta_view="full")     # first frame: _meta in full
    print(f"    [host] {d['_meta'][MCP + 'serverInfo']['name']} speaks {d['supportedVersions']}, "
          f"capabilities: {', '.join(d['capabilities'])}")
    tl = host.list_tools(SUPPORT)                     # from here on _meta is shown as {...}
    print(f"    [host] discovered tools: {list(host.palette)}  "
          f"(cache {tl['ttlMs']} ms, {tl['cacheScope']})")

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

    # --- 3. Version negotiation, stateless style. ---------------------------
    print("\n" + "-" * 72)
    print("3) VERSION MISMATCH: a host still pinned to the old revision is refused.")
    print("-" * 72)
    err = host._rpc(SUPPORT, "tools/list", {}, version="2025-06-18", meta_view="version")
    print(f"    [host] error {err['code']}: retry with one of {err['data']['supported']}")

    # --- 4. The discovered schema drives the Part 1 validator. -------------
    print("\n" + "-" * 72)
    print("4) THE DISCOVERED SCHEMA DRIVES THE CONTROLLER (Part 1's validator, over the wire).")
    print("-" * 72)
    schema = host.palette["process_refund"]["schema"]
    for args in ({"order_id": "ORD-3300", "amount": 180.0},
                 {"order_id": "ORD-3300"},
                 {"order_id": "ORD-3300", "amount": "lots"}):
        ok, err = validate_against_schema(args, schema)
        print(f"    validate {json.dumps(args)} -> {'OK' if ok else 'REJECTED: ' + err}")
    print("    The schema was not hardcoded; it arrived from tools/list. Part 1's guarantee, over MCP.")

    # --- 5. Multiplexing two servers into one palette. --------------------
    print("\n" + "-" * 72)
    print("5) MULTIPLEXING: connect a second server; the palette is the union of both.")
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

    # --- 6. The real subprocess-over-stdio path (illustrative). -----------
    print("\n" + bar)
    print("THE REAL TRANSPORT (illustrative, not executed here): server as a subprocess over")
    print("stdio. Two local processes, no network. Shown for reference; the verified run above")
    print("uses the in-process shim.")
    print(bar)
    print("    $ python mcp_server.py            # process A: reads JSON-RPC from stdin")
    print('    host -> server (stdin):  {"jsonrpc":"2.0","id":1,"method":"server/discover","params":{"_meta":{...}}}')
    print('    server -> host (stdout): {"jsonrpc":"2.0","id":1,"result":{"resultType":"complete","supportedVersions":["2026-07-28"],...}}')
    print('    host -> server (stdin):  {"jsonrpc":"2.0","id":2,"method":"tools/list","params":{"_meta":{...}}}')
    print('    server -> host (stdout): {"jsonrpc":"2.0","id":2,"result":{"resultType":"complete","tools":[...],...}}')
    print("    (same frames as above, now crossing a pipe between two OS processes)")

    print("\n" + bar)
    print("Done. Tools are no longer a hardcoded dict:")
    print("  - a SERVER advertises tools/resources/prompts; a HOST discovers them over JSON-RPC")
    print("  - no handshake: every request carries its protocol version + capabilities in _meta")
    print("  - server/discover (optional) advertises versions + capabilities; a mismatch is -32022")
    print("  - discovered inputSchemas feed Part 1's validator/controller, unchanged")
    print("  - one host MULTIPLEXES many servers into a single, run-time-assembled palette")
    print(bar)
