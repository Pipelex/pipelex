---
status: active
item: L-260829-fa8267
---

# Give the entry-pipe lookup failures the INPUT domain

## The bug, verified

An ambiguous or unknown entry `pipe_code` on the run routes is reported as a server fault. Probe on this tree (dev):

```python
from pipelex.libraries.pipe.exceptions import PipeLibraryError, PipeNotFoundError

PipeLibraryError("…").to_error_report()  # error_domain=None, http_status=500
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

All three phases landed. `make agent-check` and the full `make agent-test` are green.

**Deviations from the design, and one thing the sweep actually found.**

The alias-ambiguity translation went in as designed, wrapping only the `get_optional_pipe` delegation in `get_optional_entry_pipe` and re-raising `from` the original. Nothing else about the in-body path moved: the plain `PipeLibraryError` / `PipeNotFoundError` still come out of `get_optional_pipe` and `get_required_pipe` with no domain, pinned in both directions by the lookup suite.

The one real find was outside the design. `pipelex/cli/agent_cli/commands/validate/pipe_cmd.py` and `bundle_cmd.py` caught `PipeNotFoundError` and passed `error_type="PipeNotFoundError"` as a hardcoded string. Because `agent_error` reads the domain and hint report-first from the cause, those envelopes would have carried `EntryPipeNotFoundError`'s INPUT domain and `CHANGE_INPUT` hint while naming a class that declares neither — an envelope contradicting itself for anyone branching on `error_type`. Both arms now pass `type(exc).__name__`. That is a wire-visible change for a consumer keyed on the old string, which is the point: the string was already the wrong answer. No test asserted on it, and neither `AGENT_ERROR_HINTS` nor `AGENT_ERROR_DOMAINS` held an entry for it.

That edit opened the `cli-docs` drift contract. Reviewed, acked, and the rule is now written into `pipelex/cli/agent_cli/CLAUDE.md`'s Error-classification bullet, since the trap generalizes: with a report-first read, any hardcoded `error_type` label detaches the reported class from the classification riding beside it.

**Docs.** `docs/under-the-hood/error-model.md` gained a Behavior Summary row for the entry lookups, stating the in-body contrast. `docs/errors/entry-pipe-not-found-error.md` and `entry-pipe-ambiguous-error.md` are the generated pages (`make gep`), and `tests/data/errors/error_identity.txt` the regenerated snapshot (`make gei`).

**Also pinned.** `tests/unit/pipelex/exceptions/test_class_level_metadata.py` gained both classes in the domain, user-action and caller-facing sweeps, plus their undomained, non-caller-facing parents — so a future refactor that lets the entry classification leak onto the in-body doors, or that quietly drops it from the entry ones, fails there too.

Next: open the PR against `dev` with `Closes L-260829-fa8267` in the body. After the merge, the blocked runner-side item L-260829-a30018 becomes workable.

### Review round

Two corrections on top of the checkpoint, both inside the design's own surface.

`EntryPipeAmbiguousError`'s `user_action` detail said `Name one of the listed candidates explicitly, as 'domain.pipe_code'.` That is right for the bare-code arm and wrong for the arm translated from the alias-scoped search, whose message names domains inside a dependency package: a caller obeying it and sending `scoring.compute_score` reaches the entry lookup's host-only match (`pipe_library.py`'s `has_cross_package_prefix` exclusion), resolves nothing, and gets `EntryPipeNotFoundError` instead. One `user_action` serves both raise sites, so the detail now carries both spellings. `make gep` regenerated the ambiguous page.

The translation arm caught `PipeLibraryError`, and `PipeNotFoundError` is one — so a miss raised from inside `get_optional_pipe` would have been re-raised as a class asserting an ambiguity, carrying a hint about candidates that never existed. No in-body site raises one there today, which is exactly why the trap would have been silent; `get_optional_entry_pipe` now lets `PipeNotFoundError` through untranslated. Pinned by `test_entry_pipe_does_not_translate_a_miss_into_an_ambiguity`, which injects the raise and was mutation-checked red with the arm removed.

The review also found the same defect class one module over, left out to keep this diff at its stated scope: `validate_bundle.py`'s `_pipes_to_dry_run` raises the undomained `PipeNotFoundError` for a caller-supplied `--pipe` / `pipe_ref`, and `pipelex-api`'s build route maps it to 422 by hand. Filed as L-260901-296dfb.
