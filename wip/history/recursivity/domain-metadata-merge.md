# Handoff — domain metadata merge under the additive multi-file model (pipelex)

> **Status: DONE.** Implemented on `feature/Support-recursive-design`. Surfaced during the final `mthds-plugins/wip/recursive/design.md` review. Small, self-contained pipelex change. Builds on the additive multi-file model already shipped on this branch (see `../../TODOS.md` Parts A+B and [`recursive-followups.md`](recursive-followups.md) Tasks 1–2). Does **not** block the additive model — it removes friction the model introduces.
>
> Verified: `make agent-test` (green) + `make agent-check` (clean).
>
> **As built.** Added the order-independent, omission-quiet merge as a shared helper `pipelex/libraries/domain/domain_metadata_merge.py::merge_domain_metadata_field(...)`, wired from both `LibraryCrateFactory.make_from_blueprints` (crate-blueprint layer) and `DomainLibrary.add_domain` (runtime-`Domain` layer). The resolved conflict-resolution TODO at `domain_library.py` is gone (the separate system_prompt-inlining TODO is kept). `main_pipe` left untouched (inert, per below). Tests in `tests/unit/pipelex/libraries/test_library_crate.py` + `test_domain_library.py` (both-orders membership, same-value no-warn, conflict-warns, across description + system_prompt) with warnings asserted via `caplog`. CHANGELOG `[Unreleased]` sub-bullet folded into the "Additive multi-file library construction" entry.

## Why

The additive model authors a same-domain library as many `.mthds` files: one **root** (`bundle.mthds`) that carries the full domain header (`domain`, `description`, `main_pipe`, optional `system_prompt`) and N **non-root definition files** that carry only `domain = "<same_domain>"` to declare membership (see `design.md` §2.7 and the §3 worked example — `build_research_brief.mthds` sets only `domain = "research_brief"`).

The domain-metadata merge was written for the single-file world (first-write-wins + warn on any difference). Under the additive model it misbehaves in two ways, both rooted in "an omitted field is treated as a conflicting empty value":

1. **Spurious warnings on every validation.** A non-root file omits `description`, so the merge compares the root's real description against `""` and logs `Domain '<d>' declared with different descriptions: '<real>' vs ''. Keeping the first.` This fires once per non-root file, at **two** layers (see Where), and the PostToolUse hook validates the whole library (`-L <dir>`) on **every per-file save** — so a build of K files emits O(K) warnings on every save. Pure noise that will train authors/agents to ignore warnings.

2. **Load-order-dependent metadata loss (the real bug).** First-write-wins means the *first* domain blueprint seen wins. If a non-root file (empty description) is merged before the root, the assembled domain keeps `description = ""` and the root's real description is **discarded** (with the warning above). The assembled domain's `description` / `system_prompt` therefore depend on file load order — which for a `-L` directory is filesystem/sort order, not authoring intent. (Example: `build_research_brief.mthds` sorts before `bundle.mthds`, so the empty-description sibling can win.)

`description` / `system_prompt` are display/doc/PipeLLM-fallback metadata, not execution-critical, so this is not a correctness-of-results bug — but it is wrong, order-dependent, and noisy.

**Not affected — `main_pipe` (verified, do not "fix").** The runtime `Domain` model (`pipelex/core/domains/domain.py`) carries only `code`, `description`, `system_prompt` — **no `main_pipe`** — and `DomainFactory.make_from_blueprint` copies only description + system_prompt. The `DomainBlueprint.main_pipe` set during the crate merge is dropped when the runtime `Domain` is built, so the first-write-wins on `main_pipe` is inert. Main-pipe existence is validated **per file** on the bundle blueprint that declares it (`PipelexBundleBlueprint`, the `main_pipe in self.pipe` check), and the root always carries both `main_pipe` and the matching header (Layer 0), so that check passes. No order-fragility there. Leave it alone.

## Where (verified file:line)

Two sites apply the same first-write-wins + warn-on-difference logic. Both need the same relaxation:

- `pipelex/libraries/library_crate_factory.py` — `make_from_blueprints`, the domain block (currently ~l.63–83). Builds the per-domain `DomainBlueprint`; `description=blueprint.description or ""`; the `else` arm warns when `existing.description != (blueprint.description or "")` and when `existing.system_prompt != blueprint.system_prompt`.
- `pipelex/libraries/domain/domain_library.py` — `add_domain` (~l.33–50). Same warn-on-difference at runtime-`Domain` registration. **Already carries a TODO** at l.34: `# TODO: resolve domain metadata conflicts properly — currently first-write-wins with a warning.` This handoff is that TODO.

Supporting facts (verified):
- `PipelexBundleBlueprint.description: str | None = None` — omitting it is legal (`pipelex/core/bundles/pipelex_bundle_blueprint.py`).
- `DomainBlueprint.description: str` (required) — the factory coerces an omitted bundle description to `""` (`pipelex/core/domains/domain_blueprint.py`).
- `Domain.description: str | None = None`, `Domain.system_prompt: str | None = None` (`pipelex/core/domains/domain.py`).

## The fix

Make domain-metadata merge **order-independent** and **quiet for omissions**: an omitted (empty/`None`) `description` or `system_prompt` contributes *no opinion* — it neither overrides an established non-empty value nor triggers a warning. Warn **only** when two *non-empty* values genuinely differ (a real conflict the author should resolve).

Concretely, per domain field (`description`, `system_prompt`):
- established empty/None + incoming non-empty → take incoming, no warning (root can arrive after a sibling).
- established non-empty + incoming empty/None → keep established, no warning (sibling defers to root).
- both non-empty and equal → keep, no warning.
- both non-empty and different → keep first, **warn** (genuine conflict — unchanged behavior).

This means the root's `description`/`system_prompt` always wins over membership-only siblings regardless of load order, and the additive flow is warning-free, while genuine double-declarations still warn.

**Apply at both sites**, or — preferred — extract one shared helper (e.g. `pipelex/libraries/domain/domain_metadata_merge.py::merge_domain_metadata(...)` or a `DomainBlueprint`/`Domain` "fold" method) and call it from both `make_from_blueprints` and `add_domain`, so the two layers can't drift. Keep the existing class/`type_uri`/message slugs; this is behavior-narrowing on the no-conflict path only.

### Authoring-side alternative (rejected as primary)

We could instead require every non-root file to repeat the full domain header (`description`, `system_prompt`). Rejected: it forces prose duplication across every definition file, which is its own drift source and defeats the point of membership-only sibling files. The runtime fix is the right lever; if anything, the cheat sheet should explicitly say non-root files carry **only** `domain = "..."`.

## Tasks

- [x] Add the order-independent, omission-quiet merge (shared helper) and wire both `make_from_blueprints` and `DomainLibrary.add_domain` to it. Removed the now-resolved conflict-resolution TODO at `domain_library.py` (kept the separate system_prompt-inlining TODO).
- [x] `make agent-check` clean (ruff, plxt, pyright, mypy).
- [x] Tests below green; then full `make agent-test`.
- [x] CHANGELOG `[Unreleased]` entry (folded into the existing "Additive multi-file library construction" entry).

## Tests

- Root (real description) + sibling (`domain` only) merged **both orders** → assembled domain keeps the root's description/system_prompt; **no warning** emitted. Assert at both layers (crate factory result and `DomainLibrary` after `add_domains`).
- Two files each declaring a **different non-empty** description → first kept, **warning** still emitted (unchanged).
- Two files with the **same non-empty** description → kept, no warning.
- Cover `system_prompt` with the same matrix.
- Regression: existing single-file domain-metadata tests still pass.

(Capture warnings with `caplog`/the project's log-capture fixture; assert presence/absence explicitly — the whole point is the no-warning path.)

## Tracked from

`mthds-plugins/wip/recursive/design.md` §2.7 (the additive multi-file layout: root carries the domain header, siblings carry only `domain =`) and §3 (the worked example whose sibling files omit `description`). Also indexed in `mthds-plugins/wip/deferred-issues.md`.
