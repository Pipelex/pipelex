# CSV Support — Phase 1 code-review findings

Status: **open — to triage/fix before (or alongside) Phase 2.** Produced by an extra-high-recall `/code-review` of the Phase 1 work on branch `feature/Support-csv` (worktree `_csv`). Scope reviewed: the new files only (codec skeleton + error taxonomy + fixtures + tests) — see `TODOS.md` "Phase-1 deliverables". Nothing here is committed yet.

This doc is the cold-start anchor for verifying and resolving the findings in a fresh session. Each item carries a file:line anchor, a verification recipe, and the recommended fix. Line numbers are approximate anchors — grep the quoted token if they have drifted.

## Why this matters

Phase 1 is outside-in TDD: the tests are meant to be **RED now, GREEN in Phases 2–4**. A test that can *never* go green (RED for the wrong reason) silently breaks that premise — the Phase-2/4 author will "fix the implementation" forever and the test never passes. Findings R1–R3 are exactly that class and should be fixed before relying on the RED state. R4–R7 are contract/doc inconsistencies inside the locked skeleton that will mislead the implementer. The rest are test-quality / robustness / altitude.

## How the review was run (reproduce)

5 parallel finder agents (line-by-line, contract-feasibility, taxonomy/language, fixtures, altitude/reuse) + a sweep, then load-bearing claims verified empirically against the repo's interpreter (`.venv/bin/python` → Python 3.13.9). The two highest-value empirical checks:

```bash
# (a) pydantic coercion assumptions in the accept/reject tables — ALL HOLD
.venv/bin/python - <<'PY'
from datetime import date
from pydantic import BaseModel, ValidationError
class B(BaseModel): value: bool
class D(BaseModel): value: date
def ck(m,v):
    try: return m.model_validate({"value":v}).value
    except ValidationError: return "REJECT"
print([ (s, ck(B,s)) for s in ["true","false","1","0","yes","no","on","off"] ])  # all accept
print(ck(D,"1815-12-10"), ck(D,"31/12/2020"))   # date(1815,12,10), REJECT
PY

# (b) NUL byte does NOT raise csv.Error on Python 3.13 (basis for R2)
.venv/bin/python - <<'PY'
import csv, io
print(list(csv.reader(io.StringIO("name\nval\x00ue\n"))))   # -> [['name'], ['val\x00ue']] (NO raise)
PY

# (c) csv.writer quotes a lone empty field as "" (basis for R3)
.venv/bin/python - <<'PY'
import csv, io
buf=io.StringIO(); w=csv.writer(buf); w.writerow(["text"]); w.writerow([""]); w.writerow([""])
print(repr(buf.getvalue()))   # -> 'text\r\n""\r\n""\r\n'  (data lines are '""', not '')
PY
```

To re-confirm the tests are RED for the *intended* reason after any fix:

```bash
.venv/bin/pytest -p no:cacheprovider --disable-inference -o log_level=WARNING --tb=short -q \
  -m "dry_runnable or not (inference or llm or img_gen or extract or search)" \
  tests/unit/pipelex/tools/tabular/test_csv_codec.py \
  tests/integration/pipelex/csv/test_csv_roundtrip.py \
  tests/e2e/pipelex/cli/test_csv_run.py
# gha_disabled subprocess arm:
.venv/bin/pytest -p no:cacheprovider -o log_level=WARNING --tb=short -q -m gha_disabled \
  tests/e2e/pipelex/cli/test_csv_run.py
```

---

## Findings (ranked)

### Tier 1 — RED-for-wrong-reason: these tests can never go green as written

#### R1 — e2e `len(lines) == 4` counts physical lines, but the dry-mode summary cell is multi-line (CONFIRMED)

- **Where:** `tests/e2e/pipelex/cli/test_csv_run.py:101` (`test_save_csv_writes_file_at_literal_path`), same `splitlines()` approach feeds `:100`.
- **Problem:** In dry mode `PersonSummary.summary` is filled from the `describe_person` PipeLLM, whose dry output is `ContentGeneratorDry.make_llm_text` → `"DRY RUN: make_llm_text • ... • prompt=<LLMPrompt.desc()>"`, a long **multi-line** string. The codec correctly RFC-quotes that cell, so one logical CSV row spans several physical lines. `out_csv.read_text().splitlines()` then returns far more than 4 → the assertion false-fails on a correct implementation.
- **Verify:** run the dry pipeline and look at the output (the Phase-1 sanity run already showed the multi-line `DRY RUN: ...` summary), or once `--save-csv` exists, inspect the written file.
- **Fix:** parse the written file with `csv.reader`/`DictReader` and assert the **record** count (`== 3`) and the header, not `splitlines()` length.

#### R2 — NUL-byte test premise is false on Python 3.13 (CONFIRMED)

- **Where:** `tests/unit/pipelex/tools/tabular/test_csv_codec.py:141` (`test_read_rows_nul_byte_wrapped_as_csv_read_error`).
- **Problem:** The test assumes a NUL byte makes the stdlib csv reader raise `csv.Error`. On the repo's Python 3.13.9 `csv.reader`/`DictReader` silently accept NUL (see verify (b) above). A codec built on `read_text` + `csv.reader` therefore raises nothing, so `pytest.raises(CsvReadError)` is un-green-able without an artificial NUL scan the codec is not contracted to do.
- **Fix:** drop this test. The "wrap raw `OSError`/`UnicodeDecodeError`/`csv.Error`" contract is already covered by `test_read_rows_missing_file_raises` and `test_read_rows_bad_encoding_raises` (both reliable). There is no simple, portable input that reliably forces a `csv.Error`; do not invent one. If a `csv.Error` wrap test is still wanted, trigger it via `csv.field_size_limit` overflow, but that is brittle — prefer dropping.

#### R3 — single-column empty-cell write assertion contradicts csv.writer (CONFIRMED)

- **Where:** `tests/unit/pipelex/tools/tabular/test_csv_codec.py:343` (`test_none_and_empty_string_both_write_blank_and_read_back_none`), the `assert data_lines == ["", ""]`.
- **Problem:** For a **single-column** row whose only cell is empty, `csv.writer.writerow([""])` emits a quoted `""` (to disambiguate from a blank line), not an empty string — see verify (c). So the data lines are `['""', '""']`, not `["", ""]` → false-fail for any csv-module-based codec. (Conversely, if the codec wrote a bare empty line instead, `csv.reader` would treat it as a zero-field row and the read-back half of the test would break.) The lone-empty single-column cell is the one genuinely ambiguous CSV case.
- **Fix:** keep the *intent* (both `None` and `""` round-trip to `None`, and serialize to a blank cell) but assert it by **re-parsing** — read the file back through the codec and assert `[item.text for item in reloaded.items] == [None, None]`. Drop the brittle physical-line equality, or move it to a multi-column model where the empty cell is unambiguous.

### Tier 2 — skeleton contract / docstring inconsistencies (will mislead Phase 2)

#### R4 — `read_rows` docstring says CsvReadError for bad headers, tests expect CsvColumnError (CONFIRMED)

- **Where:** docstring `pipelex/tools/tabular/csv_codec.py:40` ("...or a duplicate/blank header cell") vs tests `test_duplicate_header_raises` / `test_blank_header_raises` (expect `CsvColumnError`).
- **Problem:** Direct contradiction inside the locked skeleton — both cannot be satisfied.
- **Fix:** pick `CsvColumnError` (duplicate/blank header is a column-shape problem) and edit the `read_rows` docstring so it no longer claims `CsvReadError` for headers. Note the layering decision while you're there: if `list_content_from_csv` reads through `read_rows`, header validation lives in one place; if it reads raw via `DictReader`, duplicate headers are silently merged (last-wins) and never raise — make sure both entry points agree.

#### R5 — `.xlsx` seam should raise `MissingDependencyError`, not `CsvError` (CONFIRMED, altitude)

- **Where:** seam `pipelex/tools/tabular/csv_codec.py:72-79`; test `tests/unit/pipelex/tools/tabular/test_csv_codec.py:361-363` (`pytest.raises(CsvError)` + `"pipelex[tabular]" in message`).
- **Problem:** The repo already has `MissingDependencyError(lib_name, lib_extra_name, msg)` in `pipelex/system/exceptions.py:23` (used by `tools/storage/{s3,gcp}_storage_provider.py`, `tracing/dynamodb_event_log.py`) — the canonical class for a missing optional extra; it renders the exact `uv pip install "pipelex[tabular]"` instruction. A missing-extra is operator-fixable (install/config), not caller INPUT. The current test pins `CsvError`, which would force the wrong class (and the wrong error domain / HTTP framing) in Phase 2.
- **Fix:** decide the seam raises `MissingDependencyError` for the `.xlsx`/missing-`tabular` case and change the test to `pytest.raises(MissingDependencyError)`. Keep `CsvError`/generic for a truly unsupported suffix (e.g. `.parquet`) — though that could also be a plain unsupported-format error. Confirm `MissingDependencyError`'s constructor signature before wiring.

#### R6 — `write_rows` docstring uses the READ error class for a WRITE failure (CONFIRMED)

- **Where:** docstring `pipelex/tools/tabular/csv_codec.py:56` ("Raises `CsvReadError` if the file cannot be written").
- **Problem:** Wrong I/O direction; there is no `CsvWriteError` in the taxonomy. A caller's `except CsvReadError` for input would wrongly trap an output failure, and the generated `csv-read-error` docs page would misdescribe it.
- **Fix:** simplest — change the docstring to raise the base `CsvError` on write failure. If write failures deserve their own type, add `CsvWriteError(CsvError)` to `exceptions.py` and use it (also update the docstring).

#### R7 — Csv* subclass titles render "Csv read", not "CSV read" (CONFIRMED, consumer-facing)

- **Where:** `pipelex/tools/tabular/exceptions.py` — only the base `CsvError` sets `_declared_title = "CSV error"` (`:14`); subclasses (`:17,:26,:36,:45`) auto-derive a case-folded title.
- **Problem:** `title()` reads `cls.__dict__` (no inheritance), so each subclass auto-humanizes its name → `CsvReadError.title() == "Csv read"` (verified live), surfacing the awkward lowercased acronym on the CLI JSON, RFC-7807 `title`, and generated `docs/errors/*.md`.
- **Fix:** add a `_declared_title` to each subclass body (e.g. `"CSV read error"`, `"CSV flatness error"`, `"CSV column error"`, `"CSV coercion error"`). Cheap. (Do not hand-edit `docs/errors/*.md` — those are generated; fixing the source title is enough.)

### Tier 3 — test-quality / robustness / altitude (lower)

#### R8 — `"2" in message` is too loose and pins an unstated row-number convention (PLAUSIBLE)

- **Where:** `tests/unit/pipelex/tools/tabular/test_csv_codec.py:269` (`test_coercion_failure_names_row_and_field`).
- **Problem:** Substring `"2"` matches almost any message (false pass when the row index is absent), and it bakes in a 1-based **data-row** convention — a reasonable 0-based or header-inclusive ("row 3") impl would false-fail.
- **Fix:** assert a structured anchor (e.g. `"row 2"` and the field name `"value"` distinctly), and pin the row-numbering convention in the A2 error-message contract.

#### R9 — exact-line CSV assertions pin QUOTE_MINIMAL (PLAUSIBLE)

- **Where:** `tests/integration/pipelex/csv/test_csv_roundtrip.py:91-92`; the write-format assertions in `test_csv_from_list_content_writes_declared_header_and_rows` (`lines[1].startswith(...)`, `lines[2].endswith(",")`).
- **Problem:** Exact raw-line matching assumes `csv.QUOTE_MINIMAL`. A codec choosing `QUOTE_ALL`/`QUOTE_NONNUMERIC` (valid, arguably safer) emits `"Ada Lovelace",...` and false-fails despite a correct round-trip.
- **Fix:** either deliberately pin QUOTE_MINIMAL as the codec contract (and say so), or assert by re-parsing the written CSV into records and comparing values.

#### R10 — e2e subprocess tests inherit ambient env (non-hermetic) + duplicate agent_cli scaffolding (PLAUSIBLE, altitude)

- **Where:** `tests/e2e/pipelex/cli/test_csv_run.py:89,126` (`env=os.environ.copy()`), `_stage_bundle:39`, and the duplicated `subprocess.run([...])` blocks.
- **Problem:** Pass/fail depends on the runner's `~/.pipelex` config + network + API-key env (green locally ≠ green on a clean box), and it leaks the developer's real credentials into the subprocess. The repo already has a hermetic harness — `tests/e2e/agent_cli/conftest.py` (`hermetic_home`, `offline_subprocess_env`, `set_gateway_enabled`, `write_active_routing_profile`, `_copy_kit_configs_into`, `write_pipelex_service_config`) — that this test reuses none of. It is also the only subprocess-style `pipelex run` e2e (the init_cmd suite runs in-process).
- **Fix (Phase 4):** add `tests/e2e/pipelex/cli/conftest.py` that builds a hermetic `HOME` + sealed env (gateway disabled / BYOK `all_anthropic`, dummy creds, unreachable remote-config URL) by reusing the agent_cli helpers, and a shared bundle-staging + `pipelex` subprocess fixture. Then point this test at it. (Recorded as a known trade-off in `TODOS.md` Session-state notes.)

#### R11 — `{country} <= EXPECTED_COUNTRIES` subset can't catch a dropped country (PLAUSIBLE, low)

- **Where:** `tests/integration/pipelex/csv/test_csv_roundtrip.py:114`.
- **Problem:** A subset check passes even if a country is lost (only an *unexpected* country fails it). The names `==` check on the line above already pins cardinality + identity, so this is a secondary weakness, but tightening country to an exact multiset would catch a partial-carry regression.
- **Fix (optional):** assert `sorted(row["country"] for row in rows) == ["United Kingdom", "United States", "United States"]` (or a Counter), matching the real CSV.

#### R12 — Csv* INPUT errors don't set `_authors_caller_facing_message` → STRICT redacts the promised detail (NOTE, low / Phase-2 decision)

- **Where:** `pipelex/tools/tabular/exceptions.py` (none of the subclasses set the flag).
- **Problem:** The docstrings promise the message carries caller-fixable detail (offending field, 1-based row/col, concept), but without `_authors_caller_facing_message = True` those messages are replaced by the generic placeholder on STRICT external surfaces. The safe direction holds (`CsvReadError`'s server-resolved file path stays redacted).
- **Fix (Phase 2 decision):** opt the input-copy errors (`CsvColumnError`, `CsvCoercionError`, `CsvFlatnessError`) into `_authors_caller_facing_message = True`; keep it OFF on `CsvReadError` so the resolved path stays redacted. Pair with the security-perimeter-test habit if/when these surfaces are exercised.

---

## Refuted finder claims (do NOT re-chase)

- "`test_supported_suffix_accepts_csv` does `assert assert_supported_table_suffix(...)` → asserts on None." **False** — line `tests/unit/pipelex/tools/tabular/test_csv_codec.py:359` is a bare call `assert_supported_table_suffix(tmp_path / "data.csv")` (no `assert`), which correctly just checks "does not raise".
- "`DictReader` skips the empty rows, so the single-column round-trip reads back 0 items." **False** — `csv.writer` writes a lone empty field as quoted `""`, so `DictReader` reads it back as a row (see verify (c)); the real issue is the *write-side* assertion in R3, not row-skipping.
- "pydantic won't accept `on`/`off`/`yes`/`no` for bool, or rejects ISO dates." **False** — all accept/reject table assumptions hold on the current pydantic (verify (a)). One caveat worth a note (not a finding): this relies on pydantic **lax** (non-strict) validation; if a row model is ever `ConfigDict(strict=True)` the string→bool/date coercion breaks. `StructuredContent` is not strict today.

## Recommended action

Fix R1–R7 now (they are cheap and keep the RED state honest), then re-run the RED-verification commands above and `make agent-check`. R8–R11 are quality hardening that can ride along or wait for the phase that implements the relevant surface. R12 is a Phase-2 taxonomy decision. After fixes, update `TODOS.md` Session state if any test file/contract anchor moved.
