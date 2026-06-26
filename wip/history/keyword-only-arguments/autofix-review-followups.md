# Keyword-only auto-fix — review follow-ups

Follow-up items from the code review of the **`--fix` auto-fix** addition to the keyword-only guard (branch `feature/Tweaks-for-validation-api`, 2026-06-17). This is a follow-on to the landed keyword-only refactor tracked in this folder's [README](README.md).

## What the auto-fix change added

- `pipelex-dev check-keyword-only --fix` — inserts a bare `*` as far left as possible (right after `self`/`cls`, and after any `/`) so **every** non-`self`/`cls` parameter becomes keyword-only, for every *mechanically-fixable* violation, and reports the rest for a manual fix. Core lives in the stdlib-only `keyword_only_guard.py` (`fix_source` / `fix_all_violations` / `_fix_insertion_point`); reporting in `check_keyword_only_cmd.py` (`_run_fix`).
- `make fix-keyword-only` / `fko` Makefile target.
- `make agent-check` now runs `fix-keyword-only` early (after `fix-unused-imports`, before `format`), replacing the old check-only `check-keyword-only` step that ran last. `make check` / `c` / `cc` keep the **check-only** variant (read-only, CI-equivalent).
- Tests in `tests/unit/pipelex/cli/dev/test_keyword_only_guard_fix.py`; docs "Auto-fix" section in `docs/contribute/keyword-only-arguments.md`.

The review (3 independent finder angles + verification, conventions/markdown clean) surfaced the items below. Ranked; each tagged **bug** (fix) or **tradeoff** (decide).

## Placement change (2026-06-17)

Per user direction, the auto-fixer places the bare `*` **as far left as possible** so all args become keyword-only — `def f(a, b)` → `def f(*, a, b)`, `def m(self, a, b)` → `def m(self, *, a, b)`, `def make(cls, source, target)` → `def make(cls, *, source, target)` — rather than the original after-subject form (`def f(a, *, b)`). The subject-stays-positional exception is a *permission*, not a requirement, and the convention explicitly calls the all-keyword-only form "always allowed and often preferable", so the fixer now takes it. `_fix_insertion_point` targets the first positional-or-keyword param that is not `self`/`cls`; a single positional-only subject is still fixable (the `*` goes after the `/`), and only two-or-more positional-only params remain unfixable. The unfixable shapes (`*args`, an existing keyword-only section) are unchanged. Tests in `test_keyword_only_guard_fix.py` and docs Auto-fix section updated to match.

## Findings

### F1 — `fix_source` can silently corrupt a file: `str.splitlines()` ≠ `ast.lineno` on exotic whitespace — **bug** — ✅ FIXED (2026-06-17)

`keyword_only_guard.py:424` — `lines = source.splitlines(keepends=True)`, indexed by `lineno - 1`.

`ast`/CPython count line breaks as only `\n`, `\r`, `\r\n`. `str.splitlines()` *also* splits on form-feed `\x0c`, ` `/` `, NEL `\x85`, VT `\x0b`, `\x1c–\x1e`. When any such character appears **before** a violation in the same file — most realistically a form-feed page-break inside a docstring — `lines[lineno-1]` points at the **wrong physical line** and the `b"*, "` insert lands there.

Verified end-to-end: when the wrong line is inside a string literal the result **still re-parses**, so the re-parse guard at `keyword_only_guard.py:431-434` does NOT catch it → corrupted file is **written to disk**, and the real violation is reported as "fixed" (it isn't). When the misplaced insert instead breaks syntax, a genuinely-fixable violation is wrongly reported "unfixable" (non-destructive but wrong).

Latent today: `grep -rlP '[\x0b\x0c\x85\x{2028}\x{2029}\x1c\x1d\x1e]' pipelex/ --include='*.py'` finds nothing. High impact when triggered. Landmine for any future file with such a char.

### F2 — pre-existing: same divergence breaks `# kw-only: ignore` detection — **bug** — ✅ FIXED (2026-06-17)

`keyword_only_guard.py` — `_def_line_has_escape_hatch` reads `source_lines[node.lineno-1]`, where `source_lines = source.splitlines()` (built in `find_violations_in_source` at `:387` and `_find_fix_records_in_source` at `:400`). Same root cause: with an exotic-whitespace char earlier in the file, the escape-hatch marker on a def line is read off the wrong line → **false-positive violation**, and the `PostToolUse` hook would wrongly block the edit. Not introduced by the `--fix` PR, but same module/mechanism, and one fix covers both (`CLAUDE.md`: "Flag and fix existing bugs").

**Proposed fix for F1+F2 (single change):** stop using `str.splitlines()` for `ast`-line indexing. Add a shared helper that splits on the tokenizer's newline set only — e.g. `re.split(r'(\r\n|\r|\n)', source)` (capturing group), take the content elements (even indices) for `source_lines`, and in `fix_source` edit the content element in place and reconstruct with `"".join(...)`. `re` is already imported in the module. Add a regression test: a form-feed-in-docstring file followed by a violation, asserting the violation (not the docstring) is what gets the `*` and the docstring is byte-for-byte intact.

**Resolution (2026-06-17):** Implemented as proposed. Added `_LINE_BREAK_RE = re.compile(r"(\r\n|\r|\n)")` and a shared `_split_source_lines(source)` helper (`_LINE_BREAK_RE.split(source)[::2]` — content lines are the even indices). The two detection paths (`find_violations_in_source`, `_find_fix_records_in_source`) now build `source_lines` via the helper, and `fix_source` splits with the capturing group (`parts = _LINE_BREAK_RE.split(source)`), edits the content element at `(lineno - 1) * 2` in place, and rejoins — reconstructing the file byte-for-byte. Two regression tests added (both verified red before the fix): `test_form_feed_in_string_neither_corrupts_nor_misreports` (F1 — exercises the *silent-corruption* path where the misplaced `*` lands inside a triple-quoted string and still re-parses) and `test_escape_hatch_survives_form_feed_earlier_in_file` (F2 — false-positive on a `# kw-only: ignore`d def). `make agent-check` green; full guard suite green.

### F3 — standalone `make fko` / `--fix` leaves the tree NOT `ruff format`-clean — **tradeoff (lean fix)** — ✅ FIXED (2026-06-17)

`Makefile:328` (`fix-keyword-only`) runs `check-keyword-only --fix --quiet` with no following `format`. The insert is correct but un-normalized: `def f(a,b)` → `def f(a,*, b)`; a multiline signature yields `*, b` on one line. Inside `agent-check` it's masked because `format` runs next — but the docs now tell a developer to run `make fko` on its own ("auto-insert the bare `*`"), and committing that output fails CI's `ruff-format --check`.

**Options:** (a) chain `format` (or `ruff-format`) into the `fix-keyword-only` target so the standalone path is self-consistent; (b) leave the target raw and add a one-line note in the docs that `fko` should be followed by `make format` (or run inside `agent-check`). (a) is the more solid fix.

**Resolution (2026-06-17):** Took option (a). The `fix-keyword-only` target (`Makefile`) now runs `$(VENV_RUFF) format . --config pyproject.toml` immediately after `check-keyword-only --fix --quiet`, so `make fix-keyword-only` / `make fko` leaves a `ruff format`-clean tree. `ruff format` (not `format`) is sufficient — the fixer only edits `.py` files, never the TOML/MTHDS that `plxt fmt` owns. Inside `agent-check` the later `format` step re-runs `ruff format`, but that is a near-instant no-op on the already-formatted tree. Docs Auto-fix section updated to match. Verified with a throwaway `pipelex/` violation: raw insert `def probe(a,*, b):` → after `make fko` → `def probe(a, *, b):`, `ruff format --check` exit 0.

### F4 — an unfixable violation now halts `agent-check` before pyright/mypy, possibly mid-mutation — **tradeoff** — ✅ FIXED (2026-06-17, Option B)

`check_keyword_only_cmd.py:127` (`_run_fix` `sys.exit(1)` on `unfixable`) + `Makefile:1168` (`agent-check: fix-unused-imports fix-keyword-only format lint pyright mypy`, fail-fast make).

Previously `check-keyword-only` ran **last** in `agent-check`, so pyright/mypy always ran. Now a single non-mechanically-fixable violation (`*args` present, an existing keyword-only section, a positional-only-only def) short-circuits the whole type-check pass. And if `fixed` was non-empty alongside `unfixable`, files were already written but `format` is skipped → partially-mutated, un-formatted tree (compounds F3).

This is partly by design (the goal was to surface keyword-only issues early). The decision: accept the fail-fast tradeoff, or run the keyword-only autofix in a way that doesn't gate the type-check phase (e.g. keep the fixer early but defer the non-zero exit on *unfixable* until after the rest, or split "fix" from "gate").

**Resolution (2026-06-17) — split fix from gate (Option B).** The `--fix` path is now **non-gating**: `_run_fix` reports both fixed and unfixable violations but no longer `sys.exit(1)`s on the unfixable ones (the `if not fixed:` "nothing to fix" branch was tightened to `if not fixed and not unfixable:` so an unfixable run never prints the empty-happy-path message). `agent-check` gained the read-only `check-keyword-only` as its **last** prerequisite (`... pyright mypy check-keyword-only`), which is what now gates. Net effect: the fixer runs early (fix → `ruff format`, both always run since `--fix` exits 0), so `format`/`lint`/`pyright`/`mypy` always run and the tree is never left half-mutated-and-unformatted (also fully closes the F3-compounded wart); the read-only check enforces last. `make check` / `c` / CI were already read-only-gating and are unchanged. Standalone `make fko` is now fix+report (exit 0); `make cko` / `make check-keyword-only` is the gate. Verified end-to-end with a fixable+unfixable probe: `fko` fixed + formatted + reported + exited 0 (`ruff format --check` clean), `cko` FAILED on the remaining unfixable, full `agent-check` runs pyright/mypy then gates last. F5 tests updated to the non-gating contract (unfixable → exit 0 + report). Docs Auto-fix section + gate list updated.

### F5 — `_run_fix` exit-code / reporting logic is untested — **tradeoff (add tests)** — ✅ FIXED (2026-06-17)

`test_keyword_only_guard_fix.py` covers `fix_source` / `fix_all_violations` well, but the command-layer control flow in `check_keyword_only_cmd.py:98-134` (`_run_fix`) has no coverage: fix-only → exit 0; unfixable → exit 1; the fixed-and-unfixable path (files written *and* exit 1); `fix` precedence over `report`; quiet vs verbose "nothing to fix" branch. `test_check_keyword_only_cmd.py` was not updated.

**Resolution (2026-06-17):** Added `tests/unit/pipelex/cli/dev/test_check_keyword_only_cmd_fix.py` (`TestCheckKeywordOnlyCmdFix`), driving the public `check_keyword_only_cmd(fix=...)` so the real `_run_fix` control flow runs. `fix_all_violations` / `collect_all_violations` are mocked (pytest-mock) to drive each branch; `get_console` is routed to a `StringIO`-backed `Console` and `SOURCE_ROOT` to a real temp dir, so assertions are deterministic and touch no real files. Pins the enumerated cases: fix-only → exit 0 + "Auto-fixed"; quiet "nothing to fix" one-liner vs verbose success panel; and `fix` precedence (`collect_all_violations` / `_print_report` asserted not called). A new module (not the existing `test_check_keyword_only_cmd.py`, which holds the guard-core `TestCheckKeywordOnly` class) — one TestClass per module. `make agent-check` green; CLI unit suite green. (Note: the unfixable cases were updated by F4 below — they now assert non-gating exit 0 + a printed manual-fix report, not `SystemExit(1)`.)

## Recommended order

1. ~~**F1 + F2** — real silent-correctness bugs; fix together with the tokenizer-accurate line split + regression test.~~ ✅ Done 2026-06-17.
2. ~~**F3** — small, worthwhile; chain `format` into `fko` (option a).~~ ✅ Done 2026-06-17.
3. ~~**F4** — decide consciously; current behavior is defensible but is a regression in feedback completeness vs the old ordering.~~ ✅ Done 2026-06-17 (Option B: split fix from gate).
4. ~~**F5** — add command-layer tests if the exit-code contract is worth pinning (it gates CI/`agent-check`, so likely yes).~~ ✅ Done 2026-06-17.
