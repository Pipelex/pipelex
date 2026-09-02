---
status: active
item: L-260831-9963b5
---

# Classify the gateway's routing refusals

## The bug, verified

The Pipelex inference gateway refuses a request it cannot route with a code of its own — an unknown model handle (`pig-01`), a model served by an integration that is disabled for want of a credential (`pig-02`), a model unreachable over the native protocol the path belongs to (`pig-05`), or a model whose integration does not serve the requested capability (`pig-06`). Every one of them answers HTTP 400. `classify_inference_error` has a class for the gateway's request-shape refusals and for its unresolvable-reference refusals, but none for this family, so all four fall through to the `status_code == 400` arm of the status ladder in `pipelex/cogt/inference/error_classify.py` and are read as CONTENT / CHANGE_INPUT: a caller who named a model the gateway does not serve is told *"The provider rejected the request — review the prompt, parameters, and inputs."* and receives `LLMCompletionError` rather than `LLMModelNotFoundError`.

Probed on this branch, with the exception built through Portkey's own `_make_status_error_from_response` so `exc.body` is the message string as in production:

```
pig-01: code=pig-01 category=content action=change_input model_not_found=False err=LLMCompletionError detail='The provider rejected the request — review the prompt, parameters, and inputs.'
pig-02: code=pig-02 category=content action=change_input model_not_found=False err=LLMCompletionError detail=(same)
pig-05: code=pig-05 category=content action=change_input model_not_found=False err=LLMCompletionError detail=(same)
pig-06: code=pig-06 category=content action=change_input model_not_found=False err=LLMCompletionError detail=(same)
```

The 404 arm of the status ladder already produces exactly the verdict the family deserves (CONFIGURATION / CHANGE_MODEL with `is_model_not_found` set) — the gateway simply never answers 404 for these, so the ladder cannot reach it.

Why the fix is possible now and was not when the item was filed: the item was discovered while reviewing the request-limits work, whose review ruling was not to widen that PR. Both halves of the mechanism have since landed on the branch this plan stacks on — the code-keyed family consulted ahead of the status ladder (`GatewayRequestLimit`, from the request-limits PR) and its second instance (`GatewayUnresolvedReference`, from the unresolvable-references PR), plus the Extract-hop fixes that make the gateway's code readable on every SDK path (the Portkey substrate reads the code back off the response, and the two Pipelex-service hops read `error.code` before `error.type`). This plan adds the third family on the same shape. The gateway side needs nothing: every code already exists on the wire.

## The code inventory, from the manifold source

Verified against `pipelex-manifold/src/pig/modelResolver.ts` (constants at lines 99–106) and `src/pig/proxyPolicy.ts`:

| Code | HTTP | Raised when | Who can produce it from the runtime |
|---|---|---|---|
| `pig-01` | 400 | the body names no model, or names one that no integration lists | a model deck whose handle the gateway does not serve — a stale deck, a typo in a `.mthds` file's model, or a model the deployment deliberately does not carry |
| `pig-02` | 400 | the model resolves to an integration that is disabled because a credential variable is unset | any call to a model whose integration the operator has not configured; the message names the integration and the variables to set |
| `pig-05` | 400 | a native-protocol path names a model another provider serves — today only Google's `/v1/v1beta/models/<model>:generateContent`, the path shape `nativeProtocolPaths.ts` admits | the runtime's `GoogleLLMWorker` pointed at the gateway with a model the gateway serves through a non-Google integration: a deck/gateway disagreement about which backend a model belongs to |
| `pig-06` | 400 | a model reaches a `/v1/pipelex/*` route (extract, search) that its integration's provider does not serve | an extract or search whose model resolves to an integration without that handler: again a deck/gateway disagreement, or a model named on a pipe it cannot serve |

Deliberately out of scope, and why:

| Code | HTTP | Why it stays with the status ladder |
|---|---|---|
| `pig-03` | 400 | "the client tried to route" — a refused `x-portkey-*` header, the `?model=` query form, a `@<slug>/<model>` virtual-key model, or a path and body naming different models. No client the runtime ships produces any of these; reaching it means a client bug, not a caller's or an operator's mistake. `tests/unit/pipelex/providers/manifold/test_manifold_clients.py` already pins that the manifold clients send none of the routing forms. |
| `pig-04` | 404 | "this gateway does not serve `<method> <path>`" — the proxy policy refusing a path only the catch-all could answer. Unreachable while the runtime calls only the routes the gateway mounts. Note for honesty: because it is a 404 the ladder reads it as model-not-found, which is wrong in kind — but a served-path drift is a deployment bug to surface loudly, not a verdict to soften, and no runtime client reaches it today. The pin test below asserts it is not a routing refusal, without blessing the ladder's verdict. |
| `pig-09` | 400 | "cannot resolve this reference" — already `GatewayUnresolvedReference.REFERENCE_UNRESOLVED`, CONTENT / CHANGE_INPUT. Nothing to do here; the pin test only asserts the two families stay disjoint. |

### Found on the way, filed elsewhere

Two things the inventory turned up that this plan deliberately does not carry, so the routing PR stays one decision:

- **`pig-12` is unmapped.** The manifold has since split "no bucket configured" out of `pig-09` on the LLM routes into its own code, `pig-12` at 400, and the runtime does not recognize it — so it gets the same "review your prompt" advice, and the runtime's doc still says `pig-09` folds that cause in. One map entry to `GatewayUnresolvedReference.STORAGE_NOT_SERVED`, a doc row and a test row: L-260901-0859e8.
- **The default is the real bug.** Three families in a row had to be filed because an unmapped gateway code falls through to the ladder's 400 arm and is read as a provider rejecting the prompt. A code the gateway minted for its own refusal is never that. The gateway's code namespaces (`pig-NN`, `pig_*`, `pipelex_*`) should get a default of their own that never says "review your prompt", so the next code degrades to honest advice and the per-family maps become refinements of a correct default: L-260902-b17ff6.

## The design decision: the arms

Grouping is by remedy, as in the two families already there: two codes share a member only when the caller's next move is the same. Here every member is its own code, because each names a different thing the caller or the operator has to change.

New enum `GatewayRoutingRefusal` in `error_classification.py`, beside the two existing families:

| Member | Code | Category / action | `is_model_not_found` | Advice (gist — final wording at implementation) |
|---|---|---|---|---|
| `UNKNOWN_MODEL` | `pig-01` | `CONFIGURATION` / `CHANGE_MODEL` | **set** | the inference gateway does not serve that model — pick a model this deployment serves; if the deck lists it, the deck and the gateway disagree |
| `DISABLED_INTEGRATION` | `pig-02` | `CONFIGURATION` / `CONTACT_SUPPORT` | unset | the model is served by an integration this deployment has not enabled — nothing about the request causes this; the message names the integration and, for whoever operates the gateway, the variables to set |
| `WRONG_PROTOCOL` | `pig-05` | `CONFIGURATION` / `CHANGE_MODEL` | unset | the model is reachable through the gateway, but not over the protocol the runtime used for it — the model deck names a backend for that model that the gateway serves it through a different one; correct the deck, or pick another model |
| `UNSERVED_CAPABILITY` | `pig-06` | `CONFIGURATION` / `CHANGE_MODEL` | unset | the model's integration does not serve that capability (extract, search) — pick a model whose provider does; the message names the integration, the provider and the capability |

Decisions taken, and why:

- **`CONFIGURATION` throughout, never `CONTENT`.** Nothing in the prompt, the parameters or the inputs causes any of these, and no edit to them avoids one. That is the whole bug: a caller sent to review their prompt for a model that does not exist.
- **`CHANGE_MODEL` for the three the caller can route around, and `is_model_not_found` set only for `pig-01`.** The flag is not a category: it selects the `*ModelNotFoundError` class, which `pipe_operator.py` catches and re-raises as `PipeOperatorModelAvailabilityError` carrying the model handle — the pipe-level error a caller already gets when the deck itself cannot find a model. `pig-01` is literally that case seen from the gateway. `pig-05` and `pig-06` leave the flag unset because the model *does* exist and *is* served — it cannot do what was asked, or was asked over the wrong protocol — and the render detail carries that distinction; the error class stays the family's generic failure class with the CHANGE_MODEL advice.
- **`pig-02` is `CONTACT_SUPPORT`, ruled at checkpoint 1.** The integration is disabled because the gateway operator never set its credential: nothing about the request causes it, and the deployment — not the caller — is what has to change. `CHECK_CREDENTIALS` would send a hosted caller to rotate their own valid key. `CHANGE_MODEL` was the draft's pick, on the argument that another model does get the caller past the refusal; the ruling is that a switched-off integration is the operator's fact, the same call `STORAGE_NOT_SERVED` and `BODY_LENGTH_REQUIRED` get, and the advice should say so rather than send the caller shopping for a model. The flag stays unset — the handle resolves, so it is not a model the deployment does not know — and the detail still points whoever operates the gateway at the variable the message names.
- **`pig-05` and `pig-06` are deck-vs-gateway disagreements as much as caller mistakes, and the advice says so.** The runtime picks the protocol and the route from its own model deck, so hitting either usually means the deck names a backend or a capability for a model that the gateway's routing table does not. The detail names the deck, because "pick another model" alone would leave an operator hunting for a model problem that is a config problem. `CONFIGURATION` / `CHANGE_MODEL` is still the right pair: the category is right in kind and the action is what an end caller can do.
- **Nothing in the family is retryable.** Same reasoning as the two families already there: the gateway refused before a provider saw the request, and an identical retry earns an identical refusal. `InferenceErrorCategory.CONFIGURATION` is already non-retryable.
- **The advice names no model, integration, protocol or capability.** The gateway's own message sits beside the detail and already states the specifics; repeating a guess is how advice contradicts the refusal it explains. Same principle as `_render_gateway_limit_detail`.
- **The code is the discriminator, not the provider.** As in both existing families: the refusal arrives under more than one `ProviderName` (the Portkey substrate, the OpenAI substrate that carries every chat call, plain `httpx` on the native routes, the shared Anthropic driver, and — for `pig-05` specifically — the Google driver), and `pig-` is the gateway's own namespace.

## Implementation steps

### 1. The classification family — `pipelex/cogt/inference/error_classification.py`

- Add `GatewayRoutingRefusal` (StrEnum) with the four members above, docstrings citing the wire code, the status and who can produce it, following `GatewayRequestLimit`'s style.
- Add `_GATEWAY_ROUTING_REFUSAL_BY_CODE` mapping the four codes. Matched on the code alone with no provider check, for the reason both existing maps give. The comment above it records the scope decision: `pig-03` and `pig-04` are not producible by the runtime's own clients and keep the status ladder; `pig-09` belongs to the unresolvable-reference family.
- Add a `gateway_routing_refusal` property on `ProviderErrorMetadata`, mirroring `gateway_request_limit` and `gateway_unresolved_reference`.

### 2. The classify step — `pipelex/cogt/inference/error_classify.py`

- Add `gateway_routing_refusal: GatewayRoutingRefusal | None = None` to `ClassificationResult` — a flag beside the two existing ones, same rationale: it does not change the retry decision, it lets Render name the refusal.
- Add `_classify_gateway_routing_refusal(*, refusal: GatewayRoutingRefusal)` returning `CONFIGURATION` / `CHANGE_MODEL` for `UNKNOWN_MODEL`, `WRONG_PROTOCOL` and `UNSERVED_CAPABILITY`, with `is_model_not_found=True` for `UNKNOWN_MODEL` only, and `CONFIGURATION` / `CONTACT_SUPPORT` for `DISABLED_INTEGRATION`.
- In `classify_inference_error`, branch on `metadata.gateway_routing_refusal` right after the unresolved-reference branch. The three code sets are disjoint, so the order among the three gateway branches carries no meaning; all three must run ahead of the status ladder, and none can collide with the quota rules, which fire only on 402 and 429.

### 3. The render step — `pipelex/cogt/inference/error_render.py`

- Add `_render_gateway_routing_refusal_detail(*, refusal: GatewayRoutingRefusal) -> str` with one advice string per member (gists above).
- In `_render_detail`, branch on `classification.gateway_routing_refusal` beside the two existing gateway branches, ahead of the action-kind match. Without it `pig-01` and `pig-02` would render the generic "The requested model was not found — pick an available model", which is acceptable but says nothing about the gateway, and `pig-05` / `pig-06` would render it for a model that exists.
- No new error class: `is_model_not_found` already switches to the family-specific `*ModelNotFoundError` classes. So no `generate-error-identity` / `generate-error-pages` run.

### 4. Tests — `tests/unit/pipelex/cogt/inference/test_gateway_routing_refusals.py`

Mirror the unresolvable-references module's structure and docstring style, including its table-driven `_EVERY_CODE_AND_MEMBER` list and the `test_the_table_covers_the_whole_production_map` case that walks the private map:

- **The code is recognized**: each of the four codes maps to its member; `None`, the other gateway codes and a vendor code do not; recognition is provider-blind across every `ProviderName`; every member is reachable from a wire code.
- **The code survives every Extract hop**: through the Portkey substrate (built through the SDK's own factory, never the constructor — Portkey's factory puts the message string on `exc.body`, and the hop must recover the code off the response), the OpenAI substrate that carries every chat call, plain `httpx` on the native routes (`pig-06` is the one that actually arrives there), and the shared Anthropic driver. `pig-05` arrives on the Google driver; add a hop through `extract_google_metadata` if that Extract function can carry a gateway envelope, otherwise say in the module docstring why it is not pinned.
- **Classification**: every member is `CONFIGURATION` and never retryable; `DISABLED_INTEGRATION` is `CONTACT_SUPPORT` and the other three `CHANGE_MODEL`; `is_model_not_found` is set for exactly `UNKNOWN_MODEL`; a bare 400 without a recognized code still takes the status ladder.
- **End to end**: `pig-01` built through Portkey's factory renders `LLMModelNotFoundError` with `model_handle` set — the headline of the ledger item — and `pig-05` renders `LLMCompletionError` with `CHANGE_MODEL` advice that does not say the model was not found.
- **Rendered advice**: no member renders the generic "review the prompt, parameters, and inputs" line; `pig-01` and `pig-05` are told apart; `pig-02` does not mention the caller's credentials and does not tell them to pick a model.
- **The scope decision is pinned**: `pig-03` and `pig-04` are not routing refusals (`gateway_routing_refusal is None`), and `pig-09` is an unresolved reference and not a routing refusal. The pin asserts family membership only, not the ladder's verdict for `pig-03`/`pig-04`.
- **The three families do not shadow each other**: extend the existing disjointness test in the unresolvable-references module — or add a three-way one here — so a code lands in exactly one map.

### 5. Docs and changelog

- `docs/under-the-hood/error-model.md` § "The Gateway's Own Refusals": the opening paragraph says the gateway refuses "for two different reasons" — make it three, and add a third `####` half ("When the model cannot be routed") after the reference one, with the four-code table, the scope table for `pig-03` / `pig-04`, and the decisions above. Update the closing paragraph, which currently says the routing refusals "belong to neither family and classify on their status like anything else" — after this change that sentence is false and must name only the deadline outcomes. Update the two layer-model table rows to name `GatewayRoutingRefusal` and `gateway_routing_refusal`.
- `CHANGELOG.md` under `[Unreleased]` → Added: one condensed entry in the style of the two existing gateway entries.
- No config change; no spec / conformance surface touched; the manifold side is untouched.

### 6. Gate

`make agent-check`, then the full `make agent-test` (the new test module and `.test_durations` need the full run).

## Checkpoints

- **Checkpoint 1 — plan ratified (2026-09-02).** Two rulings, both recorded above: `pig-02` is `CONFIGURATION` / `CONTACT_SUPPORT` with the flag unset, not `CHANGE_MODEL`; and the `pig-12` ride-along is split out, because the item it belongs with is the default itself — an unmapped gateway code must stop reading as "review your prompt" (L-260902-b17ff6), with the `pig-12` map entry its own small item (L-260901-0859e8).
- **Checkpoint 2 — implementation landed on this branch.** Steps 1–6 done, both gates green. Record here anything decided or discovered while building it beyond what the design section already says, then open the stacked PR for review with `Closes L-260831-9963b5` in its body.
