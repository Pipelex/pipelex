# Portable img-gen size — deferred review findings

Non-bug findings from the Checkpoint 4 feature-wide `/code-review` (context-free, `17f478e7b..HEAD`) that are design tradeoffs or polish rather than correctness fixes. The correctness findings from that review (non-positive `ImageSize` crash, exact-size deck default silently defeating an explicit pipe `aspect_ratio`, gateway unknown-taxonomy hard-fail on size-unset jobs) were fixed in the Checkpoint 4 follow-up commit.

## Gateway user gets a deck-config error message they cannot action

Under gateway routing, a sized request on a gemini model whose remote spec has no `rules` yields "set rules.aspect_ratio to a Gemini taxonomy (e.g. 'gemini_3_flash')" — an instruction only someone editing the gateway catalog can follow, not a gateway end user. Fail-loud and correct, but the message could branch on the spec's origin (remote catalog vs local deck) to say "this gateway model does not support size selection yet" instead. Revisit if a user actually hits it: Pipelex owns the catalog and the rules are deployed (verified live by the Phase 4 e2e smoke), so the population should be empty.

## Blueprint-load "hard validation error" only fires when routing resolves rules

The static (blueprint-load) arm of size validation silently skips when the pipe's model choice resolves through a preset/alias or a spec without rules (`PipeImgGen._validate_param_support_against_model_rules` returns early). That is the documented two-layer design — the runtime pre-call check still catches everything — but it means the default `all_pipelex_gateway` profile relies on the remote catalog carrying the rules. The related integration test forces `all_google` routing; default-routing static validation is untested by design (it depends on remote state).

## The size⊕aspect_ratio exclusivity is invisible to the JSON schema

The mutual exclusion of an exact `size` and `aspect_ratio` lives in a pydantic `model_validator`, which the generated MTHDS JSON Schema cannot express — `plxt lint` passes a bundle that blueprint load rejects. Expressing it as a schema `not`/`dependencies` construct in the generator's post-processing would close the gap; weigh against generator complexity if editor-time feedback for this case proves valuable.

## `'0.5k'` still listed by `SizeTier.quoted_tokens()` error messages

The spec field description now marks `'0.5k'` as reserved, but the parse-error message ("expected a size tier ('0.5k', '1k', '2k', '4k')...") and the blueprint exclusivity message still enumerate it via `quoted_tokens()`. It *is* a parseable token (rejected later per-model with an honest reason), so the parse layer is not lying — but a user steered to it gets a second error. Fold a "reserved" annotation into `quoted_tokens()` if this confuses anyone in practice; it disappears entirely once the 0.5k wire token is verified and enabled (see the feature's out-of-scope list).
