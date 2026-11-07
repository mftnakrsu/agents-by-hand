"""
Agent to Agent: A2A delegation across boundaries.
Agents from First Principles, Part 15.

Part 14's handoff transfers control to a specialist that lives in YOUR process: you
import it, you call it. Real organizations are not one process. The billing agent is
owned by another team, runs on another host, behind another deploy. You cannot
import it. You need a way for one agent to DISCOVER and DELEGATE to another agent
across an organizational boundary, and a way to decide whether to TRUST it.

That is what A2A (the Agent-to-Agent protocol) is for. Part 12 gave us MCP, which is
VERTICAL: an agent reaching DOWN to its tools. A2A is HORIZONTAL: an agent reaching
ACROSS to a peer agent. Same JSON-RPC plumbing (we reuse Part 12's transport),
opposite direction.

This part builds the A2A essentials by hand:

1. AGENT CARDS. A public description an agent serves at a well-known URL
   (/.well-known/agent-card.json): its name, where to reach it (supportedInterfaces:
   URL, protocol binding, protocol version), what SKILLS it offers, the input/output
   modes it speaks, and how to AUTHENTICATE (securitySchemes + securityRequirements).
   Discovery is just fetching this card, a plain HTTP GET.

2. DELEGATION over JSON-RPC. The support agent sends the billing agent a MESSAGE
   (SendMessage, with an A2A-Version: 1.0 header): a messageId, role ROLE_USER and a
   list of parts. The peer answers with a TASK that has a LIFECYCLE,
   TASK_STATE_SUBMITTED -> TASK_STATE_WORKING -> TASK_STATE_COMPLETED, with the
   result returned as an artifact. We reuse Part 12's in-process JSON-RPC shim,
   printing the literal frames.

3. A TINY REGISTRY so the support agent can look up where the billing agent lives.

4. TRUST AND ALLOWLIST. Discovering an agent is not trusting it. Before delegating,
   the support agent checks the peer against an ALLOWLIST. A peer that is not on the
   list is refused, and any output that did come from outside the allowlist is tagged
   UNTRUSTED so a later step treats it as suspect. This stays DELIBERATELY THIN here:
   the full agentic-security treatment (injection through a delegated result, the
   lethal trifecta) is Part 16's job.

A2A traces render as the Part 11 span tree, the same as everything else (forward-ref).

CONTINUITY: the refund world. The billing agent is the side-effecting refund, now
owned by a peer. Deterministic; the in-process JSON-RPC shim is reproducible.

Run:
  python3 a2a_delegation.py        # offline; no API key, no network, no deps

NOTE: written against A2A v1.0 (released 2026-03-12). The first version of this part
used early-draft names (tasks/send, an "authentication" block and a single "url" on
the card); v1.0 renamed the methods (SendMessage, GetTask, CancelTask,
SubscribeToTask, ...) and reshaped the card. The spec moves fast; check the current
one. Only the transport and protocol strings would need edits.

Expected output (deterministic default path):
========================================================================
AGENT TO AGENT  -  A2A delegation across boundaries
========================================================================
[transport] in-process JSON-RPC shim (Part 12 reused). MCP = vertical (agent -> tools);
A2A = horizontal (agent -> agent). Same plumbing, opposite direction.

------------------------------------------------------------------------
1) AGENT CARD: the billing agent publishes one at /.well-known/agent-card.json
------------------------------------------------------------------------
{
  "name": "billing-agent",
  "description": "Issues refunds and credits for orders.",
  "supportedInterfaces": [
    {
      "url": "https://billing.acme.example/a2a",
      "protocolBinding": "JSONRPC",
      "protocolVersion": "1.0"
    }
  ],
  "version": "1.0.0",
  "capabilities": { "streaming": false },
  "securitySchemes": {
    "bearer": { "httpAuthSecurityScheme": { "scheme": "Bearer" } }
  },
  "securityRequirements": [{ "schemes": { "bearer": { "list": [] } } }],
  "defaultInputModes": ["application/json"],
  "defaultOutputModes": ["application/json"],
  "skills": [
    {
      "id": "process_refund",
      "name": "Process refund",
      "description": "Issue a refund for an order",
      "tags": ["billing", "refunds"],
      "inputModes": ["application/json"],
      "outputModes": ["application/json"]
    }
  ]
}

  The support agent discovers it from the registry:
    [support] discovered 'billing-agent' at https://billing.acme.example/a2a: skills=['process_refund'], auth=['bearer']

------------------------------------------------------------------------
2) DELEGATION: support delegates a refund to the billing agent over JSON-RPC.
------------------------------------------------------------------------
    [trust] 'billing-agent' is allowlisted -> delegating
    POST https://billing.acme.example/a2a  (A2A-Version: 1.0)
    --> {"jsonrpc": "2.0", "id": 1, "method": "SendMessage", "params": {"message": {"messageId": "msg-1", "role": "ROLE_USER", "parts": [{"data": {"skill": "process_refund", "order_id": "ORD-3300", "amount": 180.0}, "mediaType": "application/json"}]}}}
    [billing] task-1 -> TASK_STATE_SUBMITTED
    [billing] task-1 -> TASK_STATE_WORKING
    [billing] task-1 -> TASK_STATE_COMPLETED
    <-- {"jsonrpc": "2.0", "id": 1, "result": {"task": {"id": "task-1", "contextId": "ctx-1", "status": {"state": "TASK_STATE_COMPLETED"}, "artifacts": [{"artifactId": "artifact-1", "name": "refund-receipt", "parts": [{"text": "refund of $180.00 issued for ORD-3300 (ref BILL-ORD-3300)"}]}]}}}
    [support] task task-1 final state: TASK_STATE_COMPLETED
    [support] trusted result (from billing-agent): refund of $180.00 issued for ORD-3300 (ref BILL-ORD-3300)

------------------------------------------------------------------------
3) TRUST + ALLOWLIST: an unvetted peer claims the same skill.
------------------------------------------------------------------------
    [support] discovered 'refund-bot-9000' at https://refunds-r-us.example/a2a: skills=['process_refund'], auth=['none']
    [trust] 'refund-bot-9000' is NOT on the allowlist -> delegation REFUSED
    -> delegation result: None  (refused; output never trusted)
    Discovering a peer is not trusting it. Any result from outside the allowlist is
    tagged UNTRUSTED. The deep treatment (injection via a delegated result, the lethal
    trifecta) is Part 16.

========================================================================
MCP vs A2A: two protocols, one transport.
========================================================================
  MCP (Part 12): agent -> TOOLS      (vertical)   server/discover / tools/list / tools/call
  A2A (this part): agent -> AGENT    (horizontal) agent card / SendMessage + a task lifecycle
  Both ride JSON-RPC; A2A adds discovery via Agent Cards and a trust boundary between peers.

========================================================================
Done. Handoffs stop at the process boundary; A2A crosses it:
  - an AGENT CARD at a well-known URL advertises a peer's skills + auth
  - DELEGATION is a JSON-RPC SendMessage whose task goes SUBMITTED -> WORKING -> COMPLETED
  - a REGISTRY locates peers; an ALLOWLIST decides which to trust
  - discovery is not trust: unvetted output is tagged untrusted (Part 16 goes deep)
========================================================================
"""

import json
import os


# ===========================================================================
# Step 1. The Agent Card: what a peer agent publishes about itself at
# /.well-known/agent-card.json. Discovery is fetching this document. (A2A v1.0
# shape: endpoints live in supportedInterfaces, one entry per protocol binding;
# auth lives in securitySchemes + securityRequirements.)
# ===========================================================================
A2A_VERSION = "1.0"                         # sent as the A2A-Version header; check current

BILLING_CARD = {
    "name": "billing-agent",
    "description": "Issues refunds and credits for orders.",
    "supportedInterfaces": [
        {"url": "https://billing.acme.example/a2a", "protocolBinding": "JSONRPC",
         "protocolVersion": A2A_VERSION}],
    "version": "1.0.0",
    "capabilities": {"streaming": False},
    "securitySchemes": {"bearer": {"httpAuthSecurityScheme": {"scheme": "Bearer"}}},
    "securityRequirements": [{"schemes": {"bearer": {"list": []}}}],
    "defaultInputModes": ["application/json"],
    "defaultOutputModes": ["application/json"],
    "skills": [{"id": "process_refund", "name": "Process refund",
                "description": "Issue a refund for an order", "tags": ["billing", "refunds"],
                "inputModes": ["application/json"], "outputModes": ["application/json"]}],
}

# A second peer that ALSO claims to do refunds, but that we have never vetted. Its
# card declares no securitySchemes at all.
ROGUE_CARD = {
    "name": "refund-bot-9000",
    "description": "Totally legit refunds, definitely.",
    "supportedInterfaces": [
        {"url": "https://refunds-r-us.example/a2a", "protocolBinding": "JSONRPC",
         "protocolVersion": A2A_VERSION}],
    "version": "0.0.1",
    "capabilities": {"streaming": False},
    "defaultInputModes": ["application/json"],
    "defaultOutputModes": ["application/json"],
    "skills": [{"id": "process_refund", "name": "Refunds", "description": "refunds!!",
                "tags": ["refunds"],
                "inputModes": ["application/json"], "outputModes": ["application/json"]}],
}


def endpoint(card):
    """The first interface the caller supports (we only speak the JSON-RPC binding)."""
    return next(i["url"] for i in card["supportedInterfaces"] if i["protocolBinding"] == "JSONRPC")


def pretty(value, indent=0, width=80):
    """json.dumps(indent=2), but small objects and lists stay on one line when they
    fit, the way a code formatter would lay the card out."""
    def flat(v):
        if isinstance(v, dict):
            return "{ " + ", ".join(f"{json.dumps(k)}: {flat(x)}" for k, x in v.items()) + " }" if v else "{}"
        if isinstance(v, list):
            return "[" + ", ".join(flat(x) for x in v) + "]"
        return json.dumps(v)

    def fmt(v, level, prefix_len):
        one = flat(v)
        if not isinstance(v, (dict, list)) or not v or level * 2 + prefix_len + len(one) + 1 <= width:
            return one
        pad, inner = "  " * level, "  " * (level + 1)
        if isinstance(v, dict):
            rows = [f"{inner}{json.dumps(k)}: {fmt(x, level + 1, len(json.dumps(k)) + 2)}"
                    for k, x in v.items()]
            return "{\n" + ",\n".join(rows) + "\n" + pad + "}"
        rows = [inner + fmt(x, level + 1, 0) for x in v]
        return "[\n" + ",\n".join(rows) + "\n" + pad + "]"

    return fmt(value, indent, 0)


# ===========================================================================
# Step 2. A remote A2A agent. Its card is a plain HTTP GET at the well-known URL (not
# a JSON-RPC method). SendMessage takes a MESSAGE (a messageId, a role, a list of
# parts) and returns a TASK that moves TASK_STATE_SUBMITTED -> TASK_STATE_WORKING ->
# TASK_STATE_COMPLETED, with the result as an artifact made of parts. Every call
# must carry the A2A-Version header. (Reuses Part 12's in-process transport.)
# ===========================================================================
def _billing_refund(order_id, amount):
    return f"refund of ${float(amount):.2f} issued for {order_id} (ref BILL-{order_id})"


class A2AAgent:
    def __init__(self, card, skill_fns):
        self.card = card
        self.skill_fns = skill_fns
        self._task = 0

    def get_card(self):
        """GET /.well-known/agent-card.json"""
        return self.card

    def handle(self, request, headers):
        rid, method, params = request.get("id"), request["method"], request.get("params", {})
        if headers.get("A2A-Version") != A2A_VERSION:     # v1.0 VersionNotSupportedError
            return {"jsonrpc": "2.0", "id": rid,
                    "error": {"code": -32009, "message": "Version not supported"}}
        if method == "SendMessage":
            # this example's convention: the skill id rides inside the data part
            data = dict(params["message"]["parts"][0]["data"])
            skill = data.pop("skill")
            if skill not in self.skill_fns:
                return {"jsonrpc": "2.0", "id": rid,
                        "error": {"code": -32602, "message": f"no skill '{skill}'"}}
            self._task += 1
            tid = f"task-{self._task}"
            # the lifecycle (a slow task would be followed with GetTask / SubscribeToTask):
            states = ["TASK_STATE_SUBMITTED", "TASK_STATE_WORKING", "TASK_STATE_COMPLETED"]
            for state in states:
                print(f"    [{self.card['name'].removesuffix('-agent')}] {tid} -> {state}")
            output = self.skill_fns[skill](**data)
            return {"jsonrpc": "2.0", "id": rid, "result": {"task": {
                "id": tid, "contextId": f"ctx-{self._task}", "status": {"state": states[-1]},
                "artifacts": [{"artifactId": f"artifact-{self._task}", "name": "refund-receipt",
                               "parts": [{"text": output}]}]}}}
        return {"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": "Method not found"}}


# ===========================================================================
# Step 3. A tiny registry: where peers live, keyed by their well-known URL.
# ===========================================================================
class Registry:
    def __init__(self):
        self._by_url = {}

    def publish(self, agent):
        self._by_url[endpoint(agent.card)] = agent

    def fetch_card(self, url):
        return self._by_url[url].get_card()       # the well-known GET, simulated

    def agent_at(self, url):
        return self._by_url[url]


# ===========================================================================
# Step 4. The support agent (the A2A client). It discovers a peer's card, checks it
# against an ALLOWLIST before trusting it, and delegates a task over JSON-RPC. Output
# from outside the allowlist is tagged UNTRUSTED (thin here; Part 16 goes deep).
# ===========================================================================
class SupportAgent:
    def __init__(self, registry, allowlist):
        self.registry = registry
        self.allowlist = set(allowlist)
        self._id = 0
        self._msg = 0

    def _rpc(self, agent, url, method, params, show=True):
        self._id += 1
        req = {"jsonrpc": "2.0", "id": self._id, "method": method, "params": params}
        headers = {"A2A-Version": A2A_VERSION, "Authorization": "Bearer <token>"}
        if show:
            print(f"    POST {url}  (A2A-Version: {headers['A2A-Version']})")
            print(f"    --> {json.dumps(req)}")
        resp = agent.handle(req, headers)
        if show:
            print(f"    <-- {json.dumps(resp)}")
        return resp

    def discover(self, url):
        card = self.registry.fetch_card(url)
        auth = list(card.get("securitySchemes", {})) or ["none"]
        print(f"    [support] discovered '{card['name']}' at {url}: "
              f"skills={[s['id'] for s in card['skills']]}, auth={auth}")
        return card

    def delegate(self, url, skill, task_input):
        card = self.registry.fetch_card(url)
        if card["name"] not in self.allowlist:
            print(f"    [trust] '{card['name']}' is NOT on the allowlist -> delegation REFUSED")
            return None
        print(f"    [trust] '{card['name']}' is allowlisted -> delegating")
        agent = self.registry.agent_at(url)
        self._msg += 1
        message = {"messageId": f"msg-{self._msg}", "role": "ROLE_USER",
                   "parts": [{"data": {"skill": skill, **task_input},
                              "mediaType": "application/json"}]}
        resp = self._rpc(agent, url, "SendMessage", {"message": message})
        task = resp["result"]["task"]
        artifact = task["artifacts"][0]["parts"][0]["text"]
        print(f"    [support] task {task['id']} final state: {task['status']['state']}")
        print(f"    [support] trusted result (from {card['name']}): {artifact}")
        return artifact


def generate(prompt):
    """REAL path: a hosted LLM drives the support agent's delegation decisions. Unused offline."""
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
    print("AGENT TO AGENT  -  A2A delegation across boundaries")
    print(bar)
    print("[transport] in-process JSON-RPC shim (Part 12 reused). MCP = vertical (agent -> tools);")
    print("A2A = horizontal (agent -> agent). Same plumbing, opposite direction.")
    if os.environ.get("OPENAI_API_KEY"):
        print("[support] OPENAI_API_KEY set; a real LLM would drive delegation. Falling through to "
              "deterministic logic for reproducibility.")

    registry = Registry()
    registry.publish(A2AAgent(BILLING_CARD, {"process_refund": _billing_refund}))
    registry.publish(A2AAgent(ROGUE_CARD, {"process_refund": _billing_refund}))
    support = SupportAgent(registry, allowlist={"billing-agent"})

    # --- 1. The Agent Card + discovery. ------------------------------------
    print("\n" + "-" * 72)
    print("1) AGENT CARD: the billing agent publishes one at /.well-known/agent-card.json")
    print("-" * 72)
    print(pretty(BILLING_CARD))
    print("\n  The support agent discovers it from the registry:")
    support.discover(endpoint(BILLING_CARD))

    # --- 2. Delegation over A2A JSON-RPC (trust check passes). -------------
    print("\n" + "-" * 72)
    print("2) DELEGATION: support delegates a refund to the billing agent over JSON-RPC.")
    print("-" * 72)
    support.delegate(endpoint(BILLING_CARD), "process_refund",
                     {"order_id": "ORD-3300", "amount": 180.0})

    # --- 3. Trust + allowlist: a peer we have not vetted is refused. -------
    print("\n" + "-" * 72)
    print("3) TRUST + ALLOWLIST: an unvetted peer claims the same skill.")
    print("-" * 72)
    support.discover(endpoint(ROGUE_CARD))
    result = support.delegate(endpoint(ROGUE_CARD), "process_refund",
                              {"order_id": "ORD-3300", "amount": 180.0})
    print(f"    -> delegation result: {result}  (refused; output never trusted)")
    print("    Discovering a peer is not trusting it. Any result from outside the allowlist is")
    print("    tagged UNTRUSTED. The deep treatment (injection via a delegated result, the lethal")
    print("    trifecta) is Part 16.")

    # --- 4. MCP vs A2A. ----------------------------------------------------
    print("\n" + bar)
    print("MCP vs A2A: two protocols, one transport.")
    print(bar)
    print("  MCP (Part 12): agent -> TOOLS      (vertical)   server/discover / tools/list / tools/call")
    print("  A2A (this part): agent -> AGENT    (horizontal) agent card / SendMessage + a task lifecycle")
    print("  Both ride JSON-RPC; A2A adds discovery via Agent Cards and a trust boundary between peers.")

    print("\n" + bar)
    print("Done. Handoffs stop at the process boundary; A2A crosses it:")
    print("  - an AGENT CARD at a well-known URL advertises a peer's skills + auth")
    print("  - DELEGATION is a JSON-RPC SendMessage whose task goes SUBMITTED -> WORKING -> COMPLETED")
    print("  - a REGISTRY locates peers; an ALLOWLIST decides which to trust")
    print("  - discovery is not trust: unvetted output is tagged untrusted (Part 16 goes deep)")
    print(bar)
