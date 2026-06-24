# Part 5 - Learning from Failure: in-loop reflection and Reflexion

> Part 4 recovers WITHIN a run by revising a broken plan, which buys a new failure: run the same agent twice on the same task and it makes the same mistake the same way both times, because nothing carries what it learned from one run to the next. The agent is an amnesiac that re-earns every lesson.

[📖 Read the essay](https://www.mefby.com/essays/reflection-and-reflexion) · [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/mftnakrsu/agents-by-hand/blob/main/part-05-reflection-and-reflexion/reflexion.ipynb)

## What it covers
- **The amnesiac-across-runs failure**: Part 4's replanning recovers within a single attempt, but no lesson persists between attempts. Run the naive actor twice on the same return and it quotes the wrong refund the same way both times. The task is a return for ORD-3300, a $200.00 order returned AFTER the 30-day window: policy says it is refundable but a 10% restocking fee applies, so the policy-correct refund is $180.00 and the decision must state the amount and the policy basis. The naive actor forgets the fee and quotes $200.00.
- **In-loop self-critique and its ceiling**: before it finishes, the agent re-reads its own draft against a checklist and fixes what it can SEE: a missing amount, an uncited policy. It turns the bare `'Your return is approved.'` into a complete, cited decision in the same trial. But it has a ceiling: it has no ground truth for the number, so it confidently polishes a draft that quotes $200.00, and the external checker still FAILs. Self-critique cannot catch a wrong number.
- **The Reflexion loop**: the mistake self-critique cannot see is caught by an external CHECKER, a reward signal from the environment. Reflexion (Shinn et al., 2023) turns that verdict into a VERBAL post-mortem, writes it to an EPISODIC BUFFER, and the next trial READS the buffer before it acts. The loop is `actor -> checker (reward) -> self-reflection (verbal) -> buffer -> actor`. This is "verbal reinforcement": the policy is not retrained, the lesson is just text the next trial reads.
- **The buffer-causes-convergence control**: convergence is genuinely CAUSED by the buffer, not by a script that flips trial 2 to "correct." The actor's computation MECHANICALLY reads the buffer: a reflection mentioning the restocking fee makes it multiply the order total by 0.9. With the buffer ON, trial 1 quotes $200.00 and FAILs, the reflection is appended, and trial 2 reads it and quotes $180.00 and PASSes. With the buffer OFF, the same actor on the same task discards the lesson each trial and repeats the identical $200.00 mistake across three trials, never converging. Same actor, same task; the only difference is whether the lesson persists.
- **The checker as RAG Part 11's judge repurposed**: the CHECKER is RAG Part 11's LLM-as-judge repurposed as an offline reward signal (does the output satisfy the policy?), a pass/fail oracle, NOT answer-quality scoring.
- **The episodic buffer as the seed of Part 6**: the reflection buffer here is the SEED of the typed episodic memory store Part 6 formalizes.
- **The sober note that reflection can regress**: reflection is not monotonic. A wrong reflection can mislead the next trial and make it WORSE. Verbal reinforcement is a heuristic, not a guarantee.
- **Reuse, not re-teaching**: this part references the ReAct loop, the tool contract, the retry taxonomy, and replanning from Parts 1 to 4 rather than re-deriving them. The only RAG touchpoint is Part 11's judge, repurposed. NET-NEW here: in-loop self-critique, the Reflexion loop, the episodic reflection buffer, verbal reinforcement, and the buffer-causes-convergence demonstration.

## Files
- **`reflexion.py`** — the single runnable script: the ORD-3300 task and its policy-correct refund, the `actor_compute` whose computation reads the reflection buffer, the naive `actor_draft`, the in-loop `self_critique` and its visible ceiling, the external `checker` (RAG Part 11's judge repurposed as a reward signal), the `reflect` reflector that turns a failure reason into a verbal lesson, the real-LLM `generate()` it stands in for, the `reflexion_run` loop with a `use_buffer` flag, and the demo that runs self-critique, the buffer-ON Reflexion loop, and the buffer-OFF control against the same task.
- **`reflexion.ipynb`** — step-by-step notebook: a markdown why before each small code step, built cell by cell.

## Run it
```bash
# from the repo root; no dependencies, no API key, no network
python3 part-05-reflection-and-reflexion/reflexion.py          # runs offline
# optional: set OPENAI_API_KEY to see the real-LLM banner (still falls through to the rule actor/checker/reflector)
```
Prefer it step by step? Open `reflexion.ipynb` in Jupyter, or click **Open in Colab** above.

## Key idea
Two ways to learn from a failure, one within a single attempt and one across attempts. In-loop self-critique re-reads the draft against a checklist and fixes what it can see, turning a bare approval into a complete, cited decision in the same trial:

```
revised: 'Refund decision for ORD-3300: $200.00 approved, per the returns policy (item returned after the 30-day window).'
...but the external checker still says: FAIL -- refund $200.00 != policy-correct $180.00: the 10% restocking fee for returns after the window was not applied
```

That FAIL is the ceiling: self-critique made the text complete, but it cannot catch a wrong number it has no ground truth for. Reflexion fills the gap. The external CHECKER (a reward signal) catches the wrong number, the reflector turns the verdict into a verbal lesson, the lesson goes to the episodic buffer, and the next trial reads it before it acts. With the buffer ON, the lesson `'Returns after the 30-day window incur a 10% restocking fee; multiply the order total by 0.9 before quoting the refund.'` is appended after trial 1, and trial 2 reads it and converges:

```
Trial 2 (reflections in buffer: 1)
  actor: applied the 10% restocking fee (learned from a reflection) -> $180.00
  ...
  checker: PASS -- refund $180.00 matches the policy-correct $180.00
-> converged on trial 2 (the buffer carried the lesson forward)
```

This is verbal reinforcement: nothing is retrained, the lesson is just text the next trial reads. Knowing a trial failed and being able to carry that lesson into the next trial are different things; the episodic buffer is the second. This traces directly to Reflexion (Shinn et al., 2023), and the episodic buffer here is the seed of Part 6's typed episodic memory.

## Offline by design
The whole demo runs with no network and no API key. A deterministic rule actor, a deterministic rule checker, and a deterministic rule reflector stand in for a trained LLM, so output is reproducible and the wrong-refund failure fires the same way every run. The honesty is load-bearing: the actor's computation MECHANICALLY reads the buffer, so convergence is genuinely caused by the appended reflection, not by a script. The buffer-OFF control proves the causation: same actor, same task, but the lesson is discarded each trial, so the identical $200.00 mistake repeats and the run never converges in three trials. The only variable is whether the buffer persists. The real path sits behind a flag: set OPENAI_API_KEY and the demo prints a banner noting the real LLM would act, check, and reflect via `generate()`, then falls through to the deterministic rules so output stays reproducible. Only `generate()` would need edits to light up production. The self-critique revision, every checker verdict, the appended reflection, the buffer-ON convergence, and the buffer-OFF non-convergence are identical either way.

---
[Series index](../) · [Part 6 — typed episodic memory (coming soon)](../)
