# TODO: Hydration follow-ups from the post-cross-process-fix review

> Goal: tighten the hydration code paths now that the cross-process registry hack is gone.
> The four items below come from a full audit of every `hydrate_working_memory` and
> `prepare_for_temporal` call site (production + tests). They are listed in priority order:
> #1 closes a real silent-failure surface, #2 is cheap insurance, #3 simplifies, #4 is
> cosmetic symmetry. Items can be shipped independently — no ordering constraints between
> them.

Reference (read first if you weren't in the audit conversation):
`wip/raw-working-memory-through-act_deliver-DONE.md` — the immediately preceding work
that removed the global-registry propagation hack and introduced the dual-mode delivery
path. The four items here all live downstream of that change.

---

## Item 1 — Make the submitter-side rehydrate self-sufficient (priority: HIGH)

### Background

Two production sites rehydrate `PipeOutput` on the submitter:

- `pipelex/temporal/tprl_pipe/temporal_pipe_router.py:84-86`
- `pipelex/temporal/tprl_pipe/temporal_pipe_run.py:69-72`

Both call `hydrate_working_memory(pipe_output.working_memory_raw)` with whatever class
registry is currently active in the submitter process. This silently assumes **the
submitter has already loaded the bundle's classes into its global `KajsonManager`
registry**. That assumption holds today because the only caller is `pipelex run bundle`,
which loads the bundle locally before submission. It is not enforced anywhere.

If a submitter that *didn't* load the bundle locally calls `TemporalPipeRun.run()` (or
`TemporalPipeRouter.run()`) — for example a remote API client that built the
`PipeJob` from a serialized `LibraryCrate` and waited for the result — rehydration will
either raise (`PipeJobError`/`ValidationError` from `_hydrate_content` failing to resolve
the structure class) or, worse, partially succeed for fields whose classes happen to
share a name with a built-in. This is a latent silent-failure surface waiting for the
second caller.

The integration test helper `tests/integration/pipelex/temporal/library_crate/helpers.py:20-74`
already does the right thing: when `pipe_job.library_crate is not None`, it opens a
fresh per-rehydration scoped `Library`, pre-seeds a scoped `ClassRegistry` from the
global, calls `library_manager.load_from_crate(...)` into that scoped library, hydrates
inside it via the `_library_id` `ContextVar`, and tears down on the way out. **Production
should do the same.** The current asymmetry between the test helper and the production
submitter is a smell.

### Plan

#### 1.1 Extract the scoped-rehydration logic into a reusable helper

Create `pipelex/temporal/tprl_pipe/submitter_hydration.py` with one public function:

```python
def rehydrate_pipe_output_with_crate(
    pipe_output: PipeOutput,
    library_crate: LibraryCrate | None,
) -> PipeOutput:
    """Rehydrate `pipe_output.working_memory_raw` into typed WorkingMemory.

    When `library_crate` is provided, opens a fresh per-call scoped Library,
    loads the crate into it, hydrates inside the scope, and tears down — so
    callers that did not load the bundle into their global registry still get
    a correct typed WorkingMemory. When `library_crate` is None, falls back to
    the active class registry (built-ins + whatever PIPELEXPATH loaded).

    Mutates `pipe_output` in place: sets `working_memory`, clears
    `working_memory_raw`. Returns the same instance for call-chain ergonomics.
    """
```

Implementation mirrors `tests/integration/pipelex/temporal/library_crate/helpers.py:20-74`:
open library, pre-seed scoped registry from global, `set_current_library`,
`load_from_crate`, hydrate, `finally` teardown + restore previous `_library_id`. Reuse
the private `_get_current_library_id_or_none` pattern.

Lift the helper into the production module rather than importing from `tests/`. The test
helper file will then collapse to a one-line call into the new production helper (see
1.4 below).

#### 1.2 Wire the helper into both submitter rehydrate sites

- `pipelex/temporal/tprl_pipe/temporal_pipe_router.py:84-86` — replace the three lines
  with `rehydrate_pipe_output_with_crate(pipe_output, pipe_job.library_crate)`. The
  `pipe_job` is already in scope (line 50).
- `pipelex/temporal/tprl_pipe/temporal_pipe_run.py:69-72` — same replacement, passing
  `pipe_job.library_crate` (the `pipe_job` is reachable via
  `pipe_run_arg.pipe_job.library_crate`).

#### 1.3 Drop the unused direct `hydrate_working_memory` import from those two files
The new helper is the only caller — keep `hydrate_working_memory` as a hydration.py
internal called by both `WfPipeRouter` (which already has the per-workflow library
opened) and the new submitter helper.

#### 1.4 Collapse the test helper

`tests/integration/pipelex/temporal/library_crate/helpers.py:20-74` — replace the body
of `rehydrate_pipe_output` with a call into the new production helper. Keeps the test
public API identical, removes ~50 lines of duplicated scoped-registry plumbing from
tests.

### Tests

#### 1.T1 — Unit test: submitter rehydrate works without bundle pre-loaded

`tests/unit/pipelex/temporal/tprl_pipe/test_submitter_hydration.py` — new file, single
TestClass `TestRehydratePipeOutputWithCrate`.

Test cases (parametrized):

| Case | Setup | Assertion |
|---|---|---|
| `crate_none_builtin_only` | `library_crate=None`, raw WM contains only `TextContent` | rehydrates correctly, `working_memory.get_main_stuff().content` is `TextContent` instance with the right text |
| `crate_none_dynamic_concept_unavailable` | `library_crate=None`, raw WM contains a dynamic concept that's NOT registered globally | raises `PipeJobError` (the existing failure mode — not a regression, just documenting it) |
| `crate_provided_dynamic_concept` | `library_crate=<Greeting bundle crate>`, raw WM contains `Greeting` instance, **submitter's global registry does NOT have Greeting** | rehydrates correctly, `main_stuff.content` is the dynamic Greeting class with `message` + `language` fields populated |
| `crate_provided_concurrent_isolation` | Two submitters call helper concurrently with two different crates that both define a concept named `Result` with different fields | each call returns the correct Result shape; the two scopes do not leak. Use `asyncio.gather` + per-call assertions |
| `previous_library_id_restored` | Set a `_library_id` ContextVar before calling, helper opens its scope, finishes | after return, `get_current_library()` returns the original id (not torn down) |
| `no_previous_library_id_torn_down` | No `_library_id` set before call | after return, `get_current_library()` raises (the helper teardown nuked the ContextVar) |
| `working_memory_raw_is_none_noop` | `pipe_output.working_memory_raw is None` | helper returns the same instance unchanged, no library opened (verify via `get_library_manager().list_libraries()` count or a spy) |
| `teardown_runs_on_hydrate_failure` | Inject a `working_memory_raw` that triggers `PipeJobError` during hydration | exception propagates, but `get_library_manager()` shows no leaked library afterwards (use `pytest.raises` + a post-check) |

Use `pytest_mock.MockerFixture`, no `unittest.mock`. The "submitter's global registry
does NOT have Greeting" condition can be enforced by:
1. building a fresh `ClassRegistry` for the test,
2. swapping it onto `KajsonManager` for the test duration via a fixture that
   `monkeypatch.setattr`s,
3. asserting the dynamic class only ever appears in the scoped library, never in the
   global registry after teardown.

#### 1.T2 — Integration test: end-to-end "submitter without bundle" scenario

`tests/integration/pipelex/temporal/library_crate/test_submitter_without_bundle.py` —
new TestClass `TestSubmitterWithoutBundleLoaded`.

The intent is to prove the production fix works against a real Temporal server
*without* the test process pre-loading the bundle into its global registry. Setup:

1. Build a `LibraryCrate` from `dynamic_concept_sequence.mthds` using a temporary
   `LibraryManager` instance. **Do not call `load_from_crate` on the global
   library_manager** in the test fixture — that's the whole point.
2. Verify pre-condition: `KajsonManager.get_class_registry().get_class("dynamic_concept_test__Greeting")` returns `None`.
3. Submit `PipeJob(pipe=..., working_memory=<input WM with Greeting input>, library_crate=<crate>)`
   via `TemporalPipeRun.run(...)` against a real Temporal server (use the existing
   `temporal_client` / `temporal_task_queue` fixtures).
4. Worker side: the existing per-workflow library mechanism handles execution.
5. **Post-assertion**: `pipe_output.working_memory.get_main_stuff().content` is a
   typed `Greeting` instance with the expected fields, even though the test process
   never pre-loaded the bundle. This is the new behavior introduced by item 1.
6. **Cleanup assertion**: after the call returns, the global registry still does NOT
   have `Greeting` registered (the scoped library was torn down). This guards against
   accidentally falling back to the old propagation-hack behavior.

Mark with `@pytest.mark.temporal` and the standard async-loop scoping. Run under
both `shared` and `isolated` parametrizations from the existing conftest.

#### 1.T3 — Concurrency regression: two submitters with conflicting crates

Same file as 1.T2, second test method `test_two_submitters_with_conflicting_result_concept`.

Use the existing `conflict_concept_alpha.mthds` and `conflict_concept_beta.mthds`
bundles. Build two crates, neither loaded globally. Fire both via `asyncio.gather` —
each call gets its own scoped library. Assert:

- alpha's main stuff is `Result(score, label)`,
- beta's main stuff is `Result(value, confidence, is_valid)`,
- after both complete, the global registry has neither (no leaks),
- crucially, no `KajsonDecoderError` and no field-name confusion.

This catches the case where two concurrent submitter rehydrates would have stomped on
each other if they shared a global registry.

---

## Item 2 — Log on the broad-except fallback in `_local_hydrate_main_stuff` (priority: MEDIUM)

### Background

`pipelex/pipe_run/delivery_executor.py:98-111`:

```python
@staticmethod
def _local_hydrate_main_stuff(working_memory_raw):
    try:
        working_memory = hydrate_working_memory(working_memory_raw)
    except (PipeJobError, ValidationError, KajsonException, KeyError):
        return None
    return working_memory.get_optional_main_stuff()
```

The except clause exists to handle "dynamic concept class not registered locally" —
that's the expected failure mode when the activity worker doesn't have the bundle
loaded. The fallback then renders the main stuff as raw JSON-in-markdown.

The problem: this same except clause also swallows real bugs in built-in concept
hydration — a Pydantic validator regression in a built-in `StuffContent` subclass
would silently degrade output to JSON dumps with no signal. We'd discover the bug only
when a user complained that their text outputs stopped looking like text.

### Plan

`pipelex/pipe_run/delivery_executor.py:_local_hydrate_main_stuff` — emit
`log.warning(f"Local hydration failed for delivery, falling back to raw render: {exc}")`
in the except branch before returning `None`. Include `exc_info=False` (the message has
the relevant info; full traceback is noisy in delivery logs).

Match the existing style in `_generate_main_stuff_files` which logs on each render
failure with a short message. No exception chain, no escalation — fallback behavior is
unchanged. The log line is the only addition.

### Tests

#### 2.T1 — Unit test: warning emitted on hydration failure, fallback still works

`tests/unit/pipelex/pipe_run/test_delivery_executor.py::TestDeliveryExecutor` — add
two test methods:

| Test | Setup | Assertion |
|---|---|---|
| `test_local_hydrate_warns_on_dynamic_class_miss` | `working_memory_raw` containing a stuff whose `concept.structure_class_name` is not in the global registry | `log.warning` called once, message contains "Local hydration failed", returned files dict contains `main_stuff.json` from the raw fallback path (not the typed path) |
| `test_local_hydrate_does_not_warn_on_builtin_success` | `working_memory_raw` containing only TextContent built-ins | `log.warning` NOT called, returned files dict contains `main_stuff.json/md/html/viewer` from typed renderers |

Use `mocker.spy(log, "warning")` (not patch — we still want it to actually log). Do
not use `caplog` directly because `pipelex.log` is a custom Rich logger; spying on
`log.warning` is the cleanest assertion.

#### 2.T2 — Verify no log spam in the happy-path E2E

After 2.T1 lands, manually re-run the `temporal-e2e-validate` Tier 2b repro and
`grep -i "local hydration"` the runner tmux capture. Assert no warnings appear (the
Greeting case lands on a runner without the crate, so `_local_hydrate_main_stuff`
*will* fall back — and *should* warn). Document expected warning count in the test
plan: exactly one per `act_deliver` invocation involving a dynamic concept main stuff.

This is a manual verification step, not an automated test — but worth calling out in
the PR description so reviewers know the warning is intended to fire on the documented
fallback path.

---

## Item 3 — Slim `_local_hydrate_main_stuff` to a single-stuff lookup (priority: LOW)

### Background

`_local_hydrate_main_stuff` currently calls full `hydrate_working_memory`, which walks
*every* stuff in `root`, every alias, every list item, builds a complete typed
`WorkingMemory`, and then we throw all of it away except the main stuff. For a
delivery activity, we only need that one stuff to drive typed rendering.

The wasted work is small (delivery isn't hot), but the indirection makes the code
read worse than it needs to: a reader sees "hydrate working memory" and reasonably
assumes we need a typed `WorkingMemory`. We don't.

### Plan

#### 3.1 Add a focused helper

In `pipelex/pipe_run/delivery_executor.py`, replace `_local_hydrate_main_stuff` with:

```python
@staticmethod
def _try_local_hydrate_stuff(stuff_raw: dict[str, Any]) -> Stuff | None:
    """Attempt to hydrate a single Stuff dict using only globally-registered classes.

    Returns None if the structure class isn't available locally — caller should
    then fall back to a generic raw-dict render.
    """
    try:
        concept = Concept.model_validate(stuff_raw["concept"])
        registry = get_class_registry()
        item_class = registry.get_class(name=concept.structure_class_name)
        if item_class is None or not issubclass(item_class, StuffContent):
            return None
        # Reuse the existing _hydrate_content logic for ListContent vs single
        content = _hydrate_content(concept=concept, raw_content=stuff_raw["content"])
        return Stuff(
            stuff_code=stuff_raw["stuff_code"],
            stuff_name=stuff_raw.get("stuff_name"),
            concept=concept,
            content=content,
        )
    except (PipeJobError, ValidationError, KajsonException, KeyError) as exc:
        log.warning(f"Local hydration failed for delivery main stuff, falling back to raw: {exc}")
        return None
```

`_hydrate_content` is already exposed inside `pipelex/temporal/tprl_pipe/hydration.py`
as a module-level function — re-export it (or move it next to the new helper). It's
currently underscore-prefixed but not actually private; the test module imports it
indirectly through `hydrate_working_memory`. Promote it: rename to `hydrate_content`
in `hydration.py` and add a `__all__` entry, since two callers will now use it.

#### 3.2 Update the call site

`generate_result_files` already calls `_get_raw_main_stuff_dict` to extract the main
stuff dict, then passes the *full* `working_memory_raw` to `_local_hydrate_main_stuff`.
Inversion: now pass `_get_raw_main_stuff_dict(...)` directly into `_try_local_hydrate_stuff`,
no more `working_memory_raw` round-trip. Fewer lines, clearer intent.

#### 3.3 Item 2's logging move into this helper

This item supersedes the bare `log.warning` add from Item 2 — the warning lives in
`_try_local_hydrate_stuff` instead. If Item 2 ships first, fold its warning call into
this helper when Item 3 lands.

### Tests

#### 3.T1 — Unit tests on the focused helper

Same `tests/unit/pipelex/pipe_run/test_delivery_executor.py` test class, add:

| Test | Setup | Assertion |
|---|---|---|
| `test_try_local_hydrate_stuff_returns_typed_for_builtin` | stuff dict with concept resolving to `TextContent` | returns `Stuff` with `content` typed as `TextContent` and the right text |
| `test_try_local_hydrate_stuff_returns_none_for_missing_class` | stuff dict whose `concept.structure_class_name` is "dynamic_test__Greeting" (not in registry) | returns `None`, warns once |
| `test_try_local_hydrate_stuff_handles_listcontent` | stuff dict with content as a list of TextContent items (the `dump_for_temporal` ListContent shape) | returns `Stuff` with `content` typed as `ListContent[TextContent]`, items count and texts match |
| `test_try_local_hydrate_stuff_returns_none_for_anything_with_unknown_item` | stuff dict where one list item has `__class__: "dynamic_test__Foo"` not registered | returns `None`, warns once. (Verifies the list path also degrades gracefully.) |
| `test_try_local_hydrate_stuff_returns_none_for_malformed_dict` | stuff dict missing `concept` key | returns `None`, warns once (KeyError path) |

#### 3.T2 — Existing `test_delivery_executor.py` tests stay green

The existing seven tests (`test_execute_storage_only`, `test_storage_failure_raises`,
…) must continue to pass after the refactor. No behavior change at the
`generate_result_files` level — only internal indirection is reduced.

#### 3.T3 — Update Tier 2b E2E expectations (no code change needed)

After Item 3 lands, re-run `/temporal-e2e-validate` Tier 2b. The runner session should
emit exactly one `Local hydration failed for delivery main stuff` warning per pipeline
run with a dynamic concept. Document this in the skill's "expected output" section so
future runs don't flag it as a regression.

---

## Item 4 — Symmetry: gate `prepare_for_temporal()` internally on both PipeJob and PipeOutput (priority: LOW / cosmetic)

### Background

- `PipeJob.prepare_for_temporal()` (`pipelex/pipe_run/pipe_job.py:34-49`) gates
  internally on `self.library_crate is not None`.
- `PipeOutput.prepare_for_temporal()` (`pipelex/core/pipes/pipe_output.py:26-41`) does
  *not* gate on a crate; it short-circuits only on `not self.working_memory.root`. The
  crate gate lives at the call site `pipelex/temporal/tprl_pipe/wf_pipe_router.py:202-204`:

```python
assert pipe_output is not None
if library_crate is not None:
    pipe_output = pipe_output.prepare_for_temporal()
```

Today there's exactly one call site for `PipeOutput.prepare_for_temporal()` and it
gates correctly. A future second caller would have to remember to add the gate or
accidentally introduce dehydration on no-crate pipelines (harmless but wasteful).

### Plan

#### 4.1 Add the crate gate to `PipeOutput.prepare_for_temporal`

`pipelex/core/pipes/pipe_output.py:26-41` — accept `library_crate: LibraryCrate | None`
as an optional parameter, default `None`, with semantics: when `library_crate is None`
*and* the WM contains no dynamic-concept-bearing root entries, skip dehydration.

Actually, simpler and matching `PipeJob`: add a `library_crate` parameter and gate on
`if library_crate is None: return self`. Move the empty-WM short-circuit after the
gate. Symmetric with `PipeJob.prepare_for_temporal()`.

```python
def prepare_for_temporal(self, library_crate: "LibraryCrate | None" = None) -> "PipeOutput":
    if library_crate is None:
        return self
    if not self.working_memory.root:
        return self
    return self.model_copy(
        update={
            "working_memory_raw": self.working_memory.dump_for_temporal(),
            "working_memory": WorkingMemory(),
        }
    )
```

#### 4.2 Update the single call site

`pipelex/temporal/tprl_pipe/wf_pipe_router.py:202-204` — drop the `if library_crate is not None`
gate at the call site, pass `library_crate=library_crate` through. Net delta: zero
lines (the gate moves inward by one frame).

### Tests

#### 4.T1 — Unit tests for the new gate

Add `tests/unit/pipelex/core/pipes/test_pipe_output_prepare_for_temporal.py` (one
TestClass `TestPipeOutputPrepareForTemporal`):

| Test | Setup | Assertion |
|---|---|---|
| `test_no_crate_returns_self_unchanged` | `PipeOutput` with non-empty WM, called with `library_crate=None` | result is the same instance, `working_memory` unchanged, `working_memory_raw is None` |
| `test_with_crate_dehydrates` | `PipeOutput` with non-empty WM, called with a real `LibraryCrate` | result is a copy, `working_memory` is empty `WorkingMemory()`, `working_memory_raw` is the dumped dict matching `dump_for_temporal()` |
| `test_with_crate_empty_wm_returns_self` | `PipeOutput` with empty WM, called with a real crate | result is the same instance (empty-WM short-circuit) |
| `test_does_not_mutate_original` | non-empty WM + crate | original `pipe_output.working_memory` is unchanged after the call |

Mirror the existing `tests/unit/pipelex/pipe_run/test_pipe_job_hydration.py` style —
those cover the analogous cases for `PipeJob`. The new file should feel like its
sibling.

#### 4.T2 — `wf_pipe_router` end-to-end stays green

No new test here. The existing TestWfLibraryCrate / TestWfDeferredHydration suites
(`tests/integration/pipelex/temporal/library_crate/`) exercise the call site through
real Temporal workflows; they must still pass after the refactor. Re-run
`/temporal-test-crate` post-merge as the regression guard.

---

## Cross-cutting verification

After each item lands (independently or batched), run:

1. `make agent-check` — pyright + mypy + ruff clean.
2. `make agent-test` — full unit + integration suite green. Pay attention to
   `tests/unit/pipelex/temporal/tprl_pipe/test_hydration.py` (still tests the underlying
   hydrate function, which stays unchanged) and the new test files added by each item.
3. `/temporal-test-crate` (dry mode) — full LibraryCrate suite, including the
   concurrent isolation tests. Items 1, 3 most likely to regress these if implemented
   wrong; item 4 is structurally inert.
4. `/temporal-e2e-validate` Mode 2 dry-run with router+runner scoped workers — Tiers
   1, 2, 2b, 3 + concurrent isolation Tests A/B/C. Tier 2b is the deterministic
   cross-process repro; if any item regresses the dehydrate/rehydrate balance, it
   surfaces here as `KajsonDecoderError` on the runner.

For Item 1 specifically, also run the new `test_submitter_without_bundle.py`
integration tests against a real Temporal server — the unit tests cover the helper in
isolation, but the integration tests prove the end-to-end "remote submitter" promise
holds.

---

## Files touched per item

| Item | Production files | Test files |
|---|---|---|
| 1 | `pipelex/temporal/tprl_pipe/submitter_hydration.py` (new), `pipelex/temporal/tprl_pipe/temporal_pipe_router.py`, `pipelex/temporal/tprl_pipe/temporal_pipe_run.py`, `tests/integration/pipelex/temporal/library_crate/helpers.py` (collapse) | `tests/unit/pipelex/temporal/tprl_pipe/test_submitter_hydration.py` (new), `tests/integration/pipelex/temporal/library_crate/test_submitter_without_bundle.py` (new) |
| 2 | `pipelex/pipe_run/delivery_executor.py` | `tests/unit/pipelex/pipe_run/test_delivery_executor.py` (extend) |
| 3 | `pipelex/pipe_run/delivery_executor.py`, `pipelex/temporal/tprl_pipe/hydration.py` (promote `hydrate_content`) | `tests/unit/pipelex/pipe_run/test_delivery_executor.py` (extend) |
| 4 | `pipelex/core/pipes/pipe_output.py`, `pipelex/temporal/tprl_pipe/wf_pipe_router.py` | `tests/unit/pipelex/core/pipes/test_pipe_output_prepare_for_temporal.py` (new) |

## Files explicitly NOT touched

- `pipelex/temporal/tprl_pipe/hydration.py` — `hydrate_working_memory`,
  `_hydrate_content`, `_hydrate_list_item`, `_validate_as_known_class` stay as-is
  (Item 3 only promotes `_hydrate_content` to public; no behavior change).
- `pipelex/core/memory/working_memory.py` — `dump_for_temporal()` is already correct.
- `pipelex/temporal/tprl_pipe/wf_pipe_router.py:51-86` — the in-workflow hydrate path
  is correct and stays untouched. Only line 202-204's call-site gate moves.
- `pipelex/temporal/tprl_content_generation/*` — independent system
  (`__kajson_class_source__`); not affected by any item.
