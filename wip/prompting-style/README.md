# Deferred — make the prompting style an explicit choice, not a model-derived one

**Status: deferred, not started.** Raised 2026-08-03 while folding the parity-gap fixes into the kernel-extraction PRs. Owner decision (Louis): the feature this plan replaces is **obsolete**, so patching it to match the interpreter would be throwaway work. Nothing here blocks the kernel extraction.

## What exists today

The prompting style is **derived from the model**, per call, in two places that must agree:

- interpreter — `pipelex/pipe_operators/llm/pipe_llm.py`: resolves the pipe's text setting, reads `llm_setting.prompting_target or inference_model.prompting_target`, and looks the style up in `prompting_config`.
- kernel — `derive_templating_style` in `pipelex/kernel/llm_ops.py`: the same lookup, over whichever `LLMSetting` the caller's op passes.

The chain is `model handle → inference model → prompting_target → prompting_config.get_prompting_style(...) → TemplatingStyle`. Note the silent arm: `derive_templating_style` returns `None` when the deck holds no inference model for the handle, which is what an external LLM plugin looks like from there.

## Why it should go

The mechanism dates from when models were genuinely sensitive to prompt shape and each family wanted its own markup. That no longer holds — current models are not meaningfully sensitive to the difference, so deriving the style from the model spends real complexity on a distinction that no longer pays.

What the indirection actually costs:

- **Two readers must agree on a derivation neither caller can see.** That is the shape of every defect in the parity-gaps track. The derivation being invisible is precisely why the divergence below was hard to reason about.
- **The style is unstateable.** A caller who wants a specific style has no way to say so — they must pick a *model* whose prompting target maps to it.
- **A deck/config change silently changes prompt text** for a method nobody edited.

## The target design

Make the prompting style an **explicit choice**, defaulting to **XML**:

- an explicit setting a caller/author can state directly, defaulting to XML when unstated;
- the model-derived path removed, along with `prompting_target` plumbing that exists only to feed it (check what else reads it before deleting — it may have non-style consumers);
- one derivation site, or none, instead of two that must be kept in agreement;
- `TemplatingStyle | None` at the op boundary reconsidered: with an explicit default, `None` may stop being a reachable state, which would let `run_llm_*` take a plain `TemplatingStyle`.

Open questions for whoever picks this up:

- Where does the explicit choice live — `.mthds` pipe-level, deck-level, config-level, or more than one with a precedence chain?
- Is it per-pipe or per-run? A pipe-level override implies a language surface (`prompting_style = "xml"`), which is an MTHDS spec change and belongs with the `mthds/` repo, not just here.
- What happens to `prompting_target` on `LLMSetting` and on inference models — deleted, or kept for another purpose?
- Migration: methods relying on a non-XML style today would change prompt text. Given the premise (models no longer sensitive), that is expected to be a no-op in output quality, but it *is* a wire-visible change to rendered prompts and should be called out in the changelog.

## What was silenced in the meantime, and what was not

The parity-gaps plan listed this as gap **2.2 — "`MethodKernel.llm_object` renders under the wrong model's prompting style"**, and called it *a wrong value*. **That was overstated.** Re-verified 2026-08-03 against `refactor/Kernel`:

| Call | Style derived from |
| --- | --- |
| `MethodKernel.llm_object(model=X)` | `X` |
| interpreter, pipe declares `for_text = X` only | `X` — **identical** |
| interpreter, pipe declares `for_object = X` only | the deck's **text** default — differs |

The façade takes one explicit `model`, which wins `resolve_llm_setting_for_object`'s first rung, so the style comes from that same setting. That matches the interpreter's single-text-choice reading — the natural reading of a parameter called `model`. **For every call the façade can express, the two agree.** The divergence needs a pipe naming *both* models, which the façade has no way to say.

So 2.2 is not a wrong value; it is the same **narrowness** as 2.1 — a two-choice form that is inexpressible. It is left alone deliberately: widening the façade to take a second choice would mean building the two-setting derivation this plan is about to delete.

**Recorded in code** as a docstring block on `MethodKernel.llm_object`, including the trap: do *not* "fix" it by deriving the style from an object-only resolution — that would *introduce* the divergence rather than close it.

**Not silenced, still open:** nothing. There is no live defect to carry. This document exists so the obsolete mechanism gets deleted deliberately rather than discovered again by the next person who compares the two readers.
