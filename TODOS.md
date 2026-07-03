# Drift Contracts — implementation plan

Implements [wip/drift-contracts-design.md](wip/drift-contracts-design.md). Read that design doc first — it is the authority on semantics (validity rule, manifest schema, ack format, command behaviors). This file tracks execution state.

## Cold-start context (update at every checkpoint)

- **Status:** Not started. Plan written, no code yet.
- **Branch / worktree:** `docs/Update` in the `_docs` worktree (the design doc landed here in `122ffd6f3`). Treat `_docs` as the repo root.
- **Key repo facts** (verified against the tree — three claims from the first draft were WRONG and are corrected here):
    - Dev CLI commands live in `pipelex/cli/dev_cli/commands/`, registered in `pipelex/cli/dev_cli/_dev_cli.py`. The `kit` sub-app (`app.add_typer(kit_app, name="kit")`, `_dev_cli.py:77`) is the one command-group precedent — `drift` follows it. House style is two-layer: a Typer wrapper in `_dev_cli.py` delegating to a keyword-only `*_cmd()` in the module; the CI-gate idiom (`check_config_sync_cmd.py`) prints a rich panel then `sys.exit(1)`.
    - Dev CLI unit tests live under `tests/unit/pipelex/cli/dev/`. **CORRECTION: no git-temp-repo fixture exists**, and there is **no `check-config-sync` test to copy** — existing check tests use inline source snippets (`find_violations_in_source`), not temp repos. A reusable `git_repo` conftest fixture is net-new (see Phase 1 test notes). With the pure-core/adapter split most tests stay pure-Python; only the adapter needs the fixture.
    - **CORRECTION: TOML I/O reuses `pipelex/tools/misc/toml_utils.py`** (`load_toml_with_tomlkit` to read `drift.toml`, `save_toml_to_path` to write ack files) — do NOT hand-roll raw `tomlkit` (that idiom is reserved for the agent-CLI *emitters* that synthesize commented documents). `tomlkit` (≥0.13.2) and `tomli` are direct deps.
    - **No git-subprocess helper exists anywhere in `pipelex/`** — the drift git adapter is net-new and needs its own tests. Mirror the `subprocess.run(..., capture_output=True, text=True, timeout=..., check=False)` idiom with `# noqa: S603/S404` from `cli/commands/init/ide_extension.py:36-47`.
    - Makefile: the `check` aggregate is at `Makefile:1081`; per-target pattern with shorthand alias is e.g. `check-config-sync`/`ccs` (`Makefile:323-328`); `.PHONY` is one block (`Makefile:196`). **CORRECTION: CI runs check targets as separate JOBS, not steps** — `lint-check.yml` has `lint-config-sync` / `lint-keyword-only` jobs and a `lint-all` aggregator (`needs: [...]`) that is the single required status check. A new gate is a new job **plus** (only when promoted from advisory to required) an entry in `lint-all`'s `needs`.
    - Contribute docs live in `docs/contribute/`; mkdocs nav references them in **two places** in `mkdocs.yml` (~lines 324 and 555) — update both.
    - Keyword-only convention applies to all new code (`make agent-check` enforces).
- **Decisions taken** (from the `/plan-eng-review` on 2026-07-03 — these override any conflicting wording in the design doc; the design doc will be corrected to match):
    1. **Digest source = index/staged blob OIDs**, read via a single `git ls-files -s` over matched trigger paths — NOT working-tree bytes via `git hash-object`. Matching and hashing come from the same index source (no working-tree leak), it is filter-normalized (CRLF/smudge safe), it IS "what lands in the commit" (the design's own stated goal), and there is no ARG_MAX concern. **Cost: `git add` the trigger files before `drift ack`** (stage, not commit; other unstaged changes are fine). This supersedes the design's `git hash-object` wording and resolves the codex #1/#3/#21 tree-state findings.
    2. **Contract digest canonicalization = normalized pydantic model → canonical JSON.** Parse `drift.toml` into the manifest model, then hash a canonical JSON dump of the contract: sorted object keys AND sorted glob lists, with the `(path, oid)` pairs as a nested JSON structure — never string concatenation (no delimiter-framing footgun). Defaulted/empty fields (missing `exclude` == `[]`) normalize identically. Reordering globs or reformatting `drift.toml` must NOT change the digest.
    3. **Engine layering = pure core + thin git adapter.** A pure module (glob-match over a given file list, digest over given `(path, oid)` pairs, plan-diff, check-compare) that takes injected data, plus one thin git adapter (`git ls-files` / `git ls-files -s`). Most tests are fast pure-Python on literals; only the adapter needs the `git_repo` fixture. Mirrors the `keyword_only_guard.py` pure-core idiom. This makes `commands/drift/` a genuine package (`core.py` + `git_adapter.py` + `models.py` + `drift_cmd.py`).
    4. **verify_commands = argv via `shlex.split`, no shell.** Each string is `shlex`-split and run with `shell=False`. Run from repo root, inherit env, stop at first failure, surface captured output when one aborts the ack. No `&&`/pipes (verify_commands are single targeted checks by design).
    5. **Rollout = advisory first, then promote.** Phase 2 adds the drift CI job but leaves it OUT of `lint-all`'s `needs` (runs + visible, does not block merges) plus `drift-check` in `make check` locally. Promote into `lint-all`'s `needs` once the current open-PR backlog lands. Reason: the seed triggers cover hot paths and the workspace has a large active-branch backlog that would eat fresh CI failures on next dev-merge.
    6. **Scope accepted as-is** — keep `plan`'s per-file trigger-diff in Phase 1 (highest-value packet content, cheap with CC).
- **Cross-model tensions — KEPT AS DESIGNED** (codex pushed on these; decision is to keep the design and let dogfooding rule): no-skip-verify (capture an audited-skip idea as a deferred item only), broad `cli-docs` trigger, three seeds vs a one-contract spike, the checkpoint `/code-review` protocol, and strict TDD (TDD the engine logic; test-after is fine for Typer wiring / rich-panel formatting). `config-docs` trigger breadth is a **dogfood-watch** item (candidate to narrow to `configs.py` + `config_model.py` + `pipelex.toml` if it opens on config plumbing edits).
- **Open questions:** (none blocking — the audited-skip-verify escape hatch is deferred, not open)

## Checkpoint protocol (mandatory — applies to every checkpoint below)

At each checkpoint the agent MUST STOP and, in order:

1. **Verify progress.** Run the phase's gates (listed per checkpoint). Do not proceed with failures.
2. **Commit the phase's work** (one coherent commit; do not push unless asked).
3. **Update this file** — tick the boxes, refresh the "Cold-start context" section (status, decisions, open questions, commit SHAs) so a brand-new session can resume with zero conversation context.
4. **Fan out `/code-review`** — spawn a Sonnet-5 sub-agent (Agent tool, `subagent_type: general-purpose`, `model: sonnet` — a fresh agent, **never** a fork) whose prompt instructs it to run the `/code-review` skill. **No inherited context:** the prompt hands it only a pointer to the changes under review (the phase's commit range, e.g. `git diff <sha-before>..<sha-after>`, or the working-tree files) — never this plan, the design doc rationale, or your own conclusions. The review goal is clean solid software, not over-engineering.
5. **Triage findings.** Fix real defects and over-engineering flags; commit the fixes. Findings that are design tradeoffs rather than defects get captured in a deferred-items doc under `wip/drift-contracts/` (fold the design doc into that folder with a README if it becomes multi-doc), not reflexively applied.
6. Only then continue to the next phase — or end the session; this is a natural handoff point.

---

## Phase 1 — engine (`pipelex-dev drift plan|check|ack`)

Everything in `pipelex/cli/dev_cli/commands/drift/` (a genuine package — the pure-core/adapter split earns it), no Makefile or CI wiring yet. **TDD the engine logic** (models, digest, matching, plan-diff, check-compare) — red-green per component. Test-after is acceptable for the Typer wiring and rich-panel formatting.

**Module layout (Decision 3 — pure core + thin git adapter):**

- `models.py` — manifest + ack pydantic models, with contract-ID charset validation.
- `git_adapter.py` — the ONLY git-touching module: `git ls-files` (matching set) and `git ls-files -s` (staged OIDs for matched paths). `subprocess.run(..., text=True, timeout=..., check=False)` + `# noqa: S603/S404`. Tested against the `git_repo` fixture.
- `core.py` — pure functions over injected data: glob-match a given file list, digest over given `(path, oid)` pairs + canonical contract JSON, plan-diff (stored map vs current), check-compare. Fast pure-Python tests on literals, no git.
- `drift_cmd.py` — Typer sub-app (three commands), wires core + adapter, presentation only.

### 1a. Skeleton and models

- [ ] Create the `drift/` package with the four modules above (merge only if two stay trivially small; do not add speculative ones).
- [ ] Manifest models per the design: `version`, `[contracts.<id>]` with `description`, `triggers`, `exclude` (defaults to `[]`), `review`, `verify_commands` (defaults to `[]`). Read `drift.toml` from the git toplevel via `toml_utils.load_toml_with_tomlkit`; schema-invalid manifest is a hard error with an actionable message. **Validate contract IDs** against a safe charset (`[a-z0-9-]+`) since they become filenames AND TOML table keys.
- [ ] Ack model per the design: `contract`, `digest`, `reviewed_by`, `reviewed_at`, `rationale`, `[trigger_files]` path→OID map. One file per contract at `.drift/acks/<contract-id>.toml`; read with `toml_utils.load_toml_with_tomlkit`, write with `toml_utils.save_toml_to_path` via a temp file + atomic `os.replace` (concurrency-safe).

### 1b. Digest engine (Decision 1 + 2)

- [ ] File matching (pure `core.py`): triggers/exclude globs evaluated against the injected `git ls-files` set (tracked files). Pin the semantics: directory review target (`docs/tools/cli/`) resolves iff ≥1 tracked file lives under it; trailing slashes normalized; matching is case-sensitive per POSIX; symlinks are not followed.
- [ ] Content hashing (`git_adapter.py`): staged blob OIDs via **one** `git ls-files -s <matched-paths>` call — matching and hashing share the index source. NOT `git hash-object`, NOT working-tree bytes. No ARG_MAX exposure (pathspecs), filter-normalized.
- [ ] Contract digest (pure `core.py`): `sha256` over a **canonical JSON** document — the normalized pydantic contract (sorted keys, sorted glob lists) plus the sorted `(path, oid)` pairs as nested JSON. Deterministic across runs, `drift.toml` reformatting, comment edits, and glob reordering.
- [ ] Tests: **pure-core** (no git) — digest stability across runs; digest stability across manifest reformatting/comments; **glob-list REORDER → SAME digest** (the executable proof of Decision 2); contract-definition change → digest change; defaulted-vs-explicit-empty `exclude` → SAME digest. **Adapter** (git_repo fixture) — trigger edit/add/delete/rename → OID/digest change; a staged edit is reflected, an unstaged edit is NOT (index semantics); `git ls-files -s` output parsed correctly.
- [ ] Build the reusable `git_repo` pytest fixture (`git init` + commit in `tmp_path`) in a dev-CLI `conftest.py` — net-new, foundational for every adapter/command test.

### 1c. `drift check` (the pure gate)

- [ ] Validates: manifest parses and is schema-valid; contract IDs are unique and charset-valid; every trigger glob matches ≥1 tracked file (dead glob = hard error); **every review target resolves the same way (a review glob/path matching zero tracked files is an equally hard error — rot symmetry)**; every contract has an ack; **every ack file maps to a manifest contract (orphan ack = hard error) and its `contract` field equals its filename stem**; every ack digest equals the recomputed digest. Git plumbing only (`ls-files`) — **no `verify_commands` execution** (correct the design's "no subprocesses" wording: it shells to git, just never runs verify).
- [ ] Failure output: per open contract, an actionable block in the style of the existing check targets, ending with "run `make drift-plan`". A dead-glob/missing-target failure additionally says "edit `drift.toml` first" (a mid-rename glob can go temporarily dead on the very PR that should fix it). Exit non-zero on any failure via `sys.exit(1)` (Typer layer idiom).
- [ ] Tests: each validation failure class (bad manifest, invalid/duplicate ID, dead trigger glob, zero-match review target, missing ack, orphan ack, `contract`≠filename, digest mismatch after staged edit), the all-green pass, and the failure message ends with "run `make drift-plan`".

### 1d. `drift plan [CONTRACT]`

- [ ] Lists open contracts; Markdown by default (per the workspace surface-output conventions — the consumer is an agent). For each open contract: description, per-file added/removed/modified trigger changes (diff of stored `[trigger_files]` map vs current index — no git-diff machinery), review targets, verify commands, previous ack's reviewer/date/rationale, and the exact `make drift-ack ...` invocation to fulfill.
- [ ] With a `CONTRACT` argument: the full packet for that contract only. Unknown contract id = hard error.
- [ ] Tests: added/removed/modified reporting correctness; previous-rationale surfacing; fulfilled contracts excluded from output; **the emitted `make drift-ack CONTRACT=… RATIONALE="…"` string is exact and copy-pasteable** (agents run it verbatim).

### 1e. `drift ack CONTRACT --rationale "…"`

- [ ] `--rationale` required; `reviewed_by` defaults from `git config user.name`, `--by` overrides. **If `git config user.name` is unset AND no `--by`: hard error with an actionable message** ("set git config user.name or pass --by") — never write an empty/placeholder reviewer. `reviewed_at` UTC ISO timestamp (audit-only, no validity semantics).
- [ ] Runs the contract's `verify_commands` first (Decision 4 — each `shlex`-split, `shell=False`, cwd=repo root, env inherited, stop at first failure, captured output shown on abort); any failure aborts the ack without writing. **No `--skip-verify` flag** (design decision; an audited-skip variant is a deferred item, see Deferred). 
- [ ] Recomputes the digest from the **index** at ack time and writes the ack file. Clean tree NOT required, but **trigger files must be staged** (`git add`) to be covered — document this in the failure/help text. Optionally warn when a matched trigger file is untracked or unstaged-modified so the author knows coverage will lag until staged.
- [ ] Tests: ack round-trip (stage → ack → check green); ack-then-edit invalidation (ack → edit+stage trigger → check fails); verify-command failure aborts without writing; missing rationale rejected; `reviewed_by` resolution trio (git-config default / `--by` override / unset+no-`--by` → error); unknown CONTRACT id → hard error; ack permitted with an otherwise-dirty tree.

### 1f. CLI registration and gates

- [ ] Register the `drift` Typer sub-app in `_dev_cli.py` following the `kit` pattern; `--help` smoke works for all three commands.
- [ ] `make agent-check` green (includes keyword-only guard).
- [ ] `make agent-test` green.

### CHECKPOINT 1 — STOP (engine done, nothing wired)

Gates: `make agent-check` + `make agent-test` green; `pipelex-dev drift --help` smoke. Then run the full checkpoint protocol above (commit → update this file → fan out `/code-review` per the no-inherited-context convention → triage → commit fixes). Natural handoff: the remaining work is integration and manifest authoring — a fresh session can pick it up from the tests and this file.

---

## Phase 2 — wiring, seeds, docs

### 2a. Make and CI wiring (Decision 5 — advisory first)

- [ ] Make targets `drift-plan`, `drift-check`, `drift-ack` (with `RATIONALE=`/`CONTRACT=` vars for ack), following the existing target+shorthand pattern; register in `.PHONY` (`Makefile:196`).
- [ ] Add `drift-check` to the `make check` aggregate (`Makefile:1081`). Deliberately NOT in `agent-check` (design decision: review obligations belong at the end of a change, not in the post-edit lint loop).
- [ ] Add a **new `lint-drift` job** to `.github/workflows/lint-check.yml` (its own job running `make drift-check`, modeled on the `lint-config-sync` job — NOT a step inside an existing job). **Leave it OUT of the `lint-all` aggregator's `needs`** so it runs and is visible but does NOT block merges (advisory grace period). Add a one-line comment marking it advisory and the promotion condition.
- [ ] **Promotion (separate, later):** once the current open-PR backlog lands, add `lint-drift` to `lint-all`'s `needs` to make it a required gate. Track this as its own follow-up, not part of the Phase 2 landing.

### 2b. Seed contracts and initial acks (the first dogfood)

- [ ] Author root `drift.toml` with the three seed contracts from the design (config-docs, cli-docs, keyword-only-convention). All nine trigger/review paths were verified to resolve (`docs/configuration/`, `docs/tools/cli/` + `pipelex/cli/agent_cli/CLAUDE.md`, `docs/contribute/keyword-only-arguments.md` + `keyword_only_guard.py` all exist) — but **re-confirm at authoring time**, otherwise `drift check` hard-errors on dead globs.
- [ ] **`config-docs` breadth is a dogfood-watch item** (codex #8): `pipelex/system/configuration/**/*.py` includes plumbing (`config_loader.py`, `config_check.py`) whose edits don't touch user-facing prose. Start broad per the design, but if it opens on plumbing edits, narrow to `configs.py` + `config_model.py` + `pipelex.toml`. Note the observation in Cold-start context if it fires.
- [ ] Perform the three initial reviews **for real** — actually read each contract's review targets against the current trigger sources, fix any staleness found, `git add` the trigger files, and only then `drift ack` each with an honest rationale. This is the first dogfood; do not rubber-stamp.
- [ ] Commit `drift.toml` + `.drift/acks/*` + any doc fixes the reviews surfaced.

### 2c. Documentation

- [ ] New page `docs/contribute/drift-contracts.md`: what a contract is, the three-tier framing (derived / linkage / review — and the rule that anything mechanizable becomes a derived check), the ack workflow (**including "`git add` trigger files before `drift ack`" — index semantics**), and the no-bypass rationale. **Merge-conflict rule — state it correctly (codex #13):** the safety net is that `drift check` recomputes the digest over the merged tree and flags the mismatch; a literal ack-file conflict is *possible but not guaranteed* (line-wise auto-merge can produce a Frankenstein ack), so the guarantee to rely on is the post-merge digest check, not the conflict. Resolution either way: finish the merge, re-`ack`. Add to `mkdocs.yml` nav in **both** places. **Also correct the same over-sold "conflict is a feature" wording in `wip/drift-contracts-design.md`.**
- [ ] Add `drift` to the pipelex-dev command list in the agent rules kit source (the section that generates the `Pipelex Dev CLI` part of `CLAUDE.md`/`AGENTS.md`) and regenerate via the kit make targets — do not edit `CLAUDE.md` directly.
- [ ] `CHANGELOG.md` entry under `[Unreleased]`.
- [ ] `make docs-check` (or the mkdocs strict build) green.

### CHECKPOINT 2 — STOP (CI enforcing, seeds live)

Gates: `make check` green end-to-end (now includes `drift-check` against the committed acks); `make agent-test` green; mkdocs strict build green. Then the full checkpoint protocol (commit → update this file → `/code-review` fan-out, no inherited context → triage → commit fixes).

**After this checkpoint: stop and dogfood for a few weeks of normal PRs before touching Phase 3 or growing the manifest.** The question only usage answers: is ack friction proportionate to the staleness caught? Record observations (reflexive acks, real catches, friction complaints) in the Cold-start section or a wip note as they happen.

---

## Phase 3 — agent ergonomics (GATED on dogfooding verdict — do not start in the implementation sessions)

- [ ] Dogfooding verdict recorded (keep / narrow / mechanize / drop, per contract).
- [ ] Polish the `drift plan` packet for agent consumption based on observed agent behavior.
- [ ] `--format json` on `plan` (and `check` if a software consumer materialized) for software consumers, per the surface-output conventions.
- [ ] Teach the workflow where agents already look: contributor docs section + the CI failure-message text. A repo-local skill only if the raw commands prove insufficient.
- [ ] CHECKPOINT 3 — STOP: same protocol (verify → commit → update this file → `/code-review` fan-out → triage).

## Deferred (tracked in the design doc — do not implement)

Symbol-level triggers (griffe), markdown-anchor targets, pytest node-ID validation, derived-tier entries in `plan` output, cross-repo contracts, cocode semantic assistance, standalone-tool extraction. See the design doc's "Deferred" section. If a review finding lands here, note it in `wip/drift-contracts/` instead of implementing it.

Added by the `/plan-eng-review` (2026-07-03), deferred not dropped:

- **Audited `--skip-verify`** (codex #11): if a targeted `verify_command` ever requires unavailable local services or flakes, the only current bypass is hand-editing ack TOML — worse than an audited escape. Deferred design: a `--skip-verify` that records `verify_skipped = true` + a reason IN the ack file (auditable, PR-visible), so it's an on-the-record override, not a silent one. Do NOT add in the MVP — the seed `verify_commands` (`make tb`, `[]`) don't need it; revisit only if a real verifier hits this.
- **Mechanical generated-path guard in `review`** (codex #12): today generated docs are forbidden from `review` lists by prose only. A denylist of known generated dirs (`docs/errors/`, `derived/`, gateway model docs) that `check` rejects would enforce it. Low priority; the manifest author knows the rule.

---

## Review outputs (`/plan-eng-review`, 2026-07-03)

### NOT in scope (considered, deliberately deferred)

- **Symbol-level triggers (griffe), markdown-anchor targets, pytest node-ID validation** — dependency weight + slower check; the seed contracts don't need them.
- **Cross-repo contracts** — separate design; the spec/conformance pair is already covered by `check-spec-links.py` (linkage tier). `drift` stays per-repo.
- **`--format json` on `plan`/`check`** — Phase 3, gated on the dogfood verdict AND a real software consumer materializing. Agents read the Markdown.
- **Audited `--skip-verify`, mechanical generated-path guard** — captured in Deferred; not built in the MVP.
- **`config-docs` trigger narrowing** — a dogfood-watch item, not a pre-optimization (design starts broad on purpose).
- **Repo-local drift skill** — Phase 3, only if the raw commands + CI failure text prove insufficient for agents.
- **Repo-wide doc backfill** — the tool enforces the floor going forward; it does not sweep the whole tree for existing drift.
- **CRLF / cross-platform hashing** — was a deferred risk under working-tree hashing; **now resolved for free** by Decision 1 (index OIDs are filter-normalized). No longer open.

### What already exists (reuse map — plan reuses, does not rebuild)

- **Derived-tier checks** (`check-config-sync`, `check-mthds-schema`, `check-gateway-models`, `check-rules`) — drift covers ONLY the review tier; it correctly does not touch these. `config-docs` deliberately covers the *prose* that `make tb`/config-sync can't.
- **Linkage-tier `check-spec-links.py`** — cross-repo, purpose-built; drift does not absorb it. Correct boundary.
- **`pipelex/tools/misc/toml_utils.py`** — reused for all TOML read/write (was slated as raw `tomlkit`). DRY win.
- **`keyword_only_guard.py`** — the pure-stdlib-core idiom that the `core.py` / `git_adapter.py` split mirrors.
- **`check_config_sync_cmd.py`** — the CI-gate presentation idiom (rich panel → `sys.exit(1)`) reused by `drift check`.
- **`cli/commands/init/ide_extension.py:36-47`** — the `subprocess.run(check=False)` + `noqa: S603/S404` pattern for the git adapter.
- **`git ls-files -s`** — reuses git's own index/OID machinery instead of a custom working-tree hashing scheme.
- **Two-layer Typer wrapper convention** (`_dev_cli.py` wrapper → keyword-only `*_cmd`) — followed.

### Failure modes (per new codepath — realistic prod failure / test / error-handling / visibility)

| Codepath | Realistic failure | Test | Handling | Visible? |
|---|---|---|---|---|
| git adapter | git binary missing / not a repo | ✅ (added) | catch → actionable error | clear error |
| git adapter | `ls-files -s` non-zero / malformed output | ✅ (added) | raise with stderr | clear error |
| `ack` verify | verify_command flakes / times out | ✅ (added) | abort ack, show captured output | ack refuses, visible |
| `ack` index | untracked new trigger file at ack → local under-coverage | ✅ index-semantics test | optional warn | **backstopped**: once the file is `git add`+committed the matched set changes → digest changes → CI `drift check` fails. Not a silent prod failure. |
| `check` merge | Frankenstein auto-merged ack | ✅ (post-merge mismatch) | digest recompute flags it | CI failure, visible |
| `check` rename | orphan ack after contract rename | ✅ (added) | hard error | CI failure, visible |
| `core` digest | glob reorder churns digest | ✅ reorder→same-digest | canonical JSON | would be noisy re-acks, not silent |

**Zero critical silent-failure gaps.** The one candidate (untracked new trigger file at ack) is backstopped by the same digest recompute in CI once the file is committed — the warn is a faster-feedback nicety, not a correctness requirement.

### Worktree parallelization

**Sequential implementation, no meaningful parallelization opportunity.** Phase 1 is one small tightly-coupled package (commands depend on core + adapter + models). Phase 2's sub-parts are loosely independent but too small and interdependent to warrant worktrees (the CI gate is meaningless before the seeds exist; the docs reference the commands). Build in order; the checkpoint boundaries are the real handoff points.

### Implementation Tasks

Synthesized from this review's findings. Each derives from a specific decision/finding above.

- [ ] **T1 (P1)** — engine — digest source = index OIDs via a single `git ls-files -s` (Decision 1); drop `git hash-object`/working-tree. Verify: adapter test — staged edit reflected, unstaged not.
- [ ] **T2 (P1)** — core — canonical-JSON digest over normalized pydantic contract + sorted `(path, oid)` (Decision 2). Verify: glob-reorder → SAME digest; reformat → SAME digest.
- [ ] **T3 (P1)** — package — pure `core.py` + thin `git_adapter.py` + `models.py` + `drift_cmd.py` (Decision 3); build the reusable `git_repo` conftest fixture. Verify: core tests run with no git.
- [ ] **T4 (P2)** — models — contract-ID charset validation, `toml_utils` I/O, atomic ack write (temp + `os.replace`). Verify: invalid ID rejected; ack round-trip.
- [ ] **T5 (P2)** — `check` — add validations: review zero-match hard error (symmetry), orphan-ack, `ack.contract`==filename, unique IDs; failure text says "edit drift.toml first" on dead glob. Verify: one test per failure class.
- [ ] **T6 (P2)** — `ack` — verify_commands `shlex`+`shell=False`, cwd=root, env-inherit, fail-fast, output-on-abort (Decision 4); `reviewed_by` unset+no-`--by` → error; document git-add-before-ack. Verify: reviewed_by trio; verify-fail aborts without write.
- [ ] **T7 (P2)** — CI — new `lint-drift` job, OUT of `lint-all` `needs` (advisory) (Decision 5). Verify: job runs, merges not blocked.
- [ ] **T8 (P3)** — docs — correct the merge-conflict framing (rely on post-merge digest mismatch, not the conflict) in `docs/contribute/drift-contracts.md` AND `wip/drift-contracts-design.md`. Verify: mkdocs strict build green.
- [ ] **T9 (P2)** — git adapter — failure-path tests: missing binary, non-zero exit, timeout. Verify: each raises an actionable error.

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` | Scope & strategy | 0 | — | — |
| Codex Review | `/codex review` | Independent 2nd opinion | 1 | issues_found | ~24 raised; 7 new, 2 consensus, rest tensions/hardening |
| Eng Review | `/plan-eng-review` | Architecture & tests (required) | 1 | clean | 9 issues folded, 0 critical gaps |
| Design Review | `/plan-design-review` | UI/UX gaps | 0 | — | — (no UI surface) |
| DX Review | `/plan-devex-review` | Developer experience gaps | 0 | — | — |

- **CODEX:** outside voice (gpt-5.5, high) surfaced the digest-source leak (index vs working-tree) — its best catch, adopted as Decision 1 — plus verify_commands exec model (Decision 4) and a batch of validation hardening (orphan acks, ID charset, atomic writes, path-matching precision, merge-conflict framing). Pushed on no-skip-verify / broad triggers / strict TDD / checkpoint ceremony — all kept as designed.
- **CROSS-MODEL:** consensus on advisory-first rollout (both reviewers) and on canonicalization being underspecified. No unresolved tension — every codex point was either adopted, folded as hardening, deferred, or explicitly kept-as-designed with rationale.
- **VERDICT:** ENG CLEARED — ready to implement. Seven decisions locked, nine findings folded into the plan, two items deferred (not dropped).

NO UNRESOLVED DECISIONS
