# The pipe entry affordance and the concept one: separate, deliberately

**Ruling: keep them separate. Do not extract a shared helper.** Recorded during the pipe-side work so that Phase 3 inherits a decision rather than a discovery — an accidental copy found later is not the same thing as a chosen duplication.

## What is actually shared

Reduced to their skeletons, the two look like twins:

```
exact ref -> direct hit
bare code -> scan entries, excluding aliased dependency keys
  1 match  -> return it
  >1 match -> raise, naming the candidates
  0 match  -> None / raise
```

That is roughly six lines of list comprehension and two error messages. If that were the whole story, sharing would be obvious.

## Why they are not twins

**1. The concept side has a step the pipe side does not, and cannot have.** Natives. `Text` is not a bare code to be searched for — it resolves to `native.Text` before any scan, by the standard's own step 1 (`NativeConceptCode.is_native_concept_ref_or_code`). There is no pipe equivalent. A shared helper would either carry a native branch that is dead for pipes, or take a "resolve specials first" callback, which is a worse thing than two small functions.

**2. The two live on different objects with different roots.** `PipeLibrary.root` is `dict[str, PipeAbstract]`; `ConceptLibrary.root` is `dict[str, Concept]`. Sharing means a generic over a protocol exposing `.code` and `.pipe_ref`/`.concept_ref` — the two ref properties are not even named the same. The generic machinery would outweigh the code it factors out.

**3. Their ambiguity answers are not obviously the same question.** For pipes, an ambiguous hand-typed code must raise: guessing which `summarize` the user meant is a coin flip with a silent wrong answer. The concept side *currently* has `search_domain_codes` and an own-domain-first preference, and its spec stops at "unique match" without saying what happens otherwise. Phase 3 has to settle whether that preference is meaningful or vestigial. **Binding the two together before that question is answered would smuggle the pipe answer into the concept surface** rather than deciding it.

## What to do instead

Phase 3 should copy the *shape* and the *reasoning* — including the aliased-dependency exclusion, which is a correctness requirement on both sides for the same reason (an installed package must not make a host code ambiguous) — and write the concept version against the concept library's own facts. If, after Phase 3 lands and the concept ambiguity question is settled, the two really have converged to the same six lines, extracting then is cheap and the decision will be informed. Extracting now would be guessing.

## The part that must not be duplicated

The *rule* — that in-body refs qualify to their owner domain and are never searched for — has exactly one implementation, `crate_qualification.qualify_crate`, and both readers consume it. That was the whole point of Phase 1. The entry affordances are the deliberate exception to no-fall-through, not a second copy of the resolution rule, and it is worth keeping the two ideas apart when reading this: sharing the *rule* is mandatory, sharing the *affordance* is not.
