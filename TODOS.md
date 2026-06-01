# CSV Support — Implementation Plan (v1)

Branch `feature/Support-csv` (worktree `_csv`). Design: [`wip/csv-support/design.md`](wip/csv-support/design.md). This file is the single source of truth for execution + cold-start.

**Approach: outside-in TDD.** Write the acceptance tests (integration + e2e) and codec unit tests first (red), then implement until green. Run `make agent-check` after every code change; `make agent-test` (and `make tb` for config) at each checkpoint.

---

## ⏱️ Session state (UPDATE AT EVERY CHECKPOINT — this is the cold-start anchor)

- **Current phase:** Phase 0 — not started.
- **Last checkpoint cleared:** none.
- **Green so far:** nothing implemented yet.
- **Next concrete action:** start Phase 1 — author the north-star bundle + fixtures and the (red) acceptance/unit tests.
- **Open questions blocking:** none.
- **Notes for next session:** plan just written; nothing built. Read the design doc + "Key code anchors" below before coding.

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
- **Reject non-flat.** A row concept used with CSV must have **scalar fields only** (`text/integer/number/boolean/date` → `str/int/float/bool`, optionals allowed). Any nested/list/dict field → clear error naming the offending field, telling the author to project to a flat concept first. No silent flatten, no JSON-in-cell, no dropped cells.
- **CSV is an I/O codec, not a prompt-render format** — it must NOT join the `rendered_plain/markdown/html/json` `TextFormat` router.
- **Input semantics:** header row required; column headers must exactly match field names (no implicit remap); empty cell → `None` (field must be optional); extra/missing columns → error. Coerce cell strings via pydantic lax validation.
- **Finer defaults:** explicit `--save-csv <path>` to trigger output (no surprise auto-emit); UTF-8 + comma dialect; **delimiter & encoding configurable, never guessed**.

---

## 🧭 Key code anchors (discovered — don't re-explore from scratch)

**Type system / binding**

- Content base + render interface: `pipelex/core/stuffs/stuff_content.py`. List container: `pipelex/core/stuffs/list_content.py`. Structured base: `pipelex/core/stuffs/structured_content.py`.
- Concept → structure class: `pipelex/core/stuffs/stuff_factory.py` (`get_class_registry().get_required_subclass(name=concept.structure_class_name, base_class=StuffContent)`).
- Structure field types enum: `pipelex/core/concepts/concept_structure_blueprint.py:37` → `text | integer | boolean | number | date`.

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

> Syntax confirmed against `tests/e2e/pipelex/pipes/pipe_controller/pipe_batch/article_briefing.mthds` (batch + sequence) and `tests/e2e/pipelex/pipes/pipe_operators/pipe_compose/cv_job_match.mthds` (`[pipe.x.construct]` with `{ from = "..." }`). PipeCompose extracts a `Text` stuff into a `str` field automatically.

---

## Phase 1 — Acceptance tests + fixtures (outside-in, all RED)

Goal: lock the contract with failing tests before any implementation.

- [ ] Confirm codec module home (proposal: `pipelex/tools/tabular/`). If unclear, ask the user (CLAUDE: place configs/modules where they fit, arbitrate if needed). Record decision in Session state.
- [ ] Sanity-check the bundle wiring with a quick dry-run (`pipelex run pipe summarize_people --library-dir <bundle> --dry-run --mock-inputs`) to confirm `PipeBatch → PipeSequence(PipeLLM + PipeCompose)` composes and `PersonSummary[]` comes out. Record any surprises.
- [ ] Create north-star fixtures: `csv_demo.mthds`, `people.csv`, `inputs.json`, and a `StructuredContent`-registering `test_structures.py` if the test bundles need Python-side classes for `Person`/`PersonSummary` (mirror `tests/integration/pipelex/pipes/pipelines/test_structures.py`). Pick the test dir (proposal: `tests/integration/pipelex/csv/`).
- [ ] Write codec **unit** tests `tests/unit/pipelex/tools/tabular/test_csv_codec.py` (RED): read→list-of-dicts with header; coercion of `integer/number/boolean/date`; empty cell→None; strict columns (extra & missing → error with field name); reject non-flat concept (clear error); write flat list→csv (header order = field order); configurable delimiter/encoding; round-trip stability.
- [ ] Write the **integration** test `tests/integration/pipelex/csv/test_csv_roundtrip.py` (RED): `PipelexRunner(...).execute_pipeline("summarize_people", inputs=<inputs.json-equivalent dict>)` in dry mode → assert `main_stuff_as_items(item_type=PersonSummary)` length matches input rows, fields present, and `Person.death_year` parsed as `None` for the blank cell; then write that list to CSV via the codec and assert header (`name,country,summary`) + rows. Mark `@pytest.mark.dry_runnable @pytest.mark.llm @pytest.mark.inference`.
- [ ] Write the **e2e** CLI test `tests/e2e/pipelex/cli/test_csv_run.py` (RED): in a tmp dir, invoke `pipelex run pipe summarize_people --library-dir <bundle> --inputs inputs.json --save-csv summaries.csv --dry-run` via subprocess; assert exit 0 and `summaries.csv` exists with header `name,country,summary` + one row per input person. Model fixtures on `tests/e2e/agent_cli/`. Mark `@pytest.mark.gha_disabled`.
- [ ] Run the new tests; confirm they fail **for the right reasons** (missing codec / missing `--save-csv` / `.csv` input not parsed), not collection errors.

### 🛑 CHECKPOINT 1 — contract locked, red for the right reasons
Verify each new test fails on the intended missing capability. Update Session state with: codec module location, bundle-vs-batch decision, exact test file paths, and the precise first implementation step. **Hard stop.**

---

## Phase 2 — Tabular codec (make the unit tests GREEN)

Goal: a self-contained, well-tested codec. No pipe-runtime coupling.

- [ ] Implement `pipelex/tools/tabular/csv_codec.py` (stdlib `csv`): `read_rows(path, *, delimiter, encoding) -> list[dict[str,str]]` and `write_rows(path, headers, rows, *, delimiter, encoding)`.
- [ ] Implement the concept binding layer (proposal `pipelex/tools/tabular/concept_table.py` or fold into codec): `list_content_from_csv(path, row_concept_or_class, ...) -> ListContent[T]` and `csv_from_list_content(list_content, path, ...)`. Resolve the row concept's `StructuredContent` subclass via the class registry; build instances with pydantic coercion; extract via `model_dump`.
- [ ] Flatness guard: inspect the row model's fields; reject any non-scalar field with an error that **names the field and the concept** and says "project to a flat concept first". Errors must carry the **file path + 1-based row/line number** for traceability (cf. keep-metadata-source rule).
- [ ] Empty-cell→None + strict column/field correspondence (extra & missing → distinct, clear errors).
- [ ] Format seam: a tiny dispatch keyed by file suffix (`.csv` built-in). `.xlsx` path raises a clear "Excel support requires `pipelex[tabular]`" error (no openpyxl dep yet). Keep it to functions, not a plugin framework.
- [ ] (Config) Add a minimal config section for default delimiter/encoding: `configs.py` (no class-level defaults; optionals=None) + `pipelex/pipelex.toml` + real values in `.pipelex/pipelex.toml`. Run `make tb` to confirm boot/config load. If this balloons, keep params with inline defaults for now and note config as a Phase-5 item.
- [ ] `make agent-check`; run codec unit tests → GREEN.

### 🛑 CHECKPOINT 2 — codec landed, unit-green, lint-clean
Update Session state. Capture the final module layout + public function signatures (the next phases call them). **Hard stop.**

---

## Phase 3 — Input integration (inputs.json `.csv` → `ListContent[row-concept]`)

Goal: a `.csv` `url` under a structured row concept loads as a typed list.

- [ ] Find the interception point where `{"concept": "...", "content": {"url": "...csv"}}` becomes a Stuff (start at `_inputs_path_resolver.py` + `working_memory_factory.make_from_pipeline_inputs` + `stuff_factory.py`). Record the exact hook in Session state.
- [ ] When the resolved `url` has a `.csv` suffix and the concept is a flat structured concept, route through the codec to produce `ListContent[row-concept]` (one CSV → one list; concept names the **row** type).
- [ ] Clear errors for: CSV bound to a non-structured/native concept, non-flat concept, header mismatch — all naming the concept and file.
- [ ] Run the integration test's input half (load inputs → assert the `people` stuff is `ListContent[Person]` with coerced fields). GREEN for input.

*(Light checkpoint — fold into CP3 unless context is large; if you stop here, update Session state.)*

---

## Phase 4 — Output integration (`--save-csv`) + close the round-trip

Goal: the headline integration + e2e tests go GREEN.

- [ ] Add `--save-csv <path>` (+ a `--csv-path` if needed) to `pipe_cmd.py`, `bundle_cmd.py`, `method_cmd.py`; thread through `_execute_run` in `_run_core.py` alongside the existing save blocks.
- [ ] On save, require the main stuff to be a flat `ListContent[StructuredContent]`; write via the codec; reject non-flat with the same clear error. Resolve the output path against `--output-dir` like the other saves.
- [ ] Run integration test → GREEN. Run e2e CLI subprocess test (`--dry-run`) → GREEN (file written, header + rows correct).
- [ ] `make agent-check`.

### 🛑 CHECKPOINT 3 — round-trip works end to end (headline milestone)
CSV in → PipeLLM → CSV out, green in dry mode via both in-process and CLI-subprocess paths. Update Session state; note any live-mode caveats. **Hard stop.**

---

## Phase 5 — Config, docs, changelog, full-suite polish

- [ ] Finalize the delimiter/encoding config if deferred from Phase 2 (`configs.py` + both `pipelex.toml` files; `make tb`).
- [ ] `CHANGELOG.md` under `## [Unreleased]` (do NOT add a versioned header — release skill does that).
- [ ] Docs: a short "CSV input & output" guide page (Material for MkDocs: blank line before lists; one-paragraph-per-line). Cover the inputs.json `.csv` convention, `--save-csv`, the flat-concept requirement, and the round-trip example. Add to `mkdocs.yml` nav.
- [ ] (Optional) a live-mode arm assertion on the integration test guarded by `if pipe_run_mode.is_live`.
- [ ] Full `make agent-check` + `make agent-test` → all GREEN. If it hangs, use `make agent-test-debug`.

### 🛑 CHECKPOINT 4 — v1 ship-ready
Everything green, docs + changelog in. Update Session state to "v1 complete". Summarize what shipped and what's deferred. **Hard stop** (ready for PR / review).

---

## ⚠️ Risks / things to confirm while implementing

- **PipeCompose field extraction** — confirm dotted-path `{ from = "person.name" }` and `Text`-stuff→`str` extraction behave as in `cv_job_match.mthds`; confirm the `PipeBatch` branch (a `PipeSequence`) sees `person` under `input_item_name`.
- **Coercion edge cases** — leading zeros, locale decimals, booleans ("true"/"1"/"yes"?), dates. Lean on pydantic's documented coercion; document, don't hand-roll. Decide the boolean/date acceptance set and note it.
- **Duplicate / blank headers** — define behavior up front (recommend: error). Add a unit test.
- **Input hook location** — the cleanest interception point for `.csv` urls is unknown until Phase 3; budget for some exploration there.
- **`--save-csv` when main stuff isn't a list** — must fail clearly, not silently no-op.
- **Don't over-build the format seam** — two functions keyed by suffix; no plugin system before xlsx exists.

## 🚫 Out of scope for v1 (deferred — see design §10)

- `.xlsx` via `pipelex[tabular]` (openpyxl) — seam only in v1.
- Streaming / out-of-core CSVs; Google Sheets / Parquet.
- Delimiter/dialect auto-detection; schema/type inference beyond the bound concept.
- A native `Table` concept / schema-free table primitive (separate language-surface decision).
