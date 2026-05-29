# WIP-Docs Tidy — Follow-Up Plan

> Plan for finishing the `_docs/wip/` cleanup and acting on what it surfaced. Multi-phase, with hard-stop **checkpoints** where the agent MUST pause, verify, and update the [Progress log](#progress-log) so a fresh session can resume from this file alone.

## Cold-start context — read this first

You are continuing a documentation-tidy effort. If you are starting cold, this section plus the three review artifacts below is everything you need.

**Where you are.** This file lives in a git worktree of the **pipelex** repo at `/Users/lchoquel/repos/Pipelex/_docs/`, on branch `docs/Tidy`. The worktree carries the full pipelex source (`pipelex/`, `tests/`, `CHANGELOG.md`) at that branch's revision — use it to verify any doc claim against real code.

**Two repos, do not confuse them.**

- `/Users/lchoquel/repos/Pipelex/_docs/` — the **pipelex repo** worktree (branch `docs/Tidy`). All the `wip/` docs live here. Moves within it are reversible (git-tracked, isolated branch).
- `/Users/lchoquel/repos/Pipelex/` — the **workspace repo** (branch `main`). Its `docs/history/` is the destination for the "move-to-history" bucket. This is a *different repo*; `git mv` cannot cross into it — use `cp` + `git rm`, and commit in each repo separately.

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

- [ ] Re-read `TIDY-MANIFEST.md` §"move-to-history" — confirm the source list is still accurate against the current `wip/` tree (the reorg moved/renamed some of these; re-derive any path that 404s).
- [ ] Create the `docs/history/` topic folders in the **workspace repo** (`/Users/lchoquel/repos/Pipelex/docs/history/...`).
- [ ] `cp` each move-to-history doc into its `docs/history/<topic>/` destination (workspace repo).
- [ ] Before removing sources: confirm every deferred item in these docs is already captured in `DEFERRED-BACKLOG.md` (it should be — the backlog was built from them). Spot-check, don't assume.
- [ ] `git rm` the source docs from the `wip/` worktree.
- [ ] Fix cross-references broken by the removal: grep the surviving `wip/` tree for links to the moved files and repoint or de-link. Held docs that link to each other (e.g. `post-pr933-xhigh-followups.md` ↔ its now-moved siblings) need attention. Run the link sweep to confirm clean.
- [ ] Decide how history docs reference back into the pipelex repo (cross-repo links are inherently broken once relocated) — either strip those links or note them as historical. Record the decision in the log.
- [ ] Commit the worktree (`docs/Tidy`): `git rm`s + link fixes.
- [ ] Commit the workspace repo (`main`): the new `docs/history/` content. **This commit is on `main` of the workspace repo — higher blast radius. Do NOT push without the user's say-so.**

### ☑ CHECKPOINT A — **STOP** (after Phase 1)

This phase touched two repos and produced two commits — a mandatory stop. Before stopping: verify both repos are clean, the link sweep passes in `wip/`, and the workspace-repo commit contains only the intended history files. Record both commit SHAs and the cross-repo-link decision in the [Progress log](#progress-log). Confirm with the user whether to push either repo.

---

## Phase 2 — Editorial in-place corrections (keep-active docs)

Fix the stale claims in docs that stay active. List: `TIDY-MANIFEST.md` → §"keep-active" notes and "Execution notes" step 6. **Each correction is a doc edit that must be validated against current code — do not apply a manifest note blindly; the manifest predates the bug verification and some of its notes are nuanced or already-addressed.**

- [ ] `02-master-plan.md` P1: reconcile the "generate_report() has zero runtime callers" note. Per `BUG-VERIFICATION.md`, `generate_report` now *does* have a caller (`_run_core.py:224`), but the cross-worker **aggregation** path (`inject_tokens_usages` / `UsageAggregator`) is still unwired. Correct the wording to match that reality; do not overstate it as "fully wired."
- [ ] `error-handling/architecture.md`: refresh the `ErrorReport` schema section (missing `title`, `type_uri`, `caller_facing_message`, `DisclosureMode`; "frozen pydantic dataclass" → frozen `BaseModel`; add the `AMBIGUOUS`/`UNKNOWN` enum nuance). Verify field names against `pipelex/base_exceptions.py` before writing.
- [ ] `error-handling/track-cli-delivery.md`: stale ContextVar names (`_agent_cli_output_format` → `_agent_cli_error_format`), `display_error_panel` `error_message: str | None`. Verify against `agent_output.py` / `error_handlers.py`.
- [ ] `error-handling/track-metadata-model.md`, `track-temporal-integration.md`, `track-worker-classification.md`: apply the minor type/name/wrapper fixes noted in the manifest, each checked against code (e.g. `azure_img_gen_worker.py` still has a `_raise_categorized_*` wrapper — reconcile doc vs code).
- [ ] `concurrency/README.md`: drop the now-shipped "retry jitter quick win" from suggested next steps (verified shipped — see backlog "Recently shipped" note).
- [ ] Run the link sweep after edits (no links should have moved, but confirm).
- [ ] Commit the worktree (`docs/Tidy`).

---

## Phase 3 — Confirm the two `[unverified]` backlog items

These two bug entries could not be settled statically; resolve them and update `DEFERRED-BACKLOG.md` + `BUG-VERIFICATION.md` with the outcome.

- [ ] **Offline baseline test** (`tests/e2e/agent_cli/test_offline_run_dry.py::...no_cache_no_network...`): run it locally — `.venv/bin/pytest tests/e2e/agent_cli/test_offline_run_dry.py -k no_cache_no_network`. It is `gha_disabled` (subprocess E2E). If green, mark the backlog row `[RESOLVED]` and drop it; if red, re-open with the real failure.
- [ ] **plxt PipeStructure schema** (cross-repo): the pipelex side is correct/test-guarded; the bundled schema lives in the sibling repo `vscode-pipelex/crates/taplo-common/schemas/mthds_schema.json`. Check whether it contains `PipeStructureBlueprint` (regenerate via the pipelex generator and diff); re-file against `vscode-pipelex` if stale. This requires leaving this worktree — flag to the user rather than wandering repos unprompted.
- [ ] Update the two rows in `DEFERRED-BACKLOG.md` and the corresponding sections in `BUG-VERIFICATION.md`; commit the worktree.

### ☑ CHECKPOINT B — **STOP** (docs tidy complete)

After Phase 3, the documentation tidy is fully complete on `docs/Tidy`. Mandatory stop: this is the clean "docs done" milestone and the natural place to open a PR or merge. Before stopping: link sweep clean, `git status` clean, all three review docs reflect final state. Record the milestone, all commit SHAs, and whether a PR was opened in the [Progress log](#progress-log). **Get the user's decision on merging `docs/Tidy` and on whether to proceed to Phase 4 at all.**

---

## Phase 4 — Code fixes (runtime; separate branch; requires the test gate)

These are *not* docs — they change `pipelex/` and need `make agent-check` + tests. They are a different risk profile and almost certainly do **not** belong on the docs-only `docs/Tidy` branch.

### ☑ CHECKPOINT C — **STOP BEFORE STARTING** (branch decision)

Do not write any code under this phase until you have confirmed with the user: (a) that they want these fixes now, and (b) which branch — mixing runtime fixes into `docs/Tidy` is wrong; expect a fresh branch off `main` of the pipelex repo (not the worktree). Record the branch decision before proceeding. After each fix: `make agent-check` then the targeted tests for the touched area (see `tests/CLAUDE.md` source→test mapping); full `make agent-test` before any push.

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

- **2026-05-29 — Plan created.** Reorg (`d2fcd0a0`) and review docs (`0d1ab679`) already committed on `docs/Tidy`; backlog verified against code. Nothing in this plan started. Next action: Phase 1 (cross-repo move-to-history). Open questions: (1) push policy for the workspace-repo `main` commit in Phase 1; (2) whether to merge/PR `docs/Tidy` at Checkpoint B; (3) branch for Phase 4 code fixes.
