# Vacuous presence lint — deferred items

Things the vacuous-presence work found and deliberately did not do. Each is a decision, not an oversight; the reasoning is here so a later session does not have to re-derive it.

## The builder's `validate_all` still carries no `warnings` key

Every other whole-bundle validate channel now assembles its `warnings` through `pipelex/pipeline/advisory_warnings.py`. One does not: `validate_all` in `pipelex/builder/operations/validate_ops.py`, which returns `{success, is_valid, validated_pipes, total_pipes}` and has never carried advisories at all. Its three siblings in the same module do, and the agent-CLI twin `validate_all_core` does — so the whole-library advisory lints are dropped on exactly this one path.

The cause is structural rather than an omission at the call site. `validate_all` delegates to `BundleValidator.acquire_and_validate`, which opens a library, sweeps it, and **tears it down before returning**. The advisory collector must run inside that window (the taint walk resolves child pipes through the hub, the descriptors read the class registry, the crate is read off the current library), so there is nowhere in `validate_all`'s body left to call it from. Closing the gap means reshaping `acquire_and_validate` — inlining its lifecycle the way `validate_all_core` already does, or giving it a hook that runs inside the window — which is a change to a method shared by several callers and squarely outside a lint's blast radius.

This was already written up during the PR #1026 review (`wip/pr-1026-review-notes.md`), where the same conclusion was reached with the same remedy. The composition point makes the fix *cheaper* than it was — the body of the change is now one `collect_advisory_warnings(...)` call rather than a fourth copy of a pattern — but it does not make it in scope.

**If it is picked up:** mirror `validate_all_core`'s inline lifecycle, compute the warnings before teardown, and take the decision the review note raised — `warnings` alone (minimal), or full alignment with the agent-CLI twin (`pending_signatures` / `is_runnable` too), which would also mean rewriting the deliberate "no `pending_signatures` here by design" comment in that function.

## Transitive vacuity and fixed-count lists

Both are stated in the design (`design.md` §7) rather than here, because they are boundaries of the *rule* rather than of the implementation: a required field that is itself an all-optional object (`{"opts": {}}`) does not warn, and neither does `Concept[N]` of an all-optional concept. One level deep is where the form kernel's trap actually bit, and the transitive notion's edges are arguable (a required text admits `""`, a required list admits `[]`). If it comes back, the natural formulation is "no path from the slot to a scalar or file field passes only through required fields", stated on the descriptor.

## `gating` and `required` cannot be told apart by any derived descriptor

The lint keys on `gating`, which the design argues for on the grounds that the renderer keys on the same fact. That argument stands, but it buys nothing observable today: `InputFormDeriver.derive_slot` computes `gating = required and not (node.kind.is_list and node.item_count is None)`, so on an `object` node — the only kind the lint looks at — `gating` is exactly `required`. The distinction is only visible on a hand-built descriptor, which is where `test_a_non_gating_object_slot_is_silent_even_when_required` pins it.

Nothing to do about it. It is recorded because a future reader may otherwise "simplify" the lint to read `required` and find every test still green — the unit case is the only thing standing in the way, and it is worth knowing that is on purpose.

## The hint lint sweeps the whole accumulated crate, and that is now visible on more channels

`build_hint_warnings` runs over the current library's *accumulated* crate — the validated bundle plus every bundle loaded beside it from `library_dirs`. The vacuous-presence lint does not: its entry refs come from `result.blueprints`, the validated batch alone, so it never comments on a library you merely depend on.

That asymmetry is the hint lint's own pre-existing scope decision, unchanged here. What changed is who sees it: the lint used to reach only the protocol validation report, and now rides every validate channel. So `pipelex validate bundle mine.mthds -L shared/` can report hint findings that belong to `shared/`, which an author cannot act on from where they are standing.

Left alone deliberately. Narrowing the hint lint to the validated batch is a change to that lint's contract, with its own question behind it (a library author does want the findings, on their own validate run), and folding it into a PR about a different lint would hide the decision. If it turns out to be noisy in practice, the fix is to scope `build_hint_warnings` by the batch's domains the way the vacuous lint is scoped by its blueprints — the composition point already holds both ingredients, so it is a small change once the decision is made.
