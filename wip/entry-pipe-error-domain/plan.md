---
status: draft
item: L-260829-fa8267
---

# Give the entry-pipe lookup failures the INPUT domain

## The bug, verified

An ambiguous or unknown entry `pipe_code` on the run routes is reported as a server fault. Probe on this tree (dev):

```python
from pipelex.libraries.pipe.exceptions import PipeLibraryError, PipeNotFoundError
PipeLibraryError("…").to_error_report()   # error_domain=None, http_status=500
PipeNotFoundError("…").to_error_report()  # error_domain=None, http_status=500
```

Both classes are declared bare (`pipelex/libraries/pipe/exceptions.py`), so `ErrorReport.http_status` falls through `error_domain_to_http_status(None)` → 500 (`pipelex/base_exceptions.py`). The raise sites are the entry-shaped lookup in `pipelex/libraries/pipe/pipe_library.py`: `get_optional_entry_pipe` raises `PipeLibraryError` on an ambiguous bare code, and `get_required_entry_pipe` raises `PipeNotFoundError` on a miss. The run path reaches them through `pipeline_run_setup.py` (`get_required_entry_pipe` on a caller-supplied `pipe_code`), so a caller typo surfaces as a 500, logged with a traceback, looking retryable to every SDK — for a mistake only the caller can fix. Meanwhile `pipelex-api`'s build routes catch `PipeLibraryError` and answer 422 (`api/routes/pipelex/crate_ops.py`), so the same typo gets two different verdicts depending on the route. `pipelex-api/api/exception_handlers.py`'s `_ERROR_TYPE_STATUS_OVERRIDES` has no entry for either class — and per the ledger item, the runtime-side domain is the better fix anyway: every presentation (CLI exit code, API status, hosted) derives from it at once.

## Design

- **Two dedicated classes** in `pipelex/libraries/pipe/exceptions.py`, subclassing the existing ones so every current catcher keeps working (`bundle_validator.py`, `validate_bundle.py`, `pipe_parallel.py`, the CLI commands, and `pipelex-api`'s `crate_ops.py` / `build/runner.py` all catch the bases):
  - `EntryPipeNotFoundError(PipeNotFoundError)` — raised by `get_required_entry_pipe` when the lookup resolves nothing.
  - `EntryPipeAmbiguousError(PipeLibraryError)` — raised by `get_optional_entry_pipe` when a bare code matches several domains.
- **Both carry** `error_domain = ErrorDomain.INPUT`, a `user_action = UserAction(kind=UserActionKind.CHANGE_INPUT, …)`, a `_declared_title`, and `_authors_caller_facing_message = True` — the messages describe only the caller's own `pipe_code` and the qualified `pipe_ref` candidates of their own loaded bundles, so STRICT disclosure may keep them verbatim. The flag spans every raise site of a class; these classes have exactly the two entry-lookup raise sites, so that is safe. Imports mirror `pipelex/pipeline/exceptions.py` (`ErrorDomain` from `base_exceptions`, `UserAction`/`UserActionKind` from `cogt/inference/error_classification`).
- **Messages** keep naming the candidates as sorted qualified `pipe_ref`s (the ambiguous message already does) and say what to send instead: name one candidate explicitly as `domain.pipe_code` in the `pipe_code` field / CLI argument.
- **In-body semantics untouched.** `get_optional_pipe` / `get_required_pipe` keep raising the existing classes. One edge: an entry-shaped `alias->bare_code` that is ambiguous inside the dependency raises `PipeLibraryError` from *inside* `get_optional_pipe` (the alias-scoped bare-remainder search) even when the call came through the entry lookup. `get_optional_entry_pipe` will translate that: wrap its `get_optional_pipe` delegation, catch `PipeLibraryError`, re-raise as `EntryPipeAmbiguousError` `from` the original. In-body callers going directly through `get_optional_pipe` see no change.
- **No `pipelex-api` change needed.** With the domain on the classes, `ErrorReport.http_status` yields 422 and `_ERROR_TYPE_STATUS_OVERRIDES` stays untouched; the build routes' explicit 422 catch is unaffected (subclasses still match).

## Phases

### Phase 1 — red tests

In `tests/unit/pipelex/libraries/test_pipe_library_lookup.py` (extend the existing suite):

- An ambiguous bare entry code (two domains declaring the same pipe code) raises `EntryPipeAmbiguousError`; the message names both qualified `pipe_ref`s; `to_error_report()` has `error_domain == ErrorDomain.INPUT` and `http_status == 422`.
- An unknown entry code raises `EntryPipeNotFoundError`; same report assertions.
- The entry-shaped `alias->bare_code` ambiguity is translated to `EntryPipeAmbiguousError` (with the `PipeLibraryError` as `__cause__`), while the same lookup through `get_optional_pipe` still raises plain `PipeLibraryError`.
- In-body miss through `get_required_pipe` still raises plain `PipeNotFoundError` with no domain (guards the "untouched" constraint).

Run them, watch them fail for the right reason.

### Phase 2 — implement

- Add the two classes to `pipelex/libraries/pipe/exceptions.py`.
- `pipe_library.py`: swap the two raise sites; add the translation wrapper in `get_optional_entry_pipe` around its `get_optional_pipe` call.
- Regenerate the error artifacts — a new error class is invisible to everything but the full suite until this is done: `make gei` (error-identity snapshot) and `make gep` (error reference pages under `docs/errors/`).
- Tests from Phase 1 go green.

### Phase 3 — sweep, docs, gates

- Sweep callers of the two lookups (`interpreter_hub.py` wrappers, `pipeline_run_setup.py`, CLI `show`/`which`/`validate`/`codegen`) for any message-matching or type branching that the new subclasses would change — none expected, verify anyway.
- CHANGELOG.md under `## [Unreleased]`: one condensed entry (fixed: entry-pipe lookup failures now carry the INPUT domain → 422 instead of 500 on the run routes).
- `make agent-check`, then full `make agent-test` (the identity snapshot and error-page tests only run there).

### Checkpoint

Record here: test results, any deviation from the design above (especially on the alias-ambiguity translation), and the commit SHA. Then open the PR against `dev` with `Closes L-260829-fa8267` in the body. After the merge, the blocked runner-side item L-260829-a30018 becomes workable.
