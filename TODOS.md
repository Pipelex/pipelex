# CSV Support — Implementation Plan (v1)

Branch `feature/Support-csv` (worktree `_csv`). Design: [`wip/csv-support/design.md`](wip/csv-support/design.md). This file is the single source of truth for execution + cold-start.

**Approach: outside-in TDD.** Write the acceptance tests (integration + e2e) and codec unit tests first (red), then implement until green. Run `make agent-check` after every code change; `make agent-test` at each checkpoint. (No `make tb` — D1 cut config from v1.)

---

## ⏱️ Session state (UPDATE AT EVERY CHECKPOINT — this is the cold-start anchor)

- **Current phase:** Phase 1 COMPLETE → **CHECKPOINT 1 cleared (2026-06-01).** All acceptance/unit/e2e tests written and RED for the right reasons; `make agent-check` green repo-wide.
- **Last checkpoint cleared:** CHECKPOINT 1 (contract locked, red for the right reasons).
- **Git state (2026-06-01):** Phase-1 skeleton + tests are committed in `acde0561` ("Phase 1 and feedback"); the **R1–R7 review-finding fixes** (and this TODOS update) are committed on top on `feature/Support-csv` — **nothing pushed**, worktree clean at session end. Files touched by the R1–R7 pass: `pipelex/tools/tabular/{csv_codec.py (R4/R6 docstrings), exceptions.py (R7 titles)}`, `tests/unit/pipelex/tools/tabular/test_csv_codec.py (R2 drop + R3)`, `tests/e2e/pipelex/cli/test_csv_run.py (R1 + `import csv`)`, `wip/csv-support/phase1-review-findings.md`. **Re-verified this session:** `make agent-check` green (pyright/mypy/ruff/plxt); the error title/location/pages tests pass (titles now `"CSV read/flatness/column/coercion error"`); the CSV trio collects with 0 errors and is RED for the right reasons on the in-process arm (codec `NotImplementedError`; CSV-url parsed as a record; `save_csv` missing from signatures). **NOT executed:** the two `gha_disabled` subprocess e2e tests (they invoke the real binary + need ambient config) — R1's record-count fix there is **latent until Phase 4** (those tests currently RED earlier at `assert result.returncode == 0`).
- **Green so far:** nothing of the feature is implemented yet (by design). The codec is a **skeleton** (every function raises `NotImplementedError` via a `_pending` sentinel). What IS landed & green: the skeleton lint/type-checks clean and conforms to the error-class-location + type_uri-uniqueness conventions.
- **Next concrete action:** start **Phase 2** — implement `pipelex/tools/tabular/csv_codec.py` (fill the bodies, keep signatures) until `tests/unit/pipelex/tools/tabular/test_csv_codec.py` goes GREEN. The public API + error taxonomy are LOCKED (see "Phase-1 deliverables" below); do NOT rename them. **Phase-1 review findings R1–R7 are now FIXED (2026-06-01)** (see [`wip/csv-support/phase1-review-findings.md`](wip/csv-support/phase1-review-findings.md)): the RED-for-wrong-reason trio — **R1** e2e now counts parsed records via `csv.DictReader` (the dry summary cell is multi-line, so `splitlines()` could never be 4), **R2** NUL-byte test dropped (false premise on Py3.13 — csv doesn't raise), **R3** single-column blank-cell test now asserts by re-parse (csv writes a lone empty field as quoted `""`, not `""`empty) — plus the skeleton docstring/title fixes — **R4** `read_rows` docstring → `CsvColumnError` for bad headers, **R6** `write_rows` docstring → `CsvError` on write failure, **R7** per-subclass `_declared_title` ("CSV read/flatness/column/coercion error"). Tests remain RED for the right reason; `make agent-check` green.
  - **R5 decided: keep `CsvError` for the `.xlsx` seam in v1** — no `pipelex[tabular]` extra exists yet, so `MissingDependencyError`'s install hint would be a false promise. **Revisit → `MissingDependencyError` when the xlsx codec + `tabular` extra actually ship.**
  - **Still-open deferred review items** (not blocking Phase 2 start): **R8** — lock the `CsvCoercionError` message format and tighten the loose `"2" in message` assertion (Phase 2, when writing the coercion error). **R9** — pin/document `QUOTE_MINIMAL` as the codec's quoting contract (the exact-line write assertions assume it; it's the stdlib default — Phase 2). **R10** — give the e2e subprocess tests a hermetic `conftest.py` (sealed HOME/env) reusing the `tests/e2e/agent_cli/` helpers instead of `env=os.environ.copy()` (Phase 4). **R11** — tighten the integration country check to an exact multiset (`["United Kingdom","United States","United States"]`) instead of the `<= EXPECTED_COUNTRIES` subset (optional). **R12** — opt the input-copy errors (`CsvColumnError`/`CsvCoercionError`/`CsvFlatnessError`) into `_authors_caller_facing_message = True` so STRICT disclosure keeps their caller-fixable detail; keep it OFF on `CsvReadError` (Phase 2 taxonomy decision).
- **Open questions blocking:** none. The two big runtime risks are now RESOLVED (see Risks section): dry mode **preserves** PipeBatch cardinality AND PipeCompose real-field extraction (confirmed by a sanity dry-run — 3 mock people in → 3 `PersonSummary` out, with composed `name`/`country` equal to the input person's fields). So the full-pipeline integration test asserts on real CSV rows in dry mode (no need to mark it live-only).
- **Notes for next session — Phase-1 deliverables (read before coding Phase 2):**
  - **Codec module (skeleton, contract LOCKED):** `pipelex/tools/tabular/csv_codec.py`. Public API to implement, with these exact signatures:
    - `read_rows(path: Path, *, delimiter=",", encoding="utf-8") -> list[dict[str, str]]`
    - `write_rows(path: Path, headers: list[str], rows: list[dict[str, str]], *, delimiter, encoding) -> None`
    - `flat_field_names(row_model: type[StuffContent]) -> list[str]`  ← the SHARED flatness classifier (used by read AND write); returns declared field order, raises `CsvFlatnessError`.
    - `assert_supported_table_suffix(path: Path) -> None`  ← format seam: `.csv` ok; `.xlsx` → `CsvError` naming `pipelex[tabular]`; else → generic `CsvError`.
    - `list_content_from_csv(path, row_model: type[T], *, delimiter, encoding) -> ListContent[T]`
    - `csv_from_list_content(list_content: ListContent[T], row_model: type[T], path, *, delimiter, encoding) -> None`
    - Module has **no `from __future__ import annotations`** on purpose (annotations are runtime so the stuff-type imports aren't flagged as type-only); Phase 2 will use those imports at runtime anyway.
  - **Error taxonomy (LOCKED):** `pipelex/tools/tabular/exceptions.py` → `CsvError(ToolError)` (`error_domain = ErrorDomain.INPUT`) + `CsvReadError`, `CsvFlatnessError`, `CsvColumnError`, `CsvCoercionError`. Conforms to the error-location convention (test passes).
  - **Fixtures:** `tests/integration/pipelex/csv/csv_demo/{csv_demo.mthds, people.csv, inputs.json}`. **No `test_structures.py` needed** — the inline `[concept.X.structure]` blocks auto-generate registered `StructuredContent` subclasses (fetch via `concept.get_structure_class()`).
  - **Tests (all RED for the right reason, 0 collection errors):**
    - `tests/unit/pipelex/tools/tabular/test_csv_codec.py` (`TestCsvCodec`) → fails with `NotImplementedError`. This is the Phase-2 GREEN target.
    - `tests/integration/pipelex/csv/test_csv_roundtrip.py` (`TestCsvRoundtrip`): (a) input → `ValidationError`/`PipeExecutionError` because Case 2.5 parses `{url:...}` as a record (Phase 3 fixes); (b) output → `NotImplementedError` (Phase 2); (c) full pipeline → input-not-parsed (Phase 3/4). Run (c) under the CI marker expr `dry_runnable or not (inference or ...)` — the default `-m` deselects it.
    - `tests/e2e/pipelex/cli/test_csv_run.py` (`TestCsvRun`): wiring checks → `save_csv` missing from signatures (Phase 4); subprocess `--save-csv` → exit 2 "No such option" (Phase 4); missing-csv → error doesn't yet name the file (Phase 3 / A2). The subprocess tests are `gha_disabled`, inherit the ambient env, run with `cwd=tmp`. **Heads-up:** the forwarding test calls `run_bundle_cmd(**call_kwargs)` with a `# type: ignore[arg-type]` so it stays type-clean before `save_csv` exists — once Phase 4 adds the param you can simplify it back to an explicit kwarg call.

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

- [ ] Implement `pipelex/tools/tabular/csv_codec.py` (stdlib `csv`): `read_rows(path, *, delimiter, encoding) -> list[dict[str,str]]` and `write_rows(path, headers, rows, *, delimiter, encoding)`.
- [ ] Implement the concept binding **in the same module** (CQ2 — one file, no `concept_table.py` split): `list_content_from_csv(path, row_concept_or_class, *, delimiter, encoding) -> ListContent[T]` and `csv_from_list_content(list_content, row_model, path, *, delimiter, encoding)`. Resolve the row concept's `StructuredContent` subclass via the class registry; build instances with pydantic coercion (map `""`→`None` BEFORE validate); **serialize on write via `model_dump(mode="json")` then map `None`→`""`** (never `str(None)`); derive write headers from the **declared `row_model`**, NOT `items[0]` (empty list → header-only file).
- [ ] **A2 error taxonomy:** define a `CsvError` base (PipelexError subclass) + concrete types (read/file, flatness, column-mismatch, coercion). The codec **catches all raw `OSError`/`csv.Error`/`ValidationError`** and re-raises typed, carrying **file path + 1-based row/col + concept + field**.
- [ ] **Flatness type-classifier** (CQ2 shared helper, used by read AND write): unwrap `Optional`; ACCEPT `str/int/float/bool/datetime.date` + `Literal`/`choices` scalars; REJECT list/dict/nested/`Union`/concept-typed/`Any`, naming the field+concept + "project to a flat concept first".
- [ ] Strict columns (CT2): extra → error; missing **required** → error; missing **optional** → field is `None` for all rows. Distinct, clear errors.
- [ ] Format seam (design §11): a tiny suffix dispatch (`.csv` built-in; `.xlsx` → clear "Excel support requires `pipelex[tabular]`" error, no openpyxl dep). Functions, not a plugin framework.
- [ ] **NO main-config in v1 (D1).** `delimiter`/`encoding` are codec params with `,`/`utf-8` defaults. Do NOT touch `configs.py`/`pipelex.toml`/`make tb`. User-facing config = deferred follow-up (Out-of-scope).
- [ ] `make agent-check`; run codec unit tests → GREEN.

### 🛑 CHECKPOINT 2 — codec landed, unit-green, lint-clean
Update Session state. Capture the final module layout + public function signatures (the next phases call them). **Hard stop.**

---

## Phase 3 — Input integration (inputs.json `.csv` → `ListContent[row-concept]`)

Goal: a `.csv` `url` under a structured row concept loads as a typed list.

- [ ] Hook the input in `stuff_factory.make_stuff_from_stuff_content_or_data` **Case 2.5** (`stuff_factory.py:399-413`) — the exact point is **pinned by A1, no re-discovery needed**. It's reached via `working_memory_factory.make_from_pipeline_inputs`; relative paths are pre-resolved by `_inputs_path_resolver.py` at CLI time (programmatic/runner callers pass the path as-is, so the codec must handle an already-absolute or caller-supplied path).
- [ ] When the resolved `url` has a `.csv` suffix and the concept is a flat structured concept, route through the codec to produce `ListContent[row-concept]` (one CSV → one list; concept names the **row** type).
- [ ] **A1 — reject remote URLs.** A `.csv` `url` that is `http://`/`https://`/`s3://`/signed (not a local path) → clear "CSV input supports local paths only in v1" error, NOT a raw `OSError` from trying to open it locally.
- [ ] Clear errors for: CSV bound to a non-structured/native concept, non-flat concept, header mismatch — all naming the concept and file (via A2 taxonomy).
- [ ] **A3/CT1 pinning tests:** a flat concept whose content `{url: ...}` value does NOT end `.csv` stays a single record; a CSV whose rows include a `url` column reads correctly. Document the residual single-record limitation.
- [ ] **Eager-core-I/O coverage (Codex):** tests for dry-run, validation-only/build-only paths, and repeated working-memory builds after the file mutates on disk.
- [ ] Run the integration test's input half (T1 part a: build WorkingMemory, assert `people` is `ListContent[Person]` with coerced fields + `death_year is None`). GREEN for input. (NB: the Phase-1 `--mock-inputs` sanity dry-run checks **bundle shape only** — it bypasses the CSV path; this is the first real CSV-input check.)

*(Light checkpoint — fold into CP3 unless context is large; if you stop here, update Session state.)*

---

## Phase 4 — Output integration (`--save-csv`) + close the round-trip

Goal: the headline integration + e2e tests go GREEN.

- [ ] Add `--save-csv <path>` (Optional[str], `None`=off — **CQ1: NO `--csv-path`**) to `pipe_cmd.py`, `bundle_cmd.py`, `method_cmd.py`; thread through `_execute_run` in `_run_core.py` as a **keyword-only** param alongside the existing save blocks.
- [ ] On save, require the main stuff to be a flat `ListContent[StructuredContent]` (reject non-list / non-flat with the shared clear error — no silent no-op); write via the codec, passing the **declared output row model**. **Write to the literal `<path>` (cwd-relative) — CQ1, do NOT resolve under `--output-dir`.**
- [ ] Run integration test (T1 parts b+c) → GREEN. Run e2e CLI subprocess test (`--dry-run`) → GREEN (file at literal path, header + rows correct). Run the T2 bundle/method wiring checks + the missing-file error e2e → GREEN.
- [ ] `make agent-check`.

### 🛑 CHECKPOINT 3 — round-trip works end to end (headline milestone)
CSV in → PipeLLM → CSV out, green in dry mode via both in-process and CLI-subprocess paths. Update Session state; note any live-mode caveats. **Hard stop.**

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

- [ ] **T1 (P1, human: ~3h / CC: ~20min)** — codec — CSV codec: read/write + binding + flatness type-classifier + A2 typed errors, one module
  - Surfaced by: CQ2 / A2 / flatness — one `tools/tabular/csv_codec.py`, shared flatness helper, wrap all raw exceptions
  - Verify: `tests/unit/pipelex/tools/tabular/test_csv_codec.py` green
- [ ] **T2 (P1, human: ~1h / CC: ~8min)** — codec — `None`↔empty-cell both sides + empty-list header-only from declared model + `model_dump(mode="json")`
  - Surfaced by: CT3 / Codec-CRIT — write `None`→`""` not `"None"`; headers from declared row model, not `items[0]`
- [ ] **T3 (P1, human: ~2h / CC: ~15min)** — core — input hook in `stuff_factory` Case 2.5 (eager, local-only, reject remote URLs)
  - Surfaced by: A1 — core hook reachable from runner; reject `http`/`s3` with clear error
- [ ] **T4 (P1, human: ~1.5h / CC: ~12min)** — cli — `--save-csv` literal-path keyword-only flag on 3 run commands + `_run_core`, reject non-flat-list
  - Surfaced by: CQ1 — drop `--csv-path`; literal cwd path; clear error when main stuff isn't a flat list
- [ ] **T5 (P1, human: ~3h / CC: ~20min)** — tests — codec unit suite: errors / coercion-fail / empty-required / dup-header / date / Literal / strict-columns / round-trip
  - Surfaced by: Test-review coverage map — 7 critical gaps + T3 accept/reject table
- [ ] **T6 (P1, human: ~2h / CC: ~15min)** — tests — integration test split (input-codec / output-codec / full-pipeline)
  - Surfaced by: T1 — mode-independent codec assertions; assert `death_year` on input only
- [ ] **T7 (P2, human: ~1.5h / CC: ~12min)** — tests — e2e `pipe --save-csv` + bundle/method wiring checks + missing-file error e2e
  - Surfaced by: T2 / A2 — one e2e on pipe; cheap wiring on bundle/method; clean error not stack trace
- [ ] **T8 (P2, human: ~45min / CC: ~6min)** — tests — A3/CT1 pinning tests + eager-core-IO coverage (dry-run / validate / refresh-after-mutation)
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
