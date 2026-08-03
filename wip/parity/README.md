# Parity gaps — one authored fact, two readers that disagree

This track fixes a family of defects that share one shape: a single authored fact (a pipe ref, a concept declaration, a model choice, an emitted line of code) is read by two pipelex implementations that disagree about what it means. Every item below is silent — both readers succeed, produce plausible output, and diverge without an error attached — which is why they are batched as one sweep rather than fixed opportunistically.

**Branch:** `fix/Parity-gaps` (this worktree, `_gaps/`). **PR:** [#1085](https://github.com/Pipelex/pipelex/pull/1085) → `dev`. **Plan:** [`parity-gaps-plan.md`](parity-gaps-plan.md).

## The gaps at a glance

| Gap | The two readers | Buildable |
| --- | --- | --- |
| Bare cross-domain pipe refs | `crate_normalization` qualifies with the owner domain; the live `PipeLibrary` searches every domain | now |
| Structureless concept base class | runtime promotes to a `TextContent` refinement; the `python-structures` projection emits `StructuredContent` + `extra="allow"` | now |
| Import-block format stability | `render_import_block` never wraps; a consumer's `ruff format` wraps past 88 columns | now |
| `MethodKernel.llm_text` narrowness | the façade hardcodes concept/class and requires a model; `run_llm_text` and the interpreter take all three | after #1081 |
| `MethodKernel.llm_object` prompting style | the façade derives style from the object setting and drops the `for_text` rung; the interpreter derives style from the text setting | after #1081 |
| Img-gen prompt constructor | `kernel/prompt_references.py` says the kernel resolves image references; only the interpreter-layer blueprint can actually build an `ImgGenPrompt` | after #1082 |

## Phasing

- **Phase 1 — the dev-buildable trio** (crate qualification, structureless base class, import wrapping). All targets exist on this branch today; each lands with its regression gate.
- **Phase 2 — the kernel trio**, gated on the kernel-extraction PRs (#1081 façade, #1082 operators) merging to `dev`. Do not destabilize those finalized PRs with review feedback; land these as follow-ups here once they merge, re-verifying each claim against the merged code first.

## Status

- **Phase 0 (planning): ✅ done 2026-08-03.** Plan written, targets verified on this tree, decisions D-1..D-3 posed with recommendations.
- **Phase 1: ✅ done 2026-08-03.** All three fixes landed with their gates, red-green verified; Checkpoint A recorded in the plan. D-1 settled as crate-wide resolution (not own-domain-first — see [`d1-domain-hint-deferred.md`](d1-domain-hint-deferred.md)); D-2 settled as recommended.
- **Phase 2: gated** on #1081/#1082.

## Cold start

**Start with [`SESSION-HANDOFF.md`](SESSION-HANDOFF.md)** — where the work stands, what runs next, and the traps. Then read [`parity-gaps-plan.md`](parity-gaps-plan.md) top to bottom — it carries the evidence, the chosen fixes, and the gates. Verify the grounding claims against the tree before building on them (each carries its file:line). Gates for every phase: `make agent-check`, full `make agent-test`, `make drift-check`, and an `[Unreleased]` changelog entry per user-visible fix.
