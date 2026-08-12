# Deferred — observations from the PR #1085 finalization review

Raised by the gstack `/review` pass over Phase 1 (2026-08-03), verified against the tree at `c36feb85b`. Each is real. None is a clear win as a code change *in this PR*, so each is recorded here rather than fixed under the standing "no over-engineering, defer when in doubt" bar. The review's verdict was **land**; these are follow-ups, not blockers.

The two findings that *were* clear wins — the `Anything` import omission and the doc/citation corrections — landed in this PR and are recorded in the plan's Checkpoint A instead.

## 1. A cross-package `refines` target is a fifth structureless shape, ungated on both sides

`test_projection_agrees_with_runtime_base.py` enumerates four authorable concept shapes and claims the enumeration is closed. It is closed only over concepts the crate can resolve on its own. A concept whose `refines` target is absent from the crate — a cross-package base — gets `structureless=True` **with** `base_ref` set (`pipelex/codegen/resolved_concepts.py:127-131`, the `elif value.refines:` branch), so it skips 1.2's new structureless arm and falls to `python_structures.py:89-90`, landing on `StructuredContent`.

That is the same choice this PR just ruled wrong for the in-crate structureless shape, taken in the sibling branch, untested on both sides.

**Why it is not fixed here.** It sits on the same B1-1 floor as the Python-class-backed case: the base is *genuinely* not visible to the crate, so there is nothing to agree with — the runtime resolves it through a package the crate does not carry. Promoting it to `TextContent` would be a guess, and keeping the root base is the honest answer to "we cannot see this". The projection is not silent about it either: that same branch sets `imprecision_reason = "refinement base '<ref>' is not available in this crate"`, which the emitter writes into the class docstring. So the reader is told, which is the bar the "surfacing imprecision, never guessing" rule actually sets. The test docstring has been scoped to say so rather than overclaim closure.

**What would settle it.** Decide whether a cross-package base should be resolved at normalization time (which would make the crate non-self-contained, a contract question) or stay deferred. Until then the root base is correct-by-honesty, not by accident. Related: [`structureless-concept-with-registered-class.md`](structureless-concept-with-registered-class.md), which is the same "the crate cannot see it" floor reached by a different channel.

## 2. Crate closedness is fixture-true, not property-true

`_qualify_pipe_ref` returns any ref containing a `.` unchanged, with **no existence check**. So a typo'd *qualified* ref (`presentation.nope`) still produces a dangling ref in the normalized crate and a run-time `PipeNotFoundError` — exactly what the closedness test's docstring warns against. The test passes because its fixtures contain no such typo.

**Why it is not fixed here.** Pre-existing, and out of Phase 1's scope: 1.1 was about *bare* refs, which had no resolution at all. Adding existence validation for qualified refs is a separate behavioural change with its own blast radius — a hand-built or transported crate legitimately carries refs to pipes it does not hold yet in some load orders, and the loader's `validate_library` already rejects the reachable cases with a better, structured error.

**Trap for whoever extends the test.** The closedness docstring invites adding a cross-package fixture to its `parametrize`. Doing that will fail the test for a legitimate reason — cross-package deps are deliberately deferred, not resolved — unless the comprehension filters them out, mirroring `_index_pipe_refs_by_code`'s own `has_cross_package_prefix` skip.

## 3. Generic concept codes in the parity test are a latent test-order flake

`test_projection_agrees_with_runtime_base.py` names its four shapes `Opaque`, `Structured`, `Refined`, `RefinesNative`. `ConceptFactory._handle_basic_blueprint` looks the **bare** code up in the process-global class registry before falling back to the generated `TextContent`-based class. No collision exists today, but any future `class Opaque(StructuredContent)` registered anywhere in the suite would silently flip `test_structureless_lands_on_text_content` — the test would fail, or worse pass, for a reason unrelated to what it gates.

**Why it is not fixed here.** Speculative today; the fix (namespacing the codes) is free but guards a scenario that does not exist. Worth doing the next time that file is touched for another reason. Recorded so the failure is diagnosable in one read if it ever happens, rather than costing an afternoon.

## 4. Cross-repo — the `mthds/` spec states the bare-ref rule for concepts only

`mthds/docs/spec/library-crate.md` §2 describes bare-reference resolution purely in *concept* terms ("resolve to `domain_path.ConceptCode`"). The bare-**pipe**-ref rule this PR settled — resolve crate-wide, unique match required, error on ambiguity or absence — is unstated there, and that file is the one `crate_normalization.py`'s own header cites as `[Library Crate Format]`.

So the implementation now has a documented behaviour its governing spec does not describe. That is a spec edit in the `mthds/` repo, not this one.

**Note the ordering dependency:** if D-1's `domain_hint` question is answered "yes, prefer the caller's domain" (see [`d1-domain-hint-deferred.md`](d1-domain-hint-deferred.md)), the rule changes and the spec text would have to be written twice. Settle D-1 first, then write the spec paragraph once.
