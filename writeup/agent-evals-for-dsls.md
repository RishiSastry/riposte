# How I evaluate coding agents that write DSLs

A coding agent does not return an answer. It returns an artifact: a program, a config, a
policy. The only thing that matters is whether that artifact does what the task claimed. So the
useful question is not "did the model say something plausible," but "is there a reproducible way
to confirm the program is correct, checked by a machine rather than asserted by the author."

That question kept coming up for agents that write in domain-specific languages, small
languages a coding agent has to target exactly. The obvious first move is to ask a capable model
whether the output looks good. That turns out to be the weakest link, and this post is about how
little I ended up needing it. The thesis:

> When the agent writes a DSL you control, you can design the judgment into the language, and
> reach a trustworthy verdict with almost no model opinion in the loop.

To keep myself honest I built a small runnable example: **Riposte**, a DSL for Pokémon battle
policies that no model has ever seen. A program compiles to a JSON policy that plays real games
on a Pokémon Showdown server. Every number below comes out of it.

## A model's opinion is not a reproducible gate

Ask a model to score the same output a few times and the score moves. That is disqualifying for
a gate. A check that flickers teaches people to ignore it, and a trust signal everyone ignores
is worse than none, because it launders unverified work as verified. The judge is not wrong to
exist. It is wrong to be the thing that blocks.

That pushes everything onto one principle: separate what a machine can decide reproducibly from
what a model can only have an opinion about, and never let the second stand in for the first.
Concretely, every check gets one of two jobs.

- **Gate**: a reproducible, falsifiable check that can block. A build. A schema match. A number
  read off a real execution.
- **Report**: a surfaced signal that never blocks, for anything a model merely has an opinion
  about.

The rule of thumb is to push every criterion onto the most deterministic check that can hold it,
and pay a model only for the residue. The interesting part, for DSLs, is how much of the residue
you can design away.

## A DSL you control lets you put the judgment in the language

When the artifact is freeform, a web page or a paragraph, you fight to drag each criterion onto
the deterministic side, and you lose some of them to the judge. When the artifact is a program
in a language you designed, you own the two things that decide most of "is it correct":

1. You own the compiler. Build and static checks are deterministic and free, and they come with
   structured diagnostics.
2. You can design the type system so whole classes of wrong programs do not compile.

The second lever is the one you cannot get any other way. Riposte battles are partially
observable, so the language separates *facts* (what you know) from *estimates* (the opponent's
hidden stats). A comparison over an estimate is not a boolean. It is a `tribool` that has to be
resolved explicitly:

```
# opponent stats are estimates, so this comparison is a tribool:
when can_ko(my.active, opponent.active)          # rejected at compile time
when likely(can_ko(my.active, opponent.active))  # the uncertainty is made honest
```

An agent that treats a guess as a certainty does not produce a plausible-but-wrong program that
a judge has to catch. It produces a program that does not compile. Reading hidden state has no
syntax at all. **Every semantic bug you can turn into a compile error is a bug you never have to
pay a judge to find.** Designing the language is where the eval work actually happens, before a
single test is written.

## Compile is the floor, execution is the truth

"It compiled" is necessary and never sufficient. An agent can emit a program that compiles
cleanly and does entirely the wrong thing. So the build gates at the bottom of the ladder, and
the verdict is carried by what the program does when you run it.

This is the second reason a DSL is a good place to evaluate agents: if the language compiles to
a domain with a real execution environment, quality becomes a number too. Riposte policies play
on an actual Showdown server, so "does this program do the job" is win rate over many real
battles against fixed baselines, not an opinion.

It also exposes a gap that compile-only evals hide. Across the runs below, programs from very
different setups compiled at different rates but played about the same once valid, around 44%
against a mid-tier heuristic baseline. Compile-pass and competitive quality are different axes;
if you only gate on the build, you never see it. (A small pleasure from this: several
agent-written programs out-played my hand-written reference policy, which manages about 37%
against the same baseline.)

## Make diagnostics a product, not a byproduct

If you are going to own the compiler, spend real effort making its errors first-class: stable
codes, precise spans, a machine-readable format. This is not polish. Structured diagnostics turn
the deterministic gate into a teaching signal, a repair loop where the agent compiles, reads the
errors, and fixes its own program.

Here is the experiment that made the point. I varied how the language was delivered to the
agent, docs dumped into the prompt versus progressive discovery through tools, each with and
without a compiler-feedback repair loop, on a frontier model (Claude Opus) and a cheap one
(Claude Haiku):

| how the language was taught | compile-pass | quirk violations | win-rate | avg tokens |
|---|---|---|---|---|
| docs, one-shot | 83% | 0.11 | 45% | 21K |
| tool-discovery, one-shot | 89% | 0.06 | 42% | 35K |
| docs + repair loop | **100%** | **0.0** | 44% | 31K |
| tool-discovery + repair loop | **100%** | **0.0** | 44% | 48K |

> **Illustrative, not settled.** This is 3 tasks × 4 conditions × 2 models × k=3, one pass, win
> rate over 60 battles per cell. A real result set would use many more tasks (the design targets
> 25 to 40), and the compile-pass intervals here are wide. Read the direction, not the decimals.

The direction was sharper than "which channel wins." **The repair loop mattered more than the
delivery channel.** Both repair conditions reached 100% compile-pass and zero semantic-quirk
violations; every failure came from a no-repair run, and several were exactly the type errors
the language is built to catch. The mechanism was being able to compile-check and fix, and it was
the same whether the language was taught by docs or by tools. Paired with docs it got there for
fewer tokens, and the benefit concentrated in the cheap model, which needed the loop to reach the
frontier model's out-of-the-box reliability.

The point underneath the numbers: that result is only available because the diagnostics were
designed to be consumed. Good structured errors are the deterministic gate and the training
signal at the same time.

## Observe the path, not just the artifact

An agent is non-deterministic and produces an artifact, so there is no fixed function to assert
on and no way to unit-test it. You can only observe what it produced and the path it took. For
DSL agents that path is unusually legible, a sequence of tool calls and compile attempts, so the
harness records it: which references the agent consulted, how many repair rounds it took, tokens
spent. A program that is right the first time is a different signal from one that is right after
thirty flailing compiles, and the trajectory is how you tell them apart.

## Use the real thing, and prove your checks aren't hollow

Two disciplines carried a lot of weight.

**Use the real thing.** The real compiler, the real runtime, the real environment. When a
dependency genuinely cannot run, mark that outcome as its own state and keep it out of your
quality numbers, but never fake it, and never mock the thing under test. A green from a mock is
the most expensive kind of false confidence, invisible until it is in front of a user. In this
harness the eval shells out to the actual compiler binary and plays on the actual server; the
only thing stubbed is the agent, and only to test the harness itself.

**Prove your checks aren't vacuous, with mutation.** A wall of green checks tells you nothing if
the checks would pass anything. The cheap, decisive test is mutation: freeze a known-good
program, generate mutants that each break exactly one thing (delete a required token, introduce
one type error, drop a rule), and replay the eval. A check whose own mutant survives cannot gate,
and the mutation is the label, so you need no hand annotation. For a DSL this is almost free: the
golden broken-program snapshots (one that should raise `E030`, one that should raise `E040`) are
the mutation suite, and they double as compiler regression tests.

## What this comes to

Evaluating a coding agent that writes a DSL comes out as a short list:

- Evals are behavioral. Observe the real artifact and the path, not a mocked stand-in.
- Gate on the deterministic, report the judged, and use the DSL to move the boundary: own the
  compiler, design the type system so illegal states do not compile, target an environment so
  quality is a number.
- Make diagnostics first-class. They are the gate and the repair signal at once.
- Prove the checks are not hollow, with mutation.

I came in expecting the hard part to be a smarter judge. For DSLs it was the opposite. The hard
and satisfying part was designing the language and its diagnostics so that the judge I was
trying to shrink, I could mostly design away.

---

*Riposte, the runnable example behind every number here, is open in this repo: compiler (Rust),
runtime (Python), MCP server, and the eval harness. `python evals/experiment.py` reruns the
matrix; the full result set is in [findings.md](./findings.md).*
