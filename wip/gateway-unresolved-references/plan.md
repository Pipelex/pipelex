---
status: landed
item: L-260901-b0bd98
---

# Classify the gateway's "cannot resolve this reference" refusals

## The bug, verified

The inference gateway's unresolvable-reference refusals arrive at `classify_inference_error` carrying their own error codes, and nothing reads them. They fall through to the `status_code == 400` arm of the status ladder in `pipelex/cogt/inference/error_classify.py`, classify as `CONTENT` / `CHANGE_INPUT`, and render the generic *"The provider rejected the request — review the prompt, parameters, and inputs."* A caller who mistyped a `pipelex-storage://` key, pointed at an object the gateway's role may not read, or aimed a document URL at a host the SSRF guard refuses, is told to revise their prompt.

Probed on this branch — every code in the family renders the generic advice:

```
pig-09:                            content / change_input  "The provider rejected the request — review the prompt, parameters, and inputs."
pipelex_storage_uri_invalid:       content / change_input  (same)
pipelex_storage_unreadable:        content / change_input  (same)
pipelex_storage_uri_unsupported:   content / change_input  (same)
pipelex_document_host_refused:     content / change_input  (same)
pipelex_document_unreachable:      content / change_input  (same)
pipelex_document_unsupported_type: content / change_input  (same)
```

The structural cause: `_GATEWAY_REQUEST_LIMIT_BY_CODE` in `pipelex/cogt/inference/error_classification.py` maps only the request-shape limits (`pig-07`, `pig-08`, `pig-10`, `pig-11`, `pipelex_storage_object_too_large`, `pipelex_document_too_large`). The unresolvable-reference codes are deliberately absent — the `gateway_request_limit` property's docstring even promises they "classify on their status like anything else", which is exactly the behaviour this plan removes.

The codes are readable today because the fix that landed on this PR's branch made the two Pipelex-service Extract hops read `error.code` before `error.type` (`_pipelex_service_error_code_from_body`). Before that, all of these arrived as `invalid_request_error`. The mechanism to classify them — a code-keyed enum ahead of the status ladder, plus a dedicated render branch — already exists for the request-limit family and is the shape this work copies.

## The code inventory, from the manifold source

Verified against `pipelex-manifold/src/pig/`:

| Code | HTTP | Raised by | Meaning |
|---|---|---|---|
| `pig-09` | 400 | `modelResolver.ts` (LLM routes) | the one fail-closed slot for "cannot resolve" — every `StorageFailureReason` but `oversize`: no bucket configured, not a storage reference, no such object, an object it cannot read, a type no provider takes, or no way to hand a file to the resolved provider. The message carries the difference; the code does not. |
| `pipelex_storage_uri_invalid` | 400 | `storage/nativeRoute.ts` | the reference does not obey the key grammar (also the traversal guard) |
| `pipelex_storage_unreadable` | 400 | `storage/nativeRoute.ts` | the object is not there, or the role may not read it |
| `pipelex_storage_uri_unsupported` | 400 | `storage/nativeRoute.ts` | no bucket configured — the scheme is not served at all |
| `pipelex_document_scheme_refused` | 400 | `pipelex/documentFetch.ts` | the document URI is not an http(s) URL |
| `pipelex_document_host_refused` | 400 | `pipelex/documentFetch.ts` | the SSRF guard refuses the host — a deliberate security refusal |
| `pipelex_document_address_refused` | 400 | `pipelex/documentFetch.ts` | the resolved address is blocked (private/internal ranges) |
| `pipelex_document_redirect_refused` | 400 | `pipelex/documentFetch.ts` | the origin answered a redirect, which the gateway refuses to follow |
| `pipelex_document_unreachable` | 400 | `pipelex/documentFetch.ts` | the origin answered a non-success status |
| `pipelex_document_empty` | 400 | `pipelex/documentFetch.ts` | the document was served empty |
| `pipelex_document_unsupported_type` | 400 | `pipelex/documentFetch.ts` | the served MIME type is not one the pipeline accepts |
| `pipelex_document_bad_data_url` | 400 | `pipelex/documentFetch.ts` | a `data:` URL that cannot be decoded |

Out of scope, noted for completeness: `pig_storage_timeout` (504) and `pig_storage_client_disconnected` (499) are deadline outcomes, not reference verdicts — 504 already classifies transient via the ≥500 arm, which is right for a timeout. They stay with the status ladder.

## The design decision: the arms

This is the work the ledger item names: deciding which `UserActionKind` each member deserves, not just adding map entries. Grouping is by remedy — members share an arm only when the caller's next move is the same — mirroring how `GatewayRequestLimit` folds three codes into `OBJECT_TOO_LARGE`.

New enum `GatewayUnresolvedReference` in `error_classification.py`, beside `GatewayRequestLimit`:

| Member | Codes | Category / action | Advice (gist — final wording at implementation) |
|---|---|---|---|
| `REFERENCE_UNRESOLVED` | `pig-09` | `CONTENT` / `CHANGE_INPUT` | a file reference in the request could not be resolved — the error message names the cause; fix the reference it names. Deliberately defers to the message because the code is the LLM routes' single fail-closed slot for every storage failure but "over its cap". |
| `STORAGE_REFERENCE_INVALID` | `pipelex_storage_uri_invalid` | `CONTENT` / `CHANGE_INPUT` | the `pipelex-storage://` reference is malformed — check the key against what the upload returned |
| `STORAGE_OBJECT_UNREADABLE` | `pipelex_storage_unreadable` | `CONTENT` / `CHANGE_INPUT` | the referenced object does not exist or cannot be read — check the reference points at an object that was uploaded to this deployment |
| `STORAGE_NOT_SERVED` | `pipelex_storage_uri_unsupported` | `CONFIGURATION` / `CONTACT_SUPPORT` | this deployment does not serve `pipelex-storage://` references at all — an operator's problem, nothing about the inputs causes it |
| `DOCUMENT_URL_REFUSED` | `pipelex_document_scheme_refused`, `pipelex_document_address_refused`, `pipelex_document_redirect_refused` | `CONTENT` / `CHANGE_INPUT` | the document URL was refused before or during the fetch — use a plain public http(s) URL, and send the final URL rather than one that redirects |
| `DOCUMENT_HOST_REFUSED` | `pipelex_document_host_refused` | `CONTENT` / `CHANGE_INPUT` | the gateway refuses to fetch documents from this host — **a security policy, stated as one**: private and internal addresses are not fetchable; host the document publicly or upload it to Pipelex storage. Never "use a smaller file" or "revise the prompt". |
| `DOCUMENT_UNREACHABLE` | `pipelex_document_unreachable` | `CONTENT` / `CHANGE_INPUT` | the document could not be fetched from its URL — check that it is live and publicly reachable |
| `DOCUMENT_CONTENT_UNUSABLE` | `pipelex_document_empty`, `pipelex_document_unsupported_type`, `pipelex_document_bad_data_url` | `CONTENT` / `CHANGE_INPUT` | the document was fetched but is unusable — the message says whether it was empty, of an unsupported type, or a malformed `data:` URL |

Decisions taken, and why:

- **`STORAGE_NOT_SERVED` is the one `CONTACT_SUPPORT` arm.** The ledger item calls this out: no bucket configured is a deployment that does not serve the scheme, so telling the caller to fix their input is wrong in kind. `CONFIGURATION` category, matching `BODY_LENGTH_REQUIRED`'s precedent for "an operator's problem".
- **`DOCUMENT_HOST_REFUSED` keeps `CHANGE_INPUT` but gets its own member.** The caller *can* act (host the file elsewhere, or upload it to storage), so the action kind is right — but the advice must say the refusal is deliberate security policy, not a fault to work around. Folding it into `DOCUMENT_URL_REFUSED` would lose exactly the distinction the item exists for.
- **`address_refused` groups with the URL-shape refusals, not with `host_refused`.** Both are SSRF-guard outcomes, but `address_refused` fires on the resolved address and reads to the caller the same way as a refused scheme: this URL form is not accepted. If review prefers it beside `host_refused` under the security wording, that is a one-line regroup.
- **`DOCUMENT_UNREACHABLE` is not retried.** The origin could have been transiently down, but the gateway renders it 400, the runtime's retry would re-run a whole inference call to re-fetch a document, and the common case is a wrong URL. The advice can mention retrying manually if the host was down; the classifier does not.
- **Nothing in the family is retryable.** Same reasoning as the request limits: the gateway refused before a provider saw the request; an identical retry earns an identical refusal.
- **Every arm defers numbers and specifics to the gateway's own message.** Same principle as `_render_gateway_limit_detail`: the refusal message beside the detail already names the key, host, status, or type; repeating a guess is how advice contradicts the refusal it explains.

## Implementation steps

### 1. The classification family — `pipelex/cogt/inference/error_classification.py`

- Add `GatewayUnresolvedReference` (StrEnum) with the members above, docstrings citing the wire codes and statuses, following `GatewayRequestLimit`'s style.
- Add `_GATEWAY_UNRESOLVED_REFERENCE_BY_CODE` mapping all twelve codes. Matched on the code alone with no provider check, for the same reason as the limits map (the codes are the gateway's own namespaces; three SDK hops report three provider names).
- Add a `gateway_unresolved_reference` property on `ProviderErrorMetadata`, mirroring `gateway_request_limit`.
- **Rewrite the `gateway_request_limit` docstring's last paragraph**, which currently promises the storage codes "classify on their status like anything else" — after this change that sentence is false.

### 2. The classify step — `pipelex/cogt/inference/error_classify.py`

- Add `gateway_unresolved_reference: GatewayUnresolvedReference | None = None` to `ClassificationResult` (a flag beside `gateway_request_limit`, same rationale: it does not change the retry decision, it lets Render name the refusal).
- Add `_classify_gateway_unresolved_reference(*, reference: GatewayUnresolvedReference)` returning `CONTENT`/`CHANGE_INPUT` for every member except `STORAGE_NOT_SERVED` → `CONFIGURATION`/`CONTACT_SUPPORT`.
- In `classify_inference_error`, branch on `metadata.gateway_unresolved_reference` right after the request-limit branch — the two code sets are disjoint, both are explicit verdicts from a service we operate, and both must run ahead of the status ladder.

### 3. The render step — `pipelex/cogt/inference/error_render.py`

- Add `_render_gateway_unresolved_reference_detail(*, reference: GatewayUnresolvedReference) -> str` with one advice string per member (gists above).
- In `_render_detail`, branch on `classification.gateway_unresolved_reference` beside the existing `gateway_request_limit` branch, ahead of the action-kind match.

### 4. Tests — `tests/unit/pipelex/cogt/inference/test_gateway_unresolved_references.py`

Mirror `test_gateway_request_limits.py`'s structure and its module docstring style:

- **The code is recognized**: each of the twelve codes maps to its member; unknown codes and `None` do not; recognition is provider-blind (`GATEWAY`, `ANTHROPIC`).
- **The code survives every Extract hop**: through the Portkey substrate (including the payload-discarding SDK path), plain `httpx` on the native routes, the shared Anthropic driver, and the OpenAI substrate — reusing that module's envelope helpers where sharable.
- **Classification**: every member is `CHANGE_INPUT` except `STORAGE_NOT_SERVED` which is `CONTACT_SUPPORT`; none is transient; a plain 400 without a recognized code still takes the status ladder.
- **Rendered advice**: `DOCUMENT_HOST_REFUSED` advice names a security refusal and never suggests revising the prompt or shrinking a file; `STORAGE_NOT_SERVED` says contact support, not fix your input; the storage members are told apart from each other; no member renders the generic "review the prompt" line.
- **The two families do not shadow each other**: `pipelex_storage_object_too_large` still classifies as a request limit, `pipelex_storage_unreadable` as an unresolved reference.

### 5. Docs and changelog

- `docs/under-the-hood/error-model.md` § "The Gateway's Own Refusals": add the second family's table (code / HTTP / member / category-action / what the caller is told) after the request-limit table, and extend the surrounding prose — one refusal family bounds request shape, the other says a reference cannot be resolved. Update the layer-model table row for `error_classification.py` to name the new enum and property.
- `CHANGELOG.md` under `[Unreleased]` → Added: one condensed entry in the style of the request-limits entry.
- No new error class is introduced (no `gei`/`gep` needed); no config change; no spec/conformance surface touched.

### 6. Gate

`make agent-check`, then `make agent-test` (full — the new test module and `.test_durations` need the full run).

## Checkpoint — the implementation landed

Every step above is implemented on this branch. What was decided or discovered while building it, beyond what the design section already records:

- **The arms are exactly as designed**; review did not move `address_refused`, so it stays with the URL-shape refusals under `DOCUMENT_URL_REFUSED` and `DOCUMENT_HOST_REFUSED` keeps its own arm.
- **The two families are pinned as disjoint by a test rather than by a comment.** `TestTheTwoGatewayFamiliesDoNotShadowEachOther` walks both code sets and asserts each reaches one family and not the other, so a code added to the wrong map fails rather than silently borrowing the other family's advice. The `pipelex_storage_*` codes are the case that needs it: `object_too_large` is a limit, `unreadable` is an unresolved reference, and both arrive from the same route.
- **The test module keeps one parametrize table as its single source of codes** (`_EVERY_CODE_AND_MEMBER`), reused by the recognition, classification, rendering and disjointness cases, plus a case asserting every enum member is reachable from a wire code — a member no code reaches would be advice that never renders for anyone.
- **The docs section grew two `####` headings** rather than one long run: the existing request-limit half is now "What the request may weigh" and the new half "When a reference cannot be resolved", under the unchanged `### The Gateway's Own Refusals`. Nothing links to those anchors, so the split breaks no reference. The closing paragraph now names `pig_storage_timeout` / `pig_storage_client_disconnected` explicitly as belonging to neither family, which is where the inventory's out-of-scope note now lives in shipped documentation.

## Checkpoint — landed

Merged as pipelex#1181, *"Classify the gateway's unresolvable-reference refusals"*, squashed onto the stack trunk `feature/Two-gateways-2` — the branch this work was stacked on. Commits are named by subject rather than by hash throughout this document, because every rebase of the trunk rewrites them.

What the merge carries, against the steps above: all six are done as written. The two commits on the branch were *"classify the gateway's unresolvable-reference refusals"* (the family, the classify branch, the render branch, the test module, the docs half) and *"recognize the scheme refusal a caller actually reaches"* — the second a review correction adding `pipelex_unsupported_uri_scheme` to `DOCUMENT_URL_REFUSED` beside `pipelex_document_scheme_refused` rather than in place of it. `classifyExtractInput` runs before any fetch and admits only `https:`, `data:` and `pipelex-storage://`, so an `http://` document URL is refused there and never reaches the fetch — which means the inventory's `pipelex_document_scheme_refused`, mapped and kept, is not the code that arm actually sees in practice. The family therefore covers thirteen wire codes, not the twelve this plan's inventory table lists.

Every check on the pull request passed — typecheck, all eight test shards on py3.11, and each lint job including the drift-contract and keyword-only gates.

**Delivery.** The merge is on `feature/Two-gateways-2` only; it has reached neither `dev` nor `main`. It ships when the trunk's own pull request lands, and reaches consumers when a pipelex release is cut after that — the repo's open release item is the one that carries #1154 (`L-260828-f4e88c`), which predates this work and does not yet include it.

**Left for a person.** Nothing this campaign asked for. The neighbouring gateway family — the routing refusals `pig-01`, `pig-02`, `pig-05` and `pig-06`, which still answer 400 and so advise a caller to revise their prompt when the real fault is an unknown model handle — is open work of its own under its own ledger item (`L-260831-9963b5`), not unfinished business here.

## Out of scope

- The manifold side is untouched: every code already exists on the wire and this is purely the runtime's reading of them.
- `pig_storage_timeout` / `pig_storage_client_disconnected` stay with the status ladder (see inventory).
- Per-plan / per-tier wording for the hosted product — same deferral as `_render_gateway_limit_detail` records.
