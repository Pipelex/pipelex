# CSV Support — Implementation Plan (v1)

Branch `feature/Support-csv` (worktree `_csv`). Design: [`wip/csv-support/design.md`](wip/csv-support/design.md). This file is the single source of truth for execution + cold-start.

**Approach: outside-in TDD.** Write the acceptance tests (integration + e2e) and codec unit tests first (red), then implement until green. Run `make agent-check` after every code change; `make agent-test` at each checkpoint. (No `make tb` — D1 cut config from v1.)

---

## ⏱️ Session state (UPDATE AT EVERY CHECKPOINT — this is the cold-start anchor)

- **Current phase:** Phase 3 (input integration) + Phase 4 (`--save-csv` output) BOTH COMPLETE → **CHECKPOINT 3 cleared (2026-06-02) — headline milestone.** The full round-trip works end to end (CSV in → `PipeBatch`→`PipeSequence`(`PipeLLM`+`PipeCompose`) → CSV out) in dry mode via BOTH the in-process runner AND the real CLI subprocess. `make agent-check` green repo-wide (pyright 0 / mypy 0 / ruff+plxt clean); **full `make agent-test` GREEN** (no regressions).
- **Last checkpoint cleared:** CHECKPOINT 3 (end-to-end round-trip, in-process + CLI-subprocess, full suite green).
- **Git state (2026-06-02):** Phase-1 in `acde0561`+`7ef68ac9`; Phase-2 + review fixes in `eec53eea`. **Phase 3+4 changes are UNCOMMITTED in the `_csv` worktree** — files: `pipelex/tools/tabular/csv_codec.py` (+`is_tabular_path`), `pipelex/core/stuffs/stuff_factory.py` (Case 2.5 hook + `_try_make_csv_list_stuff`), `pipelex/cli/commands/run/{_run_core.py,pipe_cmd.py,bundle_cmd.py,method_cmd.py}` (`--save-csv`), `tests/integration/pipelex/csv/csv_demo/csv_demo.mthds` (+`Link` concept), `tests/integration/pipelex/csv/csv_demo/links.csv` (new), `tests/integration/pipelex/csv/test_csv_input_detection.py` (new). **Next session: commit these before starting Phase 5.** Nothing pushed.
- **Green now:** codec unit suite; integration `test_csv_roundtrip.py` (a/b/c — incl. the full dry-mode pipeline); `test_csv_input_detection.py` (remote-url rejection incl. `s3://`/`gs://`, the A3/CT1 url-field residual pins, eager-IO refresh-after-mutation); e2e `test_csv_run.py` wiring + BOTH `gha_disabled` subprocess tests (literal-path round-trip + clean missing-file error). Full `make agent-test` green.
- **Next concrete action:** **Phase 5 — docs, changelog, polish** (final phase, ends at CHECKPOINT 4). (1) `CHANGELOG.md` under `## [Unreleased]` (no versioned header — release skill does that). (2) Docs guide page "CSV input & output" (Material for MkDocs: blank line before lists, one-paragraph-per-line) covering the inputs.json `.csv` convention, `--save-csv` literal path, the flat-concept requirement (incl. `date`), the round-trip example, the T3 coercion accept/reject rules, AND the documented limitations (below). (3) optional live-mode arm on the integration test. (4) final `make agent-check` + `make agent-test`. **Commit Phase 3+4 first.**
- **Open questions blocking:** none.
- **Phase 3+4 implementation (FINAL — for Phase 5 docs / any follow-up):**
  - **Input hook:** `StuffFactory._try_make_csv_list_stuff` (`stuff_factory.py`), called from **Case 2.5** BEFORE the record `model_validate`. Detection = content has a `url` str key whose suffix is tabular (`is_tabular_path`: `.csv`/`.xlsx`) AND the concept is **non-native** (`Concept.is_native_concept` False — native file concepts like Image/PDF keep their own url handling). Remote guard: `resolve_uri(url)` must be a `ResolvedLocalPath` **and** `"://" not in resolved.path` (catches `s3://`/`gs://`, which `resolve_uri` mislabels as local) — else `CsvError` "local file paths only in v1". Row model = `concept.get_structure_class()`; calls `list_content_from_csv`. Returns `None` for ordinary record dicts (no url / non-tabular suffix / native) → falls through to normal Case 2.5.
  - **Output:** `_execute_run`/`execute_run` take **keyword-only** `save_csv: str | None = None`; the 3 run commands (`pipe_cmd`/`bundle_cmd`/`method_cmd`) declare `--save-csv` and forward it. Save block (after the working-memory save) writes `csv_from_list_content(main_stuff.content, row_model=main_stuff.concept.get_structure_class(), Path(save_csv))` at the **literal cwd path** (CQ1, NOT under `--output-dir`); rejects no-main-stuff / non-`ListContent` main stuff with `typer.secho`+`Exit(1)`; the codec's `CsvFlatnessError` covers non-flat. `is_tabular_path(path) -> bool` added to `csv_codec.py` (`.csv`/`.xlsx`).
  - **Documented limitations to write up in Phase 5:** empty-string text → `None` (indistinguishable); **A3/CT1 url-field residual** — a flat concept that has a `url` field, given `{"url": "x.csv"}`, is read as a CSV table not a single record (pinned by `test_csv_with_url_column_reads` + `test_non_csv_url_stays_record`); CSV/Excel formula-injection (CT3, document-only); local-paths-only (remote `.csv` rejected, `s3://`/`gs://` too); the T3 coercion accept/reject rules.
  - **Codec API (UNCHANGED, signatures FINAL):** `pipelex/tools/tabular/csv_codec.py` (stdlib `csv`) — `read_rows`/`write_rows` primitives, `flat_field_names` (shared flatness classifier → `CsvFlatnessError`, declared order; accepts `str/int/float/bool/date/datetime/Literal/Enum` + optionals), `assert_supported_table_suffix` (`.csv` ok / `.xlsx` → `pipelex[tabular]` / else generic `CsvError`), `is_tabular_path` (NEW: `.csv`/`.xlsx`), `list_content_from_csv` (empty cell→`None` before validate; extra/missing-required col → `CsvColumnError`; per-row `ValidationError` → `CsvCoercionError`), `csv_from_list_content` (headers from declared `row_model`, empty list → header-only; `None`→`""`, bool→`true/false`).
  - **Error taxonomy (LOCKED):** `pipelex/tools/tabular/exceptions.py` → `CsvError(ToolError)` (`ErrorDomain.INPUT`) + `CsvReadError`/`CsvFlatnessError`/`CsvColumnError`/`CsvCoercionError`. All are `PipelexError`s → the CLI prints them cleanly (no traceback) via `execute_run`'s `except PipelexError` (verified by `test_missing_csv_input_fails_cleanly`).
  - **Fixtures:** `tests/integration/pipelex/csv/csv_demo/{csv_demo.mthds, people.csv, inputs.json, links.csv}`. `csv_demo.mthds` now also has a flat `[concept.Link]` (fields `label`, `url`) used by the detection tests. Inline `[concept.X.structure]` blocks auto-generate registered `StructuredContent` subclasses (fetch via `concept.get_structure_class()`).
  - **Phase 3+4 code review (xhigh, 2026-06-02) — confirmed fixes APPLIED post-CP3:** **#1** query-string/fragment URLs (e.g. S3 presigned `…csv?X-Amz-…`) no longer bypass the remote-rejection — detection now matches the suffix on `urlsplit(url).path`, and `test_remote_csv_url_rejected` gained query-string/fragment params. **#2** `concept.get_structure_class()` is wrapped so an unregistered structure class raises a typed `CsvError`, not a raw `ConceptValueError` (which is a `ValueError`, NOT a `PipelexError`). **#7** `--save-csv ""` now errors instead of silently no-opping (`is not None` + empty-string guard). **#8** the `--save-csv` parent dir is created before writing (no late failure on `reports/2026/out.csv`). All green: `make agent-check` (pyright 0 / mypy 0), CSV suite 70 passed, core+cli 1498 passed.
  - **Deferred from that review → [`wip/csv-support/phase3-4-review-followups.md`](wip/csv-support/phase3-4-review-followups.md):** (A) `resolve_uri` doesn't classify `s3://`/`gs://` (the `"://" in path` workaround papers over a cross-caller gap); (B) factory-altitude eager I/O + cwd-relative paths for non-CLI callers; (C) the `url`-field residual extends to multi-field records (Phase-5 doc / optional single-key tightening); plus minor cleanups.
  - **Still-open deferred review items (unchanged):** R10 hermetic e2e conftest (the subprocess tests currently inherit ambient env and pass); R11 exact-multiset country check; R12 `_authors_caller_facing_message` opt-in for the caller-fixable input errors; the Phase-2 cleanup items #11/#12/#13; and the #1 non-string-`Literal` flatness gap (`wip/csv-support/phase2-review-followups.md`).

---

## 🛑 Checkpoint protocol (do this at every CHECKPOINT)

A checkpoint is a **hard stop**. Before ending the turn/session:

1. Run `make agent-check` (lint/types) and the relevant tests; capture pass/fail honestly.
2. Tick the checkboxes that are truly done; leave partials unticked with a one-line note.
3. Rewrite the **Session state** block above: current phase, what's green, the exact next action, any new decisions/open questions, and any file paths/signatures discovered that the next session would otherwise have to re-find.
4. If a phase produced design-level context too big for this file, drop it in `wip/csv-support/` and link it here.
5. State clearly in the final message that a checkpoint was reached and what the next session should do.

Checkpoints exist because context grows and these are clean handoff boundaries. Do not blow past one to "just finish the next phase too."

---

## 🔒 Locked design decisions (do not re-litigate — see design doc §6)

- **Typed lists only.** A CSV ⇄ `ListContent[Concept]`. Rows = instances of a declared **row concept**; columns = its fields. **No new native content type / concept**; MTHDS language surface unchanged.
- **Full round-trip** in v1 (CSV in → process → CSV out).
- **stdlib `csv` in core; `.xlsx` deferred** behind an optional extra `pipelex[tabular]`, reached through a thin format seam (do NOT add the openpyxl dep or build xlsx now).
- **Reject non-flat.** A row concept used with CSV must have **scalar fields only** (`text/integer/number/boolean/date` → `str/int/float/bool/datetime.date`, optionals allowed; `Literal`/`choices`-constrained scalars allowed). Any nested/list/dict/`Union`/concept-typed/`Any` field → clear error naming the offending field, telling the author to project to a flat concept first. No silent flatten, no JSON-in-cell, no dropped cells. (`date` was missing from the python-target list — it IS supported; see CT-baked decisions.)
- **CSV is an I/O codec, not a prompt-render format** — it must NOT join the `rendered_plain/markdown/html/json` `TextFormat` router.
- **Input semantics:** header row required; column headers must match field names (no implicit remap); empty cell → `None` (field must be optional); **extra column → error; missing _required_ column → error; missing _optional_ column → that field is `None` for all rows (CT2 lenient — supersedes the old "missing → error" wording)**. Coerce cell strings via pydantic lax validation.
- **Finer defaults:** explicit `--save-csv <path>` to trigger output (no surprise auto-emit); UTF-8 + comma dialect; **delimiter & encoding configurable** — in v1 via codec params only, never guessed (no user-facing config surface yet, per D1).

---

## ✅ Plan-eng-review decisions (locked 2026-06-01 — these SUPERSEDE any conflicting phase text below)

Twelve decisions from `/plan-eng-review` + a Codex outside-voice pass. Where a phase checkbox below still reflects the old plan, this section wins.

**Scope / config**

- **D1 — No main-config in v1.** Do NOT touch `configs.py` / `pipelex.toml` / `.pipelex/pipelex.toml` for CSV. The codec takes `delimiter`/`encoding` as function params with defaults (`,` / `utf-8`). The user-facing config surface (toml default or `--delimiter`/`--encoding` flags) is a **deferred follow-up TODO** (see Out-of-scope). Drops `make tb` from v1.

**Architecture**

- **A1 — Input hook in CORE.** Intercept in `stuff_factory.make_stuff_from_stuff_content_or_data` Case 2.5 (`stuff_factory.py:399-413`), so CSV input is reachable from the runner API + programmatic callers, not just the CLI. Eager file read is accepted there; keep the codec a **pure module** the factory merely calls. **v1 = LOCAL filesystem paths only.** A remote `url` (`http://`, `s3://`, signed) under a flat concept with a `.csv` suffix must be **actively rejected with a clear error**, never opened as a local path.
- **A2 — Typed error taxonomy + wrap-all.** Define a small `CsvError` base (PipelexError subclass) with concrete types: file/read error, flatness rejection, column mismatch, cell-coercion error. The codec **catches every raw `OSError` / `csv.Error` / pydantic `ValidationError`** at its boundary and re-raises as the typed error carrying **file path + 1-based row/col + concept + field**. No raw exception escapes into core/runner.
- **A3 / CT1 — Keep `url` + `.csv`-suffix detection.** Trigger CSV when concept is flat `StructuredContent` AND `url` ends `.csv`. Accept the narrow residual (a single-record concept with a `url`-named field whose value ends `.csv` is misread). **Pin with tests** (CSV-with-url-column reads correctly; non-`.csv` url stays a record) and **document the one limitation**.

**Code quality**

- **CQ1 — `--save-csv <path>` is literal/cwd-relative** (NOT resolved under `--output-dir`). **Drop the redundant `--csv-path`.** Param is **keyword-only** in `_execute_run` (fits the in-flight keyword-only-args refactor). `_execute_run`'s ~15-param signature is a pre-existing data-clump smell → separate `SaveOptions`-struct refactor, out of scope.
- **CQ2 — One module.** `pipelex/tools/tabular/csv_codec.py` holds row read/write + concept-binding + the **single shared flatness/field-order helper used by BOTH read and write** + error types + a suffix dispatch (`.csv` built-in; `.xlsx` → "needs `pipelex[tabular]`"). No codec/binding file split until xlsx earns it (design §11).

**Tests**

- **T1 — Split the integration test.** (1) input-codec: build WorkingMemory from `{url:people.csv}`, assert `people` is `ListContent[Person]` with `death_year is None`, **no pipeline run**; (2) output-codec: hand-build `ListContent[PersonSummary]` → CSV, assert header+rows; (3) **separate** full-pipeline test for `PipeBatch→Compose→PersonSummary[]`, with dry-mode cardinality/extraction semantics verified first. NB (Codex): `PersonSummary` drops `death_year`, so it can only be asserted on the input list.
- **T2 — CLI breadth.** One real subprocess e2e on `run pipe`; **cheap wiring checks** (no subprocess) that `bundle_cmd` and `method_cmd` both declare `--save-csv` and forward it to `_execute_run`.
- **T3 — Pin coercion.** Table-driven test of accepted bool (`true/false/1/0/yes/no/on/off`) / date (ISO) / int / float forms **AND rejected** ones (comma-decimal `1,5`, ambiguous `DD/MM/YYYY`) + one doc line. Converts pydantic's incidental behavior into a verified, bump-proof contract.

**Cross-model (Codex) — baked in**

- **CT2 — Missing OPTIONAL column = lenient (→ all `None`).** Missing **required** column → error; **extra** column → error; missing **optional** column → that field is `None` for all rows. (Our own writer always emits every column, so this only aids hand-authored partial CSVs.) Resolves the design §8 contradiction.
- **CT3 — Document-only on injection.** Do NOT auto-escape formula-leading cells; preserve data fidelity. Document CSV/Excel formula-injection as a known v1 limitation; opt-in escape flag deferred. **Bake regardless:** serialize via `model_dump(mode="json")`, then map `None`→`""` explicitly; document non-finite floats (`nan`/`inf`).
- **`None` ↔ empty-cell, both sides (CRITICAL).** Read maps `""`→`None` BEFORE pydantic; write maps `None`→`""` (never `str(None)=="None"`). Test matrix: `Optional[str]=None`, `Optional[str]=""`, required `str=""`. Empty-string text is indistinguishable from `None` (→`None`, documented).
- **Empty / declared-model headers (CRITICAL).** The writer derives columns from the **declared row model** (resolved via the concept), NEVER from `items[0]` — an empty `ListContent` must still write a correct header-only file.
- **`date` is a supported scalar (BUG fix).** Design §6's arrow drops `date`; it must map to `datetime.date`. The flatness guard ACCEPTS `date`; round-trip writes `date.isoformat()`. Add a date-field test.
- **Flatness = a real type-classifier.** Unwrap `Optional`; ACCEPT `Literal`/`choices`-constrained scalars (cf. `ArticleReview.rating`); REJECT `Union`/nested/concept-typed/`Any`/dict/list — each with a clear named error. Not a naive field scan.
- **Eager-core-I/O coverage.** Add tests for dry-run, validation-only/build-only paths, and repeated working-memory builds after the file mutates on disk.
- **Sanity-check caveat.** The Phase-1 `--mock-inputs` dry-run only checks **bundle shape** — it bypasses the CSV path. Add a separate real-`inputs.json` check once the input hook exists.

---

## 🧭 Key code anchors (discovered — don't re-explore from scratch)

**Type system / binding**

- Content base + render interface: `pipelex/core/stuffs/stuff_content.py`. List container: `pipelex/core/stuffs/list_content.py`. Structured base: `pipelex/core/stuffs/structured_content.py`.
- Concept → structure class: `pipelex/core/stuffs/stuff_factory.py` (`get_class_registry().get_required_subclass(name=concept.structure_class_name, base_class=StuffContent)`).
- Structure field types enum: `pipelex/core/concepts/concept_structure_blueprint.py:37-45` → scalars `text | integer | number | boolean | date` **plus non-flat** `list | dict | concept` (the flatness classifier ACCEPTS the scalars + `Literal`/`choices`, REJECTS list/dict/concept/`Union`/`Any`).

**Inputs**

- CLI run subcommands (each has `--inputs/-i`, `--save-main-stuff`, `--save-working-memory`, `--output-dir/-o`, `--dry-run`, `--mock-inputs`, `--library-dir/-L`): `pipelex/cli/commands/run/{pipe_cmd.py,bundle_cmd.py,method_cmd.py}` → shared `_run_core.py` (`_execute_run`).
- Relative-path resolution for `url` fields in inputs.json: `pipelex/cli/commands/run/_inputs_path_resolver.py`.
- Inputs → memory: `pipelex/core/memory/working_memory_factory.py` (`make_from_pipeline_inputs`, `make_from_single_stuff`, `make_from_multiple_stuffs`).

**Output**

- Save logic (main_stuff json/md/html; working memory json) lives in `pipelex/cli/commands/run/_run_core.py` (the `save_main_stuff` / `save_working_memory` blocks). `--save-csv` slots in here.

**Run drivers for tests**

- In-process (integration): `PipelexRunner(library_dirs=[...], pipe_run_mode=...).execute_pipeline(pipe_code=..., inputs=PipelineInputs)` — `pipelex/pipeline/runner.py:45`.
- Low-level (alt): `get_pipe_router().run(PipeJobFactory.make_pipe_job(pipe=get_required_pipe(pipe_code=...), pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=...), working_memory=..., job_metadata=...))`.
- Assertions: `pipe_output.main_stuff`, `pipe_output.main_stuff_as(content_type=Foo)`, `pipe_output.main_stuff_as_items(item_type=Foo)` / `main_stuff_as_list(item_type=Foo)`.

**Test infra**

- Fixtures: `pipe_run_mode` (`--pipe-run-mode {live|dry}`, default dry; `--disable-inference` forces dry), `job_metadata`, `load_test_library([Path(...)])` — in `tests/conftest.py` + `pipelex/test_extras/shared_pytest_plugins.py`.
- Markers: `@pytest.mark.dry_runnable` (runs in CI under dry mode), `@pytest.mark.llm`, `@pytest.mark.inference`, `@pytest.mark.asyncio(loop_scope="class")`, `@pytest.mark.gha_disabled` (subprocess/slow, PR-gated).
- Integration bundle example: `tests/integration/pipelex/pipes/pipelines/*.mthds` + sibling `test_structures.py` (registers `StructuredContent` subclasses). Structured-concept-via-`.mthds` example: `tests/integration/pipelex/concepts/refines_custom_concept/refines_custom_concept.mthds`.
- E2E offline CLI-subprocess pattern (model for the e2e test): `tests/e2e/agent_cli/` (`hermetic_home`, `offline_subprocess_env`, `_run_agent_bundle`, `_stage_bundle`). CLI-change test dir per `tests/CLAUDE.md`: `tests/e2e/pipelex/cli/`.

---

## 🎯 North-star example (the TDD target)

Batch over the people; per person, an `PipeLLM` writes **only** the one-sentence persona text, and a `PipeCompose` assembles the output row from **selected** original fields (not all) + that description. Input rows carry enough fields (job, country, birth/death years) to ground the persona summary. The input concept `Person` and the output concept `PersonSummary` are both flat (scalar fields) → reject-non-flat satisfied. Integer `birth_year`/`death_year` exercise CSV→type coercion; the blank `death_year` exercises empty-cell→`None` (so `death_year` is optional).

Bundle `csv_demo.mthds`:

```toml
domain      = "csv_demo"
description = "CSV round-trip demo: summarize people, one persona sentence each"

[concept.Person]
description = "A person record read from a CSV row"
[concept.Person.structure]
name       = { type = "text",    required = true,  description = "Full name" }
job        = { type = "text",    required = true,  description = "Occupation" }
country    = { type = "text",    required = true,  description = "Country of origin" }
birth_year = { type = "integer", required = true,  description = "Year of birth" }
death_year = { type = "integer", required = false, description = "Year of death, if deceased" }

[concept.PersonSummary]
description = "A person row reduced to name + country plus a one-sentence persona summary"
[concept.PersonSummary.structure]
name    = { type = "text", required = true, description = "Full name" }
country = { type = "text", required = true, description = "Country of origin" }
summary = { type = "text", required = true, description = "One-sentence persona summary" }

# Batch over the list — branch runs once per person
[pipe.summarize_people]
type             = "PipeBatch"
description      = "Summarize each person in the list"
inputs           = { people = "Person[]" }
output           = "PersonSummary[]"
branch_pipe_code = "summarize_person"
input_list_name  = "people"
input_item_name  = "person"

# Per-person branch: describe (LLM) then compose the row
[pipe.summarize_person]
type        = "PipeSequence"
description = "Describe one person, then compose their summary row"
inputs      = { person = "Person" }
output      = "PersonSummary"
steps = [
  { pipe = "describe_person", result = "description" },
  { pipe = "compose_person_summary", result = "person_summary" },
]

# LLM produces ONLY the description text
[pipe.describe_person]
type        = "PipeLLM"
description = "Write a one-sentence persona summary for a person"
inputs      = { person = "Person" }
output      = "Text"
prompt = """
Write a single vivid sentence summarizing this person as a persona, drawing on their job, country, and lifespan.
@person
"""

# Compose the output row from SELECTED original fields + the description (drops job, birth_year, death_year)
[pipe.compose_person_summary]
type        = "PipeCompose"
description = "Build the summary row from selected Person fields plus the generated description"
inputs      = { person = "Person", description = "Text" }
output      = "PersonSummary"

[pipe.compose_person_summary.construct]
name    = { from = "person.name" }
country = { from = "person.country" }
summary = { from = "description" }
```

Input `people.csv` (note the trailing blank `death_year` for the living person):

```csv
name,job,country,birth_year,death_year
Ada Lovelace,Mathematician,United Kingdom,1815,1852
Grace Hopper,Computer Scientist,United States,1906,1992
Vint Cerf,Computer Scientist,United States,1943,
```

`inputs.json`:

```json
{ "people": { "concept": "csv_demo.Person", "content": { "url": "people.csv" } } }
```

Expected: a `summaries.csv` with header `name,country,summary` and one row per input person (dry mode → mock summary text; live mode → real personas). The integration test asserts the round-trip + structure (and `death_year` parsed as `None` for Vint Cerf); the live arm asserts persona content.

> Syntax **verified** (plan-eng-review) against `tests/e2e/pipelex/pipes/pipe_controller/pipe_batch/joke_batch.mthds` (real **standalone** `type = "PipeBatch"` with `branch_pipe_code`/`input_list_name`/`input_item_name` — `pipe_batch_blueprint.py:9-14`) and `tests/e2e/pipelex/pipes/pipe_operators/pipe_compose/cv_job_match.mthds` (`[pipe.x.construct]` with `{ from = "..." }` — `construct_blueprint.py:138-171`). PipeCompose auto-extracts a `Text` stuff into a `str` field (`structured_content_composer.py:329-351`). NB: `article_briefing.mthds` uses **inline** `batch_over`/`batch_as`, a different construct — not a standalone-PipeBatch template; cite `joke_batch.mthds`.

---

## Phase 1 — Acceptance tests + fixtures (outside-in, all RED)

Goal: lock the contract with failing tests before any implementation.

- [x] Codec module home is **LOCKED (CQ2 / Step 0): `pipelex/tools/tabular/csv_codec.py`** — one module (matches the `tools/{pdf,uri,storage}/` pattern; no `concept_table.py` split). No re-decision needed. **Done: skeleton created, signatures locked; error taxonomy in `pipelex/tools/tabular/exceptions.py`.**
- [x] Sanity-check the bundle wiring with a quick dry-run (`pipelex run pipe summarize_people --library-dir <bundle> --dry-run --mock-inputs`). **CONFIRMED: composes; output is `ListContent[PersonSummary]`; dry mode preserves cardinality (3→3) AND PipeCompose real-field extraction (composed name/country == input person's fields). The OPEN dry-mode risk is now closed.**
- [x] Create north-star fixtures: `csv_demo.mthds`, `people.csv`, `inputs.json` under `tests/integration/pipelex/csv/csv_demo/`. **No `test_structures.py` needed** — inline `[concept.X.structure]` auto-generates registered classes; fetch via `concept.get_structure_class()`.
- [x] Write codec **unit** tests `tests/unit/pipelex/tools/tabular/test_csv_codec.py` (RED). Covers: read→list-of-dicts, custom delimiter, missing-file/bad-encoding → `CsvReadError` (NUL-byte case dropped per R2 — csv doesn't raise on NUL in Py3.13), duplicate/blank header → `CsvColumnError`, write+read round-trip, empty→header-only; flatness classifier (declared order + `Literal` accept; list/dict/nested/`Union`/`Any` reject); coercion incl. **`date`→`datetime.date`**; empty-cell→`None` (optional) / required→`CsvCoercionError`; T3 accept (`true/false/1/0/yes/no/on/off`, int, float, ISO date) + reject (`abc`, `1,5`, `31/12/2020`) tables; coercion-failure names row+field; strict columns (extra/missing-required error, missing-optional all-`None`); write declared header + `None`→`""` (not `"None"`); empty-list header-only from declared model; round-trip stability; `None`↔`""` both sides; `.xlsx`→`pipelex[tabular]` + unsupported-suffix.
- [x] Write the **integration** test `tests/integration/pipelex/csv/test_csv_roundtrip.py` (RED) — **split per T1**: (a) **input-codec** WorkingMemory build → `ListContent[Person]` + `death_year is None` for Vint Cerf; (b) **output-codec** hand-built `ListContent[PersonSummary]` → header `name,country,summary` + rows; (c) **full pipeline** via `PipelexRunner(...).execute_pipeline("summarize_people", inputs=...)` → 3 items, names/countries from the real rows (dry-mode-safe, confirmed). `death_year` asserted on (a) only. (c) marked `@pytest.mark.dry_runnable @pytest.mark.llm @pytest.mark.inference @pytest.mark.asyncio`.
- [x] Write the **e2e** CLI test `tests/e2e/pipelex/cli/test_csv_run.py` (RED): subprocess `pipelex run pipe ... --save-csv summaries.csv --dry-run` → exit 0 + `summaries.csv` at literal cwd path (CQ1) + header `name,country,summary` + one row per person; **(T2) cheap wiring checks** that `run_pipe_cmd`/`run_bundle_cmd`/`run_method_cmd` declare `save_csv` (signature) + `bundle_cmd` forwards it to `execute_run`; **error e2e** missing input `.csv` → non-zero exit + clean message (no traceback) + names the file (A2). Subprocess tests `@pytest.mark.gha_disabled`, inherit ambient env, `cwd=tmp`.
- [x] Run the new tests; confirmed they fail **for the right reasons** (codec `NotImplementedError`; `.csv` input parsed as a record → `ValidationError`/`PipeExecutionError`; `save_csv` missing from CLI signatures; `--save-csv` → typer exit 2 "No such option"), **not collection errors**. All RED. `make agent-check` GREEN repo-wide. (NUL-byte test later dropped per R2 — see Session state.)

### 🛑 CHECKPOINT 1 — contract locked, red for the right reasons ✅ CLEARED (2026-06-01)
Each new test fails on the intended missing capability (verified). Session state updated with codec module location + locked public API, fixtures location, exact test file paths, the resolved dry-mode-semantics risk, and the precise Phase-2 first step. **Hard stop reached.**

---

## Phase 2 — Tabular codec (make the unit tests GREEN)

Goal: a self-contained, well-tested codec. No pipe-runtime coupling.

- [x] Implement `pipelex/tools/tabular/csv_codec.py` (stdlib `csv`): `read_rows(path, *, delimiter, encoding) -> list[dict[str,str]]` and `write_rows(path, headers, rows, *, delimiter, encoding)`. **Done** — both delegate to an internal `_read_table` (explicit header + raw rows) / `_row_to_dict` (pads short/blank rows). `read_rows` is a pure primitive (no suffix gate); the suffix seam fires only in the concept-binding entry points.
- [x] Implement the concept binding **in the same module** (CQ2 — one file, no `concept_table.py` split): `list_content_from_csv(path, row_model, *, delimiter, encoding) -> ListContent[T]` and `csv_from_list_content(list_content, row_model, path, *, delimiter, encoding)`. **Done** — Phase-2 takes the resolved `row_model: type[StuffContentType]` directly (concept→class resolution stays in the Phase-3 hook); pydantic coercion maps `""`→`None` BEFORE validate via `(value or None)`; write serializes via `model_dump(mode="json")` then `_to_cell` maps `None`→`""` and bool→lowercase `true/false` (round-trip-safe); write headers come from the **declared `row_model`** so empty list → header-only file.
- [x] **A2 error taxonomy:** `CsvError` base + concrete types already landed in Phase 1 (`exceptions.py`). **Done** — the codec catches every raw `OSError`/`UnicodeDecodeError`/`csv.Error` (in `_read_table`) and `ValidationError` (per row in `list_content_from_csv`) and re-raises typed, carrying file path + 1-based row + offending field(s). Write failures raise `CsvError` (not `CsvReadError`).
- [x] **Flatness type-classifier** (CQ2 shared helper, used by read AND write): **Done** — `_is_flat_annotation` unwraps `Optional`/PEP-604 unions (rejects genuine multi-arm unions), ACCEPTS `str/int/float/bool/date/datetime` + `Literal` + `Enum` (choices), REJECTS list/dict/nested-model/`Any`. `flat_field_names` raises `CsvFlatnessError` naming field+concept and returns declared order.
- [x] Strict columns (CT2): **Done** — extra column → `CsvColumnError`; missing **required** (`field_info.is_required()`) → `CsvColumnError`; missing **optional** → absent from `row_data` so pydantic default (`None`) applies.
- [x] Format seam (design §11): **Done** — `assert_supported_table_suffix` if/elif on `path.suffix.lower()`: `.csv` ok; `.xlsx` → `CsvError` naming `pipelex[tabular]`; else → generic `CsvError`.
- [x] **NO main-config in v1 (D1).** **Done** — `delimiter`/`encoding` are codec params with `,`/`utf-8` defaults; `configs.py`/`pipelex.toml` untouched; no `make tb`.
- [x] `make agent-check` (pyright 0 / mypy 0 / ruff + plxt clean); codec unit tests → **GREEN (44/44)**. Broader `tests/unit/pipelex/tools/` → 1261 passed, 1 pre-existing skip.

### 🛑 CHECKPOINT 2 — codec landed, unit-green, lint-clean ✅ CLEARED (2026-06-01)
Codec fully implemented; all 44 unit tests green; `make agent-check` green repo-wide; no tools-scope regression. Session state updated with the implemented public signatures + internal helpers (next phases call `list_content_from_csv` / `csv_from_list_content` / `assert_supported_table_suffix`). **Hard stop reached.**

---

## Phase 3 — Input integration (inputs.json `.csv` → `ListContent[row-concept]`)

Goal: a `.csv` `url` under a structured row concept loads as a typed list.

- [x] Hook the input in `stuff_factory.make_stuff_from_stuff_content_or_data` **Case 2.5** — DONE via `StuffFactory._try_make_csv_list_stuff`, called before the record `model_validate`. Reached via `working_memory_factory.make_from_pipeline_inputs`; handles already-absolute/caller-supplied paths.
- [x] When the resolved `url` has a tabular suffix (`is_tabular_path`) and the concept is non-native structured, route through `list_content_from_csv` to produce `ListContent[row-concept]` (one CSV → one list; concept names the **row** type).
- [x] **A1 — reject remote URLs.** A tabular `url` that is `http(s)`/`s3://`/`gs://`/`pipelex-storage://`/base64 → clear `CsvError` "local file paths only in v1", NOT a raw `OSError`. Guard = `not ResolvedLocalPath or "://" in resolved.path`.
- [x] Clear errors for: non-flat concept (codec `CsvFlatnessError`), header mismatch (`CsvColumnError`), remote url (`CsvError`) — all naming concept/file. (Native concepts are left to their own url handling, not errored.)
- [x] **A3/CT1 pinning tests:** `test_non_csv_url_stays_record` (Link `{url: "https://example.com"}` → single record) + `test_csv_with_url_column_reads` (links.csv with a `url` column → typed list). Residual documented in Session state for the Phase-5 docs.
- [x] **Eager-core-I/O coverage:** `test_eager_read_reflects_file_mutation` (rebuild after on-disk mutation re-reads); the dry-mode read is exercised by roundtrip (c) and both subprocess e2e dry runs.
- [x] Run the integration test's input half (T1 part a: `test_csv_input_builds_typed_list`) — GREEN (`ListContent[Person]`, coerced int `birth_year`, `death_year is None` for Vint Cerf).

*(Light checkpoint folded into CHECKPOINT 3 below.)*

---

## Phase 4 — Output integration (`--save-csv`) + close the round-trip

Goal: the headline integration + e2e tests go GREEN.

- [x] Add `--save-csv <path>` (Optional[str], `None`=off — **CQ1: NO `--csv-path`**) to `pipe_cmd.py`, `bundle_cmd.py`, `method_cmd.py`; threaded through `_execute_run`/`execute_run` in `_run_core.py` as a **keyword-only** param.
- [x] On save, require the main stuff to be a `ListContent` (reject no-main-stuff / non-list with a clear `typer` error + `Exit(1)`; the codec's `CsvFlatnessError` covers non-flat); write via `csv_from_list_content`, row model = `main_stuff.concept.get_structure_class()`. **Writes to the literal `<path>` (cwd-relative), NOT under `--output-dir`.**
- [x] Run integration test (T1 parts b+c) → GREEN. e2e CLI subprocess `--dry-run` → GREEN (file at literal path, header `name,country,summary`, 3 records). T2 bundle/method wiring checks + missing-file error e2e → GREEN.
- [x] `make agent-check` → GREEN (pyright 0 / mypy 0 / ruff+plxt clean).

### 🛑 CHECKPOINT 3 — round-trip works end to end (headline milestone) ✅ CLEARED (2026-06-02)
CSV in → PipeBatch→PipeSequence(PipeLLM+PipeCompose) → CSV out, GREEN in dry mode via BOTH in-process and CLI-subprocess paths. Full `make agent-test` GREEN (no regressions). Session state updated with the final Phase 3+4 implementation + the documented limitations Phase 5 must write up. No live-mode caveats surfaced in dry mode (live arm is an optional Phase-5 follow-up). **Hard stop reached.**

---

## Phase 5 — Docs, changelog, full-suite polish (config CUT per D1)

- [ ] ~~Finalize delimiter/encoding config~~ — **CUT from v1 (D1)**. Capture the user-facing config surface as a follow-up TODO instead (see Out-of-scope).
- [ ] `CHANGELOG.md` under `## [Unreleased]` (do NOT add a versioned header — release skill does that).
- [ ] Docs: a short "CSV input & output" guide page (Material for MkDocs: blank line before lists; one-paragraph-per-line). Cover the inputs.json `.csv` convention, `--save-csv` (literal path), the flat-concept requirement (incl. `date`), the round-trip example, and **the documented limitations: empty-string text → `None`; the A3/CT1 single-record `.csv`-url residual; CSV/Excel formula-injection (CT3); local-paths-only (no remote URLs)**; the T3 coercion accept/reject rules.
- [ ] (Optional) a live-mode arm assertion on the integration test guarded by `if pipe_run_mode.is_live`.
- [ ] Full `make agent-check` + `make agent-test` → all GREEN. If it hangs, use `make agent-test-debug`.

### 🛑 CHECKPOINT 4 — v1 ship-ready
Everything green, docs + changelog in. Update Session state to "v1 complete". Summarize what shipped and what's deferred. **Hard stop** (ready for PR / review).

---

## ⚠️ Risks / things to confirm while implementing

(Several earlier risks are now RESOLVED by the review — kept here annotated so a fresh session doesn't re-litigate them.)

- **PipeCompose field extraction** — ✅ RESOLVED at runtime (Phase-1 sanity dry-run): dotted-path `{ from = "person.name" }` and `Text`-stuff→`str` extraction work; the `PipeBatch` branch sees `person` under `input_item_name`. The composed `PersonSummary.name`/`country` equal the input person's fields.
- **Dry-mode pipeline semantics** — ✅ RESOLVED at runtime (Phase-1 sanity dry-run): dry mode preserves `PipeBatch` cardinality (3 mock people in → 3 `PersonSummary` out) AND `PipeCompose` real-field extraction. The full-pipeline test (T1 part c) asserts on real CSV rows in dry mode; no need to mark it live-only.
- **Coercion edge cases** — RESOLVED by T3: pin the accept/reject set (bool/date/number) with a table test + doc line. Lean on pydantic; don't hand-roll.
- **Duplicate / blank headers** — RESOLVED: error; unit test required in Phase 1.
- **Input hook location** — RESOLVED (A1): `stuff_factory.py:399-413` Case 2.5. No exploration needed.
- **`--save-csv` when main stuff isn't a list** — RESOLVED: Phase 4 rejects with a clear error (shared flatness guard), no silent no-op.
- **Don't over-build the format seam** — two functions keyed by suffix; no plugin system before xlsx exists (design §11 / CQ2).

## 🚫 Out of scope for v1 (deferred — see design §10)

- `.xlsx` via `pipelex[tabular]` (openpyxl) — seam only in v1.
- Streaming / out-of-core CSVs; Google Sheets / Parquet.
- Delimiter/dialect auto-detection; schema/type inference beyond the bound concept.
- A native `Table` concept / schema-free table primitive (separate language-surface decision).
- **Remote `.csv` URLs** (`http://`/`s3://`/signed) — local paths only in v1; actively rejected (A1).

### Deferred follow-up TODOs (from the review — capture, don't lose)

- **User-facing delimiter/encoding config** (D1) — toml default and/or `--delimiter`/`--encoding` CLI flags. *Why:* honors the locked "configurable, never guessed" with a real user knob (EU semicolon CSVs). *Where to start:* `configs.py` + both `pipelex.toml` (per convention) or CLI flags on the run commands; codec already accepts the params.
- **Opt-in CSV/Excel formula-escape flag** (CT3) — `escape_formulas` codec param + CLI flag, default off. *Why:* injection safety when CSVs ship to third parties (hosted runner). *Trade-off:* escaping mutates data; keep it opt-in to preserve fidelity.
- **`SaveOptions` struct** for `_execute_run` — group the save_* params (pre-existing 15-param data clump). *Why:* the CSV flag is the 4th save-related param; a struct stops the bleed. *Scope:* a refactor across the 3 run commands + `_run_core.py`; out of CSV scope.
- **Multiplicity-gated CSV detection** (CT1 option C) — only if the `.csv`-url residual proves real in practice. *Why:* fully removes the A3 ambiguity. *Cost:* thread expected concept+multiplicity into `stuff_factory`.

---

## Implementation Tasks

Synthesized from this review. P1 blocks ship; P2 same branch; P3 follow-up. Effort = human / CC.

- [x] **T1 (P1, human: ~3h / CC: ~20min)** — codec — CSV codec: read/write + binding + flatness type-classifier + A2 typed errors, one module
  - Surfaced by: CQ2 / A2 / flatness — one `tools/tabular/csv_codec.py`, shared flatness helper, wrap all raw exceptions
  - Verify: `tests/unit/pipelex/tools/tabular/test_csv_codec.py` green
- [x] **T2 (P1, human: ~1h / CC: ~8min)** — codec — `None`↔empty-cell both sides + empty-list header-only from declared model + `model_dump(mode="json")`
  - Surfaced by: CT3 / Codec-CRIT — write `None`→`""` not `"None"`; headers from declared row model, not `items[0]`
- [x] **T3 (P1, human: ~2h / CC: ~15min)** — core — input hook in `stuff_factory` Case 2.5 (eager, local-only, reject remote URLs)
  - Surfaced by: A1 — core hook reachable from runner; reject `http`/`s3` with clear error
- [x] **T4 (P1, human: ~1.5h / CC: ~12min)** — cli — `--save-csv` literal-path keyword-only flag on 3 run commands + `_run_core`, reject non-flat-list
  - Surfaced by: CQ1 — drop `--csv-path`; literal cwd path; clear error when main stuff isn't a flat list
- [x] **T5 (P1, human: ~3h / CC: ~20min)** — tests — codec unit suite: errors / coercion-fail / empty-required / dup-header / date / Literal / strict-columns / round-trip
  - Surfaced by: Test-review coverage map — 7 critical gaps + T3 accept/reject table
- [x] **T6 (P1, human: ~2h / CC: ~15min)** — tests — integration test split (input-codec / output-codec / full-pipeline)
  - Surfaced by: T1 — mode-independent codec assertions; assert `death_year` on input only
- [x] **T7 (P2, human: ~1.5h / CC: ~12min)** — tests — e2e `pipe --save-csv` + bundle/method wiring checks + missing-file error e2e
  - Surfaced by: T2 / A2 — one e2e on pipe; cheap wiring on bundle/method; clean error not stack trace
- [x] **T8 (P2, human: ~45min / CC: ~6min)** — tests — A3/CT1 pinning tests + eager-core-IO coverage (dry-run / validate / refresh-after-mutation)
  - Surfaced by: CT1 / Codex — fence the `.csv`-url residual; cover validation + dry paths
- [ ] **T9 (P2, human: ~1h / CC: ~8min)** — docs — CSV guide page + CHANGELOG `[Unreleased]`; document the limitations
  - Surfaced by: Phase 5 — Material for MkDocs; cite `joke_batch.mthds`
- [ ] **T10 (P3, follow-up)** — deferred TODOs: user-facing config; opt-in formula-escape; `SaveOptions` struct; multiplicity-gated detection

---

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` | Scope & strategy | 0 | — | — |
| Codex Review | `/codex review` | Independent 2nd opinion | 1 | issues_found | 3 blockers + 7 high/med; all resolved (2 baked, 3 tensions decided) |
| Eng Review | `/plan-eng-review` | Architecture & tests (required) | 1 | CLEAR | 12 decisions; 0 unresolved; 0 unaddressed critical gaps |
| Design Review | `/plan-design-review` | UI/UX gaps | 0 | — | n/a (backend feature) |
| DX Review | `/plan-devex-review` | Developer experience gaps | 0 | — | — |

- **CODEX:** outside voice found the `date` mapping bug, the empty-list-headers gap, and the design §8 optional-column contradiction — all real misses; folded in.
- **CROSS-MODEL:** strong overlap on the `None`-round-trip corruption and the eager-core-I/O risk (both models independently). Three tensions surfaced and decided by the user (CT1 hold A3, CT2 lenient, CT3 document-only).
- **UNRESOLVED:** 0.
- **VERDICT:** ENG CLEARED (scope reduced per D1) — ready to implement. Recommend `/ship` when the branch is green.
