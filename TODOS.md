# Codegen follow-ups from the `@pipelex/sdk` `runCodegenCheck` port (PR #31 review triage)

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

**Status: Phase 1 done and committed. Next action is Phase 2.**

**Where the work is.** Branch `feature/Codegen-followups` in `pipelex/`, cut from `d28e703e3` (v0.46.4). Phase 1 is one commit on that branch; Phases 2–5 are untouched. Nothing is pushed. When this eventually becomes a PR it targets `dev`, never `main`.

**Verify the tree is green before touching anything** (about a minute):

```bash
git add -A && make agent-check
.venv/bin/pytest -n auto -m "(dry_runnable or not (inference or llm or img_gen or extract or search)) and not pipelex_api" -o log_level=WARNING --tb=short -q tests/unit/pipelex/codegen/ tests/integration/pipelex/codegen/
```

**What Phase 1 already changed — do not redo any of it:**

| File | What is in it now |
|---|---|
| `pipelex/codegen/stamp.py` | the comment-prefix gate in `parse_stamped`, the simplified `_parse_fields`, and `_reject_json_constant` wired into `_parse_options` through `parse_constant` |
| `tests/unit/pipelex/codegen/test_stamp.py` | new tests at the end of `TestStamp` (one of them parametrized over the non-standard JSON constants) |
| `tests/unit/pipelex/codegen/test_check.py` | `test_uncommented_line_injected_into_the_header_is_hand_edited_drift` at the end of `TestCheck` |
| `subject_grants.toml` | the grant for `pipelex/codegen/stamp.py::_reject_json_constant` |
| `docs/under-the-hood/codegen-projections.md` | two paragraphs under § Stamps — the header-strictness rules and the forward tolerance |
| `CHANGELOG.md` | one `## [Unreleased]` → `### Fixed` entry — **extend it, do not add a second bullet per phase** |
| `.badges/tests.json` | refreshed to the new collected-test count |

**Five traps this repo sets, every one of them hit during Phase 1:**

1. **`drift-check` reads the git index, not the working tree.** It runs inside `make agent-check`, so `git add -A` before checking or it reports a false green on unstaged work.
2. **`make agent-check` runs the keyword-only auto-fixer**, which silently makes an ungranted positional subject keyword-only. Any new function whose first parameter must stay positional — a callback a framework invokes, which is exactly what `_reject_json_constant` is — needs `make subject-grant FUNC="<path>::<qualname>" RATIONALE="…"` recorded **before** the first check run. Put no backticks in the rationale: `make` executes them and they vanish.
3. **`make check-test-badge` is in no local aggregate.** Any commit that adds tests passes both local gates and fails CI until `.badges/tests.json` is set to what `make test-count` prints.
4. **Write the tests red first and watch them fail against current code.** Phase 2's ordering test proves nothing unless its fixture holds the adversarial `models/` -beside- `models.py` pair; mutation-test it by reverting the sort.
5. **Each phase carries its own doc edit and extends the same `## [Unreleased]` entry.** Phase 5 is the sweep that verifies nothing was missed — not the place to write all of it for the first time.

**Line references below were re-verified on 2026-08-19 and are accurate:** `check.py:101` (the locked-loop sort), `file_utils.py:80` (the `write_text` call inside `save_text_to_path`, which itself starts at line 60), `lock.py:41` and `lock.py:50` (the two `extra="forbid"`), `lock.py:151` and `lock.py:162` (`encode_lock` / `load_lock`). The two references inside Phase 1 (`stamp.py:169`, `stamp.py:196`) describe the code **before** the fix and are now stale — ignore them, that work is done.

---

## Phase 1 — Stamp parser tightenings (U1 + U5) — **DONE**

Both are strictness fixes in `pipelex/codegen/stamp.py`, both turn a malformed stamp into `parse_stamped(...) -> None`, which `_check_present_artifact` already reports as a `hand-edited` drift ("Stamp header is missing or unparseable"). No new error class, so no `gei`/`gep` run needed.

### U1 — reject uncommented lines inside the stamp header

Confirmed: `_parse_fields` (`pipelex/codegen/stamp.py:169`) has an `else raw_line.strip()` fallback that silently swallows any header line not starting with the comment prefix, and nothing in `parse_stamped` or `check.py` compensates. An artifact with `throw new Error("edited");` injected between the stamp markers parses fine and reports CURRENT, because the body is sliced below the end marker so its hash is untouched. The SDK notes are also right that this is *not* a security boundary (no signature/MAC anywhere; the defence is diff review) — this is a correctness tidy-up, but a cheap and worthwhile one: an executable line hiding inside a `DO NOT EDIT` block should not verify as pristine.

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

Confirmed: `_parse_options` (`pipelex/codegen/stamp.py:196`) uses a bare `json.loads`, which accepts Python's non-standard `NaN` / `Infinity` / `-Infinity` literals. No conformant JSON parser (JavaScript included) does, so a stamp carrying one is CURRENT to us and `hand-edited` to the SDK — the one differential where the SDK is the stricter side. Unreachable with today's emitter (`options` is `dict[str, str]` and `json.dumps` never emits those literals for string values), but the stamp header is a cross-language interchange format and should not be able to contain something only Python can read. Costs one argument.

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

One behavior verified and deliberately left alone: `_preflight_destinations` in `emission.py` also calls `parse_stamped`, so an **untracked** file whose header now fails the gate is treated as unowned and refuses to be overwritten. That is the conservative direction, and the same behavior class already existed for other unparseable stamps, so it is not a regression — but it does mean a tampered orphan is reported by the check as "remove or regenerate" while regeneration itself declines to clobber it. Noted here in case Phase 5's sweep wants to say something about it.

Phases 2–4 remain independent of Phase 1 and of each other.

---

## Phase 2 — Unify drift ordering across the check's two loops (U2) — **not started**

Confirmed: `_check_locked_artifacts` (`pipelex/codegen/check.py:101`) iterates `sorted(lock.hash_by_path().items())` — a plain `str` sort over the whole relative path — while `_find_orphans` iterates `_iter_stampable_files`, a pre-order DFS doing `sorted(directory.iterdir())` per level, which is a path-*component* sort. For a tree holding `models/` beside `models.py`, the two halves of one report order paths by different rules (`models/foo.py` before `models.py` component-wise; the reverse string-wise). The reference is internally inconsistent, and the SDK cannot mirror both rules with one comparator.

Decision (ours to make, as the reference): **unify on the plain full-string sort**, the rule the locked-artifact loop already uses. Rationale: it matches `build_lock`'s "artifacts sorted by path" ordering in the lock file itself, it is the rule the SDK already implements for both of its loops (so upstream converges toward the mirror instead of forcing a component-wise comparator on every future client), and it is the cheaper spec sentence for S1 to eventually pin.

Implementation: keep `_iter_stampable_files` exactly as is (its DFS order is a *traversal* concern — deterministic pruning and filesystem walking — not a *report* concern); in `_find_orphans`, return `sorted(orphans, key=lambda drift: drift.path)` instead of the raw accumulation order. One line. Then state the now-real guarantee where the SDK had to reverse-engineer it: extend the `run_codegen_check` docstring with the ordering contract — locked-artifact drifts first in path order, then orphans in path order, at most one drift per locked path with `hand-edited` outranking `modified`. (That last property is already structural in `_check_present_artifact`; writing it down is S1 support, zero behavior change.)

Tests (`tests/unit/pipelex/codegen/test_check.py`): a tree with a locked `models.py` (modified) plus stamped orphans at `models/foo.py` and `a.py` → assert the full `[(path, category), ...]` sequence, pinning both the loop boundary and the string sort. Written red first: the current DFS order puts `models/foo.py` before `models.py` among orphans, so the fixture must include that adversarial pair or the test proves nothing (mutation-test it by reverting the sort).

---

## Phase 3 — Emit LF artifacts on every platform (U4) — **not started**

Confirmed: `save_text_to_path` (`pipelex/tools/misc/file_utils.py:80`) is `path.write_text(text, encoding="utf-8")`; with the default `newline=None`, Python translates `\n` to `os.linesep`, so on Windows every emitted artifact is CRLF on disk while `compute_content_hash` hashed the in-memory LF string. The *verdict* survives (reads come back through universal-newline translation, and `_write_if_changed` compares translated text on both sides), but `apply_stamp`'s own docstring claim — regeneration "writes byte-identical output" — holds only per-platform: a mixed Windows/Linux team sees the generated tree churn in git when nothing changed. Reasoned from documented `write_text` behavior, not reproduced (macOS `os.linesep` is `\n` and we have no Windows CI); the reasoning is airtight enough to act on.

Decision: fix it **globally in `save_text_to_path`** — `path.write_text(text, encoding="utf-8", newline="\n")` — rather than only at codegen's write site. Every caller (JSON via `json_utils`, the `build` command outputs, codegen inputs templates, codegen artifacts + lock) writes product text artifacts meant to be platform-independent; none wants `os.linesep`. One site, one behavior, no divergent write paths to remember. Update the function's docstring to state the LF guarantee.

Tests: in the file-utils tests, write text containing `\n` and assert `path.read_bytes()` contains no `b"\r"`. Trivially green on POSIX; it exists to pin intent and to go red immediately if Windows CI ever appears or the `newline` argument is dropped. Also verify no existing test asserts platform newlines (none expected).

**Checkpoint 2.** Phases 2–3 are small and mechanical; after them run the full `make agent-test` once before starting Phase 4, which is the only design-bearing phase.

---

## Phase 4 — Version the lock format (U3) — the one with real blast radius — **not started**

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

**Checkpoint 3.** The format change is landed but release-gated on the SDK reader. Record in this file, before releasing: the SDK follow-up issue/PR link and its release status.

---

## Phase 5 — Docs, changelog, and closure — **not started** (Phase 1's own doc + changelog edits are already in)

- `docs/under-the-hood/codegen-projections.md`: document the lock's `lock_version` and the evolution policy; state the drift-ordering guarantee and the header-strictness rule alongside the existing check description. Same-change discipline: each phase above should actually carry its own doc edit; this phase is the sweep that verifies nothing was missed.
- `CHANGELOG.md` under `## [Unreleased]`: one condensed entry covering the stamp-parser tightenings (uncommented header lines and non-standard JSON constants now report `hand-edited` instead of verifying), the unified drift ordering, LF-everywhere writes, and the `lock_version` field with its coordination note. Mark the lock change as the one consumers can observe.
- Reply on the two open PR #31 threads (`chatgpt-codex-connector`, `cubic-dev-ai`) once U1 lands here — the SDK notes keep them open pending exactly that.
- Full `make agent-check` + `make agent-test` (the stamp/check/lock fixtures and the CLI check tests all touch these paths).

---

## Cross-repo follow-ups (recorded here, **not** work in this repo)

- **`pipelex-sdk-js`** — after U1/U5 release: mirror both tightenings (their notes already carry the ready-to-apply TS patch and test for U1). After U3 lands here (before our release): version-aware lock reader + fixture refresh, per Phase 4 sequencing. After U2: nothing — we converged toward their comparator; their only residual ordering divergence is the practically unreachable UTF-16-vs-code-point case their item 2a documents, which stays deferred on their side.
- **`docs/specs/pipelex-codegen.md` + `conformance/` (workspace repo pair)** — S1: when the codegen sections de-skeleton, fold in the three load-bearing properties the SDK had to derive by reading `check.py` (at most one drift per locked path with `hand-edited` outranking `modified`; the orphan predicate is `has_stamp`, not the full parse; deterministic drift ordering — locked first, then orphans, both by path), plus the stamp-header text rules (line boundaries, strip set) as part of the hashed contract, plus U3's `lock_version` and evolution policy. Keep the `> Verified by:` ↔ `pytest.mark.spec` links in sync and run `make check-spec-links` in `conformance/`. This is release-gated on a published pipelex shipping codegen, per the existing `unverified` markers.
- **`pipelex-sdk-python`** — no codegen-check mirror exists today; if one is ever built, S1's spec work is what makes that safe. Nothing to do now.
