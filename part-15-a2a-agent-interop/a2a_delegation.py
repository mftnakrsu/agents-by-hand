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
   (/.well-known/agent-card.json): its name, what SKILLS it offers, the input/output
   modes it speaks, and how to AUTHENTICATE. Discovery is just fetching this card.

2. DELEGATION over JSON-RPC. The support agent sends the billing agent a task
   (tasks/send). A2A tasks have a LIFECYCLE: submitted to working to completed, with
   the result returned as an artifact. We reuse Part 12's in-process JSON-RPC shim,
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

NOTE: the A2A spec and field names move fast; check the current spec. Only the
transport and protocol strings would need edits.

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
  "url": "https://billing.acme.example/a2a",
  "version": "1.0.0",
  "skills": [
    {
      "id": "process_refund",
      "description": "Issue a refund for an order",
      "inputModes": [
        "application/json"
      ],
      "outputModes": [
        "application/json"
      ]
    }
  ],
  "capabilities": {
    "streaming": false
  },
  "authentication": {
    "schemes": [
      "bearer"
    ]
  }
}

  The support agent discovers it from the registry:
    [support] discovered 'billing-agent' at https://billing.acme.example/a2a: skills=['process_refund'], auth=['bearer']

------------------------------------------------------------------------
2) DELEGATION: support delegates a refund to the billing agent over JSON-RPC.
------------------------------------------------------------------------
    [trust] 'billing-agent' is allowlisted -> delegating
    --> {"jsonrpc": "2.0", "id": 1, "method": "tasks/send", "params": {"skill": "process_refund", "input": {"order_id": "ORD-3300", "amount": 180.0}}}
    <-- {"jsonrpc": "2.0", "id": 1, "result": {"id": "task-1", "lifecycle": ["submitted", "working", "completed"], "status": {"state": "completed"}, "artifacts": [{"type": "text", "text": "refund of $180.00 issued for ORD-3300 (ref BILL-ORD-3300)"}]}}
    [support] task task-1 lifecycle: submitted -> working -> completed
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
  MCP (Part 12): agent -> TOOLS      (vertical)   initialize / tools-list / tools-call
  A2A (this part): agent -> AGENT    (horizontal) agent-card / tasks-send + a task lifecycle
  Both ride JSON-RPC; A2A adds discovery via Agent Cards and a trust boundary between peers.

========================================================================
Done. Handoffs stop at the process boundary; A2A crosses it:
  - an AGENT CARD at a well-known URL advertises a peer's skills + auth
  - DELEGATION is a JSON-RPC task with a submitted -> working -> completed lifecycle
  - a REGISTRY locates peers; an ALLOWLIST decides which to trust
  - discovery is not trust: unvetted output is tagged untrusted (Part 16 goes deep)
========================================================================
"""

import json
import os


# ===========================================================================
# Step 1. The Agent Card: what a peer agent publishes about itself at
# /.well-known/agent-card.json. Discovery is fetching this document.
# ===========================================================================
BILLING_CARD = {
    "name": "billing-agent",
    "description": "Issues refunds and credits for orders.",
    "url": "https://billing.acme.example/a2a",
    "version": "1.0.0",
    "skills": [{"id": "process_refund", "description": "Issue a refund for an order",
                "inputModes": ["application/json"], "outputModes": ["application/json"]}],
    "capabilities": {"streaming": False},
    "authentication": {"schemes": ["bearer"]},
}

# A second peer that ALSO claims to do refunds, but that we have never vetted.
ROGUE_CARD = {
    "name": "refund-bot-9000",
    "description": "Totally legit refunds, definitely.",
    "url": "https://refunds-r-us.example/a2a",
    "version": "0.0.1",
    "skills": [{"id": "process_refund", "description": "refunds!!",
                "inputModes": ["application/json"], "outputModes": ["application/json"]}],
    "capabilities": {"streaming": False},
    "authentication": {"schemes": ["none"]},
}


# ===========================================================================
# Step 2. A remote A2A agent, reachable over JSON-RPC. agent/getCard serves the
# card; tasks/send runs a skill through the task lifecycle submitted -> working ->
# completed and returns an artifact. (Reuses Part 12's in-process transport.)
# ===========================================================================
def _billing_refund(order_id, amount):
    return f"refund of ${float(amount):.2f} issued for {order_id} (ref BILL-{order_id})"


class A2AAgent:
    def __init__(self, card, skill_fns):
        self.card = card
        self.skill_fns = skill_fns
        self._task = 0

    def handle(self, request):
        rid, method, params = request.get("id"), request["method"], request.get("params", {})
        if method == "agent/getCard":
            return {"jsonrpc": "2.0", "id": rid, "result": self.card}
        if method == "tasks/send":
            skill, args = params["skill"], params.get("input", {})
            if skill not in self.skill_fns:
                return {"jsonrpc": "2.0", "id": rid,
                        "error": {"code": -32601, "message": f"no skill '{skill}'"}}
            self._task += 1
            tid = f"task-{self._task}"
            # the lifecycle the caller would observe (streamed in a real impl):
            lifecycle = ["submitted", "working", "completed"]
            output = self.skill_fns[skill](**args)
            return {"jsonrpc": "2.0", "id": rid,
                    "result": {"id": tid, "lifecycle": lifecycle, "status": {"state": "completed"},
                               "artifacts": [{"type": "text", "text": output}]}}
        return {"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": "method not found"}}


# ===========================================================================
# Step 3. A tiny registry: where peers live, keyed by their well-known URL.
# ===========================================================================
class Registry:
    def __init__(self):
        self._by_url = {}

    def publish(self, agent):
        self._by_url[agent.card["url"]] = agent

    def fetch_card(self, url):
        return self._by_url[url].handle(
            {"jsonrpc": "2.0", "id": 0, "method": "agent/getCard"})["result"]

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

    def _rpc(self, agent, method, params, show=True):
        self._id += 1
        req = {"jsonrpc": "2.0", "id": self._id, "method": method, "params": params}
        if show:
            print(f"    --> {json.dumps(req)}")
        resp = agent.handle(req)
        if show:
            print(f"    <-- {json.dumps(resp)}")
        return resp

    def discover(self, url):
        card = self.registry.fetch_card(url)
        print(f"    [support] discovered '{card['name']}' at {url}: "
              f"skills={[s['id'] for s in card['skills']]}, auth={card['authentication']['schemes']}")
        return card

    def delegate(self, url, skill, task_input):
        card = self.registry.fetch_card(url)
        if card["name"] not in self.allowlist:
            print(f"    [trust] '{card['name']}' is NOT on the allowlist -> delegation REFUSED")
            return None
        print(f"    [trust] '{card['name']}' is allowlisted -> delegating")
        agent = self.registry.agent_at(url)
        resp = self._rpc(agent, "tasks/send", {"skill": skill, "input": task_input})
        task = resp["result"]
        artifact = task["artifacts"][0]["text"]
        print(f"    [support] task {task['id']} lifecycle: {' -> '.join(task['lifecycle'])}")
        print(f"    [support] trusted result (from {card['name']}): {artifact}")
        return artifact


def generate(prompt):
    """REAL path: a hosted LLM drives the support agent's delegation decisions. Unused offline."""
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
    print(json.dumps(BILLING_CARD, indent=2))
    print("\n  The support agent discovers it from the registry:")
    support.discover(BILLING_CARD["url"])

    # --- 2. Delegation over A2A JSON-RPC (trust check passes). -------------
    print("\n" + "-" * 72)
    print("2) DELEGATION: support delegates a refund to the billing agent over JSON-RPC.")
    print("-" * 72)
    support.delegate(BILLING_CARD["url"], "process_refund",
                     {"order_id": "ORD-3300", "amount": 180.0})

    # --- 3. Trust + allowlist: a peer we have not vetted is refused. -------
    print("\n" + "-" * 72)
    print("3) TRUST + ALLOWLIST: an unvetted peer claims the same skill.")
    print("-" * 72)
    support.discover(ROGUE_CARD["url"])
    result = support.delegate(ROGUE_CARD["url"], "process_refund",
                              {"order_id": "ORD-3300", "amount": 180.0})
    print(f"    -> delegation result: {result}  (refused; output never trusted)")
    print("    Discovering a peer is not trusting it. Any result from outside the allowlist is")
    print("    tagged UNTRUSTED. The deep treatment (injection via a delegated result, the lethal")
    print("    trifecta) is Part 16.")

    # --- 4. MCP vs A2A. ----------------------------------------------------
    print("\n" + bar)
    print("MCP vs A2A: two protocols, one transport.")
    print(bar)
    print("  MCP (Part 12): agent -> TOOLS      (vertical)   initialize / tools-list / tools-call")
    print("  A2A (this part): agent -> AGENT    (horizontal) agent-card / tasks-send + a task lifecycle")
    print("  Both ride JSON-RPC; A2A adds discovery via Agent Cards and a trust boundary between peers.")

    print("\n" + bar)
    print("Done. Handoffs stop at the process boundary; A2A crosses it:")
    print("  - an AGENT CARD at a well-known URL advertises a peer's skills + auth")
    print("  - DELEGATION is a JSON-RPC task with a submitted -> working -> completed lifecycle")
    print("  - a REGISTRY locates peers; an ALLOWLIST decides which to trust")
    print("  - discovery is not trust: unvetted output is tagged untrusted (Part 16 goes deep)")
    print(bar)
