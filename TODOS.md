# WIP-Docs Tidy — Follow-Up Plan

> Plan for finishing the `_docs/wip/` cleanup and acting on what it surfaced. Multi-phase, with hard-stop **checkpoints** where the agent MUST pause, verify, and update the [Progress log](#progress-log) so a fresh session can resume from this file alone.

## Cold-start context — read this first

You are continuing a documentation-tidy effort. If you are starting cold, this section plus the three review artifacts below is everything you need.

**Where you are.** This file lives in a git worktree of the **pipelex** repo at `/Users/lchoquel/repos/Pipelex/_docs/`, on branch `docs/Tidy`. The worktree carries the full pipelex source (`pipelex/`, `tests/`, `CHANGELOG.md`) at that branch's revision — use it to verify any doc claim against real code.

**Run from here.** Set your working directory to `/Users/lchoquel/repos/Pipelex/_docs/` (the worktree this plan targets) and stay there. Every code path in this plan (`pipelex/...`, `tests/...`, `_run_core.py`, `delivery_executor.py`) is relative to this root, and `make agent-check` / `make agent-test` + `.venv/` are available here. The plan was originally authored from the workspace root one directory up; every path below is absolute or rooted here so it still resolves, but `_docs` is the correct place to stand for a cold start (it's the `docs/Tidy` revision of the source, not the parent `dev` checkout).

**Two repos, do not confuse them.**

- `/Users/lchoquel/repos/Pipelex/_docs/` — the **pipelex repo** worktree (branch `docs/Tidy`). All the `wip/` docs live here. Its parent (non-worktree) checkout is `/Users/lchoquel/repos/Pipelex/pipelex/` (currently on `dev`) — relevant only for the Phase 4 branch-off-`main` step. Moves within the worktree are reversible (git-tracked, isolated branch).
- `/Users/lchoquel/repos/Pipelex/` — the **workspace repo**, a *separate* git repo (NOT pipelex). Its `docs/history/` is the intended destination for the "move-to-history" bucket, but **that folder does not exist yet — Phase 1 creates it.** **Do NOT assume this repo is on `main`: as of 2026-05-29 it is checked out on `docs/spec-conformance-links`.** Before committing anything here (Phase 1), run `git -C /Users/lchoquel/repos/Pipelex branch --show-current` and confirm the target branch with the user — do not drop a docs-history commit onto whatever feature branch happens to be checked out. `git mv` cannot cross repo boundaries — use `cp` + `git rm`, and commit in each repo separately.

**Authoritative artifacts (at the worktree root, already committed on `docs/Tidy`).**

- `TIDY-MANIFEST.md` — per-file dispositions, red-flags, supersession map, an Execution-status section recording what already ran, and copy-paste `git mv` / `cp` / `git rm` command blocks under "Execution notes". **The move-to-history file list and its exact command block are in §"move-to-history" + "Execution notes" step 4. The keep-active in-place corrections are in §"keep-active" + "Execution notes" step 6.** Reference these instead of re-deriving.
- `DEFERRED-BACKLOG.md` — deferred items / follow-ups / bugs consolidated by theme. Every bug-kind row is tagged with a verified verdict (`[REAL]`, `[REAL — deferred]`, `[partial → low]`, `[RESOLVED]`, `[unverified]`) and a corrected severity.
- `BUG-VERIFICATION.md` — the evidence (file:line) behind each bug verdict. Authoritative when it disagrees with an older note in `TIDY-MANIFEST.md`.

**What is already done (committed on `docs/Tidy`).**

- `d2fcd0a0` — the reorganization: loose top-level docs grouped into `crate-architecture/` and `graph-model/`; finished docs moved into `archive/` subfolders (incl. a new `wip/error-handling/archive/`); the mislabeled live-bug doc renamed `archive-delivery-error-path-request-id.md` → `track-delivery-error-path-request-id.md`; derived `.html` renders and dead/duplicate archive docs deleted; all cross-references repointed and verified with a link-resolution sweep.
- `0d1ab679` — the three review docs above, with the backlog corrected to the verified verdicts.

**What is NOT done = this plan.** Nothing here has been started. Phases 1–3 are docs-only work on `docs/Tidy`. Phase 4 is *runtime code* and must not start without the branch decision at Checkpoint C.

**Convention reminders.** `track-*.md` = current-state reference (active); `archive/` and `archive-*.md` = finished/history; `0X-master-plan.md` numbered (higher = newer; `02-master-plan.md` is live). MkDocs markdown: blank line before every list/table; never hard-wrap (one paragraph = one line); never hardcode counts of items in prose.

## Checkpoint protocol

At every checkpoint marked **STOP** below, you MUST, before doing anything else:

1. **Verify.** Run `git status --short` in *both* repos as applicable; for docs phases run the link sweep (see [Verification commands](#verification-commands)); for code phases run `make agent-check` and the targeted tests.
2. **Record.** Append a dated entry to the [Progress log](#progress-log): what completed, commit SHAs (both repos), decisions taken, anything surprising, and the exact next action. Tick the checkboxes you finished.
3. **Stop and hand off.** Do not continue past a STOP checkpoint in the same session unless the user explicitly says to. The point is a clean cold-start boundary.

---

## Phase 1 — Cross-repo move-to-history

Relocate the finished internal-planning docs that should leave the public pipelex repo but be kept as institutional memory. Authoritative file list + ready-to-run command block: `TIDY-MANIFEST.md` → §"move-to-history" and "Execution notes" step 4.

- [x] Re-read `TIDY-MANIFEST.md` §"move-to-history" — confirm the source list is still accurate against the current `wip/` tree (the reorg moved/renamed some of these; re-derive any path that 404s).
- [x] Create the `docs/history/` topic folders in the **workspace repo** (`/Users/lchoquel/repos/Pipelex/docs/history/...`).
- [x] `cp` each move-to-history doc into its `docs/history/<topic>/` destination (workspace repo).
- [x] Before removing sources: confirm every deferred item in these docs is already captured in `DEFERRED-BACKLOG.md` (it should be — the backlog was built from them). Spot-check, don't assume. — Coverage complete except one gap: added the two `activity_queues` startup validators (orphan-queue + unknown-activity) from `per-activity-queue-routing-v1.md`.
- [x] `git rm` the source docs from the `wip/` worktree.
- [x] Fix cross-references broken by the removal: grep the surviving `wip/` tree for links to the moved files and repoint or de-link. Held docs that link to each other (e.g. `post-pr933-xhigh-followups.md` ↔ its now-moved siblings) need attention. Run the link sweep to confirm clean. — Done; 0 new danglers (verified by diff against a clean `git archive HEAD` export).
- [x] Decide how history docs reference back into the pipelex repo (cross-repo links are inherently broken once relocated) — either strip those links or note them as historical. Record the decision in the log. — Decision recorded in the log entry below (de-link, no cross-repo fs links).
- [x] Commit the worktree (`docs/Tidy`): `git rm`s + link fixes.
- [x] Commit the workspace repo: the new `docs/history/` content. **First check which branch it is on (`git -C /Users/lchoquel/repos/Pipelex branch --show-current`) — it is NOT necessarily `main` (was `docs/spec-conformance-links` on 2026-05-29). Confirm the target branch with the user before committing; this lands in a different repo with higher blast radius. Do NOT push without the user's say-so.**

### ☑ CHECKPOINT A — **STOP** (after Phase 1)

This phase touched two repos and produced two commits — a mandatory stop. Before stopping: verify both repos are clean, the link sweep passes in `wip/`, and the workspace-repo commit contains only the intended history files. Record both commit SHAs, **the branch the workspace-repo commit landed on**, and the cross-repo-link decision in the [Progress log](#progress-log). Confirm with the user whether to push either repo.

---

## Phase 2 — Editorial in-place corrections (keep-active docs)

Fix the stale claims in docs that stay active. List: `TIDY-MANIFEST.md` → §"keep-active" notes and "Execution notes" step 6. **Each correction is a doc edit that must be validated against current code — do not apply a manifest note blindly; the manifest predates the bug verification and some of its notes are nuanced or already-addressed.**

- [x] `02-master-plan.md` P1: reconcile the "generate_report() has zero runtime callers" note. Per `BUG-VERIFICATION.md`, `generate_report` now *does* have a caller (`_run_core.py:224`), but the cross-worker **aggregation** path (`inject_tokens_usages` / `UsageAggregator`) is still unwired. Correct the wording to match that reality; do not overstate it as "fully wired." — Done; also corrected the two stale `reporting_manager.py` line refs (`:191`→`:227`, `:247`→`:369`) and the obsolete `_get_registry` TODO acceptance-criterion (method is now `_get_registry_strict` at `:119`, no TODO).
- [x] `error-handling/architecture.md`: refresh the `ErrorReport` schema section (missing `title`, `type_uri`, `caller_facing_message`, `DisclosureMode`; "frozen pydantic dataclass" → frozen `BaseModel`; add the `AMBIGUOUS`/`UNKNOWN` enum nuance). Verify field names against `pipelex/base_exceptions.py` before writing. — Done; verified all fields + `ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)` against `base_exceptions.py:210-243`, added the VERBOSE/STRICT `DisclosureMode` projection and the `to_error_report()` field list.
- [x] `error-handling/track-cli-delivery.md`: stale ContextVar names (`_agent_cli_output_format` → `_agent_cli_error_format`), `display_error_panel` `error_message: str | None`. Verify against `agent_output.py` / `error_handlers.py`. — Done; the ContextVar backs the **error** stream only (`set/get_agent_cli_error_format`); success is threaded explicitly via `agent_success_formatted(..., output_format)`. Also documented the two-option model (`--format` + `--error-format`) and fixed `error_message: str | None` against `error_handlers.py:51`.
- [x] `error-handling/track-metadata-model.md`, `track-temporal-integration.md`, `track-worker-classification.md`: apply the minor type/name/wrapper fixes noted in the manifest, each checked against code (e.g. `azure_img_gen_worker.py` still has a `_raise_categorized_*` wrapper — reconcile doc vs code). — Done. metadata-model: same frozen-`BaseModel`/schema/`AMBIGUOUS` fixes as architecture.md. temporal-integration: `recover_error_report` is **total** (returns `ErrorReport`, never `None`; `from_dict` is `extra="forbid"`, malformed payload synthesizes an `UnrecoverableWorkflowFailureError` fallback) — the old "unknown keys dropped / yields None" claim was wrong. worker-classification: the Azure img-gen worker **still** has `_raise_categorized_azure_status_error` (`azure_img_gen_worker.py:65`, called at `:159`) — softened the "all `_raise_categorized_*` deleted" overclaim.
- [x] `concurrency/README.md`: drop the now-shipped "retry jitter quick win" from suggested next steps (verified shipped — see backlog "Recently shipped" note). — Done; `transport_retry.py:44` already uses full-jitter `wait_random_exponential`. Reframed the doc (section heading → "Shipped — retry jitter", status line, weakness-3 mechanism, layering table, and "Suggested next step") to mark it shipped, not pending.
- [x] Run the link sweep after edits (no links should have moved, but confirm). — Done; **0 new danglers**. Diffed unique-dangler sets HEAD vs working tree: the only deltas were `../../../TODOS.md` links that resolve in the real worktree but not in a `wip`-only `git archive` export (a comparison artifact, not a regression). The 22 remaining danglers are the pre-existing out-of-scope set from Phase 1.
- [x] Commit the worktree (`docs/Tidy`).

---

## Phase 3 — Confirm the two `[unverified]` backlog items

These two bug entries could not be settled statically; resolve them and update `DEFERRED-BACKLOG.md` + `BUG-VERIFICATION.md` with the outcome.

- [x] **Offline baseline test** (`tests/e2e/agent_cli/test_offline_run_dry.py::...no_cache_no_network...`): run it locally — `.venv/bin/pytest tests/e2e/agent_cli/test_offline_run_dry.py -k no_cache_no_network`. It is `gha_disabled` (subprocess E2E). If green, mark the backlog row `[RESOLVED]` and drop it; if red, re-open with the real failure. — **Green: 1 passed (16.8s), 8 deselected.** Marked `[RESOLVED]` in `BUG-VERIFICATION.md` and dropped from the live backlog (moved to "Recently shipped").
- [x] **plxt PipeStructure schema** (cross-repo): the pipelex side is correct/test-guarded; the bundled schema lives in the sibling repo `vscode-pipelex/crates/taplo-common/schemas/mthds_schema.json`. Check whether it contains `PipeStructureBlueprint` (regenerate via the pipelex generator and diff); re-file against `vscode-pipelex` if stale. This requires leaving this worktree — flag to the user rather than wandering repos unprompted. — **Pipelex side re-confirmed in-worktree** (`pipelex/language/mthds_schema_generator.py:33` lists `PipeStructureBlueprint`). The cross-repo diff against `vscode-pipelex` was **NOT** performed (requires leaving this worktree) — **flagged to the user** below and annotated in both review docs as `[unverified — cross-repo, flagged to user]`.
- [x] Update the two rows in `DEFERRED-BACKLOG.md` and the corresponding sections in `BUG-VERIFICATION.md`; commit the worktree. — Done (plus a self-review correction to the Phase 2 worker-classification edit, see log).

### ☑ CHECKPOINT B — **STOP** (docs tidy complete)

After Phase 3, the documentation tidy is fully complete on `docs/Tidy`. Mandatory stop: this is the clean "docs done" milestone and the natural place to open a PR or merge. Before stopping: link sweep clean, `git status` clean, all three review docs reflect final state. Record the milestone, all commit SHAs, and whether a PR was opened in the [Progress log](#progress-log). **Get the user's decision on merging `docs/Tidy` and on whether to proceed to Phase 4 at all.**

---

## Phase 4 — Code fixes (runtime; separate branch; requires the test gate)

These are *not* docs — they change `pipelex/` and need `make agent-check` + tests. They are a different risk profile and almost certainly do **not** belong on the docs-only `docs/Tidy` branch.

### ☑ CHECKPOINT C — **STOP BEFORE STARTING** (branch decision)

Do not write any code under this phase until you have confirmed with the user: (a) that they want these fixes now, and (b) which branch — mixing runtime fixes into `docs/Tidy` is wrong; expect a fresh branch off `main` of the pipelex repo, created from the parent checkout at `/Users/lchoquel/repos/Pipelex/pipelex/` (currently on `dev`), **not** from this `_docs` worktree. Record the branch decision before proceeding. After each fix: `make agent-check` then the targeted tests for the touched area (see `tests/CLAUDE.md` source→test mapping); full `make agent-test` before any push.

- [ ] **4a — `request_id` on delivery failure messages** (verified `[REAL]`, low, S). In `pipelex/pipe_run/delivery_executor.py`: append the already-in-scope `request_id_suffix` to the `StorageDeliveryError` failure message (~`:244`) and to both `WebhookDeliveryError` branches (~`:291`, `:294`), mirroring the success paths. Add unit assertions that the messages contain `request_id=`. Evidence in `BUG-VERIFICATION.md`.
- [ ] **4b — cross-worker cost report assembly** (verified `[REAL]`, medium, M). The single genuine functional gap: wire `UsageAggregator.aggregate(events)` → `ReportingManager.inject_tokens_usages(...)` → `generate_report` into the post-run readback, parallel to the existing graph readback, for both direct mode (`pipe_run/pipe_run.py:71` / `graph_assembly.py`) and Temporal (`act_assemble_graph` / post-workflow). Add a cross-worker test. This is its own scoped piece of work — consider a dedicated plan.

---

## Deferred / out of scope here (tracked in `DEFERRED-BACKLOG.md`)

These are real but intentionally not in the active plan above; pick up individually if/when prioritized:

- `[REAL]` GraphSpec causal ordering for parent/child topologies (medium, observability-only).
- `[REAL]` kajson class-registry race under pytest-xdist (low, test-hygiene; needs runtime repro).
- `[REAL — deferred]` `get_config()` replay-determinism — the cheap parts (a `docs/distributed-execution` note on the config-edit-while-in-flight constraint, plus a Replayer regression test) are file-able; the full fix is Worker Versioning (large).
- Pre-existing broken links in historical archive docs (the absolute-style `wip/...`-from-inside-`wip/` pattern, and wrong relative paths in `archive/00-master-plan.md` / `archive/01-master-plan.md`) — optional sweep; not introduced by this cleanup.

---

## Verification commands

- **Link sweep** (run from the worktree root after any docs move/edit) — resolves every relative `.md`/`.html` link in `wip/` and reports danglers:

  ```sh
  cd /Users/lchoquel/repos/Pipelex/_docs && python3 - <<'PY'
  import os, re
  root='wip'; link=re.compile(r'\[[^\]]*\]\(([^)]+)\)'); bad=[]
  for dp,_,fs in os.walk(root):
    for f in fs:
      if not f.endswith('.md'): continue
      p=os.path.join(dp,f)
      for m in link.finditer(open(p,encoding='utf-8').read()):
        t=m.group(1).strip()
        if t.startswith(('http','#','mailto:','file:')): continue
        t=t.split('#')[0].split(' ')[0]
        if not re.search(r'\.(md|html)$',t): continue
        if not os.path.exists(os.path.normpath(os.path.join(dp,t))): bad.append((p,t))
  [print(p,'->',t) for p,t in sorted(bad)]; print('dangling:',len(bad))
  PY
  ```

- **State check:** `git -C /Users/lchoquel/repos/Pipelex/_docs status --short` and `git -C /Users/lchoquel/repos/Pipelex status --short`.
- **Code gate (Phase 4 only):** `make agent-check`, then targeted tests per `tests/CLAUDE.md`, then `make agent-test` before any push.

---

## Progress log

Append a dated entry at every checkpoint. Newest last.

- **2026-05-29 — Plan created.** Reorg (`d2fcd0a0`) and review docs (`0d1ab679`) already committed on `docs/Tidy`; backlog verified against code. Nothing in this plan started. Next action: Phase 1 (cross-repo move-to-history). Open questions: (1) push policy for the workspace-repo commit in Phase 1; (2) whether to merge/PR `docs/Tidy` at Checkpoint B; (3) branch for Phase 4 code fixes.
- **2026-05-29 — Adjusted for cold-start from `_docs`.** Verified the live git topology so this plan is self-sufficient for an agent whose CWD is `/Users/lchoquel/repos/Pipelex/_docs/`: `_docs` is a worktree of the pipelex repo (common dir `pipelex/.git/worktrees/_docs`, parent checkout `pipelex/` on `dev`), carrying full source + `.venv` + the three artifacts at the `docs/Tidy` revision. Corrected a stale assumption: the workspace repo (`/Users/lchoquel/repos/Pipelex/`) is on `docs/spec-conformance-links`, **not** `main`, and `docs/history/` does not exist yet — so Phase 1 must verify the branch and confirm with the user before committing there. No phases executed; this was a plan-portability edit only.
- **2026-05-29 — Phase 1 (move-to-history) executed; paused at Checkpoint A for the workspace-repo branch decision.** Verified all move-to-history sources were still in place, then copied them into the workspace history store at `/Users/lchoquel/repos/Pipelex/docs/history/{error-handling,console-output,template-preprocessor,temporal-listcontent-decode-bug,temporal-primitives,temporal-library-crate}/`. Those copies are **uncommitted** in the workspace repo, staged for the user's branch decision. Deferred-item spot-check: coverage was complete except one gap — the two `activity_queues` startup validators (orphan-queue + unknown-activity, deferred in `per-activity-queue-routing-v1.md`) were captured nowhere, so I added a row for them to `DEFERRED-BACKLOG.md` before removing the source. `git rm`'d the sources from `wip/`. Fixed every cross-reference the removal broke — active docs `error-handling/README.md` (nav list + intro), `track-temporal-integration.md`, `track-testing.md`, `api-companion-revisions.md`, `temporal-next/01-deferred-items.md`, `temporal-primitives/01-id-and-naming-design.md`, and archived docs `archive/00-master-plan.md`, `archive/phase2-implementation-plan.md`, `archive/distributed-tracing-and-reporting.md`, `error-handling/archive/post-xhigh-review-followups.md`. **Link sweep: 0 new danglers** — verified by diffing the sweep against a clean `git archive HEAD wip` export (baseline 29 → 22 current; the remaining 22 are all pre-existing, out-of-scope: the absolute-style `wip/...`-from-inside-`wip/` pattern, wrong relative paths in `archive/00-`/`01-master-plan.md`, and external-path links). **Cross-repo-link decision:** history docs are frozen institutional memory — their content (including any outbound links into the pipelex repo) is left untouched; surviving pipelex docs that linked to a moved doc were **de-linked** (link markup stripped, plain filename kept, annotated `(moved to workspace docs/history/<topic>/)` where reader-facing). No cross-repo filesystem links were created — they break in rendered/published output and would couple the two repos. Committed the worktree on `docs/Tidy` (the `git rm`s, the link fixes, the `DEFERRED-BACKLOG.md` addition, and this log + checkbox ticks). **NOT done — blocked on the user:** the workspace-repo `docs/history/` commit. That repo (`/Users/lchoquel/repos/Pipelex/`) is on branch `docs/spec-conformance-links` (NOT `main`), carrying unrelated in-progress work (`CLAUDE.md`, `docs/specs/README.md`, and untracked `conformance/`, `pipelex-demo-mistral/`, `pipelex-mistralai-workflows/`). Awaiting the user's decision on (1) which branch to land the history commit on and (2) push policy for both repos. Next action: get those answers, commit the workspace repo with only the `docs/history/` files, then add a closing log entry recording both commit SHAs and the branch.
- **2026-05-29 — Checkpoint A closed; Phase 1 complete.** User decisions: history commit on a **new branch off current HEAD**, and **push both**. Created `docs/history-store` in the workspace repo off the current `docs/spec-conformance-links` HEAD, staged only `docs/history/`, and committed it as **`c5b5d24`** — the unrelated spec-conformance WIP (`CLAUDE.md`, `TODOS.md`, `docs/specs/README.md`, untracked `conformance/`/`pipelex-demo-mistral/`/`pipelex-mistralai-workflows/`) was left uncommitted. Pushed both: pipelex `docs/Tidy` → `origin/docs/Tidy` (`fe8e7dd2..f860a76c`, fast-forward; the move-to-history content commit) and pipelex-workspace `docs/history-store` → new remote branch (tracking set). Both repos clean apart from the workspace repo's pre-existing WIP. **STOP boundary:** the user asked to execute only up to the first checkpoint, so Phase 2 (editorial in-place corrections to keep-active docs) is NOT started — resume there in a fresh session.
- **2026-05-29 — Checkpoint B closed; Phases 2 + 3 complete — docs tidy done on `docs/Tidy`.** Resumed from Checkpoint A and executed both remaining docs phases in one session. **Phase 2 (`3b011694`)** — in-place corrections to the seven keep-active docs, each verified against current code: `02-master-plan.md` (generate_report() now has a CLI caller `_run_core.py:224` but `UsageAggregator`/`inject_tokens_usages` are still unwired — corrected the "zero callers" claim, the two stale `reporting_manager.py` line refs, and the obsolete `_get_registry` TODO criterion); `architecture.md` + `track-metadata-model.md` (ErrorReport is a frozen `BaseModel`, not a pydantic dataclass — added `title`/`type_uri`/`caller_facing_message`, the VERBOSE/STRICT `DisclosureMode` projection, and the `AMBIGUOUS`/`UNKNOWN` `InferenceErrorCategory` nuance); `track-cli-delivery.md` (the ContextVar is `_agent_cli_error_format` and backs the error stream only — documented the two-option `--format`/`--error-format` model and `display_error_panel(error_message: str | None)`); `track-temporal-integration.md` (`recover_error_report` is **total** — never returns `None`; `from_dict` is `extra="forbid"`, a malformed payload synthesizes an `UnrecoverableWorkflowFailureError` fallback so the failure webhook still fires — the old "unknown keys dropped / yields None" claim was wrong); `concurrency/README.md` (retry jitter already shipped — `transport_retry.py:44` uses `wait_random_exponential` — moved out of next-steps). **Phase 3 (`de6395d0`)** — the two `[unverified]` items: the offline baseline E2E `test_gateway_no_cache_no_network_fails_with_unavailable` ran **green locally (1 passed, 16.8s)** → marked `[RESOLVED]`, dropped from the live backlog; the plxt PipeStructure schema item's pipelex side was re-confirmed in-worktree (`mthds_schema_generator.py:33` lists `PipeStructureBlueprint`) but the cross-repo diff against `vscode-pipelex/crates/taplo-common/schemas/mthds_schema.json` requires leaving this worktree, so it stays `[unverified — cross-repo, flagged to user]`. **Surprises / self-corrections:** (1) my first Phase 2 edit to `track-worker-classification.md` overstated the Azure img-gen `_raise_categorized_azure_status_error` as a pure bypass; on review it is a **hybrid** (4xx → shared `classify_inference_error`+`render_inference_error`; 5xx → forced `AMBIGUOUS` for the non-idempotent POST) — corrected the doc and reconciled the matching backlog row (now in "Recently shipped"). (2) Several doc line refs were stale (verified and fixed). **Link sweep:** 22 unique danglers, **0 new** vs the Phase 1 baseline (diffed against HEAD; the only deltas were `../../../TODOS.md` links that resolve in the real worktree but not in a `wip`-only `git archive` export — a comparison artifact). The 22 are the pre-existing out-of-scope set. Both review docs (`DEFERRED-BACKLOG.md`, `BUG-VERIFICATION.md`) reflect final state. **MILESTONE: documentation tidy is fully complete on `docs/Tidy`.** Worktree clean after the checkpoint-close commit. **NOT pushed** (Phase 2/3 commits are local only — awaiting the user's push decision). **STOP — user decisions needed:** (a) push `docs/Tidy` and/or open a PR / merge it? (b) proceed to Phase 4 (runtime code fixes 4a request_id + 4b cross-worker cost report) at all — and if so, Checkpoint C requires a fresh branch off `main` from the parent `pipelex/` checkout, NOT this `docs/Tidy` worktree. (c) the plxt PipeStructure cross-repo check is parked for action in `vscode-pipelex`.
