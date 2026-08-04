# Parity gaps — one authored fact, two readers that disagree

This track fixes a family of defects that share one shape: a single authored fact (a pipe ref, a concept declaration, a model choice, an emitted line of code) is read by two pipelex implementations that disagree about what it means. The **Phase 1 trio** are silent in the strict sense — both readers succeed, produce plausible output, and diverge with no error attached anywhere — which is why they are batched as one sweep rather than fixed opportunistically. The **Phase 2 kernel items fail differently**, and the difference is worth keeping straight: 2.1 was a *contract* gap whose divergence surfaces one step later as a `StuffContentTypeError` on read-back, 2.3 an *expressiveness* gap where one reader cannot state the fact at all, and 2.2 turned out on re-verification not to be a defect.

**Branch:** `fix/Parity-gaps` (this worktree, `_gaps/`). **PR:** [#1085](https://github.com/Pipelex/pipelex/pull/1085) → `dev`. **Plan:** [`parity-gaps-plan.md`](parity-gaps-plan.md).

## The gaps at a glance

| Gap | The two readers | Buildable |
| --- | --- | --- |
| Bare cross-domain pipe refs | `crate_normalization` qualifies with the owner domain; the live `PipeLibrary` searches every domain | now |
| Structureless concept base class | runtime promotes to a `TextContent` refinement; the `python-structures` projection emits `StructuredContent` + `extra="allow"` | now |
| Import-block format stability | `render_import_block` never wraps; a consumer's `ruff format` wraps past 88 columns | now |
| `MethodKernel.llm_text` narrowness | the façade hardcodes concept/class and requires a model; `run_llm_text` and the interpreter take all three | ✅ fixed **in** #1081 |
| `MethodKernel.llm_object` prompting style | the façade derives style from the object setting and drops the `for_text` rung; the interpreter derives style from the text setting | ⚠️ withdrawn — not a live defect |
| Img-gen prompt constructor | `kernel/prompt_references.py` says the kernel resolves image references; only the interpreter-layer blueprint can actually build an `ImgGenPrompt` | ✅ fixed **in** #1082 |

## Phasing

- **Phase 1 — the dev-buildable trio** (crate qualification, structureless base class, import wrapping). All targets exist on this branch today; each lands with its regression gate.
- **Phase 2 — the kernel trio.** Originally gated on the kernel-extraction PRs (#1081 façade, #1082 operators) merging to `dev`, to avoid destabilizing finalized PRs. **Louis overrode that gate:** the two live ones (2.1 and 2.3 — 2.2 was withdrawn) are defects *those PRs introduce*, so deferring meant knowingly merging a package whose stated contract is false and re-opening the same files to repair it. Phase 2 therefore shipped **inside** #1081 and #1082, not on this branch.

## Status

- **Phase 0 (planning): ✅ done 2026-08-03.** Plan written, targets verified on this tree, decisions D-1..D-3 posed with recommendations.
- **Phase 1: ✅ done 2026-08-03.** All three fixes landed with their gates, red-green verified; Checkpoint A recorded in the plan. D-1 settled as crate-wide resolution (not own-domain-first — see [`d1-domain-hint-deferred.md`](d1-domain-hint-deferred.md)); D-2 settled as recommended.
- **Phase 2: ✅ done 2026-08-04, folded into the kernel stack.** 2.1 fixed in #1081 (`9fbb12f34`); 2.3 fixed in #1082 (`7279effbd`), with the boot-contract arm it turned out to owe in the same PR (`2643b137c`) and the doc review on #1083 (`5af77589b`). 2.2 **withdrawn** on re-verification — the façade's single `model` wins the object resolution's first rung, so the style it derives already matches an interpreted run for every call the façade can express; the surviving narrowness is deferred as KF-16, because the whole model-derived-style mechanism is slated to become an explicit user choice (design in `wip/prompting-style/README.md`, which ships on the kernel stack — not on this branch). D-3 settled as recommended, (a), and its predicted layering cost did not materialise.

## Deferred, not dropped

- [`d1-domain-hint-deferred.md`](d1-domain-hint-deferred.md) — whether `PipeLibrary` should prefer the caller's domain on an ambiguous bare pipe ref. A language call; the normalizer follows for free once settled.
- [`structureless-concept-with-registered-class.md`](structureless-concept-with-registered-class.md) — a description-only concept bound to a same-named hand-written class through a channel the crate structurally cannot see. Raised on PR #1085, verified pre-existing; the correct fix is a language call.
- [`deferred-review-observations.md`](deferred-review-observations.md) — four follow-ups from the #1085 finalization review: the cross-package `refines` shape, qualified-ref closedness, a latent test-order flake, and the `mthds/` spec's missing bare-**pipe**-ref rule (a cross-repo edit, ordered *after* D-1).

## Cold start

**Start with [`SESSION-HANDOFF.md`](SESSION-HANDOFF.md)** — where the work stands, what runs next, and the traps. Then read [`parity-gaps-plan.md`](parity-gaps-plan.md) top to bottom — it carries the evidence, the chosen fixes, and the gates. Verify the grounding claims against the tree before building on them (each carries its file:line). Gates for every phase: `make agent-check`, full `make agent-test`, `make drift-check`, and an `[Unreleased]` changelog entry per user-visible fix.
