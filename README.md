# agents-by-hand

Build an LLM **agent** from first principles — one runnable Python file per
concept, no frameworks hiding the moving parts. Companion code for the
**Agents from First Principles** series on
[mefby.com](https://www.mefby.com/essays/agents): a 17-part arc that grows a
single agent from a bare reason/act/observe loop into a durable, observable,
secured production agent, then scales it out across the MCP/A2A wire into a
multi-agent system and finally grades it with a trajectory regression gate.

> "Build it by hand, understand every line."

This is the sequel to [rag-by-hand](https://github.com/mftnakrsu/rag-by-hand).
There, retrieval was the whole system; here the **agent** is the system and
retrieval is just one tool it may call. Each folder maps 1:1 to an essay.

Every part ships **two ways to learn the same concept**: a single runnable `.py`
(the whole idea, top to bottom) and a step-by-step **Jupyter notebook**
(`.ipynb`) that rebuilds it cell by cell, with the *why* spelled out before each
small step. Both run **offline with no API key**: a deterministic, rule-based
controller (and a lexical retriever stand-in) is the reproducible default, and a
real LLM is one env flag away via a single swappable `generate()`.

## The series

The **failure-driven** spine: every part opens on a concrete way the previous
part's agent breaks, and resolves it with exactly one new mechanism.

| Part | Topic | Code | Notebook | Essay |
|---|---|---|---|---|
| 1 | The Augmented LLM: a real loop with typed tools | [augmented_llm_loop.py](part-01-augmented-llm-loop/augmented_llm_loop.py) | [notebook](part-01-augmented-llm-loop/augmented_llm_loop.ipynb) | [read](https://www.mefby.com/essays/augmented-llm-loop) |
| 2 | When Tools Fail: retries, timeouts, and a failure taxonomy | [robust_execution.py](part-02-robust-tool-execution/robust_execution.py) | [notebook](part-02-robust-tool-execution/robust_execution.ipynb) | [read](https://www.mefby.com/essays/robust-tool-execution) |
| 3 | Planning the Work: plan-and-execute, ReWOO, and the tool DAG | [planners.py](part-03-planning-and-the-tool-dag/planners.py) | [notebook](part-03-planning-and-the-tool-dag/planners.ipynb) | [read](https://www.mefby.com/essays/planning-and-the-tool-dag) |
| 4 | Surviving a Broken Plan: the critic and error-triggered replanning | [replanning_critic.py](part-04-replanning-and-critic/replanning_critic.py) | [notebook](part-04-replanning-and-critic/replanning_critic.ipynb) | [read](https://www.mefby.com/essays/replanning-and-critic) |
| 5 | Learning from Failure: in-loop reflection and Reflexion | [reflexion.py](part-05-reflection-and-reflexion/reflexion.py) | [notebook](part-05-reflection-and-reflexion/reflexion.ipynb) | [read](https://www.mefby.com/essays/reflection-and-reflexion) |
| 6 | The Four Memories: typed stores the agent edits itself | [four_memories.py](part-06-four-memories-self-editing/four_memories.py) | [notebook](part-06-four-memories-self-editing/four_memories.ipynb) | [read](https://www.mefby.com/essays/four-memories-self-editing) |
| 7 | Surviving the Long Haul: compaction and forgetting | [compaction_and_forgetting.py](part-07-compaction-and-forgetting/compaction_and_forgetting.py) | [notebook](part-07-compaction-and-forgetting/compaction_and_forgetting.ipynb) | [read](https://www.mefby.com/essays/compaction-and-forgetting) |
| 8 | Stopping the Runaway: budgets, loop detection, and the circuit breaker | [budget_circuit_breaker.py](part-08-budgets-and-circuit-breaker/budget_circuit_breaker.py) | [notebook](part-08-budgets-and-circuit-breaker/budget_circuit_breaker.ipynb) | [read](https://www.mefby.com/essays/budgets-and-circuit-breaker) |
| 9 | The Durable Agent: event journal, replay, and effectively-once | [durable_agent.py](part-09-durable-agent/durable_agent.py) | [notebook](part-09-durable-agent/durable_agent.ipynb) | [read](https://www.mefby.com/essays/durable-agent) |
| 10 | Pause, Approve, Resume, Steer: human-in-the-loop | [pause_approve_resume.py](part-10-pause-approve-resume/pause_approve_resume.py) | [notebook](part-10-pause-approve-resume/pause_approve_resume.ipynb) | [read](https://www.mefby.com/essays/pause-approve-resume) |
| 11 | Shipping It: tracing, cost-per-success, and the core capstone | [observable_agent.py](part-11-observable-agent/observable_agent.py) | [notebook](part-11-observable-agent/observable_agent.ipynb) | [read](https://www.mefby.com/essays/observable-agent) |
| 12 | Tools as a Protocol: a minimal MCP server and host by hand | [mcp_server_and_host.py](part-12-mcp-by-hand/mcp_server_and_host.py) | [notebook](part-12-mcp-by-hand/mcp_server_and_host.ipynb) | [read](https://www.mefby.com/essays/mcp-by-hand) |
| 13 | The Code-Running Tool: sandboxed execution and computer-use | [sandboxed_code_tool.py](part-13-code-execution-and-sandbox/sandboxed_code_tool.py) | [notebook](part-13-code-execution-and-sandbox/sandboxed_code_tool.ipynb) | [read](https://www.mefby.com/essays/code-execution-and-sandbox) |
| 14 | The Supervisor and the Handoff: multi-agent, and when it hurts | [supervisor_and_handoffs.py](part-14-supervisor-and-handoffs/supervisor_and_handoffs.py) | [notebook](part-14-supervisor-and-handoffs/supervisor_and_handoffs.ipynb) | [read](https://www.mefby.com/essays/supervisor-and-handoffs) |
| 15 | Agent to Agent: A2A delegation across boundaries | [a2a_delegation.py](part-15-a2a-agent-interop/a2a_delegation.py) | [notebook](part-15-a2a-agent-interop/a2a_delegation.ipynb) | [read](https://www.mefby.com/essays/a2a-agent-interop) |
| 16 | Securing the Agent: the lethal trifecta and untrusted tools | [secure_agent.py](part-16-securing-the-agent/secure_agent.py) | [notebook](part-16-securing-the-agent/secure_agent.ipynb) | [read](https://www.mefby.com/essays/securing-the-agent) |
| 17 | Grading the Agent: three-layer eval and the regression gate | [agent_eval.py](part-17-agent-evaluation/agent_eval.py) | [notebook](part-17-agent-evaluation/agent_eval.ipynb) | [read](https://www.mefby.com/essays/agent-evaluation) |

### Roadmap (building in order)

**Core track — grow one agent from a bare loop to production**

**Frontier track — open the agent to the protocol wire and multi-agent**

## Quick start

```bash
# from the repo root; no dependencies, no API key, no network
python3 part-01-augmented-llm-loop/augmented_llm_loop.py
```

Prefer it step by step? Open the part's `.ipynb` in Jupyter or Colab.

Optional real paths (any one):
```bash
export OPENAI_API_KEY=...        # see the real LLM-driven controller path
# the deterministic rule controller still runs so output stays reproducible
```

## How the offline fallback works

The teaching point of every part is something you can *read*: the controller is a
transparent set of rules in the offline default, so you can see exactly why the
agent takes each step. With an API key, the same loop is driven by a real model
through `generate()` — but the file always falls through to the deterministic
policy so the printed trace is reproducible. SDK names and model ids move fast;
only `generate()` ever needs editing to light up the real path.

## License

MIT — see [LICENSE](LICENSE).
