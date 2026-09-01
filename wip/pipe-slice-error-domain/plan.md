---
status: draft
item: L-260901-296dfb
---

# Give the `--pipe` / `pipe_ref` slice miss in `validate_bundle` the INPUT domain

Follow-up to the entry-pipe error-domain work (`wip/entry-pipe-error-domain/plan.md`, PR #1180), which deliberately left this raise site out of its diff and filed it as L-260901-296dfb.

## The bug, verified

`_pipes_to_dry_run` (`pipelex/pipeline/validate_bundle.py:229`) raises the bare, undomained `PipeNotFoundError` when `dry_run_pipe_codes` names a pipe absent from the loaded bundle. Its own docstring calls the trigger "a typo'd `--pipe` argument" — entry-shaped input a human typed, exactly the case PR #1180 classified for the two library lookups. The class declares no `error_domain`, so `ErrorReport.http_status` falls through `error_domain_to_http_status(None)` to 500.

Live probe on `dev` (same caller typo, two verdicts):

```bash
.venv/bin/pipelex-agent validate bundle tests/data/input_semantics/probe_bundle.mthds --pipe nonexistent_zzz --format json
# → error_type: PipeNotFoundError, NO error_domain, no hint

.venv/bin/pipelex-agent validate pipe nonexistent_zzz --format json
# → error_type: EntryPipeNotFoundError, error_domain: input, CHANGE_INPUT hint
```

The only consumer that repairs this is `pipelex-api`'s `api/routes/pipelex/build/runner.py:174`, which catches `PipeNotFoundError` by hand and maps it to a 422 — the same "one input, two verdicts depending on the route" shape PR #1180's changelog says it removes. Any other surface reaching `validate_bundle` with `dry_run_pipe_codes` renders the caller's typo as a server fault, logged with a traceback and looking retryable to every SDK.

## Design

**Raise `EntryPipeNotFoundError` at the existing site — no new class.** The `--pipe` / `pipe_ref` selector is entry-shaped input by the class's own definition ("one a human typed... a CLI argument, the `pipe_code` field of a run request"), so the concept already has a home. Reusing it means:

- Every current catcher keeps matching, because all of them catch the base `PipeNotFoundError`: the passthrough in `validate_bundle.py`'s `translate_to_validate_bundle_error` (`except PipeNotFoundError: raise`), the agent CLI arms (`bundle_cmd.py`, `pipe_cmd.py`), the bare CLI (`cli/commands/validate/_validate_core.py`), and `pipelex-api`'s hand catch.
- No new error identity: `make gei` / `make gep` produce no diff for a new class (verify by running them — the class docstring's summary line, which is all the generated page renders, does not change).
- The agent CLI arms already pass `error_type=type(exc).__name__` (PR #1180's carry-along), so the envelope will name `EntryPipeNotFoundError` and the INPUT domain + `CHANGE_INPUT` hint riding it report-first will finally be attributed to the class that declares them. `bundle_cmd.py:190`'s comment ("The real class, not the caught base") stops describing an intent and starts describing behaviour — no edit needed there.

**The message stays the raise site's own.** `_pipes_to_dry_run` keeps its bundle-scoped wording ("Pipe(s) 'x' not found in the bundle. Check for typos and make sure they are declared in the bundle.") — more precise here than the class's library-lookup message. This is safe under `_authors_caller_facing_message = True`: the flag spans every raise site of the class, and this message names only the caller's own `--pipe` codes (derived from `wanted`, which is caller-supplied), nothing from the loaded library.

**Docstring corrections that must ride the same diff:**

- `EntryPipeNotFoundError`'s docstring says "this class has exactly one [raise site]" — after this change it has two. Reword the caller-facing-copy paragraph to state the invariant per raise site instead of counting them.
- `_pipes_to_dry_run`'s `Raises:` section names `PipeNotFoundError` — update to `EntryPipeNotFoundError` and say why (caller-supplied selector → INPUT domain).
- `builder/operations/validate_ops.py`'s docstrings name `PipeNotFoundError` for this path — update the wording (the subclass still satisfies any `except`, but the docs should name the real class).

**Out of scope, unaffected:** the in-body lookups (`get_optional_pipe` / `get_required_pipe`) and `bundle_validator.py`'s sweep-time `except PipeNotFoundError` (it catches sub-pipe resolution misses during the dry-run sweep; `_pipes_to_dry_run` runs before the sweep and its raise never reaches that arm).

**The `pipelex-api` half is a dependent ledger item, not this diff.** Once a pipelex release carries this change, `build/runner.py`'s hand-written `except PipeNotFoundError` → 422 catch becomes redundant: the global `PipelexError` handler (`api/exception_handlers.py`) renders `report.http_status`, which the INPUT domain now makes 422 on its own. Dropping the catch is `pipelex-api` work gated on that release — filed as its own item, blocked by L-260901-296dfb (see the ledger).

## Phases

### Phase 1 — red tests

- `tests/integration/pipelex/cli/test_agent_validate_pipe_in_bundle.py::test_pipe_slice_unknown_pipe_raises_not_found`: tighten `pytest.raises(PipeNotFoundError)` to `EntryPipeNotFoundError`, and assert on the caught error's `to_error_report()`: `error_domain == ErrorDomain.INPUT`, `http_status == 422`, and the message still names the missing code. This is the red test: it fails on `dev` because the raise is the bare base class.
- Verify the class-metadata sweeps in `tests/unit/pipelex/exceptions/test_class_level_metadata.py` already pin `EntryPipeNotFoundError`'s domain, user action, and caller-facing flag (they do, from PR #1180) — nothing to add there.

### Phase 2 — implement

- `pipelex/pipeline/validate_bundle.py`: import `EntryPipeNotFoundError`, swap the raise at the `missing` check in `_pipes_to_dry_run`, update its `Raises:` docstring. Leave the `translate_to_validate_bundle_error` passthrough arm as `except PipeNotFoundError: raise` (the base catch is the point: it must let the subclass through raw), refreshing its comment to name the entry class.
- `pipelex/libraries/pipe/exceptions.py`: reword the `EntryPipeNotFoundError` docstring's "exactly one raise site" sentence.
- `pipelex/builder/operations/validate_ops.py`: update the docstring mentions.
- Phase 1's test goes green.

### Phase 3 — sweep, docs, gates

- Sweep the remaining catchers for message-matching or type branching the subclass would change — none expected: `_validate_core.py:242` (bare CLI, prints `str(exc)`), `pipe_cmd.py:187` (unreachable from this raise site but catches the base), `bundle_validator.py`'s sweep arm (unreachable, see Design).
- Run `make gei` and `make gep`; confirm both produce no diff (no new class, unchanged summary line). If `gep` does diff, commit the regenerated page.
- `docs/under-the-hood/error-model.md`: extend the Behavior Summary row for entry pipe lookups (line ~491) to mention the `--pipe` / `pipe_ref` bundle-slice miss as a third raise context of `EntryPipeNotFoundError`.
- `CHANGELOG.md` under `## [Unreleased]`: one condensed entry — fixed: a typo'd `--pipe` / `pipe_ref` slice selector in bundle validation now raises `EntryPipeNotFoundError` (INPUT domain → 422), matching the entry lookups, instead of the undomained base class that rendered 500 off the build route.
- `make agent-check`, targeted tests (`tests/unit/pipelex/pipeline/ tests/integration/pipelex/pipeline/ tests/unit/pipelex/cli/ tests/integration/pipelex/cli/`), then full `make agent-test` before the PR.

### Checkpoint

After Phase 3: record what landed, any deviations, and open the PR against `dev` with `Closes L-260901-296dfb` in the body. After the merge, the `pipelex-api` follow-up item becomes workable once a release carries the change.
