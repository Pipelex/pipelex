# Subject Grants — dropping the generic positional-subject exception

Hardens the keyword-only-arguments convention: Exception 1 (the positional subject) stops being a generic permission and becomes an **explicitly granted, recorded exception**. There is no separate design doc — this file is the authority on the design (decisions, rubric, registry format) and tracks execution state.

## Cold-start context (update at every checkpoint)

- **Status:** **PHASE 4 COMPLETE — CHECKPOINT 3 REACHED (2026-07-11). ZERO `seeded = true` entries remain across the whole registry** (`--report` proves it: `seeded remaining: 0`). All 4 remaining packages ground out this session (batches 8–11): **plugins (150 kept, 8 demoted), cli (168 kept, 47 demoted), cogt (274 kept, 7 demoted), tools (283 kept, 1 demoted)**. 1,516 grants total. Gates green after every batch (`make agent-check`) + full `make agent-test` green after every batch AND at the checkpoint. Batch commits (NOT pushed), one per batch on top of the checkpoint-2 tracker tip `a1649f269`: `ea0e642e6` (plugins), `c3aa0ee3c` (cli), `f542ba941` (cogt), `ff8bfbdc6` (tools). **CHECKPOINT 3 review IN FLIGHT:** cold no-context Sonnet `/code-review` fan-out over `a1649f269..ff8bfbdc6`, 3 agents (code-correctness, grant-judgment, mechanical-rewrite-safety) launched — triage + record `wip/subject-grants/checkpoint-3-review.md` pending. **NEXT SESSION: Phase 5 — Finalization** (delete `--seed` + `seeded`-field support, tighten registry schema, CHANGELOG breaking note, final docs pass, hand off demoted-public-surfaces to the release-gated cross-repo sweep, re-ack drift if the guard changed). Nothing pushed.
- **Resume point:** `feature/Signatures` tip in the `_sig` worktree (treat `_sig` as repo root). Working tree clean, **nothing pushed** — branch tip is `ff8bfbdc6` (tools batch 11) once the checkpoint-3 review triage lands. No branch/rebase/pull needed. Phase 5 is the only remaining work.
- **Registry state:** 1,516 grants total, **0 `seeded = true` remaining — every package fully reviewed.** Cumulative Phase-4 tally: ~1,453 kept (real rationales), ~150 demoted (defs made keyword-only, call sites fixed, entries deleted) across batches 1–11. Zero `# kw-only: ignore` hatches added. Fully-reviewed = ALL packages.
- **Rubric case-law built up over batches 1–7 (apply consistently to cli/cogt/plugins/tools):**
    - DEMOTE patterns: key+payload attachment (`set_event_log(context_key, *, event_log)` — the payload is the verb's object, the positional is a registry/target key); field-bag factories (`ConceptFactory.make(concept_code, *, domain_code, description, …)` — first field arbitrarily positional); mode/option params (`to_dict(disclosure_mode)`, `render_stuff_spec(output_format)`, `rendered_for_prompt(text_format)`, `pretty_print_*(title)`); instrumental/context params (`_evaluate_expression(working_memory)`, `_start_pipe_span(parent_otel_context)`, `render_with_images(registry)`, `_emit_via_registered_context(context)`); optional-selector-among-alternatives (`build_inputs_for_pipe(pipe_code=None, *, mthds_contents, bundle_path)`); symmetric/near-symmetric pairs (`expected`/`actual`, `domain_path`+`local_code`, `trace_name`+`trace_name_redacted`, and **same-type operand pairs** like `is_compatible(tested_concept: Concept, *, wanted_concept: Concept)` — two `Concept`s, no single candidate, demote like `copy_file(source, target)`); lone recursion accumulators (`needed_inputs(visited_pipes)`); config-first (`pipeline_run_setup(execution_config)`) and dependency-first (`load_telemetry_config(secrets_provider)`); filter/scope params (`list_models(categories)`, `validate_all(library_dirs)`); bare-literal call sites (`_get_config_file_not_found_error_msg("routing profile library")`); derived-value lookups (`_get_structure_class_import(class_name)`).
    - KEEP families: entity-keyed getters/setters/managers (hub, libraries, registries, working memory, env — `get_stuff(name)`, `set_config(config)`, `open_tracer(graph_id)`); predicates (`is_x(value)`); single-operand transformations/conversions/parsers/validators/normalizers; factories-from-source (`make_from_blueprint(blueprint)`); protocol event/payload handlers (`observe_before_run(payload)`, `run(pipe_job)`, `emit(event)`, `on_pipe_end_success(node_id, *, …)`); positional-Callable protocols (visitors, re.sub repl, tenacity before_sleep, threading.excepthook, decorators, sort keys); pytest hooks (pluggy binds by name); noun-named single-operand derivations (`page_slug(cls)`, `_make_pk(pipeline_run_id)` — id encoded, not looked up); type-directed accessors (`main_stuff_as(content_type)`, `get_items(item_type)`).
    - **job_metadata run-family demoted hierarchy-wide** (JobMetadata = information, not operand): PipeAbstract run/validate/span family + all operator/controller/signature overrides + PipeFactoryProtocol.make + factory impls. ⚠ cogt batch: `dry_mock.py`'s `__call__(self, job_metadata, *, …)` reporter protocol was deliberately LEFT positional — decide that family (report_dry_llm_job / report_mock_usage_llm_job must match the protocol) in the cogt batch; `update_job_metadata(job_metadata)` is a genuine keep (metadata IS the operand there).
    - Registry edits are done with a tomlkit script per batch (`load_toml_with_tomlkit(path)` / `save_toml_to_path(data, path=…)`); keeps = replace rationale + drop `seeded`, demotes = delete entry, guard's `dead-grant` full-scan confirms nothing dangles. Rationale style: terse but def-specific family formulas (explicitly allowed by the rubric). (Single-entry deletions can be a plain line-block delete — deletion preserves sort order; agent-check's plxt-format + cko validate the result.)
    - **Batches 8–11 learnings (plugins/cli/cogt/tools — now settled case-law):** (a) **console/logger/registry/client/secrets_provider as first param = instrumental sink/dependency → DEMOTE** even when it's the sole param — the object is in the verb name (`display_gateway_accepted_message(console)`, `InferenceBackendLibrary.load(secrets_provider)` matches the demoted `load_telemetry_config(secrets_provider)`). Consistency check: no reviewed package kept a console-as-sink grant (`PipelexHub.set_console(console)` is the lone exception — there console IS the operand being installed). (b) **`X | None = None` first positional that is a scope/location/destination/override and is often omitted or keyword at call sites → DEMOTE** (`check_config_files(config_dir=None)`, `make_pipelex_for_agent_cli(library_dirs=None)`, `generate_error_pages_cmd(output=None)`). But an **optional param that is genuinely the operand being resolved/parsed/acted-upon stays KEEP** (`_resolve_repo_root(repo_root)`, `_parse_config_arg(config_arg)`, `_end_otel_span_with_error(span)` — span is the object ended; `drift_plan_cmd(contract_id)` — contract_id is the direct object). Optionality is a *signal*, not a verdict — the discriminator is the verb-object/single-candidate test. (c) **optional-selector-among-alternatives → DEMOTE** (`make_prompt_document(uri=None, *, base64_data, raw_bytes)` — three co-equal sources; matches demoted `build_inputs_for_pipe`). (d) **positional-Callable protocols → KEEP** and this bit hard in cogt: `report_dry_llm_job`/`report_mock_usage_llm_job` are assigned as a `report_func` and called `report_func(job_metadata, ...)` positionally to satisfy `_ReportLLMJobFunc.__call__(job_metadata, *, ...)` — so job_metadata STAYS positional there (the hierarchy-wide job_metadata demote does NOT apply to protocol-satisfying reporters). Same KEEP for jinja `finalize`, `re.sub` repl, tenacity `should_retry`/`_transport_retry_wait`, Rich `__rich_repr__`, decorators (`update_job_metadata(func)`). (e) **mode/strategy selector as sole param → DEMOTE** (`get_aws_access_keys_with_method(api_key_method)` — enum match/case). (f) **bare-literal label param → DEMOTE** (`_validate_version("mthds-ui", value=...)` — name is only for the error msg, value is the real subject). (g) **Mechanical tooling that worked well (reuse for Phase-5-style sweeps):** a signature rewriter that moves the first non-self/cls positional after `*` (AST-reconstructs the param list preserving defaults/annotations; handles multiline) + a call-site fixer that inserts `<param>=` before the first positional arg at every call keyed by simple function name, run over `pipelex/` AND `tests/`, then pyright drives the checklist of remaining positional call sites. Scripts in the session scratchpad; `fko` handles single-param no-`*` defs, the rewriter handles `subject, *, opt` shapes fko can't.
    - **Checkpoint-2 review learnings (apply to cli/cogt/plugins/tools):** (a) **Protocol/ABC parity is mandatory when demoting** — if a def implements a `@runtime_checkable` Protocol or overrides an ABC, demote the interface AND every implementer together (mode-param demotes on `StuffContent`/`StuffArtefact.rendered_for_template_async` left the `TextFormatRenderable` protocol positional → type-checker-blind landmine; caught at checkpoint 2). When a demote touches a class in a not-yet-reviewed batch's file (its protocol/base), reach in and demote it too (the ImageRenderable spillover precedent). (b) `rendered_for_template_async(text_format)` joins the mode/option DEMOTE family alongside `rendered_for_prompt(text_format)`. (c) **cli batch action item:** `cli/agent_cli/commands/pipe_cmd.py::_add_type_specific_fields` (seeded) is a near-duplicate of the already-demoted `builder/operations/pipe_ops.py::add_type_specific_fields` — demote the cli twin to match. (d) A grant whose call sites ALL pass by keyword isn't automatically a demote (grants permit but don't require positional) — the disqualifier is the *single-candidate* test, not call-site style.
- **Batch execution recipe (how to grind one package — cli/cogt/plugins/tools):**
    1. `.venv/bin/pipelex-dev check-keyword-only --report` — confirm the package's seeded count (and that violations = 0 before you start).
    2. **Enumerate the batch's seeded entries.** Each `["pipelex/<pkg>/….py::<qualname>"]` with `seeded = true` in `subject_grants.toml` is one def to review. A python read is cleanest: `tomllib.load` the registry, filter keys `startswith("pipelex/<pkg>/")` where the entry still has `seeded`. (grep works too: entries are 3–4 lines, key → `param` → `rationale` → `seeded = true`.)
    3. **Review each entry** against the Rubric + the case-law above. Open the def (`path::qualname` → file+symbol), read its signature, `git grep` its call sites, then pick exactly one: **KEEP** (replace the SEEDED placeholder with a real def-specific rationale, drop the `seeded` line) · **DEMOTE** (move the subject param after the `*` — insert one if absent — on the def AND every Protocol/ABC/override sibling together, fix call sites pyright-guided, delete the entry) · **HATCH** (rare: `# kw-only: ignore` on the def line for framework-positional shapes, delete the entry).
    4. **Apply registry edits** with a tomlkit script (`from pipelex.tools.misc.toml_utils import load_toml_with_tomlkit, save_toml_to_path`) — batch all keeps/demotes for the package in one pass; keeps mutate `rationale` + delete the `seeded` key, demotes `del data[key]`. Single-entry deletions may instead be a plain line-block Edit (deletion preserves sort order). Never hand-roll tomlkit (D10).
    5. **Gate:** `make agent-check` (runs fko → format → lint → pyright → mypy → cko; cko's dead-grant full-scan confirms nothing dangles). Run targeted tests for touched areas; run **full `make agent-test` if the batch demoted ANY framework-adjacent def** (Protocol/callback/Jinja/Typer/pytest-hook — pyright is blind to those, per the Risks section).
    6. **Commit** one per batch: `Subject grants batch N: review <pkg> (X kept, Y demoted)`. Do NOT push. Update this file's Status line (seeded-remaining + commit SHA) as you go, or at the next checkpoint.
    ⚠ **Protocol/ABC parity (checkpoint-2 learning, bites silently):** demoting a def that implements a `@runtime_checkable` Protocol or overrides an ABC MUST demote the interface + every implementer in the same commit — even when the interface lives in a not-yet-reviewed file (reach in, `*`-it, delete its seeded grant). Leaving the interface positional while impls are keyword-only is a type-checker-blind landmine (exactly the two defects checkpoint 2 caught).
- **Deviations from the plan (all deliberate):**
    - The seed NEVER enters literal-typed subjects (rather than seeding then removing them) — they can never be granted (D4), so seeding them would only create entries destined for deletion. Same end state, no dead entries.
    - `--report` grant/seeded progress meter lives in `check-keyword-only --report`; violation kinds are `missing-star` / `ungranted-subject` / `literal-subject` / `grant-param-mismatch` (def-level, lean path sees it) / `dead-grant` (full-scan only — covers deleted, renamed, demoted-to-all-keyword, and newly-carved-out defs).
    - `SubjectGrantRegistryError` is defined IN `keyword_only_guard.py` (not an `exceptions.py`): the lean hook path cannot import a sibling module without dragging the `pipelex` package chain. It is a plain `Exception` subclass, not a `PipelexError` (no error page needed; `make gep` not required).
    - TWO drift contracts opened (not one): `cli-docs` also triggered because the literal sweep touched `pipelex/cli/**`. Both acked genuinely; dogfood log has a real-catch (keyword-only-convention) + a clean-pass (cli-docs) entry.
    - The workspace-root `.claude/rules/python-standards.md` keyword-only section was spliced from the kit source by hand (section-only replacement — the rest of that file tracks dev, which is ahead of this branch on Python-3.10-drop wording; do NOT copy the whole kit file over it).
- **Branch / worktree:** `feature/Signatures` in the `_sig` worktree (branched off `docs/Update`). Treat `_sig` as the repo root. This file replaced the drift-contracts tracker inherited from `docs/Update` — that plan lives on in the `docs/Update` branch history and is in its dogfood phase; not this project's concern.
- **Problem being solved:** the guard mechanically allows ANY first non-`self`/`cls` parameter to stay positional-or-keyword. Coding agents abuse that judgment-shaped permission, leaving first arguments positional when they are not the subject or not obviously so. The check must stay deterministic, but the exception must become deliberate, recorded, and reviewable — and **every existing positional subject is considered new: seeded into the registry unreviewed, then actually checked** (Phase 4).
- **The shape in one paragraph:** a committed registry (`subject_grants.toml` at repo root) lists every def allowed a positional subject, with the subject param name and a one-sentence rationale. `check-keyword-only` fails on any positional subject without a matching grant, on any grant without a matching def (staleness is symmetric), and on any literal-typed positional subject regardless of grant. `make fko` already rewrites to the all-keyword form, so the lazy path is the strict path; keeping a positional subject costs a deliberate `subject-grant` command with an honest rationale, visible as a registry diff in every PR. Judgment happens at grant time and in review of the registry diff — CI stays 100% deterministic (no LLM in any gate, ever).

### Decisions (settled — do not relitigate without Louis)

- **D1 — Generic exception dropped.** A positional-or-keyword subject is legal only when a subject grant exists for that def. No grant → violation; `fko` auto-fixes it to all-keyword.
- **D2 — Registry** = `subject_grants.toml` at repo root. One entry per def, keyed `<relative_path>::<qualified_name>` (exactly the guard's `Violation.key` format), recording `param` (the subject's name) and `rationale`. The file is rewritten sorted by key on every change so diffs are stable and merge conflicts stay trivial.
- **D3 — CI stays deterministic.** No model verdict in any gate. The guard only verifies grant existence, param match, and freshness. The judgment lives in the grant rationale and in PR review of the registry diff (drift-ack spirit: an honest sentence, on the record).
- **D4 — Literal-typed subjects banned outright**, grant impossible: a subject annotated `bool`, `int`, or `float` (including `X | None` / `Optional[X]` forms of those) is a violation no matter what. `f(True)` call sites are never acceptable. `str` subjects stay grantable — they are the house style (`pipe_code`, `name`, `uri`, …).
- **D5 — Strict-all scope.** Grants are required for every positional subject: lone-subject defs (`def render(node)`) and subject-plus-kwonly defs (`def f(spec, *, ...)`) alike. Relaxing later (e.g. exempting lone-subject defs) is trivial; re-tightening later reopens ~1,000 defs — so start strict.
- **D6 — All existing positional subjects are treated as NEW.** Seeded into the registry with `seeded = true` and a placeholder rationale, then every one is genuinely reviewed in Phase 4: real rationale (keep), or converted to keyword-only (demote), or `# kw-only: ignore` (rare, framework-positional). Zero `seeded` entries may remain at finalization.
- **D7 — Staleness is symmetric and hard-fails.** Positional subject without grant = violation. Grant whose def no longer exists, or whose recorded `param` no longer matches the def's first param = violation. Renames and file moves therefore force a re-grant — that is a deliberate re-decision, not friction to engineer away.
- **D8 — Existing mechanisms unchanged.** `# kw-only: ignore` (stronger hatch, short-circuits before the rule — required for framework-positional callables), the symmetric-tuple allowlist (whole-function, stays curated in code, NOT merged into the registry — different semantics), all carve-outs, and `fko`'s insert-leftmost behavior. Note `fko`'s reach grows: an ungranted subject def is now a violation, so `fko` (which runs inside `make agent-check`) will silently kwonly it — grant BEFORE running checks if you want the subject positional.
- **D9 — `/` (positional-only) stays banned.** The convention doc's deliberate no-`/` decision stands; callers keep keyword discretion on granted subjects.
- **D10 — Hook budget preserved.** The lean single-file path (`keyword_only_guard.py` run by file path from the PostToolUse hook) stays stdlib-only: it reads the registry with `tomllib` (read-only, machine-written file — the tomli-error-attrs concern applies to user-config parsing, not here). Registry writes happen only in the full CLI via `pipelex/tools/misc/toml_utils.py` (`load_toml_with_tomlkit` / `save_toml_to_path` — do not hand-roll tomlkit).
- **D11 — Same-qualname defs share one entry.** `@overload` stubs and conditional redefinitions collapse onto one key; the recorded `param` must match each of them (forces overload stubs to align their subject name — acceptable).

### Scan snapshot (2026-07-10 — point-in-time measurements, they WILL drift; regenerate via the Phase 1 `--report` extension)

- ~2,600 defs inspected by the guard (after carve-outs); ~650 of them take no params.
- **~1,700 use Exception 1 today** (~1,000 lone-subject, ~700 subject-plus-kwonly) — roughly 9 in 10 param-bearing inspected defs. The stock is the house style and looks overwhelmingly legitimate (top subject names: `name`, `pipe_code`, `exc`, `value`, `path`, `content`, `data`, `node`, …) — which is why the stock is seeded-then-reviewed rather than mass-demoted.
- ~220 defs are already fully keyword-only; zero use `/`; a handful of `# kw-only: ignore` hatches.
- **~30 literal-typed subjects** (`bool`/`int`/`float`, e.g. `do_doctor_cmd(fix: bool)`) — the mechanically-catchable slice of exactly the abuse this project kills. Beware: some are framework-positional (`version_callback(value: bool)` is invoked positionally by Typer via `callback=` — pyright is blind to that; `make agent-test` is the safety net).

### Key repo facts (verified 2026-07-10)

- Guard core: `pipelex/cli/dev_cli/commands/keyword_only_guard.py` (pure stdlib; `_evaluate_def` order = dunder → escape hatch → decorator carve-outs → typer-annotation → symmetric allowlist → rule). Presentation layer: `check_keyword_only_cmd.py`. Hook: `.claude/hooks/check-keyword-only.sh` invokes the guard **by file path** (never `-m` — that would import the `pipelex` package chain and blow the cold-start budget).
- `make fko` inserts the bare `*` leftmost (all-keyword form) and is non-gating; read-only `make cko` owns the gate and runs last in `agent-check`, in `make check`, and as the `lint-keyword-only` CI job (aggregated by `lint-all`).
- Convention doc: `docs/contribute/keyword-only-arguments.md`. **Drift contract `keyword-only-convention`** (in root `drift.toml`) triggers on the guard file with that doc as review target → Phase 3 must stage the trigger and `make drift-ack CONTRACT=keyword-only-convention RATIONALE="…"` after genuinely updating the doc. The new dev-CLI command sits under `pipelex/cli/dev_cli/**`, which the `cli-docs` contract excludes — only the one contract opens.
- Dev CLI house style: Typer wrapper in `_dev_cli.py` delegating to a keyword-only `*_cmd()` in the module; CI-gate idiom prints a rich panel then `sys.exit(1)` (see `check_config_sync_cmd.py`). Unit tests: `tests/unit/pipelex/cli/dev/`, inline-source style (`find_violations_in_source` on snippets); a reusable `git_repo` fixture already exists in that conftest (built by the drift project) if needed.
- If new CLI error classes are added (grant-command failures), they go in an `exceptions.py` per house rules and require `make gep` (error-pages regeneration) in the same commit.
- Agent-rules source: the keyword-only section of `.claude/rules/python-standards.md` (workspace root) is generated from the kit rules source in this repo — edit the kit source, then regenerate (`make rules` family), never the generated file.
- Makefile: per-target + shorthand-alias pattern (`check-keyword-only`/`cko`); `.PHONY` is one block. mkdocs nav lists contribute docs in TWO places in `mkdocs.yml` — update both if a doc is added (none planned; the convention doc already exists).

## Checkpoint protocol (mandatory at every CHECKPOINT below)

1. **Verify:** the phase's gates green — `make agent-check`, full `make agent-test` (targeted tests are fine between checkpoints), plus the checkpoint's specific gates. Do not proceed with failures.
2. **Commit** the phase's work as one coherent commit (do not push unless asked).
3. **Update this file** — tick boxes, refresh Cold-start context (status, decisions, deviations, commit SHAs) so a brand-new session resumes with zero conversation context.
4. **Fan out `/code-review`** — a fresh no-context Sonnet sub-agent (Agent tool, `general-purpose`, `model: sonnet`, never a fork) pointed only at the commit range; never hand it this plan or your own conclusions.
5. **Triage findings:** fix real defects; findings that are design tradeoffs get captured in a deferred-items doc under `wip/subject-grants/`, not reflexively applied.
6. **STOP** — natural handoff point.

## Rubric — what earns a grant

Applies to every Phase 4 review and every future grant. Formalized into the convention doc in Phase 3; until then this section is the reference.

A subject grant is warranted when EITHER:

- **Verb–object test:** the function name is a verb (phrase) and the param is its direct object — the call reads as a sentence (`render(node)`, `validate_bundle(bundle)`, `parse_concept_spec(spec_data)`) — AND it is the **single candidate** (if you hesitate between two params, neither is the subject) — AND typical call sites pass a **self-labelling expression**, never a bare literal (literal-typed subjects are banned by D4 anyway);
- OR the def must satisfy a **positional `Callable` protocol** (it is passed as a value to something that calls it positionally) and a grant keeps it compliant without reaching for the heavier `# kw-only: ignore`.

When in doubt → keyword-only. The grant is the exception tier; all-keyword is always compliant and often more readable. Rationales must be def-specific but may be terse for obvious keeps ("verb–object; single operand") — the value is that someone actually looked; copy-paste boilerplate across dozens of entries defeats the point and is what Louis will spot-check for.

## Registry format

```toml
version = 1

["pipelex/graph/render.py::render_node"]
param = "node"
rationale = "Verb–object: renders the node; single obvious operand."

# Transitional shape during Phases 2-4 only (rejected entirely by the guard after Phase 5):
["pipelex/foo/bar.py::SomeClass.some_method"]
param = "spec"
rationale = "SEEDED 2026-07 — pre-registry tree, treated as new, review pending"
seeded = true
```

Schema after finalization: exactly `param` + `rationale` per entry, `version` at top; unknown keys are a check failure.

## Phase 1 — Mechanism: guard + registry + commands

- [x] Guard core (`keyword_only_guard.py`, stays stdlib-only): load `subject_grants.toml` from repo root (`tomllib`); missing registry file = explicit check error (not mass-violation). New rule: a positional-or-keyword subject requires a matching grant (key + `param`); a literal-typed subject (D4) is a violation even with a grant; grants with no matching def or mismatched `param` are check failures. `# kw-only: ignore` keeps short-circuiting everything (existing evaluation order).
- [x] Distinct violation messages per kind — "ungranted positional subject" / "banned literal-typed subject" / "stale grant" — each naming its fix (`make fko`, `make subject-grant FUNC=… RATIONALE=…`, or registry cleanup). Update the lean `main()` hook message text too.
- [x] `pipelex-dev subject-grant "<path>::<qualname>" --rationale "…"`: validates the def exists, its first non-`self`/`cls` param is positional-or-keyword and not literal-typed, rationale non-empty; records `param` automatically; rewrites the registry sorted. Make target `subject-grant` (+ short alias, e.g. `sgr`), following the existing per-target pattern.
- [x] Temporary `--seed` mode on `subject-grant` (deleted in Phase 5): scan the tree, emit an entry for every existing positional subject with `seeded = true` + the placeholder rationale.
- [x] Extend `check-keyword-only --report`: per-package grant totals and seeded-remaining counts — this is the Phase 4 progress meter.
- [x] Verify `fko` handles the new violation kind (it already inserts `*` leftmost; ungranted subject defs must be mechanically fixable; the re-parse-before-write guarantee is unchanged).
- [x] Unit tests (inline-source style + injected registry content): grant match / missing grant / param mismatch / dead entry / seeded accepted (transitional) / literal ban incl. union and Optional forms / ignore-hatch precedence / same-qualname sharing (D11) / lean single-file path reads the registry / sorted-write round-trip / grant-command refusals (literal subject, non-positional subject, empty rationale, missing def).
- [x] New code itself passes the convention; new error classes (if any) in `exceptions.py` + `make gep`.

## Phase 2 — Seed + literal-subject sweep (lands atomically with Phase 1 — the tree must never gate red)

⚠ **Ordering hazard:** between flipping the guard and committing the seed, NEVER run `make fko` / `make agent-check` on the tree — the fixer would kwonly ~1,700 defs. Generate the seed first (standalone scan), commit guard + registry together.

- [x] Run `--seed`, commit the registry: every existing positional subject enters as `seeded = true`.
- [x] Sweep the literal-typed subjects (~30 per snapshot): kwonly each (fix call sites, pyright-guided), EXCEPT framework-positional ones (Typer `callback=`, etc.) which get `# kw-only: ignore` with a nearby justification. Remove their seed entries. `make agent-test` is the safety net for the pyright-blind cases.
- [x] Gates green: `make agent-check`, `make agent-test`, `make cko`.

## Phase 3 — Docs, rules, drift-ack (before the grind — mid-grind sessions must read the NEW convention, not the stale one)

- [x] Rewrite `docs/contribute/keyword-only-arguments.md`: Exception 1 becomes "granted subjects" (registry, commands, staleness semantics, D4 literal ban), add the rubric verbatim, record the reversal honestly (generic permission → explicit grant, and why: agents follow checks, not prose). Keep the no-`/` decision section (D9).
- [x] Update the kit rules source for the keyword-only section (the generated `.claude/rules/python-standards.md` block) + regenerate; update the summary block in this repo's `CLAUDE.md`.
- [x] Drift: stage the trigger files, then `make drift-ack CONTRACT=keyword-only-convention RATIONALE="…"` — a genuine review, and a real dogfood data point for the drift system (log it via the drift-review skill's dogfood log).

### CHECKPOINT 1 — mechanism live, seeded, documented

Everything except the grind is done and reviewed as one unit. Gates: full checkpoint protocol + `make check` end-to-end (includes `drift-check`) + mkdocs strict build if docs changed.

## Phase 4 — The review grind (every seeded grant treated as new)

Batch by top-level package (`pipelex/core`, `pipelex/builder`, `pipelex/cli`, `pipelex/cogt`, …), sized via `--report` — expect on the order of 10–15 batches for ~1,700 entries. This phase is the dominant cost of the project.

Per seeded entry, apply the rubric and pick exactly one:

- **Keep:** replace the placeholder with a real, def-specific rationale; drop `seeded`.
- **Demote:** convert the def to all-keyword (`*` leftmost), fix call sites (pyright-guided), delete the entry.
- **Hatch (rare):** `# kw-only: ignore` when the positional shape is framework-owned; delete the entry.

Rules of engagement:

- [x] Each batch is one commit, gates green (`make agent-check` + targeted tests; full `make agent-test` at checkpoints and after any batch that demoted framework-adjacent defs). — done for all 11 batches; full agent-test run after each of batches 8–11.
- [x] Expect drift toward all-keyword — that is desired; grants are the luxury tier. — confirmed: ~150 demoted, ~1,453 kept overall.
- [x] **Demoted public surfaces:** appended below (see the new batch-8–11 entries). No backward compat, but the breakage is inventoried for the release-wave cross-repo sweep.

Demoted public surfaces (append as you grind — the Phase 2 literal sweep already demoted these; external consumers calling them positionally break):

- `pipelex.tools.misc.string_utils.pluralize` / `count_with_noun` — `count` now keyword-only
- `pipelex.tools.log.log.Log.set_level_by_int` (`level_int`) and `pipelex.tools.log.log_levels.LogLevel.from_int` (`logging_level`)
- `pipelex.tools.misc.pretty.PrettyPrinter.pretty_width` (`width`)
- `pipelex.hub.PipelexHub.set_dry_run_forced` (`is_forced`)
- `pipelex.cli.installed_methods.discover_installed_methods` (`include_global`)
- `pipelex.cli.commands.init.config_files.init_config` (`reset`)
- `pipelex.system.telemetry.*.is_custom_portkey_logging_enabled` / `is_pipelex_gateway_portkey_logging_enabled` (`is_debug_configured`; internal callers already keyword)
- `pipelex.plugins.anthropic.anthropic_factory.AnthropicFactory.calculate_safe_max_tokens_for_timeout` (`timeout_seconds`)
- `pipelex.runtime_bridge.bootstrap.ensure_pipelex_booted` (`config_overrides`) — runtime_bridge is consumed by pipelex-api / pipelex-worker; positional callers break
- `pipelex.builder.operations` entry points `build_inputs_for_pipe` (`pipe_code`), `list_models` (`categories`), `validate_all` (`library_dirs`) — agent-CLI/MCP plumbing, but importable
- `pipelex.errors.error_pages_generator.generate_error_pages` (`output_dir`) — dev tooling, listed for completeness
- `pipelex.reporting` protocol methods `set_event_log` / `clear_event_log` (`context_key`) — external ReportingProtocol implementations must match
- `pipelex.core.pipes.pipe_abstract.PipeAbstract` run-family (`run_pipe`, `live_run_pipe`, `dry_run_pipe`, `validate_before_run`, `validate_after_run`, `needed_inputs`) — `job_metadata` / `visited_pipes` now keyword-only; any external code subclassing or invoking pipes positionally breaks
- `pipelex.core.stuffs.stuff_content.StuffContent.rendered_for_prompt` / `rendered_for_template_async` (`text_format`) and `pretty_print_content` (`title`) — public content API; positional TextFormat callers break
- `pipelex.libraries.library_manager_abstract.LibraryManagerAbstract` load family (`load_libraries`, `load_from_blueprints`, `load_from_crate`, …) — `library_id` now keyword-only
- `pipelex.pipeline.pipeline_run_setup.pipeline_run_setup` (`execution_config`) and `pipelex.pipeline.pipeline_manager_abstract.add_new_pipeline` (`pipe_code`)
- `pipelex.tools.jinja2.image_renderable.ImageRenderable.render_with_images` (`registry`) — protocol + all content-class implementations
- CLI-internal helpers (doctor/show/update/validate `*_cmd` delegates and UI builders) — almost certainly not called externally, listed for completeness in the diff, not here
- `pipelex.tools.jinja2.text_format_renderable.TextFormatRenderable.rendered_for_template_async` (`text_format`) — `@runtime_checkable` protocol; external implementers/positional callers break (checkpoint-2 spillover completion)
- `pipelex.libraries.concept.concept_library_abstract.ConceptLibraryAbstract.is_compatible` / `concept_library.ConceptLibrary.is_compatible` (`tested_concept`) — external code subclassing or calling `is_compatible` positionally breaks (checkpoint-2 demote)
- **Batch 8–11 demoted public surfaces (external consumers calling positionally break):**
  - `pipelex.cogt.image.prompt_image_factory.PromptImageFactory.make_prompt_image` (`uri`) and `pipelex.cogt.document.prompt_document_factory.PromptDocumentFactory.make_prompt_document` (`uri`) — public content factories; positional-`uri` callers (cookbook, cocode, app) break
  - `pipelex.cogt.models.model_manager_abstract.ModelManagerAbstract.setup` + its `ModelManager.setup` override (`secrets_provider`) and `pipelex.cogt.model_backends.backend_library.InferenceBackendLibrary.load` (`secrets_provider`) — external code subclassing/invoking the model-manager setup/backend-load positionally breaks (dependency-first demote, matches `load_telemetry_config`)
  - `pipelex.cogt.llm.llm_setting.LLMSettingChoices.make_completed_with_defaults` (`for_text`) and `pipelex.cogt.model_routing.routing_profile.RoutingProfile.get_backend_match_for_model` (`enabled_backends`)
  - `pipelex.tools.aws.aws_config.AwsConfig.get_aws_access_keys_with_method` (`api_key_method`) — mode selector
  - The remaining batch-8–11 demotes are CLI-internal / plugin-internal helpers (list_*_models, discovery register helpers, console UI, doctor check_*, run/validate/build cores, gateway `_call_relay`) — not part of the importable `pipelex` public API; listed in the commit diffs, not here.

### CHECKPOINT 2 — mid-grind (after roughly half the batches) ✅ DONE 2026-07-10

Full checkpoint protocol completed. Gates green (`make agent-check` + full `make agent-test`, run twice — before and after the review fixes). Cold no-context Sonnet `/code-review` fan-out over `9f5bd54a3..227b98822` (4 agents) ran and was triaged: two real interface/impl-parity defects fixed in `f10b9ad37` (TextFormatRenderable protocol spillover, is_compatible near-symmetric demote), one low-confidence rationale deferred, test changes clean. Record: `wip/subject-grants/checkpoint-2-review.md`. Seeded-remaining count and rubric learnings updated in the Cold-start context above. NEXT: grind cli / cogt / plugins / tools.

### CHECKPOINT 3 — grind complete ✅ REACHED 2026-07-11

Zero `seeded = true` entries remain (`--report` confirms `seeded remaining: 0`). Gates green: `make agent-check` + full `make agent-test` green at the checkpoint (and after each of batches 8–11). Batches 8–11 committed (`ea0e642e6` plugins, `c3aa0ee3c` cli, `f542ba941` cogt, `ff8bfbdc6` tools). Cold no-context Sonnet `/code-review` fan-out over `a1649f269..ff8bfbdc6` (3 agents: code-correctness, grant-judgment, mechanical-rewrite-safety) launched — triage + `wip/subject-grants/checkpoint-3-review.md` record pending. NEXT: Phase 5 finalization.

## Phase 5 — Finalization

- [ ] Delete `--seed` and all `seeded`-field support; tighten the registry schema (exactly `param` + `rationale`; unknown keys fail the check).
- [ ] CHANGELOG `[Unreleased]`: convention hardened (grants registry, literal-subject ban) + breaking note covering the demoted signatures.
- [ ] Final docs pass (convention doc reflects the post-transitional state; no `seeded` mentions survive); re-ack drift if the guard changed again.
- [ ] Hand off the demoted-public-surfaces list to the release-gated cross-repo sweep (house pattern).
- [ ] Full gates: `make check` end-to-end + `make agent-test`. Update Cold-start context to COMPLETE.

## Risks & safety nets

- **Framework-positional callers** (Typer `callback=`, Jinja filters, SDK hooks): pyright passes a wrongly-kwonly'd callback; `make agent-test` is the net — mandatory after the Phase 2 sweep and any suspicious Phase 4 demotion.
- **fko-before-seed hazard** (Phase 2 warning above) — the one truly destructive misstep; land guard + seed atomically.
- **Rubber-stamp risk in the grind:** rationale honesty can't be mechanized. Mitigations: def-specific rationale rule, Louis spot-checks registry diffs, batches small enough to review for real.
- **Registry merge conflicts** across parallel branches: sorted, append-mostly file; conflicts resolve trivially, same as the drift manifest.
- **Hook cold-start budget:** one `tomllib` read of a machine-written file — negligible; keep the lean path import-clean (no tomlkit there).

## Out of scope

- Any LLM verdict inside CI (D3 — permanent).
- Other repos' conventions; the conformance suite (this is repo-internal dev tooling, no cross-repo spec surface).
- Retro-fitting the symmetric-tuple allowlist into the registry (D8 — different semantics, stays in code).
