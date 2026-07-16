# Envelope chaining vs D8 — `--with-memory` output is no longer valid input

**Status:** confirmed regression in v0.39.0, **deliberately deferred** out of the release (decision taken 2026-07-14 during the PR #1048 review).
**Reported by:** Codex (P2) on the [v0.39.0 release PR #1048](https://github.com/Pipelex/pipelex/pull/1048#pullrequestreview-4698103093).
**Area:** D8 (strict unknown input names) × the agent CLI's stdin working-memory envelope.

## The bug

The agent CLI can no longer consume its own documented output. Piping an upstream `--with-memory` envelope into a downstream pipe that declares only *some* of the carried stuffs fails with `UnknownInputNameError`.

Three hops:

1. `resolve_stdin_inputs` (`pipelex/cli/agent_cli/commands/run/stdin_resolver.py:107-126`) explodes **every** entry of `working_memory.root` into an input entry. Its own docstring names the producer: *"Full envelope: a dict with a `working_memory` key at the top level (from upstream `--with-memory` output)"*.
2. Those inputs reach the shaper unchanged: `run_pipeline_core` → `PipelexMTHDSProtocol.execute(inputs=…)` → `prepare_pipe_job` (`pipelex/pipeline/execution_seams.py:195-207`, which always passes `input_specs=pipe.inputs`) → `WorkingMemoryFactory.make_from_pipeline_inputs` → `InputShaper.shape`.
3. `InputShaper._check_input_names` (`pipelex/core/memory/input_shaper.py:136-142`) raises on the **first** provided name absent from `input_specs.declared_names`. There is no envelope-vs-flat distinction, no ignore-extras path, and the only way to skip the shaper entirely is handing `execute` an already-built `WorkingMemory` — which the CLI never does.

An upstream sequence carries its own inputs in the envelope alongside its results, so the very first extra name (`text`) kills the run even though the declared input (`summary`) is present.

## Reproduction

Bundle with a `prepare` sequence (`inputs = { text = "Text" }`, step `result = "summary"`) and a `classify` pipe (`inputs = { summary = "Summary" }`):

```bash
pipelex-agent run bundle chain.mthds --pipe prepare \
  --inputs '{"text":"The quick brown fox jumps over the lazy dog."}' \
  --dry-run --no-graph --with-memory --format json > up.json
# working_memory.root keys: ['text', 'summary'];  aliases: {'main_stuff': 'summary'}

cat up.json | pipelex-agent run bundle chain.mthds --pipe classify --dry-run --no-graph --format json
```

```json
{
  "error": true,
  "error_type": "UnknownInputNameError",
  "message": "Input 'text' is not declared by this pipe. Declared inputs: 'summary'."
}
```

## Why it is a regression

`git show v0.38.0:pipelex/core/memory/working_memory_factory.py` — `make_from_pipeline_inputs` took no `input_specs` and performed no name check, so extra envelope entries were carried harmlessly into the working memory. `input_shaper.py` does not exist in v0.38.0; it arrived with Smart Inputs (#1028). v0.39.0 is therefore the first release where the envelope the CLI emits is not an envelope the CLI accepts.

The design anticipated the *class* of breakage but not this instance. `smart-inputs-design.md` (D8, "Risk to weigh") says: *"any workflow deliberately over-providing inputs … would break — if that pattern matters, downgrade to a warning."* What was never considered is that **the CLI itself is a first-party over-providing producer**: `--with-memory` exists precisely to carry the whole memory forward.

## Blast radius

- **The chaining pattern is taught in shipped agent skills.** `mthds-plugins/mthds/skills/mthds-run/SKILL.md` and `mthds-plugins/mthds/skills/shared/mthds-agent-guide.md` both instruct `run … --with-memory | run … --with-memory | run …`, with `--with-memory` on intermediate steps and a bare final step. Those examples are broken until this is fixed — **fixing them (or updating them) is part of the follow-up, and lives in the `mthds-plugins` repo, not here.**
- **It fails loudly**, with a precise, actionable message — not silent corruption. That is what made deferral acceptable.
- **Workarounds:** narrow the envelope before piping (`jq '{working_memory: {root: {summary: .working_memory.root.summary}, aliases: .working_memory.aliases}}'`), or drop `--with-memory` and pass `--inputs`.
- **Narrower than it looks for single-pipe upstreams:** when the upstream is a single pipe, its result lands under the literal key `main_stuff` with empty aliases, so a downstream declaring `summary` finds nothing to bind even with extras ignored. Full-envelope chaining is genuinely useful when the upstream is a *sequence* whose step `result` names match the downstream's declared inputs (the repro above). The fix restores a real but narrow capability.

## Fix options

**1. Core policy param — recommended.** Keep D8 strict for flat/file/inline inputs; make *envelope-derived* inputs lenient about extras. Thread the signal along the rails `inputs_base_dir` already uses (same shape, same call sites): `ParsedCliInputs` (`stdin_resolver.py:20-31`, gains a memory-derived marker set when `resolve_stdin_inputs` saw a `working_memory` key) → `run_pipeline_core` → `PipelexMTHDSProtocol.execute` → `prepare_pipe_job` (`execution_seams.py:172,202`) → `make_from_pipeline_inputs` (`working_memory_factory.py:71-107`) → `InputShaper.shape`. Carry it as a `StrEnum` (`UnknownInputNamePolicy.ERROR | IGNORE`, defaulting to `ERROR` everywhere — project standards ban `bool` params). Under `IGNORE`, filter `pipeline_inputs` down to `input_specs.declared_names` **before both** `_check_input_names` and the build loop — the loop calls `get_required_stuff_spec`, so undeclared names must be *dropped*, not merely un-raised.

**2. CLI-local filter.** After boot the CLI can resolve the target pipe, so it could filter the envelope-derived dict against the pipe's declared names itself. Zero core churn — but it puts the leniency outside the shaper that owns input semantics, and every other envelope consumer (the hosted runner) stays broken.

**3. Downgrade D8 to a warning.** The design doc's own escape hatch. One function, no plumbing, un-breaks every path including `--runner api`. Cost: gives up the misspelled-input safety net D8 was deliberately added to provide. Only worth it if we conclude the typo-catching value was overrated.

## Open question to settle with the fix

**Is envelope chaining a local-runner-only capability?** `--runner api` ships `inputs` as a plain dict to the hosted runner (`_run_core_api.py:22,45`), which applies the same D8 check server-side. A CLI-local policy signal (options 1 and 2) does not reach it, so `--runner api` + envelope chaining stays broken unless the MTHDS protocol carries the same signal — a cross-repo change (`mthds/protocol`, `pipelex-api`). Decide this explicitly rather than letting the local path quietly diverge from the hosted one.

A more principled alternative worth weighing at that point: treat a `working_memory` envelope as a **`WorkingMemory`**, not as inputs — hydrate it CLI-side and hand it to `execute`, which already bypasses the shaper (`execution_seams.py:196-197`). Semantically right ("memory in → memory continues", intermediates stay readable) and needs no shaper change; the cost is a hydrator from `smart_dump()` that needs the class registry loaded, which the CLI does not have before it builds the runner. That is why it was not done, not a reason it is wrong.

## Test approach for whoever fixes it

- **Shaper unit:** the lenient twin of the D8 test at `tests/unit/pipelex/core/memory/input_shaper/test_errors.py` — extras dropped, declared slots still shaped, strict policy still raising.
- **CLI unit:** `tests/unit/pipelex/cli/test_stdin_resolver.py` — pin that an envelope parse is flagged memory-derived and a flat parse is not.
- **e2e (the real chain):** `tests/e2e/pipelex/pipes/smart_inputs/` — a fixture bundle with an upstream sequence + downstream consumer; dry-run the upstream, feed the resolved envelope into the downstream, assert success. (`tests/e2e/pipelex/cli/test_toml_inputs_build.py` is the precedent if you want it to shell the real binary.)
