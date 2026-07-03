# Drift Contracts — implementation plan

Implements [wip/drift-contracts-design.md](wip/drift-contracts-design.md). Read that design doc first — it is the authority on semantics (validity rule, manifest schema, ack format, command behaviors). This file tracks execution state.

## Cold-start context (update at every checkpoint)

- **Status:** Not started. Plan written, no code yet.
- **Branch / worktree:** `docs/Update` in the `_docs` worktree (the design doc landed here in `122ffd6f3`). Treat `_docs` as the repo root.
- **Key repo facts** (verified against the tree, no need to re-derive):
    - Dev CLI commands live in `pipelex/cli/dev_cli/commands/`, registered in `pipelex/cli/dev_cli/_dev_cli.py`. The `kit` sub-app (`app.add_typer(kit_app, name="kit")`, `_dev_cli.py:77`) is the pattern for a command group — `drift` should be a sub-app the same way.
    - Dev CLI unit tests live under `tests/unit/pipelex/cli/dev/`.
    - `tomlkit` is a direct dependency — use it to read `drift.toml` and write ack files.
    - Makefile: the `check` aggregate is at `Makefile:1081`; per-target pattern with shorthand alias is e.g. `check-config-sync`/`ccs` (`Makefile:323-328`). CI runs the check targets as **individual steps** in `.github/workflows/lint-check.yml` (see the `make check-config-sync` and `make check-keyword-only` steps), not via `make check`.
    - Contribute docs live in `docs/contribute/`; mkdocs nav references them in **two places** in `mkdocs.yml` (~lines 324 and 555) — update both.
    - Keyword-only convention applies to all new code (`make agent-check` enforces).
- **Decisions taken:** (none yet — record them here as they happen)
- **Open questions:** (none yet)

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

Everything in `pipelex/cli/dev_cli/commands/drift/` (small sub-package), no Makefile or CI wiring yet. TDD: write the failing tests for each component first, then implement.

### 1a. Skeleton and models

- [ ] Create `pipelex/cli/dev_cli/commands/drift/` sub-package: keep it lean — roughly `models.py` (manifest + ack pydantic models), `engine.py` (file matching, digest, plan computation), `drift_cmd.py` (Typer sub-app with the three commands). Merge modules if they stay small; do not add speculative ones.
- [ ] Manifest models per the design: `version`, `[contracts.<id>]` with `description`, `triggers`, `exclude`, `review`, `verify_commands`. Parse `drift.toml` from repo root with tomlkit; schema-invalid manifest is a hard error with an actionable message.
- [ ] Ack model per the design: `contract`, `digest`, `reviewed_by`, `reviewed_at`, `rationale`, `[trigger_files]` path→blob-hash map. One file per contract at `.drift/acks/<contract-id>.toml`, read and written with tomlkit.

### 1b. Digest engine

- [ ] File matching: triggers/exclude globs evaluated against `git ls-files` output only (tracked files). Review targets resolve against tracked files/dirs too.
- [ ] Content hashing: git blob hashes of working-tree content (`git hash-object`) — batch the call (one subprocess for all files, not one per file).
- [ ] Contract digest: `sha256` over the canonically serialized contract definition + the sorted `(path, blob-hash)` list. Canonical serialization must be deterministic (sorted keys, no formatting sensitivity to `drift.toml` whitespace/comments).
- [ ] Tests (write first): digest stability across runs and across manifest reformatting; contract-definition change → digest change; trigger file edit/add/delete/rename → digest change. Tests need a temp-git-repo fixture (`git init` + commits in `tmp_path`) since matching and hashing go through git.

### 1c. `drift check` (the pure gate)

- [ ] Validates: manifest parses and is schema-valid; every trigger glob matches at least one tracked file (dead glob = hard error); every review target resolves; every contract has an ack; every ack digest equals the recomputed digest. No subprocesses beyond git plumbing, no `verify_commands` execution.
- [ ] Failure output: per open contract, an actionable block in the style of the existing check targets, ending with "run `make drift-plan`". Exit non-zero on any failure.
- [ ] Tests (write first): each validation failure class (bad manifest, dead glob, missing target, missing ack, digest mismatch after edit), plus the all-green pass.

### 1d. `drift plan [CONTRACT]`

- [ ] Lists open contracts; Markdown by default (per the workspace surface-output conventions — the consumer is an agent). For each open contract: description, per-file added/removed/modified trigger changes (diff of stored `[trigger_files]` map vs current tree — no git-diff machinery), review targets, verify commands, previous ack's reviewer/date/rationale, and the exact `make drift-ack ...` invocation to fulfill.
- [ ] With a `CONTRACT` argument: the full packet for that contract only. Unknown contract id = hard error.
- [ ] Tests (write first): added/removed/modified reporting correctness; previous-rationale surfacing; fulfilled contracts excluded from output.

### 1e. `drift ack CONTRACT --rationale "…"`

- [ ] `--rationale` required; `reviewed_by` defaults from `git config user.name`, `--by` overrides; `reviewed_at` UTC ISO timestamp (audit-only, no validity semantics).
- [ ] Runs the contract's `verify_commands` first; any failure aborts the ack. **No `--skip-verify` flag** — do not add one even if it feels convenient (design decision: every escape hatch is a rubber-stamp invitation).
- [ ] Recomputes digest from the working tree at ack time and writes the ack file. Clean tree NOT required.
- [ ] Tests (write first): ack round-trip (ack → check green); ack-then-edit invalidation (ack → edit trigger → check fails); verify-command failure aborts without writing; missing rationale rejected.

### 1f. CLI registration and gates

- [ ] Register the `drift` Typer sub-app in `_dev_cli.py` following the `kit` pattern; `--help` smoke works for all three commands.
- [ ] `make agent-check` green (includes keyword-only guard).
- [ ] `make agent-test` green.

### CHECKPOINT 1 — STOP (engine done, nothing wired)

Gates: `make agent-check` + `make agent-test` green; `pipelex-dev drift --help` smoke. Then run the full checkpoint protocol above (commit → update this file → fan out `/code-review` per the no-inherited-context convention → triage → commit fixes). Natural handoff: the remaining work is integration and manifest authoring — a fresh session can pick it up from the tests and this file.

---

## Phase 2 — wiring, seeds, docs

### 2a. Make and CI wiring

- [ ] Make targets `drift-plan`, `drift-check`, `drift-ack` (with `RATIONALE=`/`CONTRACT=` vars for ack), following the existing target+shorthand pattern; register in `.PHONY`.
- [ ] Add `drift-check` to the `make check` aggregate (`Makefile:1081`). Deliberately NOT in `agent-check` (design decision: review obligations belong at the end of a change, not in the post-edit lint loop).
- [ ] Add a `make drift-check` step to `.github/workflows/lint-check.yml`, following the `check-config-sync` step pattern.

### 2b. Seed contracts and initial acks (the first dogfood)

- [ ] Author root `drift.toml` with the three seed contracts from the design (config-docs, cli-docs, keyword-only-convention). **Settle exact trigger/review path lists against the current tree first** — verify each glob matches tracked files and each review target exists (e.g. confirm the real path of the CLI docs under `docs/`), otherwise `drift check` hard-errors on dead globs.
- [ ] Perform the three initial reviews **for real** — actually read each contract's review targets against the current trigger sources, fix any staleness found, and only then `drift ack` each with an honest rationale. This is the first dogfood; do not rubber-stamp.
- [ ] Commit `drift.toml` + `.drift/acks/*` + any doc fixes the reviews surfaced.

### 2c. Documentation

- [ ] New page `docs/contribute/drift-contracts.md`: what a contract is, the three-tier framing (derived / linkage / review — and the rule that anything mechanizable becomes a derived check), the ack workflow, the merge-conflict resolution rule (finish merge, re-ack), and the no-bypass rationale. Add to `mkdocs.yml` nav in **both** places.
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
