# Plan — let `codegen types` project concepts without an in-process PipeFunc

**Status:** planned, not started. Written 2026-08-05, revised the same day after `/plan-eng-review` (empirical instrumentation on `dev`) and a Codex outside-voice pass.

**One line:** `pipelex build structures` cannot run on a method whose custom PipeFunc Python is absent or unimportable, which makes a new PipeFunc method impossible to bootstrap — fix it with a narrow, named capability used by `codegen types` alone, not by relaxing what "load" means for every command.

## The bug

Structure codegen is a pure function of the concept set — the emitter's input type proves it:

```python
class ResolvedLibrary(BaseModel):
    mthds_version: str
    concepts: list[ResolvedConcept]      # no pipes field; emit_python_structures never reads one
```

But the command path builds the whole live pipe library first, and `PipeFunc` consults the global function registry while the object is being constructed. So codegen needs the customer's Python importable in-process before it will emit the structures that Python must import.

### The bootstrap deadlock

- To write the PipeFunc you need `structures.py` — the validator enforces `return type == the output concept's structure class`.
- To generate `structures.py` you need that function already registered with that exact return type.

Unbreakable without hand-writing a throwaway stub. Reproduced on `atlas-quote-app/method/fr`: generating its structures required stubbing both `@pipe_func()`s against a bootstrap `structures.py`, then regenerating and restoring.

## Measured evidence (runtime instrumentation on `dev`, not code reading)

Probe: wrap `FuncRegistry.get_function` / `get_required_function` and `PipeAbstract.validate_with_libraries`, tag each call with its immediate caller, drive load then validate.

**One PipeFunc, one validate run — the registry is consulted five times:**

```
[LOAD]     get_function('echo_it')          <- pipe_func.py:51    @field_validator
[LOAD]     get_required_function('echo_it') <- pipe_func.py:90    validate_output_with_library
[VALIDATE] get_required_function('echo_it') <- pipe_func.py:90    same method, second call
[VALIDATE] get_required_function('echo_it') <- pipe_func.py:342
[VALIDATE] get_required_function('echo_it') <- pipe_func.py:274
```

**`validate_with_libraries()` runs twice on the same pipe object** — `library.py:161` (inside `load_from_crate` → `library.validate_library()`) and `bundle_validator.py:217` (the validate sweep).

Two load-phase lookups is why deleting only the field validator fixes nothing: the load still fails at `:90`.

**A worktree with both deletions actually applied confirmed the shape of the fix:** load succeeded with the function missing, `codegen types` on `method/fr` (12 pipes, `price_quote.py` fully commented out) emitted `structures.py` with its classes, and lookups dropped 5 → 3 with zero during load. That experiment is the proof the deadlock is breakable; it is **not** the design we are shipping — see below.

## Why "load stops validating" was rejected

The empirical result above tempted a broader fix: delete the field validator and the load-time sweep, making `BundleValidator` the single owner of pipe validation. The outside voice killed it, correctly:

- **`load_normalized_crate` documents the opposite contract** — `crate_loading.py:29`: *"Load, **validate**, and normalize the crate for a bundle closure."* Four callers depend on it: `resolve_cmd`, `codegen/types_cmd`, `codegen/inputs_cmd`, and the agent CLI's `codegen/types_cmd`. Relaxing it silently lets `pipelex resolve` emit crates for structurally invalid libraries.
- **`codegen inputs` is not concept-only.** `inputs_cmd.py:77` calls `get_required_pipe(...)` and renders from the **live pipe**. The "codegen only needs concepts" argument holds for `codegen types` and is false for its sibling.
- **`BundleValidator` is not a drop-in owner** unless every caller that needs a valid crate calls it — `load_normalized_crate` does not.
- **`validate_bundle` dry-runs only the bundle's pipes**, not everything pulled in via `library_dirs`, whereas `library.validate_library()` walks the whole live library. Coverage would shrink invisibly.
- **The sandbox regresses**: `rehydration.py:46` calls `load_from_crate` directly and bypasses `BundleValidator`, so a validation problem becomes an execution-time sandbox failure.

Owner constraint was *best practice, future-proof, robust, **no product regression***. Relaxing a documented contract for three commands that never asked fails that test.

## The change — one named capability, reusing an existing escape hatch

The codebase already has exactly this concept. `PipeFunc` skips both the construction check and the with-library output check when the implementation is not in this process:

```python
# pipe_func.py:45  (field validator)          # pipe_func.py:85  (validate_output_with_library)
if is_pipe_func_sandbox_hosted():             if is_pipe_func_sandbox_hosted():
    return function_name                          return
```

Sandbox-hosted mode is *one reason* the implementation is absent in-process. Concept projection is *another*. So introduce the semantic capability those two share, rather than a boolean threaded through four layers:

- **A predicate** — "an in-process PipeFunc implementation is not required here" — with `is_pipe_func_sandbox_hosted()` becoming one of its two reasons. The two existing call sites read the predicate instead of the mode.
- **A scoped context manager** to turn it on for exactly one operation, mirroring `scoped_current_library`. Never a global mutation.
- **A named loader entry** in `crate_loading.py` beside `load_normalized_crate` — a *different documented contract*, not a flag on the existing one. `codegen types` (bare + agent CLI) calls it; `resolve` and `codegen inputs` keep `load_normalized_crate` untouched.

Consequences: no `load_from_crate` split, no partial-load fingerprint bookkeeping, no change to `resolve` / `codegen inputs` / `run` / the sandbox, and the deadlock closes.

```
codegen types  ──► load_crate_for_concept_projection()  ──► [capability ON] ──► crate ──► concepts ──► structures.py
resolve        ──┐
codegen inputs ──┼► load_normalized_crate()             ──► [capability OFF, unchanged] ──► validated crate
agent codegen  ──┘
```

**Deliberately NOT done:** flipping `pipe_func_config.execution_mode` to make the validator lenient. That selects a sandbox backend that need not be installed (`No PipeFunc executor is registered for 'daytona'`) and mutes a check rather than expressing intent.

## Open questions to settle during Phase 1

1. **Validation-skip vs execution-skip must not be conflated.** `pipe_func.py:274` uses the same sandbox predicate to decide *not to fetch the function for execution* (`function = None if is_pipe_func_sandbox_hosted() else ...`). That is a different meaning from "don't validate". Decide whether one predicate covers both or they split into two.
2. **The field validator checks more than existence** — function *eligibility* (`get_ineligible_function_info`) and `issubclass(return_type, StuffContent)`. Confirm each survives under the capability, or is deliberately deferred to `validate_output_with_library`.
3. **Does anything else want this capability?** `mthds_validate` over the API on a bundle whose Python cannot be imported is the obvious candidate. Do not build for it speculatively; note it.

## Phases

**Phase 1 — the capability.** Introduce the predicate + scoped context manager; repoint `pipe_func.py:45` and `:85` at it. Settle the three open questions above. No caller changes yet.

> **Checkpoint A** — full suite green with the capability defined but never enabled. Behavior must be provably identical to today before any caller opts in.

**Phase 2 — the loader entry.** Add the concept-projection entry to `crate_loading.py` with its own docstring stating the weaker contract explicitly, and its own exit-code mapping. Do not touch `load_normalized_crate`.

**Phase 3 — wire `codegen types`, both surfaces.** Bare CLI (`cli/commands/codegen/types_cmd.py:64`) and agent CLI (`cli/agent_cli/commands/codegen/types_cmd.py:84`). Leave `codegen inputs` and `resolve` alone. Re-check `needs_model_specs=True` in `types_cmd` — its comment justifies the flag by pipe model-pin validation, which no longer happens on this path; dropping it would also cut codegen's startup cost.

> **Checkpoint B** — `pipelex build structures` succeeds on `method/fr` with `price_quote.py` absent, and `pipelex resolve` / `codegen inputs` still reject the same bundle. Both halves are the checkpoint: the fix works AND nothing else moved.

**Phase 4 — regression armour.** The tests below, including the ones pinning what must NOT change.

> **Checkpoint C** — the before/after matrix is green in both directions: every "still fails" row was written against unmodified `dev` and seen passing there BEFORE the capability landed, and the byte-identical `structures.py` assertion holds. A no-regression test that has only ever run on the new code is not evidence.

**Phase 5 — spec, conformance, changelog.** `docs/specs/pipelex-codegen.md` (workspace root) is the paired spec; update it and its verifying conformance test together, then `make check-spec-links` in `conformance/`. CHANGELOG under `## [Unreleased]`.

## Test plan

Every test below runs against **one fixture pair**, so before/after is a controlled comparison rather than two unrelated scenarios:

- `impl_present/` — a bundle with a PipeFunc and its working `@pipe_func()` implementation.
- `impl_missing/` — byte-identical `.mthds` files, implementation absent (or present but unimportable).

### The load-bearing test: the projection must not depend on the implementation

```
structures.py generated from impl_present/   ==   structures.py generated from impl_missing/
```

**Byte-identical, asserted.** This is the whole claim of the change in one assertion: if the concept projection is genuinely concept-only, the presence of the Python cannot change its output. If these ever diverge, the premise is wrong and the capability is unsafe — this test fails loudly rather than the deadlock quietly returning.

### Before/after matrix (write these so they run against both old and new behavior)

| Scenario | Before the change | After the change |
|---|---|---|
| `codegen types` on `impl_missing/` | **fails** `LibraryError: … 'function_name': … not found in registry` | **emits** `structures.py` + `codegen.lock` |
| `codegen types` on `impl_present/` | emits `structures.py` | emits **the same bytes** |
| `resolve` on `impl_missing/` | fails | **still fails, same exit code, same error shape** |
| `codegen inputs` on `impl_missing/` | fails | **still fails** (it reads live pipes) |
| `run` on `impl_missing/` | fails | **still fails** |
| agent-CLI `codegen types` on `impl_missing/` | fails | **emits**, matching the bare CLI |
| sandbox transported run | works | **unchanged** |

The rows in bold-with-"still" are the no-regression pins. Write them **first**, against unmodified `dev`, and watch them pass — a regression test that has never been seen green on the old code proves nothing.

### Instrumentation-backed guards (from this review's probes)

The `/plan-eng-review` probes are worth keeping as tests, because they caught what code reading missed:

- **Registry-lookup count during the concept-projection load is zero.** Wrap `FuncRegistry.get_function` / `get_required_function`, run the projection load, assert no calls. This is the direct assertion that the capability did its job — stronger than "it didn't raise", which would also pass if the function happened to be importable.
- **`load_normalized_crate` still consults the registry.** The same probe on the untouched path, asserting the count is non-zero. Pins that the capability did *not* leak into the validated contract.

### Regression tests (mandatory — these pin the contract that must not move):

- `pipelex resolve` on a bundle with a missing PipeFunc → still fails, same exit code, same structured error. **CRITICAL**: this is the contract Codex identified as silently breakable.
- `codegen inputs` on the same bundle → still fails (it reads live pipes).
- Agent-CLI `codegen types` → succeeds like the bare CLI (both surfaces, or they drift).
- The sandbox transported path → unchanged; the capability is off there, and `is_pipe_func_sandbox_hosted()` still governs.
- `load_from_crate` fingerprint idempotency → unchanged (there is an existing test for the failed-load case; add the sibling).

**New-behavior tests:**

- `load_crate_for_concept_projection` on a bundle whose PipeFunc file is absent → returns a crate; assert concept count.
- Same, PipeFunc file present but unimportable (raises on import) → returns a crate.
- `codegen types` end-to-end on a PipeFunc bundle with no implementation → emits `structures.py`; assert the class set.
- The capability is scoped: assert it is off after the context manager exits, including on the exception path.

**Coverage diagram**

```
CODE PATHS                                          CONTRACT TO PRESERVE
[+] capability predicate + context manager          [+] load_normalized_crate
  ├── [GAP] on / off / restored-on-exception          ├── [GAP] resolve still rejects invalid
  └── [GAP] sandbox reason still honored              ├── [GAP] codegen inputs still rejects
[+] load_crate_for_concept_projection                └── [GAP] error shape + exit codes unchanged
  ├── [GAP] missing PipeFunc file
  ├── [GAP] unimportable PipeFunc file              [+] sandbox path
  └── [GAP] no .mthds in closure (exit 2)             └── [GAP] [→E2E] transported run unaffected
[+] codegen types (bare + agent CLI)
  ├── [GAP] emits structures.py, no impl
  └── [GAP] agent CLI parity
```

## Failure modes

| Codepath | Realistic production failure | Test? | Error handling? | Silent? |
|---|---|---|---|---|
| capability leaks past its scope | a `run` loads with validation disabled and a broken PipeFunc reaches execution | GAP → add | context manager `finally` | **would be silent — critical gap if untested** |
| concept-projection entry used by the wrong caller | `resolve` emits a crate for an invalid library | GAP → add | none today | silent |
| sandbox predicate conflated with execution skip | `function = None` on a path that needed the real function | GAP → add | `get_required_function` raises | loud |
| agent CLI not wired with the bare CLI | agent codegen keeps failing while bare CLI works | GAP → add | existing error | loud but confusing |

**Critical gap:** capability leakage is the one failure that is both silent and severe. The scoped context manager plus its exception-path test is the mitigation, and neither is optional.

## What already exists

- **The escape hatch** — `is_pipe_func_sandbox_hosted()` at `pipe_func.py:45` and `:85` already implements "skip when the implementation isn't in this process". The plan generalizes it rather than inventing a mechanism.
- **The three-way validation split** — `validate_library()` already separates domain / concept / pipe validation.
- **Concept-level validation** — `validate_concept_references_in_blueprints` already runs, blueprint-level and registry-free, before pipes load.
- **`scoped_current_library`** — the precedent for scoping ambient state to one operation.
- Nothing here is rebuilt; every piece is an existing mechanism given a second, named reason to fire.

## NOT in scope

- **Deleting the duplicate `validate_with_libraries()` sweep** (`library.py:161` vs `bundle_validator.py:217`) — measured, real, 5→3 lookups, but it changes validation semantics for every command. Separate change, separate review. See TODO.
- **Moving the registry check off the field validator entirely** — the deeper design question. Not needed once the capability exists.
- **The sandbox `structures/` shadowing bug** — `direct_pipe_func_executor.py:131` tests `workdir / "structures.py"` exactly, so a shipped `structures/` **package** does not match, both get written, and Python resolves the package over the generated module. This is what broke `method/fr` today. Real bug, different file, own fix.
- **`codegen inputs` bootstrap** — it genuinely needs live pipes; a method with no working PipeFunc cannot project inputs. Not a regression, a property.
- **Duplicate-domain descriptions silently dropped** — `domain_metadata_merge.py:46` warns and keeps the first. Pre-existing.

## Repro

```bash
cd atlas-quote-app
rm method/fr/structures.py method/fr/price_quote.py
pipelex build structures method/fr -o /tmp/out
```

Today: `LibraryError: … 'function_name': Value error, Function 'price_quote' not found in registry`. After Phase 3: emits `structures.py` + `codegen.lock`.

## Parallelization

| Step | Modules touched | Depends on |
|---|---|---|
| Capability + context manager | `pipelex/config.py`, `pipe_operators/func/` | — |
| Loader entry | `cli/commands/crate_loading.py` | capability |
| Wire bare + agent codegen | `cli/commands/codegen/`, `cli/agent_cli/commands/codegen/` | loader entry |
| Regression tests | `tests/` | all of the above |
| Spec + conformance | `docs/specs/`, `conformance/` | wiring |

`Lane A: capability → loader entry → wiring` (sequential, each depends on the last). `Lane B: the sandbox structures/ shadowing bug` (independent module, no overlap). Everything else is sequential behind Lane A. Launch A and B in parallel worktrees; no shared module directories, so no conflict flags.

## Implementation Tasks

Synthesized from this review's findings. Each derives from a specific finding above.

- [ ] **T1 (P1, human: ~4h / CC: ~20min)** — `pipe_operators/func` — introduce the "in-process PipeFunc implementation not required" predicate + scoped context manager; repoint `pipe_func.py:45` and `:85`
  - Surfaced by: Architecture — the sandbox escape hatch already implements this, unnamed
  - Verify: full suite green with the capability defined but never enabled (Checkpoint A)
- [ ] **T2 (P1, human: ~2h / CC: ~10min)** — `cli/commands/crate_loading.py` — add the concept-projection loader entry with its own documented (weaker) contract
  - Surfaced by: Cross-model tension — `load_normalized_crate` promises "Load, validate, and normalize" and four callers rely on it
  - Verify: `load_normalized_crate` untouched; new entry has its own exit-code mapping
- [ ] **T3 (P1, human: ~2h / CC: ~10min)** — `cli/commands/codegen`, `cli/agent_cli/commands/codegen` — wire both `codegen types` surfaces; leave `codegen inputs` and `resolve` alone
  - Surfaced by: Audit — `codegen types` exists twice and the original plan named only one
  - Verify: Checkpoint B, both halves
- [ ] **T4 (P1, human: ~1 day / CC: ~30min)** — `tests/` — regression suite pinning `resolve` + `codegen inputs` + sandbox behavior, and the capability-leak exception path
  - Surfaced by: Failure modes — capability leakage is silent and severe
  - Verify: `make agent-test`
- [ ] **T5 (P2, human: ~1h / CC: ~5min)** — `cli/commands/codegen/types_cmd.py` — re-evaluate `needs_model_specs=True` now that pipe model pins are not validated on this path
  - Surfaced by: Phase 3 — the flag's justifying comment no longer applies
  - Verify: codegen works offline without the model deck
- [ ] **T6 (P2, human: ~2h / CC: ~10min)** — `docs/specs/`, `conformance/` — document the two contracts; `make check-spec-links`
  - Surfaced by: workspace rule — spec and conformance move together
  - Verify: `make check-spec-links` in `conformance/`

## Adjacent findings (tracked, not in this plan)

- **`direct_pipe_func_executor.py:131`** — shipped-copy guard is name-exact; a shipped `structures/` package silently shadows the generated `structures.py`. Cost a full debugging session today.
- **`library.py:113`** — `"This should NEVER fail … TODO: Make this non mandatory in production, or a test"`, still there.
- **The double sweep** — `validate_with_libraries()` twice per pipe, measured. Worth its own change.
- **`--output` default** — `build structures` defaults to `<target>/structures/`, so the flat module lands at `structures/structures.py`; `-o <method_dir>` is what makes `from structures import …` work.

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` | Scope & strategy | 0 | — | — |
| Codex Review | `/codex review` | Independent 2nd opinion | 1 | issues_found | outside voice, 1 tension accepted |
| Eng Review | `/plan-eng-review` | Architecture & tests (required) | 1 | issues_open | 5 issues, 1 critical gap |
| Design Review | `/plan-design-review` | UI/UX gaps | 0 | — | — |
| DX Review | `/plan-devex-review` | Developer experience gaps | 0 | — | — |

**CODEX:** Rejected the review's own "load stops validating" design as strategic overreach — `load_normalized_crate` documents "Load, validate, and normalize" and four callers depend on it; `codegen inputs` reads live pipes so the concept-only argument holds for `codegen types` alone. Also caught that the deleted validator checks eligibility and return-type base class (not just existence), that a caught `FuncRegistryError` would land as a `dry_run` category rather than a structured `pipe_validation` item, that source attribution would be lost, and that `library_dirs` pipes would stop being validated. Tension resolved in Codex's favour by the owner.

**CROSS-MODEL:** Both reviewers agreed the deadlock is real, that the emitter is concept-only, and that the construction-time registry lookup is misplaced. They disagreed on blast radius: the eng review measured the redundancy and concluded load should stop validating; Codex weighted the documented contract and the three commands that never asked to change. Owner constraint (no product regression) settled it. The eng review's measurements survive as evidence for a separate follow-up, not as this change.

**Evidence base:** findings were verified by runtime instrumentation on `dev`, not code reading — registry lookups counted per phase (5 per PipeFunc, 2 during load), `validate_with_libraries` proven to run twice (`library.py:161` + `bundle_validator.py:217`), and both candidate deletions applied in a throwaway worktree where `codegen types` on `method/fr` emitted `structures.py` with the PipeFunc file fully commented out.

**VERDICT:** ENG REVIEW COMPLETE — plan revised and ready to implement, subject to the critical gap below being covered by Phase 4 tests before merge. CEO and Design reviews not required (backend refactor, no product or UI surface change).

**UNRESOLVED DECISIONS:**
- Capability leakage is the one failure mode that is both silent and severe: if the concept-projection capability escapes its scope, a `run` could load with PipeFunc validation disabled. The scoped context manager plus its exception-path test are the mitigation; neither exists yet, so this stays open until Phase 4 lands.
