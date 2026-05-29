# Tidy Manifest — `_docs/wip/` cleanup

This is a review artifact, not an executed change. It consolidates the per-file triage produced by upstream agents into one actionable plan for tidying the `_docs/wip/` working-docs tree. It lives on branch `docs/Tidy`. **Nothing has been moved, renamed, or deleted yet** — every disposition below is a proposal awaiting your review. Once approved, the steps in "Execution notes" make the changes mechanical. Two destinations do not exist yet and will be created on execution: the workspace history store at `/Users/lchoquel/repos/Pipelex/docs/history/` (a separate repo, sibling to this worktree) and the `wip/error-handling/archive/` subfolder.

## Execution status

**Executed** on branch `docs/Tidy` (staged, not yet committed): the in-worktree reorganization — files grouped into the new `crate-architecture/`, `graph-model/`, and `wip/error-handling/archive/` folders; finished docs moved into `archive/`; the misnamed live-bug doc renamed (`archive-delivery-error-path-request-id.md` → `track-delivery-error-path-request-id.md`); the derived `.html` renders and dead/duplicate archive docs deleted; and all cross-references repointed (verified with a full link-resolution sweep).

**Held** for a separate, confirmed step: the **move-to-history** bucket. Every doc in that bucket is still in place under `wip/`; nothing has been copied to the workspace `docs/history/` repo yet.

**Deviation from the per-file triage:** `error-handling/track-extract-classify-render.md` was triaged for archival but is kept **active** — the curated `error-handling/README.md` and two other docs treat it as the authoritative current-state doc, so archiving it would have contradicted the folder's structure.

**Convention:** finished error-handling docs were archived into a `wip/error-handling/archive/` subfolder (not an `archive-` filename prefix).

**Not done (editorial, deferred):** the in-place content corrections to keep-active docs (the stale `generate_report()` claim in `02-master-plan.md` P1, the `ErrorReport` schema section in `architecture.md`, and the minor type/name fixes in a few `track-*` docs). Each needs a code check; best done as a focused follow-up. See [keep-active](#keep-active) and [Execution notes](#execution-notes).

**Pre-existing broken links** (not introduced by this cleanup) remain in a few archived/historical docs — chiefly an absolute-style `wip/...`-from-inside-`wip/` link pattern and a couple of wrong relative paths in `archive/00-master-plan.md` and `archive/01-master-plan.md`. Left untouched; flag for a separate sweep if wanted.

## Summary

Every doc was triaged into one disposition. The buckets, in the order they appear under [Dispositions](#dispositions): **keep-active** (live plans, current-state `track-*` docs, and docs already correctly in an `archive/`), **organize-into-folder** (a few loose top-level files grouped into topic folders), **mark-archived** (finished docs still loose in the active tree → an `archive/` subfolder), **promote-to-official** (none this round), **move-to-history** (finished internal planning → the separate workspace `docs/history/` repo), and **delete** (derived `.html` renders + dead/duplicate archive docs).

The dimension that matters most is whether a doc's claims still match the shipped code. Most docs are consistent or describe pure history (not-applicable); some are partially-consistent (minor drift, fixable in place); the docs that actively **contradict** the code are enumerated in the next section — those are the real liabilities.

## Red flags — docs inconsistent with code

These are the docs whose content actively contradicts the codebase. They matter most: a doc that lies about the code is worse than no doc. Most are already archived/superseded design records where the inconsistency is harmless history — but two are live (`archive-delivery-error-path-request-id.md`, `phase3-mode2-regression.md` is closed) and one (`template-preprocessor-css-collision.md`) is a superseded design still sitting in the active tree.

| Path | What contradicts the code | Recommended action |
| --- | --- | --- |
| `wip/archive/early-temporal-library-fix-proposals.md` | Describes `LibraryContext` / `TemporalPipeJobEnvelope` that were never built; shipped code uses `LibraryCrate` + in-workflow loading. | Leave in `archive/` — pure design history, no action. |
| `wip/archive/operators-as-activities-analysis.md` | "Current architecture" section contradicts the shipped `tprl_content_generation` collapse. | **Delete** — CHANGELOG is the durable record. |
| `wip/archive/scoped-registry-teardown.md` | Proposes a ContextVar token-teardown pattern that was replaced by the per-workflow `ClassRegistry` in `wf_pipe_router.py`. | Leave in `archive/` as superseded — no action. |
| `wip/archive/tier2-live-bug-recap.md` | References `WfMakeObject`, `ContentGeneratorChild.make_object_direct`, `_collect_class_sources` — all removed. | **Delete** — resolved by crate-propagation; `phase2-crate-propagation-rationale.md` is the record. |
| `wip/archive/tier2-live-registry-propagation.md` | Marked "Open — needs architectural decision" but the fix (`SchemaToModelFactory`) has shipped. | **Delete** — stale "still open" noise. |
| `wip/archive/workflow-and-activity-ids.md` | Describes wfid/LRU machinery that no longer exists in `content_generator_in_workflow.py`. | Leave in `archive/` — complete historical record, no open items. |
| `wip/archive/phase3-mode2-regression.md` | Historical bug investigation; described state no longer matches code. | Leave in `archive/` — purpose served, no action. |
| `wip/template-preprocessor-css-collision.md` | Proposed heuristic regex superseded by the strict line-bounded approach that actually shipped. | **Organize into `wip/archive/`** — move out of the active tree (see Dispositions). |

## Dispositions

### keep-active

Live plans, current-state track docs, deferred-item indexes, and finished docs already sitting correctly in an `archive/` subfolder. No move; a few flagged for in-place correction.

| Path | Current location | Proposed target | Why |
| --- | --- | --- | --- |
| `wip/02-master-plan.md` | `wip/` | stays | The live master plan. P0 done; P0.1/P0.2/P1/P2/P3 open. Correct the stale "generate_report() has zero runtime callers" claim in P1. |
| `wip/deferred-items.md` | `wip/` | stays | Canonical non-temporal deferral index, cross-referenced by temporal-next and crate docs. |
| `wip/phase6a-local-cross-package-deps.md` | `wip/` | stays | P2 in the master plan; not-started forward plan. |
| `wip/phase6b-remote-deps-from-github.md` | `wip/` | stays | P3 in the master plan; not-started forward plan. |
| `wip/security/webhook-signing.md` | `wip/security/` | stays | Open security gap; all tracked items unimplemented. |
| `wip/structured-logging/kickoff.md` | `wip/structured-logging/` | stays | Cold-start brief for the upcoming structured-logging refactor; matches current code. |
| `wip/tracing-cost-reporting-as-built.md` | `wip/` | stays | As-built tracing reference; T2/T3 still open. Supersedes the distributed-tracing analysis. |
| `wip/concurrency/README.md` | `wip/concurrency/` | stays | Topic index. Update: remove the now-shipped "retry jitter quick win" as a suggested next step. |
| `wip/concurrency/batch-partial-failure.md` | `wip/concurrency/` | stays | Active design for unimplemented feature. |
| `wip/concurrency/fan-out-scheduling.md` | `wip/concurrency/` | stays | Active design; `gather_bounded` still uses old chunking. |
| `wip/concurrency/rate-limiting.md` | `wip/concurrency/` | stays | Active design; direct-mode inference gate not built. |
| `wip/error-handling/README.md` | `wip/error-handling/` | stays | Authoritative nav index for the error-handling folder. |
| `wip/error-handling/api-companion-revisions.md` | `wip/error-handling/` | stays | API-layer design contract; Stage 5 (webhook signing) open. |
| `wip/error-handling/architecture.md` | `wip/error-handling/` | stays | Structural reference for the track docs. Update: `ErrorReport` schema section is stale (missing `title`, `type_uri`, `caller_facing_message`, `DisclosureMode`). |
| `wip/error-handling/archive-delivery-error-path-request-id.md` | `wip/error-handling/` | rename to `wip/error-handling/track-delivery-error-path-request-id.md` | Misleadingly named "archive-"; describes an OPEN bug still present at `delivery_executor.py:244/291/294`. Drop the prefix. |
| `wip/error-handling/archive-llm-retry-loop-bypass.md` | `wip/error-handling/` | stays | Already correctly named/placed as a superseded archive entry; README references it. |
| `wip/error-handling/track-cli-delivery.md` | `wip/error-handling/` | stays | Current-state track doc. Correct in place: stale ContextVar naming + `error_message` type signature. |
| `wip/error-handling/track-metadata-model.md` | `wip/error-handling/` | stays | Current-state track doc with real open gaps. Correct stale type/field/enum details in place. |
| `wip/error-handling/track-retry-and-resilience.md` | `wip/error-handling/` | stays | Authoritative retry/resilience reference; consistent. |
| `wip/error-handling/track-temporal-integration.md` | `wip/error-handling/` | stays | Authoritative Temporal error-bridge reference; minor `recover_error_report` wording fix. |
| `wip/error-handling/track-testing.md` | `wip/error-handling/` | stays | Test-coverage reference; cosmetic path/name drift only. |
| `wip/error-handling/track-worker-classification.md` | `wip/error-handling/` | stays | Per-worker classification reference; minor `azure_img_gen_worker` wrapper fix. |
| `wip/temporal-next/00-enterprise-readiness-analysis.md` | `wip/temporal-next/` | stays | Owner doc for the enterprise-readiness roadmap; Phase 0 hygiene still open. |
| `wip/temporal-next/01-deferred-items.md` | `wip/temporal-next/` | stays | Active temporal deferred-items index; items verifiably open. |
| `wip/temporal-primitives/01-id-and-naming-design.md` | `wip/temporal-primitives/` | stays | Self-declared authoritative design reference; consistent with code. |
| `wip/temporal-primitives/03-temporal-error-handling-revamp.md` | `wip/temporal-primitives/` | stays | Scoped, deferred proposal; workaround still in code. |
| `wip/text-then-object/deferred-items.md` | `wip/text-then-object/` | stays | Deferred-items index for PR #891 punts; all items open. |
| `wip/archive/00-master-plan.md` | `wip/archive/` | stays | Completed plan, already archived correctly. |
| `wip/archive/01-master-plan.md` | `wip/archive/` | stays | Superseded by 02-master-plan; already archived correctly. |
| `wip/archive/activity_storage-plan.md` | `wip/archive/` | stays | Completed plan, already archived. |
| `wip/archive/activity_storage.md` | `wip/archive/` | stays | Completed design, already archived. |
| `wip/archive/collapse-content-generation-workflow-layer-v2-plan.md` | `wip/archive/` | stays | Finished plan, already archived. |
| `wip/archive/collapse-content-generation-workflow-layer-v2.md` | `wip/archive/` | stays | Finished analysis, already archived. |
| `wip/archive/early-library-as-execution-context.md` | `wip/archive/` | stays | Early vision, already archived; one open question surfaced as deferred. |
| `wip/archive/early-temporal-library-fix-proposals.md` | `wip/archive/` | stays | Superseded design history (see Red flags). |
| `wip/archive/id-and-naming-plan-pre-checkpoints.md` | `wip/archive/` | stays | Pre-checkpoint plan, correctly archived. |
| `wip/archive/offline-mode-remote-config-cache.md` | `wip/archive/` | stays | Completed plan, already archived. |
| `wip/archive/phase0-pipe-namespace-fix.md` | `wip/archive/` | stays | Finished plan, already archived. |
| `wip/archive/phase1-handoff.md` | `wip/archive/` | stays | Completed handoff, already archived. |
| `wip/archive/phase2-implementation-plan.md` | `wip/archive/` | stays | Completed plan, already archived; known-limitations map to future phases. |
| `wip/archive/phase3-mode2-regression.md` | `wip/archive/` | stays | Historical bug record (see Red flags). |
| `wip/archive/phase4.5-distributed-tracing-implementation.md` | `wip/archive/` | stays | Completed plan, already archived. |
| `wip/archive/phase5-payload-codec-DONE.md` | `wip/archive/` | stays | Completed plan, already archived. |
| `wip/archive/scoped-registry-teardown.md` | `wip/archive/` | stays | Superseded design (see Red flags). |
| `wip/archive/workflow-and-activity-ids.md` | `wip/archive/` | stays | Completed historical record (see Red flags). |

### organize-into-folder

Active docs that should be grouped into a topic folder to reduce top-level clutter. The crate-architecture trio is the main grouping; the other two each found a sensible home.

**New folder `wip/crate-architecture/`** — collect the crate-first design rationale with its two forward plans (currently the plans live at the top level; consider whether they move too, but per triage only the design doc is in scope here):

| Path | Current location | Proposed target | Why |
| --- | --- | --- | --- |
| `wip/future-crate-first-architecture.md` | `wip/` | `wip/crate-architecture/future-crate-first-architecture.md` | Durable crate-first design rationale; companion to phase6a/phase6b which reference it. |

**New folder `wip/graph-model/`**:

| Path | Current location | Proposed target | Why |
| --- | --- | --- | --- |
| `wip/stuffs-as-nodespec.md` | `wip/` | `wip/graph-model/stuffs-as-nodespec.md` | Active graph-model design starter; no sibling folder exists yet, so create `graph-model/`. |

**Into existing `wip/archive/`** (a superseded design that should leave the active tree):

| Path | Current location | Proposed target | Why |
| --- | --- | --- | --- |
| `wip/template-preprocessor-css-collision.md` | `wip/` | `wip/archive/template-preprocessor-css-collision.md` | Superseded design (inconsistent — see Red flags); archive alongside the line-bounded reference. |

### mark-archived

Finished/superseded docs in the active `wip/` or `wip/error-handling/` tree that should move into an `archive/` subfolder. The error-handling ones need a **new** `wip/error-handling/archive/` subfolder (does not exist yet). Two error-handling docs use an `archive-` filename prefix in place rather than an `archive/` subfolder per their triage target — those are flagged.

| Path | Current location | Proposed target | Why |
| --- | --- | --- | --- |
| `wip/distributed-tracing-and-reporting.md` | `wip/` | `wip/archive/distributed-tracing-and-reporting.md` | Self-declared "SUPERSEDED"; superseded by `tracing-cost-reporting-as-built.md`. Lands beside the impl plan in `archive/`. |
| `wip/error-handling/archive-error-handling-2.md` | `wip/error-handling/` | `wip/error-handling/archive/archive-error-handling-2.md` | Self-declared "ARCHIVED — COMPLETE"; move beside peer archive docs. |
| `wip/error-handling/archive-retry-and-resilience.md` | `wip/error-handling/` | `wip/error-handling/archive/archive-retry-and-resilience.md` | Header redirects to `track-retry-and-resilience.md`; move into archive subfolder. |
| `wip/error-handling/archive-retry-graph-trace.md` | `wip/error-handling/` | `wip/error-handling/archive/archive-retry-graph-trace.md` | Documents a resolved-by-removal gap; move into archive subfolder. |
| `wip/error-handling/archive-temporal-submitter-boundary.md` | `wip/error-handling/` | `wip/error-handling/archive/archive-temporal-submitter-boundary.md` | Fully shipped; current state lives in `track-temporal-integration.md`. |
| `wip/error-handling/archive-todos.md` | `wip/error-handling/` | `wip/error-handling/archive/archive-todos.md` | Completed execution ledger; header says "ARCHIVED — superseded". One deferred item (cause-chain serialization) to preserve. |
| `wip/error-handling/archive-worker-classification-sweep.md` | `wip/error-handling/` | `wip/error-handling/archive/archive-worker-classification-sweep.md` | Archived 2026-05-15; current state in `track-worker-classification.md`. |
| `wip/error-handling/changes-for-api-early-draft.md` | `wip/error-handling/` | `wip/error-handling/archive/changes-for-api-early-draft.md` | Superseded by `api-companion-revisions.md`; two open items extracted as deferred. |
| `wip/error-handling/post-pr933-followups-code-review.md` | `wip/error-handling/` | `wip/error-handling/archive/post-pr933-followups-code-review.md` | All findings resolved; finished code-review artifact. |
| `wip/error-handling/post-pr933-review-followups.md` | `wip/error-handling/` | `wip/error-handling/archive-post-pr933-review-followups.md` (prefix-rename per triage) | All phases complete; decisions recorded. Note: triage target uses an `archive-` prefix rather than the `archive/` subfolder — reconcile with the others below. |
| `wip/error-handling/post-xhigh-review-followups.md` | `wip/error-handling/` | `wip/error-handling/archive-post-xhigh-review-followups.md` (prefix-rename per triage) | Fully completed tracker; both commits in git history. Same prefix-vs-subfolder note as above. |
| `wip/error-handling/track-extract-classify-render.md` | `wip/error-handling/` | `wip/error-handling/archive/archive-extract-classify-render-track.md` | ECR refactor shipped; content is pre-refactor narrative, duplicates the archive companion. Superseded by `archive-extract-classify-render.md`. |
| `wip/error-handling/track-strict-disclosure-input-domain-gap.md` | `wip/error-handling/` | `wip/error-handling/archive/track-strict-disclosure-input-domain-gap.md` | Landed 2026-05-22; both gaps closed in code. |
| `wip/text-then-object/text-then-object-plan.md` | `wip/text-then-object/` | `wip/archive/text-then-object-plan.md` | All phases complete; deferred items already in sibling `deferred-items.md`. Topic folder stays for the active deferred index. |

> Convention note: most error-handling archive moves target a new `wip/error-handling/archive/` subfolder, but `post-pr933-review-followups.md` and `post-xhigh-review-followups.md` were triaged to an in-place `archive-` filename prefix. Pick one convention before executing. The subfolder is cleaner and matches `wip/archive/`; recommend routing all three (these two plus the others) into `wip/error-handling/archive/`.

### promote-to-official

None. No `wip/` doc was triaged as ready to promote into the published docs under `_docs/docs/` (e.g. `distributed-execution/`, `under-the-hood/`, `reliability/`, `advanced/`, `features/`, `errors/`). The closest durable references (`tracing-cost-reporting-as-built.md`, `temporal-primitives/01-id-and-naming-design.md`, `error-handling/architecture.md`) are kept active for now and would be promotion candidates in a later pass — likely into `under-the-hood/` — but none are proposed for promotion in this round.

### move-to-history

Finished docs with no residual active value, worth preserving as institutional memory. Target is the **separate workspace repo** at `/Users/lchoquel/repos/Pipelex/docs/history/` — NOT this worktree. That `history/` directory does not exist yet and must be created. These are cross-repo copies (the source files are then removed from `wip/`).

| Path | Current location | Proposed target | Why |
| --- | --- | --- | --- |
| `wip/api-readiness-2-handoff-drafts.md` | `wip/` | `docs/history/error-handling/api-readiness-2-handoff-drafts.md` | Finished message drafts; branch landed, placeholders never filled. |
| `wip/api-readiness-2-handoff.md` | `wip/` | `docs/history/error-handling/api-readiness-2-handoff.md` | Launchpad doc; PR #943 landed. Useful coordination memory. |
| `wip/console-targets-and-agent-cli-stdout.md` | `wip/` | `docs/history/console-output/console-targets-and-agent-cli-stdout.md` | Both parts shipped; acceptance criteria ticked. |
| `wip/template-preprocessor-line-bounded-at.md` | `wip/` | `docs/history/template-preprocessor/template-preprocessor-line-bounded-at.md` | Fully-shipped TDD plan; validator spec diverged from impl, so not kept as reference. |
| `wip/template-preprocessor-residual-edge-cases.md` | `wip/` | `docs/history/template-preprocessor/template-preprocessor-residual-edge-cases.md` | Self-declared superseded (inconsistent); old sigil architecture gone. |
| `wip/temporal-listcontent-decode-bug.md` | `wip/` | `docs/history/temporal-listcontent-decode-bug/temporal-listcontent-decode-bug.md` | Fix shipped 2026-05-10; historical root-cause record. |
| `wip/error-handling/archive-extract-classify-render.md` | `wip/error-handling/` | `docs/history/error-handling/archive-extract-classify-render.md` | Self-archived; current state in `track-extract-classify-render.md`. Keeps deviation rationale. |
| `wip/error-handling/archive-temporal-activity-boundary.md` | `wip/error-handling/` | `docs/history/error-handling/archive-temporal-activity-boundary.md` | Self-archived; TDD checkpoint record. Two low-severity optional items surfaced as deferred. |
| `wip/error-handling/archive-todos-api-readiness-2.md` | `wip/error-handling/` | `docs/history/error-handling/archive-todos-api-readiness-2.md` | Self-archived 2026-05-28; all phases checked. |
| `wip/error-handling/post-pr933-xhigh-followups.md` | `wip/error-handling/` | `docs/history/error-handling/post-pr933-xhigh-followups.md` | All findings resolved in one session; zero residual planning value. |
| `wip/error-handling/track-webhook-payload-collision.md` | `wip/error-handling/` | `docs/history/error-handling/track-webhook-payload-collision.md` | Fix landed 2026-05-22; CHANGELOG is the authoritative record. |
| `wip/error-handling/review-notes/search-worker-review-followups.md` | `wip/error-handling/review-notes/` | `docs/history/error-handling/search-worker-review-followups.md` | Phase 12 review note; two optional test-gap follow-ups surfaced as deferred. |
| `wip/error-handling/review-notes/temporal-activity-boundary-review-followups.md` | `wip/error-handling/review-notes/` | `docs/history/error-handling/temporal-activity-boundary-review-followups.md` | Parent plan archived; one stale + one optional item. |
| `wip/archive/per-activity-queue-routing-v1.md` | `wip/archive/` | `docs/history/temporal-primitives/per-activity-queue-routing-v1.md` | v1 fully landed; historical design context. Two deferred test-upgrade items surfaced. |
| `wip/archive/phase2-crate-propagation-rationale.md` | `wip/archive/` | `docs/history/temporal-library-crate/phase2-crate-propagation-rationale.md` | Completed ADR; durable rationale worth preserving in history. |
| `wip/archive/phase4-explicit-class-registry.md` | `wip/archive/` | `docs/history/temporal-primitives/phase4-explicit-class-registry.md` | Fully shipped; internal refactor mechanics. |
| `wip/archive/queue-options-and-worker-profiles-plan.md` | `wip/archive/` | `docs/history/temporal-primitives/queue-options-and-worker-profiles-plan.md` | All phases shipped 2026-05-11; three deferred follow-ups surfaced. |
| `wip/archive/queue-options-and-worker-profiles.md` | `wip/archive/` | `docs/history/temporal-primitives/queue-options-and-worker-profiles.md` | Companion design; code matches; three deferred follow-ups surfaced. |
| `wip/temporal-primitives/00-temporal-id-primitives.md` | `wip/temporal-primitives/` | `docs/history/temporal-primitives/00-temporal-id-primitives.md` | Research input; design session over, `01-id-and-naming-design.md` is the durable doc. |
| `wip/temporal-primitives/02-id-and-naming-plan.md` | `wip/temporal-primitives/` | `docs/history/temporal-primitives/02-id-and-naming-plan.md` | All phases shipped; rationale trail. Four deferred items surfaced. |

### delete

Derived `.html` PR-story renders whose `.md` source is preserved, plus finished/superseded docs already in `archive/` with no residual value (their durable record is the code, CHANGELOG, or a companion doc). Extract any listed deferred items before deleting.

| Path | Current location | Proposed target | Why |
| --- | --- | --- | --- |
| `wip/offline-mode-pr-story.html` | `wip/` | (delete) | Derived render; source archived at `archive/offline-mode-remote-config-cache.md`. Deferred items already in the archive plan. |
| `wip/archive/collapse-content-generation-workflow-layer-v1.md` | `wip/archive/` | (delete) | v1 fully executed; superseded by v2 docs in same folder. |
| `wip/archive/collapse-content-generation-workflow-layer.html` | `wip/archive/` | (delete) | Derived render; v2 `.md` companion is authoritative. Extract section-12 deferred items first. |
| `wip/archive/kajson-decoder-class-registry.md` | `wip/archive/` | (delete) | Bug fully shipped; traceable via CHANGELOG. |
| `wip/archive/operators-as-activities-analysis.md` | `wip/archive/` | (delete) | Decision shipped; "current architecture" section now wrong (see Red flags). |
| `wip/archive/phase3-eng-review.md` | `wip/archive/` | (delete) | Pre-impl review; impl shipped, rationale in `phase3-execution-plan.md`. |
| `wip/archive/phase3-execution-plan.md` | `wip/archive/` | (delete) | Pure checklist, all shipped; rationale preserved in `phase3-eng-review.md`. (Note: the two reference each other — keep at least one if either is wanted; both triaged delete.) |
| `wip/archive/phase5-payload-codec-strategy.md` | `wip/archive/` | (delete) | Superseded by `phase5-payload-codec-DONE.md`; impl shipped. Extract the one monitor item. |
| `wip/archive/pr-943-review-agents-triage.md` | `wip/archive/` | (delete) | All fixes verified; residual items were transient ops tasks. |
| `wip/archive/preserved-from-registry-commits.md` | `wip/archive/` | (delete) | Obsolete re-apply note; knowledge migrated to `under-the-hood/temporal-integration.md`. |
| `wip/archive/raw-working-memory-through-act_deliver-DONE.md` | `wip/archive/` | (delete) | All work shipped; no deferred items. |
| `wip/archive/refactor-drop-text-then-object.html` | `wip/archive/` | (delete) | Derived render; source plan in `wip/text-then-object/`. Extract kajson-race deferred item first. |
| `wip/archive/tier2-live-bug-recap.md` | `wip/archive/` | (delete) | References removed code (see Red flags). |
| `wip/archive/tier2-live-registry-propagation.md` | `wip/archive/` | (delete) | Fix shipped; "still open" status is stale (see Red flags). |
| `wip/error-handling/api-readiness-2.html` | `wip/error-handling/` | (delete) | Derived render; source `api-companion-revisions.md` kept; deferred items tracked in live docs. |
| `wip/error-handling/error-handling.html` | `wip/error-handling/` | (delete) | Derived visual briefing; all content authoritative in co-located track docs. |
| `wip/temporal-primitives/id-and-naming.html` | `wip/temporal-primitives/` | (delete) | Derived render; source `.md` docs kept in same folder. |
| `wip/temporal-primitives/queues-and-options.html` | `wip/temporal-primitives/` | (delete) | Derived render; one stale claim; source archived. |
| `wip/text-then-object/PR-text-then-object.html` | `wip/text-then-object/` | (delete) | Derived render; deferred items already in sibling `deferred-items.md`. |

## Supersession & duplicates

**Supersession chains** (newer replaces older):

- `archive/00-master-plan.md` → `archive/01-master-plan.md` → `02-master-plan.md` (live).
- `archive/collapse-content-generation-workflow-layer-v1.md` → `archive/collapse-content-generation-workflow-layer-v2.md` (+ `-v2-plan.md`).
- `archive/id-and-naming-plan-pre-checkpoints.md` + `archive/workflow-and-activity-ids.md` → `temporal-primitives/02-id-and-naming-plan.md` (which itself moves to history; `01-id-and-naming-design.md` is the surviving authoritative reference).
- `archive/early-library-as-execution-context.md` → `archive/00-master-plan.md`; `archive/early-temporal-library-fix-proposals.md` → `archive/phase2-crate-propagation-rationale.md`.
- `distributed-tracing-and-reporting.md` (+ `archive/phase4.5-distributed-tracing-implementation.md`) → `tracing-cost-reporting-as-built.md`.
- `error-handling/changes-for-api-early-draft.md` → `error-handling/api-companion-revisions.md`.
- `error-handling/archive-llm-retry-loop-bypass.md` → `error-handling/archive-retry-and-resilience.md` → `error-handling/track-retry-and-resilience.md`.
- `error-handling/archive-extract-classify-render.md` ↔ `track-extract-classify-render.md` (the archive doc is now the source-of-truth; the track doc is being archived as a duplicate narrative).
- `error-handling/post-pr933-followups-code-review.md` → `error-handling/post-pr933-review-followups.md`.
- `archive/phase5-payload-codec-strategy.md` → `archive/phase5-payload-codec-DONE.md`.
- `archive/scoped-registry-teardown.md` / `archive/kajson-decoder-class-registry.md` → resolved by the per-workflow `ClassRegistry` pattern in `wf_pipe_router.py`.
- `archive/tier2-live-bug-recap.md` / `archive/tier2-live-registry-propagation.md` → `archive/phase2-crate-propagation-rationale.md` (+ `schema_to_model_factory.py`).
- `template-preprocessor-css-collision.md` / `template-preprocessor-residual-edge-cases.md` → `template-preprocessor-line-bounded-at.md`.

**`.html` / `.md` duplicate pairs** (the `.html` is a derived render of a `.md` plan; all `.html` are slated for deletion):

| `.html` (derived, delete) | `.md` source kept |
| --- | --- |
| `wip/offline-mode-pr-story.html` | `wip/archive/offline-mode-remote-config-cache.md` |
| `wip/archive/collapse-content-generation-workflow-layer.html` | `wip/archive/collapse-content-generation-workflow-layer-v2.md` |
| `wip/archive/refactor-drop-text-then-object.html` | `wip/text-then-object/text-then-object-plan.md` (+ `deferred-items.md`) |
| `wip/error-handling/api-readiness-2.html` | `wip/error-handling/api-companion-revisions.md` |
| `wip/error-handling/error-handling.html` | `wip/error-handling/track-*.md` + `architecture.md` |
| `wip/temporal-primitives/id-and-naming.html` | `wip/temporal-primitives/00/01/02-*.md` |
| `wip/temporal-primitives/queues-and-options.html` | `wip/archive/queue-options-and-worker-profiles*.md` |
| `wip/text-then-object/PR-text-then-object.html` | `wip/text-then-object/text-then-object-plan.md` |

## Execution notes

Run everything from the worktree root `/Users/lchoquel/repos/Pipelex/_docs/` unless noted. Stay on branch `docs/Tidy`. None of the steps below have been executed.

**Before any move — harvest deferred items.** Several docs slated for delete/move/history carry open deferred items (e.g. `collapse-content-generation-workflow-layer.html` §12, `refactor-drop-text-then-object.html` kajson race, `phase5-payload-codec-strategy.md` monitor item, `changes-for-api-early-draft.md` Stages 5/6, `archive-todos.md` cause-chain serialization, the queue-routing/queue-options/id-and-naming/console-targets deferred lists). Confirm each is already captured in a surviving index (`wip/deferred-items.md`, `wip/temporal-next/01-deferred-items.md`, `wip/text-then-object/deferred-items.md`, `wip/security/webhook-signing.md`, `wip/error-handling/track-metadata-model.md`) before deleting or moving its source. Add any that are missing.

**0. Create new destination folders.**

```sh
mkdir -p wip/crate-architecture wip/graph-model wip/error-handling/archive
mkdir -p /Users/lchoquel/repos/Pipelex/docs/history
```

**1. organize-into-folder** (`git mv` within the worktree):

```sh
git mv wip/future-crate-first-architecture.md wip/crate-architecture/future-crate-first-architecture.md
git mv wip/stuffs-as-nodespec.md wip/graph-model/stuffs-as-nodespec.md
git mv wip/template-preprocessor-css-collision.md wip/archive/template-preprocessor-css-collision.md
```

**2. mark-archived** (`git mv` within the worktree). Recommend routing ALL error-handling archive moves into the `archive/` subfolder (override the two prefix-only triage targets for consistency):

```sh
git mv wip/distributed-tracing-and-reporting.md wip/archive/distributed-tracing-and-reporting.md
git mv wip/error-handling/archive-error-handling-2.md wip/error-handling/archive/archive-error-handling-2.md
git mv wip/error-handling/archive-retry-and-resilience.md wip/error-handling/archive/archive-retry-and-resilience.md
git mv wip/error-handling/archive-retry-graph-trace.md wip/error-handling/archive/archive-retry-graph-trace.md
git mv wip/error-handling/archive-temporal-submitter-boundary.md wip/error-handling/archive/archive-temporal-submitter-boundary.md
git mv wip/error-handling/archive-todos.md wip/error-handling/archive/archive-todos.md
git mv wip/error-handling/archive-worker-classification-sweep.md wip/error-handling/archive/archive-worker-classification-sweep.md
git mv wip/error-handling/changes-for-api-early-draft.md wip/error-handling/archive/changes-for-api-early-draft.md
git mv wip/error-handling/post-pr933-followups-code-review.md wip/error-handling/archive/post-pr933-followups-code-review.md
git mv wip/error-handling/post-pr933-review-followups.md wip/error-handling/archive/post-pr933-review-followups.md
git mv wip/error-handling/post-xhigh-review-followups.md wip/error-handling/archive/post-xhigh-review-followups.md
git mv wip/error-handling/track-extract-classify-render.md wip/error-handling/archive/archive-extract-classify-render-track.md
git mv wip/error-handling/track-strict-disclosure-input-domain-gap.md wip/error-handling/archive/track-strict-disclosure-input-domain-gap.md
git mv wip/text-then-object/text-then-object-plan.md wip/archive/text-then-object-plan.md
```

**3. keep-active rename** (the misnamed live bug report):

```sh
git mv wip/error-handling/archive-delivery-error-path-request-id.md wip/error-handling/track-delivery-error-path-request-id.md
```

**4. move-to-history** (cross-repo: copy into the sibling `docs/` repo, then remove from the worktree). The history store is a different git repo, so a plain `cp` + `git rm` is correct — `git mv` cannot cross repos.

```sh
H=/Users/lchoquel/repos/Pipelex/docs/history
mkdir -p "$H/error-handling" "$H/console-output" "$H/template-preprocessor" \
         "$H/temporal-listcontent-decode-bug" "$H/temporal-primitives" "$H/temporal-library-crate"

# top-level wip
cp wip/api-readiness-2-handoff-drafts.md "$H/error-handling/"
cp wip/api-readiness-2-handoff.md "$H/error-handling/"
cp wip/console-targets-and-agent-cli-stdout.md "$H/console-output/"
cp wip/template-preprocessor-line-bounded-at.md "$H/template-preprocessor/"
cp wip/template-preprocessor-residual-edge-cases.md "$H/template-preprocessor/"
cp wip/temporal-listcontent-decode-bug.md "$H/temporal-listcontent-decode-bug/"

# error-handling
cp wip/error-handling/archive-extract-classify-render.md "$H/error-handling/"
cp wip/error-handling/archive-temporal-activity-boundary.md "$H/error-handling/"
cp wip/error-handling/archive-todos-api-readiness-2.md "$H/error-handling/"
cp wip/error-handling/post-pr933-xhigh-followups.md "$H/error-handling/"
cp wip/error-handling/track-webhook-payload-collision.md "$H/error-handling/"
cp wip/error-handling/review-notes/search-worker-review-followups.md "$H/error-handling/"
cp wip/error-handling/review-notes/temporal-activity-boundary-review-followups.md "$H/error-handling/"

# archive + temporal-primitives
cp wip/archive/per-activity-queue-routing-v1.md "$H/temporal-primitives/"
cp wip/archive/phase2-crate-propagation-rationale.md "$H/temporal-library-crate/"
cp wip/archive/phase4-explicit-class-registry.md "$H/temporal-primitives/"
cp wip/archive/queue-options-and-worker-profiles-plan.md "$H/temporal-primitives/"
cp wip/archive/queue-options-and-worker-profiles.md "$H/temporal-primitives/"
cp wip/temporal-primitives/00-temporal-id-primitives.md "$H/temporal-primitives/"
cp wip/temporal-primitives/02-id-and-naming-plan.md "$H/temporal-primitives/"

# then remove the sources from the worktree
git rm wip/api-readiness-2-handoff-drafts.md wip/api-readiness-2-handoff.md \
       wip/console-targets-and-agent-cli-stdout.md \
       wip/template-preprocessor-line-bounded-at.md wip/template-preprocessor-residual-edge-cases.md \
       wip/temporal-listcontent-decode-bug.md \
       wip/error-handling/archive-extract-classify-render.md \
       wip/error-handling/archive-temporal-activity-boundary.md \
       wip/error-handling/archive-todos-api-readiness-2.md \
       wip/error-handling/post-pr933-xhigh-followups.md \
       wip/error-handling/track-webhook-payload-collision.md \
       wip/error-handling/review-notes/search-worker-review-followups.md \
       wip/error-handling/review-notes/temporal-activity-boundary-review-followups.md \
       wip/archive/per-activity-queue-routing-v1.md \
       wip/archive/phase2-crate-propagation-rationale.md \
       wip/archive/phase4-explicit-class-registry.md \
       wip/archive/queue-options-and-worker-profiles-plan.md \
       wip/archive/queue-options-and-worker-profiles.md \
       wip/temporal-primitives/00-temporal-id-primitives.md \
       wip/temporal-primitives/02-id-and-naming-plan.md
```

Commit the history copies in the sibling repo separately (`cd /Users/lchoquel/repos/Pipelex/docs && git add history && git commit`).

**5. delete** (`git rm` within the worktree — do this only after step "harvest deferred items" is confirmed):

```sh
git rm wip/offline-mode-pr-story.html \
       wip/archive/collapse-content-generation-workflow-layer-v1.md \
       wip/archive/collapse-content-generation-workflow-layer.html \
       wip/archive/kajson-decoder-class-registry.md \
       wip/archive/operators-as-activities-analysis.md \
       wip/archive/phase3-eng-review.md \
       wip/archive/phase3-execution-plan.md \
       wip/archive/phase5-payload-codec-strategy.md \
       wip/archive/pr-943-review-agents-triage.md \
       wip/archive/preserved-from-registry-commits.md \
       wip/archive/raw-working-memory-through-act_deliver-DONE.md \
       wip/archive/refactor-drop-text-then-object.html \
       wip/archive/tier2-live-bug-recap.md \
       wip/archive/tier2-live-registry-propagation.md \
       wip/error-handling/api-readiness-2.html \
       wip/error-handling/error-handling.html \
       wip/temporal-primitives/id-and-naming.html \
       wip/temporal-primitives/queues-and-options.html \
       wip/text-then-object/PR-text-then-object.html
```

**6. keep-active in-place corrections** (manual edits, no move). These are the small fixes flagged in the keep-active table — apply with the Edit tool, not a script:

- `wip/02-master-plan.md` — correct the stale "generate_report() has zero runtime callers" claim in P1.
- `wip/concurrency/README.md` — drop the now-shipped "retry jitter quick win" from suggested next steps.
- `wip/error-handling/architecture.md` — refresh the `ErrorReport` schema section (add `title`, `type_uri`, `caller_facing_message`, `DisclosureMode`).
- `wip/error-handling/track-cli-delivery.md`, `track-metadata-model.md`, `track-temporal-integration.md`, `track-worker-classification.md` — apply the minor type/name/wrapper corrections noted per-doc.

**promote-to-official** — no editorial rewrites required this round (no docs were triaged for promotion).

**Cross-reference fixups after moving.** Several docs link to files that move. After steps 1–5, grep the surviving `wip/` tree for references to moved/deleted paths and repoint them — notably the error-handling `README.md` (links to several archive- docs), `02-master-plan.md` (links to `future-crate-first-architecture.md` and the tracing as-built), and `phase6a`/`phase6b` (link to `future-crate-first-architecture.md`, now under `crate-architecture/`).
