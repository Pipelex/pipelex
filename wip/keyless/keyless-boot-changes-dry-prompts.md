# Bug report — a keyless boot silently changes what a DRY run renders

**Filed 2026-08-14 as the brief for this fix branch (`fix/Keyless-dry-run`).** Measured 2026-08-08 against the then-current tip; re-verify on this branch before building the fix — the boot and deck code has moved since (v0.43.x, v0.44.0).

> ## ✅ CLOSED 2026-08-14 — dissolved, not fixed
>
> **This bug no longer exists, and the mechanism it describes has been deleted.** Prompt shape is now an authoring decision: a pipe declares `templating_style`, anything that declares nothing takes one runtime default from config, and **no code path consults the deck, a model spec, or a credential to decide how a prompt is tagged**. A keyless boot and a keyed boot therefore render byte-identical prompts by construction — there is no longer a derivation that could disagree with itself.
>
> The two load-bearing facts in "Why it happens" are both gone: `derive_templating_style` is deleted, and the `TagStyle.TICKS` fallback that made a `None` style silently *render* rather than *fail* is deleted too. Where a style is genuinely absent, the Jinja2 filters now raise `Jinja2ContextError` instead of quietly picking a shape — so the specific failure mode named in this report's title, *silently*, is unreachable even in principle.
>
> Shipped on this same branch: design in [`../prompting-style/prompt-style-as-an-authoring-decision.md`](../prompting-style/prompt-style-as-an-authoring-decision.md), build in [`../prompting-style/templating-style-implementation-plan.md`](../prompting-style/templating-style-implementation-plan.md). Note the change was **not** undertaken to fix this bug — it was a separate design ruling that happened to dissolve it, which is why the fix plan's core survives while its headline does not.
>
> **What did not get fixed.** The underlying boot behaviour this report *diagnosed* is untouched: a keyless boot still drops every backend and still yields an empty deck. That still has consequences — a skipped `max_prompt_images` check, skipped image-param validation, handle-pinned bundles rejected, and the two CLIs disagreeing about whether `--dry-run` needs credentials. Those survive in the re-scoped [`keyless-dry-prompts-fix-plan.md`](keyless-dry-prompts-fix-plan.md) and are pending their own re-judging. **"Why it stayed invisible" below is still worth reading** — the two-sided-gate blindness it describes is a general lesson about measurement, not a fact about prompting.

## The claim it undermines

A DRY run's whole purpose is to rehearse the real run without spending money — which is why it is documented as needing no keys. That promise is naturally read as "same program, mocked leaves". It currently is not: **a dry run booted keyless renders different prompts from a dry run booted with credentials, and nothing in either run says so.**

## Reproduction

Take any method where a second `PipeLLM` step's prompt embeds a first step's output (so the tag style is observable in the rendered prompt), and run it DRY twice — identical inputs, identical method. The only difference is the boot: `needs_inference=False` (keyless) vs `needs_inference=True` (keyed).

| boot | `derive_templating_style(llm_setting=…)` | how step 1's output is tagged into step 2's prompt |
| --- | --- | --- |
| keyless | `None` | fallback style, e.g. `` result: ``` `` |
| keyed | the model's own, e.g. `xml/plain` | `<result>` |

Both runs complete, both report the same usage records, neither logs anything about the difference. The two output texts differ only in how the first step's result is tagged into the second step's prompt.

## Why it happens

`RuntimeBoot.make` derives `effective_needs_model_specs` from `needs_inference`, so a keyless boot loads no inference models into the deck. `pipelex/kernel/llm_ops.py::derive_templating_style` then takes its documented `None` path — written for the external-LLM-plugin case, where "the deck has no model for this handle" means the model is real but managed elsewhere. A keyless boot satisfies that condition for **every** model at once, and the caller cannot tell the two situations apart. Prompt rendering downstream falls back to its default tag style instead of the model's own.

## Why it stayed invisible

Any gate whose two sides boot the same way cannot see this variable at all, and reads as evidence that it does not matter. Two keyless sides agree with each other perfectly; the divergence only surfaces when a keyless side is compared against a side that *cannot* boot keyless (e.g. a worker whose boot hard-fails without credentials). It first presents as a downstream divergence ("the same program produces different content over there") — it is not; splitting the boot variable isolates it.

## Blast radius, as far as it was measured

- Only the *rendered prompt* was compared. Whether anything else keyed off the deck changes under a keyless boot was not enumerated — worth enumerating as part of the fix.
- A dry run used for **validation** — "does this method's prompt render?" — is validating a prompt the live run will not send, whenever it is run keyless.

## What the fix has to decide first

Is a keyless dry run meant to be **faithful** (then the deck's prompting metadata must load without credentials — `needs_model_specs=True` already exists as that seam) or merely **cheap** (then the divergence is by design and should be said out loud, at least as a log line)? Either way, the current state — faithful-looking and unfaithful, with no signal — is the one that should not persist.

---

## Re-verified 2026-08-14 at this branch's base (tip `84b1f682c`, v0.44.0 — before the templating-style change) — and one premise above is wrong

The divergence reproduces exactly as described: a keyless boot derives `None`, a keyed boot derives `xml/plain`, and `None` renders as `TICKS` because `apply_tag_style` defaults to it when `TAG_STYLE` was never put on the Jinja2 context.

> **The TICKS half is now false, deliberately** — see the CLOSED box above. `apply_tag_style` has no fallback any more: a render context with no tag style raises `Jinja2ContextError` rather than quietly choosing a shape, and there is no deck-derived style left to be `None`. Kept as the record of what reproduced at that tip.

**But the last paragraph's parenthesis is false.** `needs_model_specs=True` is *not* the faithful seam. Measured on a machine with no credentials at all, it changes nothing — the deck is empty in both modes. `needs_model_specs` only governs whether the *gateway's* remote specs are fetched or dummied; what empties the deck is `lenient=not needs_inference`, which makes the backend loader **skip every backend whose `${…_API_KEY}` cannot substitute** — and every shipped backend, gateway included, declares its key that way. There is currently no flag combination that gives a credential-free process a populated deck. The seam has to be built, not switched on.

Two things also worth carrying forward: the prompting metadata itself was credential-free on-disk data (~~`prompting_target` lives in the per-backend spec TOMLs~~ — that field is deleted too), which is what made "faithful" cheap; and the blast radius includes a *loud* converse — on a keyless machine a bundle pinning a bare model handle is **rejected** by validation, while preset-pinned methods silently get rewritten prompts.

Full measurements, the enumerated blast radius, and the TDD fix plan: [`keyless-dry-prompts-fix-plan.md`](keyless-dry-prompts-fix-plan.md).
