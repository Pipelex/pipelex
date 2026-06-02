# CSV Support — Feature Guide & PR-Review Reference

Branch `feature/Support-csv` (worktree `_csv`), targeting `dev`. This document describes the shipped CSV input/output feature so a PR-review agent can review the diff against intent without re-deriving the design. Design rationale lives in [`wip/csv-support/design.md`](wip/csv-support/design.md); deferred follow-ups in the other `wip/csv-support/*.md` files.

**Status: v1 complete — PR [#955](https://github.com/Pipelex/pipelex/pull/955) finalized, ready to merge.** All phases done; `make agent-check` green (pyright 0 / mypy 0 / ruff + plxt clean); full `make agent-test` green; docs + changelog landed. The PR went through 9 automated review rounds (greptile / cubic / codex) to convergence, then a pre-landing gstack `/review` (5 specialists + Codex adversarial) — which caught 3 issues the bot rounds missed (BOM/Excel input, a coercion-error data leak under STRICT, and `--save-csv` error framing) — and the bot re-review of those fixes also converged. All review threads resolved; CI green; mergeable. Deferred items are documented in `wip/csv-support/` (security-followups, phase2/phase3-4 followups).

---

## What this feature does

A CSV (or, behind a not-yet-built seam, an Excel `.xlsx`) file maps to a `ListContent[YourConcept]`: each row is one instance of a flat concept, each column is one of its fields. The MTHDS language surface is unchanged — there is **no new native content type or concept**. You describe the row concept exactly as any structured concept.

- **Input:** an `inputs.json` reference whose `content.url` ends in a tabular suffix, under a flat structured concept, is read into a typed `ListContent` (one file → one list; the concept names the *row* type). Reachable from the CLI, the runner API, and programmatic callers, because the hook lives in core, not the CLI.
- **Output:** `--save-csv <path>` on `pipelex run pipe|bundle|method` writes the main stuff to a literal, cwd-relative CSV path when that output is a flat list.

The headline acceptance test is a full round trip: `people.csv` → `PipeBatch` → `PipeSequence`(`PipeLLM` + `PipeCompose`) → `summaries.csv`, green in dry mode via both the in-process runner and a real CLI subprocess.

User-facing docs: [`docs/building-methods/pipes/csv-input-and-output.md`](docs/building-methods/pipes/csv-input-and-output.md) + `--save-csv` in [`docs/tools/cli/run.md`](docs/tools/cli/run.md); CHANGELOG `[Unreleased]`.

---

## Code map (what to review, where)

**Codec — `pipelex/tools/tabular/csv_codec.py`** (stdlib `csv`, one module per CQ2; no codec/binding split until `.xlsx` earns it):

- `read_rows` / `write_rows` — low-level primitives over an internal `_read_table` (explicit header + raw rows) / `_row_to_dict` (pads short/blank rows). `read_rows` has no suffix gate.
- `flat_field_names(row_model)` — the **single shared flatness classifier** used by BOTH read and write. `_is_flat_annotation` unwraps `Optional`/PEP-604 unions, ACCEPTS `str/int/float/bool/date/datetime` + **string-valued** `Literal`/`Enum` (only those round-trip through a CSV cell), REJECTS genuine multi-arm unions, non-string `Literal`/`Enum`, list/dict/nested-model/`Any`. Raises `CsvFlatnessError` naming field + concept; returns declared field order.
- `list_content_from_csv(path, row_model, *, delimiter, encoding)` — read path. Maps `""`→`None` before validate; extra/missing-required column → `CsvColumnError`; missing-optional column → field absent → pydantic default (`None`); per-row `ValidationError` → `CsvCoercionError` (1-based row + field).
- `csv_from_list_content(list_content, row_model, path, *, delimiter, encoding)` — write path. Headers from the **declared `row_model`** (so an empty list still writes a header-only file); serializes via `model_dump(mode="json")`; `_to_cell` maps `None`→`""` and bool→`true`/`false`.
- `is_tabular_path(path)` — suffix membership in `_TABULAR_SUFFIXES` (`.csv`, `.xlsx`).
- `assert_supported_table_suffix(path)` — the format seam: `.csv` ok; `.xlsx` → `CsvError` naming `pipelex[tabular]`; else generic `CsvError`.
- `delimiter`/`encoding` are function params (`,` / `utf-8`); no main-config touched (D1).

**Error taxonomy — `pipelex/tools/tabular/exceptions.py`:** `CsvError(ToolError)` base (`ErrorDomain.INPUT`) + `CsvReadError` / `CsvFlatnessError` / `CsvColumnError` / `CsvCoercionError`. All are `PipelexError`s, so the CLI prints them cleanly (no traceback) via `execute_run`'s `except PipelexError`. The codec catches every raw `OSError` / `UnicodeDecodeError` / `csv.Error` / pydantic `ValidationError` at its boundary and re-raises typed, carrying file path + 1-based row + concept + field — no raw third-party exception escapes into core/runner.

**Input hook — `pipelex/core/stuffs/stuff_factory.py`:** `_try_make_csv_list_stuff`, called from **Case 2.5** of `make_stuff_from_stuff_content_or_data` BEFORE the record `model_validate`. Detection: content has a `url` str key whose **path** (via `urlsplit(url).path`, so a query-string/fragment can't hide the suffix) is tabular AND the concept is **non-native** (`Concept.is_native_concept` False — native file concepts like Image/PDF keep their own url handling). Remote guard: `resolve_uri(url)` must be a `ResolvedLocalPath` AND `"://" not in resolved.path` (the `://` clause catches `s3://`/`gs://`, which `resolve_uri` currently mislabels as local) — else `CsvError` "local file paths only in v1". Row model = `concept.get_structure_class()` (wrapped so an unregistered structure class raises a typed `CsvError`, not a raw `ConceptValueError`). Returns `None` for ordinary record dicts (no url / non-tabular suffix / native) → falls through to normal Case 2.5.

**Output hook — `pipelex/cli/commands/run/_run_core.py`:** `_execute_run` / `execute_run` take keyword-only `save_csv: str | None = None`. The three run commands (`pipe_cmd.py` / `bundle_cmd.py` / `method_cmd.py`) declare `--save-csv` and forward it. The save block (after the working-memory save): rejects empty path, no-main-stuff, and non-`ListContent` main stuff with `typer.secho` + `Exit(1)`; creates the parent dir; writes via `csv_from_list_content(...)` at the literal cwd path (CQ1 — NOT under `--output-dir`); the codec's `CsvFlatnessError` covers non-flat rows.

---

## Test map

- **Unit — `tests/unit/pipelex/tools/tabular/test_csv_codec.py`:** read→dicts, custom delimiter, missing-file/bad-encoding → `CsvReadError`, duplicate/blank header → `CsvColumnError`, write+read round-trip, empty→header-only; flatness classifier (declared order + `Literal` accept; list/dict/nested/`Union`/`Any` reject); coercion incl. `date`→`datetime.date`; empty-cell→`None` (optional) / required→`CsvCoercionError`; **T3 coercion accept/reject tables** (bool `true/false/1/0/yes/no/on/off`, int, float, ISO date / reject `abc`, `1,5`, `31/12/2020`); strict columns (extra/missing-required error, missing-optional all-`None`); `None`↔`""` both sides.
- **Integration — `tests/integration/pipelex/csv/test_csv_roundtrip.py`** (split per T1): (a) input-codec WorkingMemory build → `ListContent[Person]` + `death_year is None` for Vint Cerf; (b) output-codec hand-built `ListContent[PersonSummary]` → header + rows; (c) full pipeline via `PipelexRunner(...).execute_pipeline("summarize_people", ...)` → 3 items, names/countries from real rows (dry-mode-safe).
- **Integration — `tests/integration/pipelex/csv/test_csv_input_detection.py`:** A3/CT1 pins (`.csv`-url column reads as a table; non-`.csv` url stays a single record), remote-url rejection (`http(s)`/`s3://`/`gs://`, incl. query-string/fragment), eager-IO refresh-after-mutation.
- **E2E — `tests/e2e/pipelex/cli/test_csv_run.py`** (`@pytest.mark.gha_disabled`, subprocess): `run pipe --save-csv --dry-run` → exit 0 + file at literal cwd path + header + one row per person; **T2 cheap wiring checks** that all three run commands declare `save_csv` and forward it; clean missing-`.csv` error (non-zero exit, no traceback, names the file).
- **Fixtures — `tests/integration/pipelex/csv/`:** the runnable demo lives in `csv_demo/` (`csv_demo.mthds` with flat `Person`/`PersonSummary`, `people.csv`, `inputs.json`); the url-field detection fixture is split out into `url_field_concept/` (`url_field_concept.mthds` with the pipe-less `Link` concept that declares its own `url` field, plus `links.csv`). Inline `[concept.X.structure]` blocks auto-generate registered `StructuredContent` subclasses (no `test_structures.py`).

---

## The contract (input/output semantics — do not silently change)

- **Flat concepts only.** Scalar fields: `text`→`str`, `integer`→`int`, `number`→`float`, `boolean`→`bool`, `date`→`datetime.datetime` (the MTHDS `date` type generates `datetime.datetime`; the codec also accepts a hand-built `datetime.date`). Optionals allowed; string-valued `Literal`/`StrEnum` choices allowed. Nested/list/dict/`Union`/concept-typed/`Any`/non-string `Literal`/`Enum` → `CsvFlatnessError` naming the field. No silent flatten, no JSON-in-cell, no dropped cells.
- **Input headers:** required; must match field names exactly (no implicit remap). **Extra column → error; missing required column → error; missing *nullable* column → that field is `None` for all rows; missing non-nullable-but-defaulted column → that field keeps its own default** (CT2 lenient). Empty cell → `None` before pydantic (field must be optional).
- **Coercion:** through pydantic lax validation; the accept/reject set is pinned by T3 (see test map). Don't hand-roll coercion.
- **Output:** `--save-csv` triggers explicitly (no auto-emit). Header from the declared row model (empty list → header-only). `None`→`""` (never `"None"`); bool→lowercase. Literal cwd-relative path, parent dir created.
- **CSV is an I/O codec, not a prompt-render format** — it must NOT join the `rendered_plain/markdown/html/json` `TextFormat` router.

---

## Locked design decisions (do not re-litigate — see design doc §6 + plan-eng-review)

- **Typed lists only**; full round-trip in v1; **no new native `Table` concept**.
- **stdlib `csv` in core; `.xlsx` deferred** behind `pipelex[tabular]`, reached through the thin suffix seam (`assert_supported_table_suffix`). Don't add openpyxl or build xlsx now.
- **Input hook in CORE** (`stuff_factory` Case 2.5), not the CLI, so it's reachable from the runner API. Eager local-disk read accepted there; codec stays a pure module.
- **v1 = local filesystem paths only.** Remote tabular `url` (`http(s)`/`s3`/`gs`/signed) actively rejected, never opened.
- **No main-config in v1 (D1).** Delimiter/encoding are codec params, never guessed; no TOML/CLI surface yet. `make tb` not needed.
- **`--save-csv` is literal/cwd-relative** (CQ1), keyword-only in `_execute_run`. No `--csv-path`.
- **A3/CT1:** keep `url` + tabular-suffix detection; accept the narrow residual (a flat concept with a `url` field given a `.csv` value reads as a table) — pinned by tests, documented as a limitation.

---

## Documented limitations (written up in the guide page)

- **Local paths only** — remote tabular URLs rejected.
- **`.xlsx` recognized but not implemented** — routed to the `pipelex[tabular]` message; backend not built.
- **Empty string indistinguishable from `None`** — empty cell ⇄ `None` both directions.
- **Single-key `{"url": "x.csv"}` residual (A3/CT1)** — a bare `{"url": "x.csv"}` reference under a flat concept reads as a table, not a single record. Detection is gated to the exact single-key wrapper, so a record with sibling keys (`{"label": "Home", "url": "x.csv"}`) stays a record — its fields are never dropped (was a silent-drop; fixed in PR #955 review round 1).
- **No formula-injection escaping (CT3)** — cells written verbatim for data fidelity; opt-in escape deferred.

---

## Deferred follow-ups (NOT in v1 — captured, do not expand scope into them)

Out of scope for v1 (design §10): `.xlsx` via openpyxl; streaming/out-of-core; Google Sheets/Parquet; delimiter/dialect auto-detection; a native `Table` concept; remote `.csv` URLs.

Captured review follow-ups (decisions deferred, not bugs to fix in this PR):

- [`wip/csv-support/phase3-4-review-followups.md`](wip/csv-support/phase3-4-review-followups.md): (A) `resolve_uri` doesn't classify `s3://`/`gs://` — a cross-caller `tools/uri` gap the `"://"` heuristic papers over; fix is its own change. The same root cause is the `?`/`#`-in-local-filename mis-strip (niche, graceful). (B) factory-altitude eager I/O + cwd-relative paths for non-CLI callers — design decision. **(C) RESOLVED in PR #955 review round 1** — detection tightened to the single-key `{"url": ...}` wrapper, so a multi-field record no longer silently drops siblings. Plus minor cleanups (output-side error framing, suffix-vocabulary drift, header-only-vs-empty-list parity, redundant casts).
- [`wip/csv-support/phase2-review-followups.md`](wip/csv-support/phase2-review-followups.md): non-string `Literal`/`Enum` flatness — **RESOLVED in PR #955 review round 3** (Option A: the gate now accepts only string-valued `Literal`/`Enum`, rejecting `Literal[int]`/`IntEnum` that serialize but don't coerce back).

Also addressed in PR #955 review rounds (not deferred): error row numbers now point at the physical CSV line (incl. across multiline quoted cells, via `csv.reader.line_num`); CSV detection gated to the single-key `{"url": ...}` wrapper; `--save-csv` validates before `mkdir` and frames its own failures as "Failed to --save-csv" (not a pipeline failure); newline + quote delimiters rejected with a typed `CsvError`; strict CSV parsing (malformed quotes → `CsvReadError`); `write_rows` wraps `UnicodeEncodeError`; an omitted *nullable* column is `None` for all rows regardless of the row-model default while a non-nullable defaulted column keeps its own default (CT2); `CsvError` opts into `_authors_caller_facing_message` so STRICT disclosure keeps its caller-facing message, and that message sanitizes the offending url (strips query/fragment/userinfo, guards malformed port + bad-IPv6-bracket) so a signed/token-bearing url never leaks; the CLI `s3://` remote-rejection bypass (`is_relative_local_path`) is fixed; **reads default to `utf-8-sig` so Excel-exported BOM CSVs parse**; and the coercion error no longer echoes the raw cell value (no data leak under STRICT).

Deferred (documented): local paths containing URL-reserved `?`/`#` (cubic agreed; entangled with `resolve_uri` scheme-classification, item A); nullable-but-required columns stay mandatory (phase2-followups #2). Security review follow-ups (gstack `/review`) in [`wip/csv-support/security-followups.md`](wip/csv-support/security-followups.md): platform-wide untrusted-`url` local-file-read confinement (pre-existing input model, not CSV-specific), CSV formula-injection (locked CT3 document-only decision), embedded-NUL path error-hygiene (niche).

Deferred feature TODOs: user-facing delimiter/encoding config (D1); opt-in CSV/Excel formula-escape flag (CT3); `SaveOptions` struct for `_execute_run`'s param clump; multiplicity-gated CSV detection (CT1 option C, only if the residual proves real).
