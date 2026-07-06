# Deferred design-tradeoff items from the Checkpoint C cold review

Review findings on the Step C diff (`7d2ed6bf4..0df759bd6`) that are deliberate tradeoffs, not bugs. Recorded here per the checkpoint protocol instead of reflexively applied; revisit when the shapes stabilize (after Step E at the earliest, since Step E touches the same boundaries).

## 1. The tri-state branch-collect pattern is hand-rolled per controller

`resolve_main_stuff()` → `isinstance AbsenceRecord` → policy appears in `pipe_parallel.py` (D11 combine policy), `pipe_batch.py` collect loop (compaction), and `pipe_batch.py` dry stamping (guard). The three policies are genuinely different (omit-or-error vs drop vs skip-stamping), so a shared helper today would abstract only the two-line resolve+isinstance prelude while forcing the policies through a callback. Decision: keep the pattern inline until a fourth site appears (e.g. a future controller); then extract a `resolve_branch_output()` helper with the re-keying rule from `pipe_parallel.py` as part of it.

## 2. `_generate_absence_files` shares the JSON + escaped-`<pre>` triplet with `_generate_main_stuff_files_from_raw`

Both render `clean_json_dumps` + `html.escape` inside `<pre>`. The overlap is a few lines and the markdown bodies are entirely different. Decision: not worth a shared helper for two call sites; if a third "render this dict as json/md/html artifact triplet" site appears in Step E (execute response? CLI?), extract then.

## 3. Nesting depth in `PipeParallel._run_branches_and_combine`

The per-branch loop nests name bookkeeping, the D11 required-field guard, and accumulation. An extraction like `_resolve_branch_or_record_absence(...) -> Stuff | None` would flatten it. Decision: cosmetic; fold into item 1's helper if/when it happens.

## 4. Non-`None` field defaults absorb the absence as the default (documented, kept)

The D11 absorption check is `field_info.is_required()`, so a non-required field with a non-`None` default absorbs an absent branch as that default. This is deliberate: it matches pydantic semantics, and an author-declared default on an optional field is exactly a per-field coalescing declaration (a preview of the phase-2 `??`). Changelog and docs now state "the field's default (`None` unless the author declared another default)" rather than promising `None`.
