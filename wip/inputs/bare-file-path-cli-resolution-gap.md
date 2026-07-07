# Deferred: bare Image/Document path strings are not resolved against the inputs-file dir

**Status:** deferred — no code change in Phase 2; the fix IS Phase 3's first task (D3). Surfaced by the PR #1030 bot review, 2026-07-07 ([Codex thread](https://github.com/Pipelex/pipelex/pull/1030#discussion_r3538032585), [cubic thread](https://github.com/Pipelex/pipelex/pull/1030#discussion_r3538053292) — the two unresolved threads on `execution_seams.py`).

## What the reviewers flagged (verified — the mechanism is real)

With Phase 2 shaping live, a bare string for a declared `Image`/`Document`-family input is shaped into `ImageContent(url=<raw string>)` / `DocumentContent(url=<raw string>)` (the `InputKind.IMAGE | InputKind.DOCUMENT` arm in `pipelex/core/memory/input_shaper.py` does `{"url": value}` → `_make_content`). But the CLI inputs-file path resolver `resolve_url_in_value` (`pipelex/cli/commands/run/_inputs_path_resolver.py`) rewrites relative local paths **only under dict keys literally named `"url"`**, and it runs on the raw parsed dict *before* the pipe signature exists (`_run_core.py` and the agent CLI's `stdin_resolver.py`, base_dir = inputs file's parent).

Net effect: for an inputs file outside the CWD, `{"contract": "docs/a.pdf"}` for a `Document` input stays unresolved and is later read relative to the process CWD — while the explicit `{"url": "docs/a.pdf"}` form IS resolved against the inputs-file dir. Phase 2 made the two forms diverge.

## Why deferred, not fixed in Phase 2

- **It is a known, scheduled gap, not a regression.** `TODOS.md` names it three times: the cold-start "Path resolution today (D3/D7)" fact, the "D3 path-resolution seam" gap (with the recommended fix), and Phase 3's **first task** ("Settle the D3 path-resolution mechanism"). `smart-inputs-design.md` §D3 defers the same question to implementation time. Phase 3 is the immediate next work on this branch.
- **No previously-working path regresses.** Explicit `{"url": …}`, absolute paths, and storage URIs all resolve exactly as before. Only the *new* bare-string convenience is half-wired.
- **The common failure is loud, not silent.** An unresolved relative path raises `FileNotFoundError` at extraction. The "reads the wrong file" case requires a same-named file to also exist under the CWD — a narrow footgun.
- Building the fix now would pull Phase 3 scope forward and duplicate its tests-first sequencing.

## Interim guard → considered and NOT added

The bots' alternative — gate bare *relative local* paths for Image/Document (typed shaping error pointing at absolute paths or `{"url": …}`) until Phase 3 — was considered and rejected: it is churn Phase 3 immediately rips out, for a low-severity window whose common failure mode is already loud.

## The fix (Phase 3, D3 — already planned)

Make the CLI resolver signature-aware: resolve the pipe first, then pass its `InputStuffSpecs` into `resolve_inputs_paths` so bare relative strings whose declared concept is Image/Document-family get resolved against the inputs-file dir *alongside* `"url"` keys — keeping path resolution a CLI concern (API/SDK callers pass absolute URLs / storage URIs; no base_dir leaks into core). Tests first, per the Phase 3 checklist: the e2e must pin both the bare form and the `{"url": …}` form to the same resolved result, driven through the CLI file-load path (the current smart_inputs e2e passes in-process dicts, which never hit `resolve_inputs_paths`).

When Phase 3 lands, answer + resolve the two open PR #1030 threads.
