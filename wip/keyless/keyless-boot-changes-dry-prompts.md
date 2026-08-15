# Bug report — a keyless boot silently changed what a DRY run rendered

**Filed 2026-08-14 as the brief for `fix/Keyless-dry-run`; measured 2026-08-08 and re-verified on the branch at v0.44.0. ✅ CLOSED 2026-08-14 — dissolved, not fixed.** Kept as the record of what the bug was and of the measurement lesson at the end. The residue that survived it is tracked in [`keyless-dry-prompts-fix-plan.md`](keyless-dry-prompts-fix-plan.md).

## What the bug was

A DRY run's whole purpose is to rehearse the real run without spending money — which is why it is documented as needing no keys. That promise reads as "same program, mocked leaves". It was not: **a dry run booted keyless rendered different prompts from a dry run booted with credentials, and nothing in either run said so.**

Take any method where a second `PipeLLM` step's prompt embeds a first step's output, and run it DRY twice — identical inputs, identical method — varying only the boot: `needs_inference=False` (keyless) vs `needs_inference=True` (keyed).

| boot | derived templating style | how step 1's output was tagged into step 2's prompt |
| --- | --- | --- |
| keyless | `None` | the Jinja2 filter's own fallback, `` result: ``` `` |
| keyed | the model's own, e.g. `xml/plain` | `<result>` |

Both runs completed, both reported the same usage records, neither logged anything about the difference. A dry run used for **validation** — "does this method's prompt render?" — was validating a prompt the live run would never send, whenever it ran keyless.

**Why it happened.** `RuntimeBoot.make` derived the boot's need for model specs from `needs_inference`, and — the actual mechanism — a keyless boot loaded the backend library leniently, which skipped every backend whose `${…_API_KEY}` could not substitute. Every shipped backend declares its key that way, so the deck was empty. `derive_templating_style` then took its documented `None` path, written for the external-LLM-plugin case where "the deck has no model for this handle" means the model is real but managed elsewhere; a keyless boot satisfied that condition for **every** model at once and the caller could not tell the two situations apart. `None` reached the Jinja2 filters, whose `TICKS` fallback silently rendered rather than failed.

## Why it is gone

Prompt shape is now an authoring decision — a pipe declares `templating_style`, anything that declares nothing takes one runtime default from config, and **no code path consults the deck, a model spec, or a credential to decide how a prompt is tagged.** A keyless boot and a keyed boot therefore render byte-identical prompts by construction. Both load-bearing facts above are deleted: `derive_templating_style` no longer exists, and the Jinja2 filters raise `Jinja2ContextError` where a style is genuinely absent instead of quietly picking a shape — so the failure mode named in this report's title, *silently*, is unreachable even in principle. Design: [`../prompting-style/prompt-style-as-an-authoring-decision.md`](../prompting-style/prompt-style-as-an-authoring-decision.md); build: [`../prompting-style/templating-style-implementation-plan.md`](../prompting-style/templating-style-implementation-plan.md). The change was **not** undertaken to fix this bug — it was a separate design ruling that happened to dissolve it.

**What did not get fixed.** The boot behaviour this report *diagnosed* is untouched: a keyless boot still drops every backend and still yields an empty deck, which still governs things unrelated to prompting — a skipped `max_prompt_images` check, skipped image-param validation, and handle-pinned bundles rejected on a keyless machine. Those are the subject of the fix plan. One correction from the re-verification is worth carrying: `needs_model_specs=True` is **not** a credential-free seam — it only governs whether the gateway's remote specs are fetched or dummied; the deck is emptied by the lenient backend load, and no flag combination gives a credential-free process a populated deck today.

## Why it stayed invisible — the lesson that outlives the bug

Any gate whose two sides boot the same way cannot see this variable at all, and reads as evidence that it does not matter. Two keyless sides agree with each other perfectly; the divergence only surfaces when a keyless side is compared against a side that *cannot* boot keyless (e.g. a worker whose boot hard-fails without credentials). It first presents as a downstream divergence ("the same program produces different content over there") — it is not; splitting the boot variable isolates it. Any future two-sided gate on this area must vary exactly one thing, credential presence, and nothing else.
