"""
Learning from Failure: in-loop reflection and Reflexion.
Agents from First Principles, Part 5.

Part 4 taught the agent to revise a plan when the world disagrees mid-run. But run
the same agent twice on the same task and it makes the same mistake the same way
both times. Replanning recovers WITHIN a run; nothing carries WHAT IT LEARNED from
one run to the next. The agent is an amnesiac that re-earns every lesson.

This part gives it two ways to learn from a failure, one within a single attempt
and one across attempts.

1. IN-LOOP SELF-CRITIQUE. Before it finishes, the agent re-reads its own draft
   against a checklist and fixes what it can SEE: a missing amount, an uncited
   policy. Cheap, and it catches presentation mistakes in the same trial. But it
   has a ceiling: the agent cannot self-critique a WRONG NUMBER it has no ground
   truth for. It will confidently polish a draft that is quietly incorrect.

2. REFLEXION (Shinn et al., 2023). The mistake that self-critique cannot see is
   caught by an external CHECKER, a reward signal from the environment. Reflexion
   turns that verdict into a VERBAL post-mortem and writes it to an EPISODIC
   BUFFER, and the next attempt READS the buffer before it acts. The loop is:
       actor -> checker (reward) -> self-reflection (verbal) -> buffer -> actor ...
   This is "verbal reinforcement": the policy is not retrained, the lesson is just
   text the next trial reads.

THE HONEST PART (this is the whole point, do not fake it). The deterministic
reflection here is a REAL rule whose output the actor MECHANICALLY reads on the
next trial. Convergence is genuinely CAUSED by the buffer, not by a script that
flips trial 2 to "correct." We prove it by running the same loop with the buffer
TURNED OFF: with no memory, the agent repeats the identical mistake every trial and
never converges. Same actor, same task; the only difference is whether the lesson
persists.

A sober note carried throughout: reflection is not monotonic. A wrong reflection
can mislead the next trial and make it WORSE. Verbal reinforcement is a heuristic,
not a guarantee.

THE TASK. A return for order ORD-3300, a $200 order, comes in AFTER the 30-day
window. Policy: a return after the window still gets a refund, but a 10% restocking
fee applies, so the correct refund is $180.00, and the decision must state the
amount and the policy basis. The naive actor forgets the fee and quotes $200.00.

CONNECTION: the CHECKER is RAG Part 11's LLM-as-judge repurposed as an offline
reward signal (does the output satisfy the policy?), not answer-quality scoring.
The episodic buffer here is the SEED of the typed episodic memory store Part 6
formalizes.

CONTINUITY: same refund world; deterministic rule actor/checker/reflector offline,
with generate() the real-LLM path one env flag away.

Run:
  python3 reflexion.py        # offline; no API key, no network, no deps

NOTE: SDK names and model ids move fast; only generate() would need edits.

Expected output (deterministic default path):
========================================================================
LEARNING FROM FAILURE  -  in-loop self-critique and cross-trial Reflexion
========================================================================
[actor] no OPENAI_API_KEY; using deterministic rule actor/checker/reflector (offline default)

TASK: refund decision for ORD-3300, a $200.00 order returned AFTER
the 30-day window. Policy-correct refund is $180.00 (a 10% restocking fee).

------------------------------------------------------------------------
IN-LOOP SELF-CRITIQUE: fix the draft you can see (within one trial).
------------------------------------------------------------------------
  draft:  'Your return is approved.'
  critique: state the refund amount; cite the policy basis
  revised: 'Refund decision for ORD-3300: $200.00 approved, per the returns policy (item returned after the 30-day window).'
  ...but the external checker still says: FAIL -- refund $200.00 != policy-correct $180.00: the 10% restocking fee for returns after the window was not applied
  -> self-critique made the text complete; it could NOT catch a wrong number
     it has no ground truth for. That gap is what Reflexion fills.

========================================================================
REFLEXION (buffer ON): the checker's verdict becomes a lesson the next trial reads.
========================================================================
  Trial 1 (reflections in buffer: 0)
    actor: full refund (no restocking fee considered) -> $200.00
    self-critique: revise (state the refund amount; cite the policy basis)
      -> 'Refund decision for ORD-3300: $200.00 approved, per the returns policy (item returned after the 30-day window).'
    checker: FAIL -- refund $200.00 != policy-correct $180.00: the 10% restocking fee for returns after the window was not applied
    reflection appended: 'Returns after the 30-day window incur a 10% restocking fee; multiply the order total by 0.9 before quoting the refund.'
  Trial 2 (reflections in buffer: 1)
    actor: applied the 10% restocking fee (learned from a reflection) -> $180.00
    self-critique: revise (state the refund amount; cite the policy basis)
      -> 'Refund decision for ORD-3300: $180.00 approved, per the returns policy (item returned after the 30-day window).'
    checker: PASS -- refund $180.00 matches the policy-correct $180.00
  -> converged on trial 2 (the buffer carried the lesson forward)

========================================================================
THE CONTROL (buffer OFF): same actor, same task, but the lesson is discarded.
========================================================================
  Trial 1 (reflections in buffer: 0)
    actor: full refund (no restocking fee considered) -> $200.00
    self-critique: revise (state the refund amount; cite the policy basis)
      -> 'Refund decision for ORD-3300: $200.00 approved, per the returns policy (item returned after the 30-day window).'
    checker: FAIL -- refund $200.00 != policy-correct $180.00: the 10% restocking fee for returns after the window was not applied
    buffer OFF: reflection discarded; next trial starts amnesiac
  Trial 2 (reflections in buffer: 0)
    actor: full refund (no restocking fee considered) -> $200.00
    self-critique: revise (state the refund amount; cite the policy basis)
      -> 'Refund decision for ORD-3300: $200.00 approved, per the returns policy (item returned after the 30-day window).'
    checker: FAIL -- refund $200.00 != policy-correct $180.00: the 10% restocking fee for returns after the window was not applied
    buffer OFF: reflection discarded; next trial starts amnesiac
  Trial 3 (reflections in buffer: 0)
    actor: full refund (no restocking fee considered) -> $200.00
    self-critique: revise (state the refund amount; cite the policy basis)
      -> 'Refund decision for ORD-3300: $200.00 approved, per the returns policy (item returned after the 30-day window).'
    checker: FAIL -- refund $200.00 != policy-correct $180.00: the 10% restocking fee for returns after the window was not applied
    buffer OFF: reflection discarded; next trial starts amnesiac
  -> did NOT converge in 3 trials

========================================================================
WHAT JUST HAPPENED
========================================================================
  buffer ON : converged on trial 2 -- the appended reflection changed the
              actor's computation from $200.00 to $180.00.
  buffer OFF: never converged -- the identical mistake repeated every trial.
  The only difference was whether the lesson persisted, so the BUFFER (not a
  script) is what caused convergence. This is the seed of Part 6's episodic memory.
  Sober note: reflection is not monotonic. A wrong lesson can mislead the next
  trial and make it worse; verbal reinforcement is a heuristic, not a guarantee.
========================================================================
"""

import os


# ===========================================================================
# Step 0. The task and its policy-correct answer. The restocking fee is the trap:
# a return after the window is refundable, but at 90% of the order total.
# ===========================================================================
ORDER_ID = "ORD-3300"
ORDER_TOTAL = 200.0
RESTOCKING_FEE = 0.10                     # 10% for returns after the 30-day window
CORRECT_REFUND = round(ORDER_TOTAL * (1 - RESTOCKING_FEE), 2)   # 180.00


# ===========================================================================
# Step 1. The actor. Its computation READS the reflection buffer: if any reflection
# tells it about the restocking fee, it applies the fee; otherwise it quotes the
# full total. This is the mechanical link that makes the buffer matter -- the actor
# behaves differently ONLY because of what it read.
# ===========================================================================
def actor_compute(order_total, reflections):
    learned_fee = any("restocking fee" in r.lower() for r in reflections)
    if learned_fee:
        refund = round(order_total * (1 - RESTOCKING_FEE), 2)
        note = "applied the 10% restocking fee (learned from a reflection)"
    else:
        refund = order_total
        note = "full refund (no restocking fee considered)"
    return refund, note


def actor_draft():
    """The naive first draft: a bare approval, missing the amount and the basis."""
    return "Your return is approved."


# ===========================================================================
# Step 2. In-loop self-critique. Within ONE trial, re-read the draft against a
# checklist and fix what is visible: state the amount, cite the policy. Note what
# it CANNOT do: it has no ground truth for the number, so it cannot tell that a
# polished $200.00 is wrong.
# ===========================================================================
def self_critique(draft, refund):
    issues = []
    if f"${refund:.2f}" not in draft:
        issues.append("state the refund amount")
    if "policy" not in draft.lower():
        issues.append("cite the policy basis")
    if not issues:
        return draft, issues
    revised = (f"Refund decision for {ORDER_ID}: ${refund:.2f} approved, per the "
               "returns policy (item returned after the 30-day window).")
    return revised, issues


# ===========================================================================
# Step 3. The external CHECKER -- the reward signal. It knows the policy-correct
# refund (the environment does), so it can catch the wrong number self-critique
# cannot. This is RAG Part 11's judge repurposed: a pass/fail oracle, not a quality
# score.
# ===========================================================================
def checker(refund):
    if abs(refund - CORRECT_REFUND) < 0.01:
        return True, f"refund ${refund:.2f} matches the policy-correct ${CORRECT_REFUND:.2f}"
    return (False, f"refund ${refund:.2f} != policy-correct ${CORRECT_REFUND:.2f}: the 10% "
            "restocking fee for returns after the window was not applied")


# ===========================================================================
# Step 4. The reflector. Turn the checker's failure reason into a concrete,
# actionable verbal lesson the actor can read next time. The offline version is a
# real rule (it keys on the failure reason); generate() would write the same note
# in prose. The lesson MUST be specific enough to change behavior.
# ===========================================================================
def reflect(checker_reason):
    if "restocking fee" in checker_reason:
        return ("Returns after the 30-day window incur a 10% restocking fee; multiply "
                "the order total by 0.9 before quoting the refund.")
    return f"Trial failed: {checker_reason}. Try a different approach."


# ===========================================================================
# Step 5. generate() -- the real LLM path (reference shape only). Offline, the rule
# actor/checker/reflector is the source of truth (same device as Parts 1-4).
# ===========================================================================
def generate(prompt):
    """REAL path: ask a hosted LLM to act, check, or reflect. Unused offline."""
    from openai import OpenAI
    client = OpenAI()
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
    )
    return resp.choices[0].message.content


# ===========================================================================
# Step 6. The Reflexion loop. Each trial: the actor (reading the buffer) computes
# and drafts, self-critique fixes the draft, the checker grades. On failure, the
# reflector writes a lesson; if the buffer is ON, that lesson is appended and the
# next trial reads it. With the buffer OFF, the lesson is discarded and the agent
# starts the next trial amnesiac.
# ===========================================================================
def reflexion_run(max_trials=3, use_buffer=True):
    reflections = []
    final = None
    for trial in range(1, max_trials + 1):
        print(f"  Trial {trial} (reflections in buffer: {len(reflections)})")
        refund, compute_note = actor_compute(ORDER_TOTAL, reflections)
        print(f"    actor: {compute_note} -> ${refund:.2f}")
        draft = actor_draft()
        revised, issues = self_critique(draft, refund)
        if issues:
            print(f"    self-critique: revise ({'; '.join(issues)})")
            print(f"      -> {revised!r}")
        else:
            print(f"    self-critique: no issues")
        final = revised
        ok, reason = checker(refund)
        if ok:
            print(f"    checker: PASS -- {reason}")
            print(f"  -> converged on trial {trial}"
                  + (" (the buffer carried the lesson forward)" if use_buffer and trial > 1 else ""))
            return trial, final
        print(f"    checker: FAIL -- {reason}")
        note = reflect(reason)
        if use_buffer:
            reflections.append(note)
            print(f"    reflection appended: {note!r}")
        else:
            print(f"    buffer OFF: reflection discarded; next trial starts amnesiac")
    print(f"  -> did NOT converge in {max_trials} trials")
    return None, final


# ===========================================================================
# Demo. Everything below RUNS OFFLINE.
# ===========================================================================
if __name__ == "__main__":
    bar = "=" * 72
    print(bar)
    print("LEARNING FROM FAILURE  -  in-loop self-critique and cross-trial Reflexion")
    print(bar)
    if os.environ.get("OPENAI_API_KEY"):
        print("[actor] OPENAI_API_KEY set; the real LLM would act/check/reflect via "
              "generate(). Falling through to the deterministic rules so output is reproducible.")
    else:
        print("[actor] no OPENAI_API_KEY; using deterministic rule actor/checker/reflector "
              "(offline default)")
    print(f"\nTASK: refund decision for {ORDER_ID}, a ${ORDER_TOTAL:.2f} order returned AFTER")
    print(f"the 30-day window. Policy-correct refund is ${CORRECT_REFUND:.2f} (a 10% restocking fee).")

    # --- In-loop self-critique: what it fixes, and its ceiling. -------------
    print("\n" + "-" * 72)
    print("IN-LOOP SELF-CRITIQUE: fix the draft you can see (within one trial).")
    print("-" * 72)
    refund0, note0 = actor_compute(ORDER_TOTAL, [])          # no reflections yet
    draft0 = actor_draft()
    print(f"  draft:  {draft0!r}")
    revised0, issues0 = self_critique(draft0, refund0)
    print(f"  critique: {'; '.join(issues0)}")
    print(f"  revised: {revised0!r}")
    ok0, reason0 = checker(refund0)
    print(f"  ...but the external checker still says: {'PASS' if ok0 else 'FAIL'} -- {reason0}")
    print("  -> self-critique made the text complete; it could NOT catch a wrong number")
    print("     it has no ground truth for. That gap is what Reflexion fills.")

    # --- Reflexion WITH the buffer: the lesson persists across trials. ------
    print("\n" + bar)
    print("REFLEXION (buffer ON): the checker's verdict becomes a lesson the next trial reads.")
    print(bar)
    trial_on, ans_on = reflexion_run(max_trials=3, use_buffer=True)

    # --- The control: same actor, buffer OFF. Proves the buffer causes it. --
    print("\n" + bar)
    print("THE CONTROL (buffer OFF): same actor, same task, but the lesson is discarded.")
    print(bar)
    trial_off, ans_off = reflexion_run(max_trials=3, use_buffer=False)

    print("\n" + bar)
    print("WHAT JUST HAPPENED")
    print(bar)
    print(f"  buffer ON : converged on trial {trial_on} -- the appended reflection changed the")
    print(f"              actor's computation from ${ORDER_TOTAL:.2f} to ${CORRECT_REFUND:.2f}.")
    print(f"  buffer OFF: never converged -- the identical mistake repeated every trial.")
    print("  The only difference was whether the lesson persisted, so the BUFFER (not a")
    print("  script) is what caused convergence. This is the seed of Part 6's episodic memory.")
    print("  Sober note: reflection is not monotonic. A wrong lesson can mislead the next")
    print("  trial and make it worse; verbal reinforcement is a heuristic, not a guarantee.")
    print(bar)
