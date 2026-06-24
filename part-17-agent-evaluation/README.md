# Part 17 - Grading the Agent: three-layer eval and the regression gate

> Through sixteen parts we judged the agent the same way: by eyeball. Eyeballing has one fatal blind spot. It checks the ANSWER, and an agent can reach the right answer through a wrong, wasteful, or unsafe PATH: a refund that lands only after three redundant searches, or a correct summary produced by a run that also tried to email your customer list. The fix is to GRADE a run in three orthogonal layers (OUTCOME, TRAJECTORY, COMPONENT) plus a golden-trajectory CI gate with an operating envelope, so the right-answer-wrong-path run is caught before it ships and a cost regression flips a case red. RAG Part 11 evaluated retrieval and generation QUALITY for a single-shot pipeline and cataloged the answer-quality judge biases; this evaluates the PATH of a multi-step run. This is the finale: the last thing we build is how to know the agent is right.

[📖 Read the essay](https://www.mefby.com/essays/agent-evaluation) · [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/mftnakrsu/agents-by-hand/blob/main/part-17-agent-evaluation/agent_eval.ipynb)

## What it covers
- **Eyeballing only checks the answer**: through all sixteen prior parts we judged the agent by reading its final text. That checks the ANSWER and nothing else, so an agent that reaches the right answer through a wrong, wasteful, or unsafe PATH sails through. A refund that lands only after three redundant searches, or a correct summary produced by a run that also tried to email the customer list, both look fine on the surface. This part replaces the eyeball with a graded run.
- **The three layers, graded independently**: OUTCOME (did the world end up correct, ideally checked against world STATE not just the text, tau2-style), TRAJECTORY/process (was the PATH good: tool-call set precision/recall, argument validity, an order-aware edit distance against a golden trajectory, and step count against a budget), and COMPONENT (do the individual pieces pass their unit checks). Each layer catches a different class of failure, and a run can be green on two while red on the third.
- **The right-answer-wrong-path case**: the motivating run. `refund (good path)` is `outcome=True component=True trajectory: precision=1.0 recall=1.0 edit=0 steps=3/3 -> PASS`. `refund (right answer, wrong path)` reaches the SAME correct refund but takes a detour: `outcome=True component=True trajectory: precision=0.75 recall=1.0 edit=2 steps=5/3 -> FAIL`. Outcome and component pass; the trajectory layer is the only thing that catches it. Eyeballing the final answer would have shipped it.
- **The gameable judge vs the programmatic guard**: an LLM-as-judge can score a trajectory against a rubric, but for TRAJECTORIES it is gameable. On the SAME bad path, terse narration scores `0.6` and verbose, confident self-narration ("I carefully and thoroughly worked step by step...") scores `0.9` (higher, for the same path), while reordering also fools it. The programmatic guard (precision/recall, edit distance, the envelope) returns `FAIL` either way, unchanged by narration. The judge rewards confident prose; the guard measures the path. (RAG Part 11 cataloged the ANSWER-quality judge biases; we cite it, we do not re-list them.)
- **The golden-trajectory CI gate, the operating envelope, and cost-per-success**: a CI-style suite of curated cases, each a (task -> expected outcome + expected trajectory + OPERATING ENVELOPE of max steps / max tool-calls / max token-cost / timeout). Replay them all, assert outcome AND tool-call correctness AND the envelope, and report COST PER SUCCESS (Part 11). At `<= 400 tokens/run` the gate is `3/4 green` with cost-per-success `$0.00320`: GREEN `refund (good path)` `$0.00240`, RED `refund (right answer, wrong path)` `$0.00400` (trajectory), GREEN `warranty lookup` `$0.00160`, GREEN `security: poisoned ticket (Part 16)` `$0.00160`. TIGHTEN the envelope to `<= 200 tokens/run` and the gate drops to `2/4 green` with cost-per-success `$0.00480`: `refund (good path)` flips RED `$0.00240` (over token budget). Tightening the envelope is how you catch the regression where the agent quietly got more expensive.
- **tau2-style verifiable success**: the strongest outcome check is world STATE plus POLICY, not text. The ledger holds exactly the authorized refund, not "the text said done." Caveats apply: a contaminated suite or a reward-hacked trajectory can pass the letter while missing the point, so verifiable success is necessary but not sufficient. (See tau-bench / tau2-bench.)
- **Security as eval**: a security guarantee you do not test is a security guarantee you do not have. The Part 16 poisoned-ticket attack becomes just another case in the suite: replay it and assert NO unauthorized refund and NO exfiltration. Here that is `ledger={} (no unauthorized refund), no exfiltration -> GREEN`.

## Files
- **`agent_eval.py`** — the single runnable script: the three grading layers (`grade_outcome` against world state, `grade_trajectory` with set precision/recall + an order-aware `_edit_distance` + step count vs budget, `grade_component` for unit checks), the deterministic `judge_trajectory` stub whose verbosity bias we expose alongside the `generate()` real-LLM judge one flag away, the golden-trajectory regression `SUITE` (each case a run + expected state + golden trajectory + operating envelope, including the Part 16 security case), `grade_case` rolling the layers plus token-cost into a pass/fail, and the `run_gate` driver that prints GREEN/RED, the green count, and cost-per-success at two envelopes. All wired into the offline demo: the three layers, the gameable judge, the gate at `<= 400` then tightened to `<= 200`, and verifiable success + security as eval.
- **`agent_eval.ipynb`** — step-by-step notebook: a markdown why before each small code step, built cell by cell.

## Run it
```bash
# from the repo root; no dependencies, no API key, no network
python3 part-17-agent-evaluation/agent_eval.py   # runs offline
```
Prefer it step by step? Open `agent_eval.ipynb` in Jupyter, or click **Open in Colab** above.

## Key idea
Eyeballing checks the ANSWER; an agent can reach the right answer through a wrong, wasteful, or unsafe PATH. So you grade a run three orthogonal ways and gate it in CI:

```
  THREE LAYERS (grade one run three independent ways):
    OUTCOME     did the world end up correct?   -> state + policy, not text (tau2-style)
    TRAJECTORY  was the PATH good?               -> precision/recall + edit distance + steps vs budget
    COMPONENT   do the pieces pass unit checks?  -> per-call argument validity

  the motivating case:  right answer, wrong path
    outcome=True  component=True  trajectory: precision=0.75 recall=1.0 edit=2 steps=5/3 -> FAIL

  the judge is gameable (for trajectories):  same bad path, terse -> 0.6, verbose -> 0.9
    the programmatic guard -> FAIL (unchanged by narration)

  the golden-trajectory gate (replay; assert outcome + trajectory + envelope):
    <= 400 tokens/run -> 3/4 green, cost-per-success $0.00320
    <= 200 tokens/run -> 2/4 green, cost-per-success $0.00480   (tightening catches a cost regression)
```

A summarize-shaped refund task that lands the right answer through the wrong path shows why eyeballing fails: outcome and component both pass, and only the trajectory layer catches it. The golden-trajectory gate turns that judgment into a CI guarantee with an operating envelope and a cost-per-success number, and security-as-eval (the Part 16 poisoned ticket: `ledger={}`, no exfiltration) makes the safety property a test rather than a hope. RAG Part 11 graded answer QUALITY for a single-shot pipeline; this grades the PATH of a multi-step run. Multi-turn and long-horizon trajectory eval is the reader's next extension.

## Offline by design
The whole demo runs with no network, no API key, and no dependencies. The grading layers are plain arithmetic over fixed trajectories: `grade_trajectory` computes set precision/recall and an order-aware Levenshtein edit distance against the golden path, `grade_outcome` compares world state, and `grade_component` checks per-call arguments, so the same numbers print every run. The LLM-as-judge is a deterministic stub (`judge_trajectory`) that rewards the verbosity keywords on purpose, so its trajectory bias is visible offline (terse `0.6`, verbose `0.9`, same path) the same way RAG P11/P12 made their biases visible; the programmatic guard returns `FAIL` regardless. Cost is `len(traj) * TOKENS_PER_STEP * PRICE_PER_TOKEN`, and the envelope check is a membership-style comparison against the token budget, so the gate reports `3/4` then `2/4` green identically every run. Set `OPENAI_API_KEY` and a real LLM would be the judge via `generate()`, but the demo falls through to the deterministic judge for reproducibility. Only `generate()` would need edits to light up the real path. The verifiable-success framing follows tau-bench / tau2-bench (world state + policy, with contamination and reward-hacking caveats); eval methodology moves fast, so check the current guidance.

---
[Series index](../) · The series is complete — Parts 1 to 17. We started with a bare model and a loop and ended with an agent that is robust, planful, reflective, remembering, bounded, durable, supervised, observable, protocol-speaking, sandboxed, multi-agent, secured, and now GRADED. Built by hand, one mechanism at a time. 🎉
