# Codegen follow-ups from the `@pipelex/sdk` `runCodegenCheck` port (PR #31 review triage)

> **ARCHIVED from the repo-root `TODOS.md` on 2026-08-19 — the code work is complete, the release gate is not.** Phases 1 through 5 shipped on `feature/Codegen-followups` (PR #1127): U1–U5 are implemented, tested, documented and swept. What remains open is not code but the `@pipelex/sdk` release gate — until an SDK that tolerates `lock_version` is *published*, the very release that fixes U3 triggers the failure U3 describes in every pinned consumer's CI, because their `rejectUnknownKeys` hard-throws on the new key. Pick that up from the "Cross-repo" and checkpoint sections below rather than re-deriving it. Moved off the repo root because the root tracker belongs to whatever work is currently in flight, and this work is waiting on a publish rather than on a keyboard.
>
> **Paths below are relative to the repository root, not to this file's own directory** — they were written while this document sat at the root and are deliberately left as they were.

Source: `../pipelex-sdk-js/wip/pr-31-review-notes.md` → "Upstream follow-ups". The SDK team built a second implementation of the offline codegen check and surfaced five upstream items (U1–U5) plus one spec item (S1). All five upstream claims were **verified against this repo's code on `feature/Codegen-followups` (base `d28e703e3`, v0.46.4) and confirmed accurate** — file/line references, reasoning, and proposed fixes all check out. Every U-item is work in **this repo**; S1 is not (see the cross-repo section at the end).

Triage verdict per item:

| Item | Verdict | Owner | Action |
|---|---|---|---|
| U1 — stamp parser accepts uncommented header lines | **Confirmed** | this repo | fix (Phase 1) |
| U5 — `_parse_options` accepts `NaN`/`Infinity` | **Confirmed** | this repo | fix (Phase 1) |
| U2 — the two check loops sort by different rules | **Confirmed** | this repo | fix (Phase 2) |
| U4 — Windows artifacts written CRLF while hashes are over LF | **Confirmed** (by code reading; not reproduced on a Windows host — we have no Windows CI) | this repo | fix (Phase 3) |
| U3 — any new `codegen.lock` key is a hard break for every pinned client | **Confirmed** | this repo (format owner) | fix: add `lock_version` (Phase 4) |
| S1 — spec under-specifies what a second implementation needs | **Confirmed** (demonstrated by the SDK port) | workspace `docs/specs/` + `conformance/` — **not this repo** | recorded below, not planned here |

Cross-repo sequencing constraint, stated once: `src/codegen-check.ts` in `pipelex-sdk-js` is a byte-for-byte verdict mirror of `pipelex/codegen/`. Parser **tightenings** (U1, U5) land here first, the SDK follows — the SDK must never be stricter than the CLI it mirrors (their review already defers to us on exactly this ground). The lock **format change** (U3) is the reverse: the SDK's reader must tolerate the new key *before* a pipelex release starts writing it, because `rejectUnknownKeys` turns an unknown lock key into a hard no-verdict throw in every consumer's CI. U2 and U4 need no coordination (U2 converges toward the SDK's existing full-string sort; U4 is invisible to the SDK, which already normalizes newlines).

---

## Cold start — read this first

**Status: Phases 1–5 done and committed (Checkpoint 4 reached). All five upstream items are implemented, tested, documented and swept. What is left is not code and it is one thing: the SDK follow-up has been delivered into `pipelex-sdk-js`, but an `@pipelex/sdk` that tolerates `lock_version` must be *published* before this branch's release. Every PR #31 thread is resolved; nothing there is waiting on a reply. See the end of Phase 5.**

**Where the work is.** Branch `feature/Codegen-followups` in `pipelex/`, cut from `d28e703e3` (v0.46.4). Phase 1 is one commit, Phases 2–3 a second, Phase 4 a third, Phase 5 a fourth. The branch is pushed and open as PR #1127 against `dev` (never `main`), with every CI check green.

**Verify the tree is green before touching anything** (about a minute):

```bash
git add -A && make agent-check
.venv/bin/pytest -n auto -m "(dry_runnable or not (inference or llm or img_gen or extract or search)) and not pipelex_api" -o log_level=WARNING --tb=short -q tests/unit/pipelex/codegen/ tests/integration/pipelex/codegen/
```

**What Phases 1–3 already changed — do not redo any of it:**

| File | What is in it now |
|---|---|
| `pipelex/codegen/stamp.py` | the comment-prefix gate in `parse_stamped`, the simplified `_parse_fields`, and `_reject_json_constant` wired into `_parse_options` through `parse_constant` |
| `tests/unit/pipelex/codegen/test_stamp.py` | new tests at the end of `TestStamp` (one of them parametrized over the non-standard JSON constants) |
| `tests/unit/pipelex/codegen/test_check.py` | `test_uncommented_line_injected_into_the_header_is_hand_edited_drift` at the end of `TestCheck` |
| `subject_grants.toml` | the grant for `pipelex/codegen/stamp.py::_reject_json_constant` |
| `docs/under-the-hood/codegen-projections.md` | two paragraphs under § Stamps — the header-strictness rules and the forward tolerance |
| `CHANGELOG.md` | one `## [Unreleased]` → `### Fixed` entry — **extend it, do not add a second bullet per phase** |
| `pipelex/codegen/check.py` | `_find_orphans` returns `sorted(orphans, key=…path)`, and `run_codegen_check`'s docstring states the ordering contract |
| `pipelex/tools/misc/file_utils.py` | `save_text_to_path` writes `newline="\n"`, with the rationale in its (now raw) docstring |
| `tests/unit/pipelex/tools/misc/test_save_text_to_path.py` | new module — the LF tripwire, the CRLF-verbatim case, and a reader round-trip |
| `pipelex/codegen/lock.py` | `CODEGEN_LOCK_VERSION`, the `lock_version` field, `_reject_unknown_lock_version` called **before** `model_validate`, the `except CodegenLockError: raise` passthrough, and the evolution policy in the module docstring |
| `tests/unit/pipelex/codegen/test_lock.py` | the `_LEGACY_LOCK_WITHOUT_VERSION` fixture and the version tests at the end of `TestLock` |
| `tests/unit/pipelex/codegen/test_emission.py` | the two regeneration tests (legacy lock relocked; newer-version lock replaced) |
| `.badges/tests.json` | refreshed to the new collected-test count (repeat after every test-adding phase) |

**Five traps this repo sets, every one of them hit during Phase 1:**

1. **`drift-check` reads the git index, not the working tree.** It runs inside `make agent-check`, so `git add -A` before checking or it reports a false green on unstaged work.
2. **`make agent-check` runs the keyword-only auto-fixer**, which silently makes an ungranted positional subject keyword-only. Any new function whose first parameter must stay positional — a callback a framework invokes, which is exactly what `_reject_json_constant` is — needs `make subject-grant FUNC="<path>::<qualname>" RATIONALE="…"` recorded **before** the first check run. Put no backticks in the rationale: `make` executes them and they vanish.
3. **`make check-test-badge` is in no local aggregate.** Any commit that adds tests passes both local gates and fails CI until `.badges/tests.json` is set to what `make test-count` prints.
4. **Write the tests red first and watch them fail against current code.** Phase 2's ordering test proves nothing unless its fixture holds the adversarial `models/` -beside- `models.py` pair; mutation-test it by reverting the sort.
5. **Each phase carries its own doc edit and extends the same `## [Unreleased]` entry.** Phase 5 is the sweep that verifies nothing was missed — not the place to write all of it for the first time.
6. **Ruff `D301` rejects a docstring containing a backslash unless it is raw.** Phase 3's newline docstrings tripped it; prefix them `r"""` and write single backslashes rather than doubling them.

**Pointers below name symbols rather than line numbers, which drift with every edit to these files** (the numbers this document originally carried were all taken against the branch base `d28e703e3`, and this work's own diff moved every one of them): `check.py` → the `sorted(lock.hash_by_path().items())` loop in `_check_locked_artifacts`; `file_utils.py` → the `write_text(..., newline="\n")` call inside `save_text_to_path`; `lock.py` → the two `extra="forbid"` model configs (`CodegenLockEntry` and `CodegenLock`) and the `encode_lock` / `load_lock` pair; `stamp.py` → `_parse_fields` and `_parse_options`. The `stamp.py` pair is cited inside Phase 1 as the code **before** the fix — kept for the record, since that work is done.

---

## Phase 1 — Stamp parser tightenings (U1 + U5) — **DONE**

Both are strictness fixes in `pipelex/codegen/stamp.py`, both turn a malformed stamp into `parse_stamped(...) -> None`, which `_check_present_artifact` already reports as a `hand-edited` drift ("Stamp header is missing or unparseable"). No new error class, so no `gei`/`gep` run needed.

### U1 — reject uncommented lines inside the stamp header

Confirmed: `_parse_fields` (`pipelex/codegen/stamp.py`) has an `else raw_line.strip()` fallback that silently swallows any header line not starting with the comment prefix, and nothing in `parse_stamped` or `check.py` compensates. An artifact with `throw new Error("edited");` injected between the stamp markers parses fine and reports CURRENT, because the body is sliced below the end marker so its hash is untouched. The SDK notes are also right that this is *not* a security boundary (no signature/MAC anywhere; the defence is diff review) — this is a correctness tidy-up, but a cheap and worthwhile one: an executable line hiding inside a `DO NOT EDIT` block should not verify as pristine.

Implementation, in `parse_stamped` immediately after the `header_region` slice:

```python
if any(not line.startswith(comment_prefix) for line in header_region.splitlines()):
    return None
```

Then simplify `_parse_fields`: the `else raw_line.strip()` fallback is dead once the gate exists — drop it, so the function reads `stripped = raw_line[len(comment_prefix):].strip()` unconditionally.

Verified safe on shape: `apply_stamp` emits `[begin] + [f"{prefix} {key}: {value}" ...] + [end]` — every header line carries the prefix, no blank lines. So the gate rejects no stamp we ever wrote. An empty `header_region` passes vacuously and then fails on the missing `projection` field, as today.

Tests (`tests/unit/pipelex/codegen/test_stamp.py`, plus one check-level test in `test_check.py`) — write them red first against current code where possible (TDD):

- An uncommented line injected between the markers → `parse_stamped` returns `None`. (Red today.)
- A blank line injected inside the header → `None`. (Red today.)
- A *commented* unknown field line (`# future_field: value`) still parses — pins the additive tolerance of the stamp header in the forward direction, so U3's evolution policy ("stamp additions never need a version") stays true and cannot be silently reversed by a later over-tightening.
- Check-level: a locked tree whose artifact carries an injected uncommented header line → exactly one drift, category `hand-edited`. (Red today — this is the SDK's reproduction, ported.)

### U5 — reject `NaN` / `Infinity` in the stamp's `options` JSON

Confirmed: `_parse_options` (`pipelex/codegen/stamp.py`) uses a bare `json.loads`, which accepts Python's non-standard `NaN` / `Infinity` / `-Infinity` literals. No conformant JSON parser (JavaScript included) does, so a stamp carrying one is CURRENT to us and `hand-edited` to the SDK — the one differential where the SDK is the stricter side. Unreachable with today's emitter (`options` is `dict[str, str]` and `json.dumps` never emits those literals for string values), but the stamp header is a cross-language interchange format and should not be able to contain something only Python can read. Costs one argument.

Implementation:

```python
def _reject_json_constant(value: str) -> NoReturn:
    msg = f"Non-standard JSON constant in stamp options: {value}"
    raise ValueError(msg)
```

and in `_parse_options`, `json.loads(options_raw, parse_constant=_reject_json_constant)` with the existing `except` widened from `json.JSONDecodeError` to `ValueError` (its superclass, so the one clause catches both).

Tests: `options: {"x": NaN}` and `options: Infinity` in a stamp → `parse_stamped` returns `None` (red today); a normal `options: {}` and a populated string-valued object still parse (green guard).

**Checkpoint 1 — REACHED (2026-08-19), committed on `feature/Codegen-followups`.** Both tightenings landed with red→green tests. `make agent-check` clean; `tests/unit/pipelex/codegen/`, `tests/integration/pipelex/codegen/` and the whole CLI unit/integration/e2e set green. Full `make agent-test` stays deferred to Checkpoint 2, as planned.

Three things the plan above did not anticipate, all now folded into the cold-start section as reusable traps:

- `_reject_json_constant` is a callback `json.loads` invokes positionally, so it needed a subject grant (trap 2).
- Phase 1 carried its own doc edit and its own `## [Unreleased]` changelog entry — later phases extend that entry rather than adding one each (trap 5).
- `.badges/tests.json` needed refreshing for the added tests (trap 3).

One behavior verified and deliberately left alone: `_preflight_destinations` in `emission.py` also calls `parse_stamped`, so an **untracked** file whose header now fails the gate is treated as unowned and refuses to be overwritten. That is the conservative direction, and the same behavior class already existed for other unparseable stamps, so it is not a regression — but it does mean a tampered orphan is reported by the check as "remove or regenerate" while regeneration itself declines to clobber it. Noted here in case Phase 5's sweep wants to say something about it. **It did** — Phase 5 pinned it with a test and named the seam in the docs and the changelog; see there.

Phases 2–4 remain independent of Phase 1 and of each other.

---

## Phase 2 — Unify drift ordering across the check's two loops (U2) — **DONE**

Confirmed: `_check_locked_artifacts` (`pipelex/codegen/check.py`) iterates `sorted(lock.hash_by_path().items())` — a plain `str` sort over the whole relative path — while `_find_orphans` iterates `_iter_stampable_files`, a pre-order DFS doing `sorted(directory.iterdir())` per level, which is a path-*component* sort. For a tree holding `models/` beside `models.py`, the two halves of one report order paths by different rules (`models/foo.py` before `models.py` component-wise; the reverse string-wise). The reference is internally inconsistent, and the SDK cannot mirror both rules with one comparator.

Decision (ours to make, as the reference): **unify on the plain full-string sort**, the rule the locked-artifact loop already uses. Rationale: it matches `build_lock`'s "artifacts sorted by path" ordering in the lock file itself, it is the rule the SDK already implements for both of its loops (so upstream converges toward the mirror instead of forcing a component-wise comparator on every future client), and it is the cheaper spec sentence for S1 to eventually pin.

Implementation: keep `_iter_stampable_files` exactly as is (its DFS order is a *traversal* concern — deterministic pruning and filesystem walking — not a *report* concern); in `_find_orphans`, return `sorted(orphans, key=lambda drift: drift.path)` instead of the raw accumulation order. One line. Then state the now-real guarantee where the SDK had to reverse-engineer it: extend the `run_codegen_check` docstring with the ordering contract — locked-artifact drifts first in path order, then orphans in path order, at most one drift per locked path with `hand-edited` outranking `modified`. (That last property is already structural in `_check_present_artifact`; writing it down is S1 support, zero behavior change.)

Tests (`tests/unit/pipelex/codegen/test_check.py`): `test_drifts_are_ordered_locked_first_then_orphans_each_by_path` asserts the full `[(path, category), ...]` sequence.

⚠ **The fixture this plan originally proposed could not go red**, and the correction is worth keeping. Orphans at `models/foo.py` and `a.py` sort identically under both rules (`a.py` precedes `models/foo.py` either way), so that tree proves nothing. The two rules only diverge on a **directory sitting beside a file whose name extends it**: the DFS descends into `sub/` before reaching `sub.py` because `"sub" < "sub.py"`, while a full-string sort puts `sub.py` first because `.` (0x2E) precedes `/` (0x2F). The adversarial pair must therefore be **two orphans**, `sub.py` and `sub/foo.py` — the locked `models.py` cannot play that role, since a locked path is never an orphan.

The fixture as landed: locked `models.py` restamped-but-not-relocked (a `modified` drift — `_restamp_without_relocking`, a new helper, builds a self-consistent stamp via `build_stamped_projection` and writes the artifact only), locked `types.ts` deleted (`missing`), and the two orphans. `types.ts` sorts *after* both orphans yet is asserted first, so the test pins the loop boundary as well as the sort. Verified red before the fix, failing at exactly index 2 (`sub/foo.py` where `sub.py` belonged) with indices 0–1 already passing.

Worth noting for Phase 5: `modified` had no test coverage at all before this — every prior drift test exercised `missing`, `hand-edited` or `orphan`.

---

## Phase 3 — Emit LF artifacts on every platform (U4) — **DONE**

Confirmed: `save_text_to_path` (`pipelex/tools/misc/file_utils.py`) is `path.write_text(text, encoding="utf-8")`; with the default `newline=None`, Python translates `\n` to `os.linesep`, so on Windows every emitted artifact is CRLF on disk while `compute_content_hash` hashed the in-memory LF string. The *verdict* survives (reads come back through universal-newline translation, and `_write_if_changed` compares translated text on both sides), but `apply_stamp`'s own docstring claim — regeneration "writes byte-identical output" — holds only per-platform: a mixed Windows/Linux team sees the generated tree churn in git when nothing changed. Reasoned from documented `write_text` behavior, not reproduced (macOS `os.linesep` is `\n` and we have no Windows CI); the reasoning is airtight enough to act on.

Decision: fix it **globally in `save_text_to_path`** — `path.write_text(text, encoding="utf-8", newline="\n")` — rather than only at codegen's write site. Every caller (JSON via `json_utils`, the `build` command outputs, codegen inputs templates, codegen artifacts + lock) writes product text artifacts meant to be platform-independent; none wants `os.linesep`. One site, one behavior, no divergent write paths to remember. Update the function's docstring to state the LF guarantee.

Tests: new module `tests/unit/pipelex/tools/misc/test_save_text_to_path.py` (there were none for this function). Three cases — no `\r` reaches the disk; text that deliberately carries `\r\n` round-trips byte-for-byte rather than being doubled to `\r\r\n` (the failure mode of the *default* write, which translates only the `\n`); and a round-trip through `load_text_from_path`.

Stated honestly in the docstrings: **these are tripwires, not discriminating tests.** On POSIX `os.linesep` is already `\n` and CPython's C `TextIOWrapper` has no write-translation path at all, so they pass with or without the fix and cannot be mutation-tested here. They go red the day a Windows runner appears or the `newline` argument is dropped. Swept for platform-newline assumptions elsewhere: no `os.linesep` anywhere in `pipelex/` or `tests/`, and no existing test asserts platform newlines.

**Checkpoint 2 — REACHED (2026-08-19), committed on `feature/Codegen-followups`.** Both phases landed with the ordering test written red first. `make agent-check` clean, `make check-test-badge` refreshed to the new count, and the full `make agent-test` green.

Two things found along the way that the plan did not anticipate:

- **The proposed Phase 2 fixture was not discriminating** — see the ⚠ note in Phase 2 above. Trap 4 in the cold-start section was right that the fixture is where this test lives or dies; it just named the wrong pair.
- **A sibling of U4 exists outside codegen and is deliberately NOT fixed here** (a pre-existing bug, reported to Louis rather than folded into this diff). `fix_all_violations` in `pipelex/cli/dev_cli/commands/keyword_only_guard.py` reads each source file with `path.read_text(encoding="utf-8")` and writes it back with `path.write_text(...)`, neither passing `newline`. The read translates `\r\n` to `\n`, so the CRLF-preservation logic in `fix_source` — which `test_crlf_line_endings_preserved_and_fixed` pins byte-for-byte, and whose docstring says a regression "would corrupt every Windows-authored file the fixer touches" — is unreachable through the only caller that touches the filesystem: a CRLF file is silently normalized to LF on POSIX, and the write would emit `\r\r\n` on Windows. It is left alone because it is dev-only tooling outside this plan's scope and the fix carries a real design question (genuinely preserve CRLF by reading and writing with `newline=""`, or delete the now-pointless CRLF branch and declare the fixer LF-only). Decide that on its own terms, not inside a codegen change.

---

## Phase 4 — Version the lock format (U3) — the one with real blast radius — **DONE**

Confirmed: `CodegenLock` and `CodegenLockEntry` both carry `extra="forbid"` (`pipelex/codegen/lock.py`), the SDK mirrors that deliberately, and the format has no version field and no written evolution policy. Consequence, correctly identified by the SDK notes: the day we add *any* key to `codegen.lock`, every consumer pinned to an older `@pipelex/sdk` (and every older `pipelex` reading a newer lock) gets a hard `CodegenLockError` no-verdict in CI — not a drift, not a warning. Nothing today makes an additive change safe, and nobody has decided whether that is policy or accident.

Decision: **add `lock_version` now**, while the only two readers are ours and the cost is zero, rather than declaring the format closed. A closed format would make every future addition a coordinated three-repo breaking release *discovered at release time*; a version field makes it a planned one with an actionable error message.

Implementation, all in `pipelex/codegen/lock.py`:

- Module constant `CODEGEN_LOCK_VERSION = 1`.
- `CodegenLock` gains `lock_version: int = 1`. The default is the compatibility hinge: every existing lock on disk (no key) validates as version 1, so no migration of existing trees is needed. `extra="forbid"` stays — strictness *within* a known version remains correct.
- `encode_lock` writes `lock_version = 1` as the first key of the payload, before `crate_fingerprint`.
- `load_lock`, after `model_validate`: if `lock.lock_version != CODEGEN_LOCK_VERSION`, raise `CodegenLockError` with an actionable message distinguishing the direction — a *greater* version means "this lock was written by a newer Pipelex codegen; upgrade pipelex (or the SDK) to read it", anything else is malformed. Reuse `CodegenLockError`; no new error class.
- Write the evolution policy down as the module docstring's contract paragraph: any change to the lock's key set or semantics bumps `lock_version`; readers reject versions they do not know, loudly and with upgrade guidance; the **stamp header** deliberately needs no version because unknown *commented* `key: value` lines are ignored by every reader (the tolerance Phase 1 pins by test).

Sequencing (this is the part that must not be improvised at release time):

1. Land here on `dev`, unreleased. The lock bytes change (every regeneration rewrites the lock once — expected, `_write_if_changed` sees the new key).
2. File the SDK follow-up: accept `lock_version`, mirror the reject-unknown-version rule and its message verbatim, refresh the vendored fixtures. **The SDK release must be available before the pipelex release that writes the key** — their `rejectUnknownKeys` hard-throws otherwise, which is precisely the failure mode U3 exists to eliminate. Note it in the release-notes draft for whichever pipelex version first ships this.
3. The spec's "Lock format" section (workspace `docs/specs/pipelex-codegen.md`) gains the field and the evolution policy — workspace-repo change, listed in the cross-repo section below.

Tests (`tests/unit/pipelex/codegen/test_lock.py`, plus emission round-trip in `test_emission.py`):

- `encode_lock` output contains `lock_version = 1` and `load_lock` round-trips it.
- A lock **without** the key (yesterday's format, verbatim TOML fixture) loads as version 1 — the no-migration guarantee, pinned.
- A lock with `lock_version = 2` → `CodegenLockError` whose message names the found version and says to upgrade. Same for a non-integer value (pydantic shape error path, already wrapped).
- `write_stamped_projection` over a tree locked by the old format rewrites the lock once and reports current on the next check.

**Checkpoint 3 — REACHED (2026-08-19), committed on `feature/Codegen-followups`.** The version field landed with its tests written red first, both load-bearing ones mutation-tested. `make agent-check` clean, badge refreshed, full `make agent-test` green.

⚠ **Still open, and it gates the release:** the SDK follow-up is **filed** at the workspace inbox — `../wip/inbox/2026-08-19-pipelex-sdk-js-codegen-lock-version.md` (it carries the four rules to mirror, the ordering trap, and the fixture refresh). It is *not yet triaged into `pipelex-sdk-js`*, and no SDK PR exists. Record here, before releasing: the `pipelex-sdk-js` issue/PR link and its release status. Until an `@pipelex/sdk` that tolerates `lock_version` is published, a pipelex release carrying this change hard-breaks every consumer pinned to the current SDK — the exact failure U3 exists to eliminate.

**Two corrections to the plan above, both found while implementing:**

- **The version gate must run BEFORE `model_validate`, not after it.** The plan put the check after validation, which is unreachable for the case that matters: `extra="forbid"` rejects a v2 lock that *adds a key* as a pydantic shape error before the version is ever read, so the reader emits an opaque "Extra inputs are not permitted" complaint instead of "upgrade pipelex" — precisely the unactionable no-verdict U3 exists to eliminate. `load_lock` now reads `lock_version` out of the parsed TOML first. Pinned by `test_a_newer_lock_version_is_refused_even_when_it_carries_unknown_keys`, and mutation-tested by moving the call back after `model_validate` (goes red with the pydantic message). The `except CodegenLockError: raise` passthrough (mirroring `run_codegen_check`) keeps the verdict from being re-wrapped as "Malformed or unsafe" — also mutation-tested.
- **The plan's "reuse `CodegenLockError`, no new error class" has a consequence worth stating explicitly, and it was a real decision.** `_previous_tracked_paths` in `emission.py` discriminates on `exc.__cause__`, so a bare `raise` makes an unreadable-version lock **replaceable prior state during regeneration**, exactly like a corrupt one — `codegen types` overwrites it rather than failing. Deliberate: the run has already rewritten every artifact with this engine, the lock is purely derived, and refusing would strand a developer on a generated file. The cost is that pruning is skipped, so anything the newer engine emitted lingers — but it surfaces loudly as an orphan on the very next check rather than silently. Pinned by `test_regeneration_replaces_a_lock_written_by_a_newer_codegen`. The alternative (a `CodegenLockVersionError` subclass that propagates through regeneration) was rejected as buying little for a derived artifact, at the cost of a new error class plus its `gei`/`gep` runs.

One test in the plan turned out to be untestable and is documented rather than written: `build_lock` passes `lock_version=CODEGEN_LOCK_VERSION` while the field default is the literal `1`. The split is what makes a future bump a one-line change (bump the constant; the "absent key means version 1" statement stays true forever), but with only one version in existence the two values coincide, so no test can distinguish them. The reasoning is in the field's docstring.

---

## Phase 5 — Docs, changelog, and closure — **DONE**

The sweep found one real gap and one loose end, which is what a sweep is for; the rest of the pass confirmed Phases 1–4 had each carried their own doc and changelog edit as intended.

**The gap: Phase 3's LF guarantee never reached `docs/`.** It was written into `save_text_to_path`'s docstring and nowhere else — a grep for line-ending vocabulary across `docs/` returned only unrelated hits in `migration-ledger.md` and `plxt.md`. That mattered because the codegen page is where byte-identical regeneration is *promised* to a reader, and the promise was platform-conditional without saying so. § Idempotent emission now states that every artifact is written LF on every platform, and why: the same projection emitted on Windows and on Linux would otherwise land as different bytes while both recorded the same content hash, so a mixed-platform team would watch the generated tree churn with no change of content.

**The loose end: the `_preflight_destinations` seam Phase 1 flagged for this sweep, now pinned rather than merely noted.** Verified by running it, not by reading it: a stamped file whose header carries an injected uncommented line has `has_stamp() == True` but `parse_stamped() == None`, so the check reports it as an **orphan** advising "remove or regenerate" while `write_stamped_projection` raises `CodegenError: Refusing to overwrite unowned file` and leaves it byte-for-byte intact. Half the advice is wrong. This is a behavior U1 *changed* — before the strict gate such a file parsed, so regeneration silently overwrote it — and nothing guarded it, so `test_a_stamped_file_whose_header_was_tampered_is_an_orphan_the_regenerator_refuses_to_reclaim` in `test_emission.py` now does. It is discriminating: mutating the U1 gate to `if False` leaves the orphan assertion green and turns the refusal assertion red (`DID NOT RAISE`), so the test fails for the reason it exists. The refusal itself is left alone — declining to clobber a file we cannot prove we own is the same conservatism that protects a hand-authored module sharing the output directory — but § Idempotent emission now names the seam, and the changelog's stamp bullet tells a user hitting it to remove the file before regenerating.

Everything else was confirmed already in place: § Stamps carries the header-strictness rules and the forward tolerance, § Offline check carries the drift-ordering contract, § Lock carries `lock_version` and the evolution policy, and `## [Unreleased]` carries one `### Added` entry for the lock version plus three `### Fixed` entries for the stamp tightenings, the unified ordering and the LF writes. Swept the codegen write path too: `emission.py` reaches the disk only through `save_text_to_path`, so the LF fix covers the whole trust chain with no bypass.

`make agent-check` clean, `.badges/tests.json` refreshed to the count the added test produced, and the full `make agent-test` green.

**Checkpoint 4 — REACHED (2026-08-19), committed on `feature/Codegen-followups`.** The code work for U1–U5 is complete. One item remains, and it is not code — it gates the release. The second is kept below as a closed record rather than as work:

1. ⚠ **The SDK follow-up is delivered; the release gate is now an SDK *release*, not a filing.** Triaged out of the workspace inbox on 2026-08-19 and delivered into `pipelex-sdk-js` as `wip/upstream-codegen-followups-mirror.md`, committed on `feature/Codegen-follow-ups` (the PR #31 branch) as "docs: record what the upstream codegen landing requires of this SDK". It carries the four rules to mirror, the read-the-version-before-the-key-set ordering trap, the fixture refresh, and a direction table for all five items — the SDK's own `pr-31-review-notes.md` gained per-item status lines in the same commit, since its claim that nothing had been filed upstream was no longer true. **What still blocks a pipelex release is unchanged in substance:** until an `@pipelex/sdk` that tolerates `lock_version` is *published*, the very release that fixes U3 causes the failure U3 describes in every consumer's CI, because their `rejectUnknownKeys` hard-throws on the new key. Record the published `@pipelex/sdk` version here before cutting a pipelex release.
2. **The PR #31 threads are now all resolved — this item is closed.** It read, until 2026-08-19, that two threads (`chatgpt-codex-connector` and `cubic-dev-ai`, both on item 1 of `../pipelex-sdk-js/wip/pr-31-review-notes.md`) were waiting on a reply, and a later correction raised the count to five. Every review thread on PR #31 now reports resolved, so nothing there is blocking. Kept as a record of what the replies had to say, not as work: U1 has landed on this branch and is unreleased, so any reply could only claim "fixed upstream, pending release", never "shipped".

   A count correction worth carrying, from when these were open: PR #31 had **five** unresolved threads, not two. Besides the two U1 ones, a third (`cubic-dev-ai`, `src/codegen-check.ts:552`, the drift-ordering deferral) is materially changed by Phase 2 — upstream converged on the SDK's own full-string comparator, closing the reachable ASCII half of that finding — so it got a draft too. The remaining two are SDK-only and untouched by this work: the `WINDOWS_DRIVE = /^.:/u` regex missing U+2028 / U+2029 (verified real from this side — `validate_artifact_path` rejects `\u2028:models.py` as a drive prefix, and U+2028 is `Zl` so the control-character gate does not catch it first, leaving the SDK the permissive side), and a duplicated CRLF test row. Both are recorded at the end of the delivered SDK doc.

## Cross-repo follow-ups (recorded here, **not** work in this repo)

- **`pipelex-sdk-js`** — after U1/U5 release: mirror both tightenings (their notes already carry the ready-to-apply TS patch and test for U1). After U3 lands here (before our release): version-aware lock reader + fixture refresh, per Phase 4 sequencing. After U2: nothing — we converged toward their comparator; their only residual ordering divergence is the practically unreachable UTF-16-vs-code-point case their item 2a documents, which stays deferred on their side.
- **`docs/specs/pipelex-codegen.md` + `conformance/` (workspace repo pair)** — S1: when the codegen sections de-skeleton, fold in the three load-bearing properties the SDK had to derive by reading `check.py` (at most one drift per locked path with `hand-edited` outranking `modified`; the orphan predicate is `has_stamp`, not the full parse; deterministic drift ordering — locked first, then orphans, both by path), plus the stamp-header text rules (line boundaries, strip set) as part of the hashed contract, plus U3's `lock_version` and evolution policy. Keep the `> Verified by:` ↔ `pytest.mark.spec` links in sync and run `make check-spec-links` in `conformance/`. This is release-gated on a published pipelex shipping codegen, per the existing `unverified` markers.
- **`pipelex-sdk-python`** — no codegen-check mirror exists today; if one is ever built, S1's spec work is what makes that safe. Nothing to do now.
