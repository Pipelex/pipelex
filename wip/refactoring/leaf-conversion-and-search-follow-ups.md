# Leaf-conversion and structured-search follow-ups — what the review of `refactor/Follow-ups` left open

The items a full pre-landing `/review` of `refactor/Follow-ups` surfaced and **did not fix**. The branch itself carries the critical fixes that review found; this file is the residue.

Every claim below was re-verified against the tree on **2026-07-31 at `2cc27966a` plus the review's own fixes** — that is, *after* the critical work landed, so nothing here is a stale reading of the pre-review tree. The command that produced each measurement is inline, so a new session can re-take it rather than trust it.

**Stable ids:** cite these as **RF-1** … **RF-7**. They are deliberately not `FU-n`: that namespace belongs to the modularity track in [`modularity-review-follow-ups.md`](modularity-review-follow-ups.md), and the two docs sit in the same folder.

| id | one line | verdict | size | blocked on |
| --- | --- | --- | --- | --- |
| [RF-1](#rf-1--the-live-validationerror-contract-is-inconsistent-and-the-plugins-own-two-arms-disagree-about-it) | The live-`ValidationError` contract is inconsistent; the plugin's own two arms disagree | **design decision needed** | small code, real thinking | nothing — decide before the sweep |
| [RF-2](#rf-2--by_alias-and-dump_mode-reach-no-live-path-here-and-the-plugins-copy-diverges-on-the-announced-fix) | `by_alias` / `dump_mode` reach no live path here; the plugin's copy diverges on the announced fix | true, disclosed | small (a swap) | RF-1, then a `pipelex` release |
| [RF-3](#rf-3--the-test-gaps-this-branch-left) | Test gaps this branch left — one of them lets the headline fix be deleted silently | true | small | nothing |
| [RF-4](#rf-4--no-request-timeout-ever-reaches-the-linkup-sdk) | No request timeout ever reaches the Linkup SDK, so `LinkupTimeoutError` is unreachable | true, pre-existing | small + a config call | nothing |
| [RF-5](#rf-5--the-llm-paths-schema-check-is-implicit-and-a-plausible-optimisation-would-delete-it) | The LLM path's schema check is implicit, and a plausible optimisation deletes it | true | small | nothing |
| [RF-6](#rf-6--dry-search-leaves-report-no-usage) | Dry search leaves report no usage | true, pre-existing | small design | nothing |
| [RF-7](#rf-7--the-relays-envelope-contract-is-unpinned-on-the-producing-side) | The relay's envelope contract is unpinned on the producing side | true | small, cross-repo | a `pipelex-relay` PR |
| [RF-8](#rf-8--an-envelope-whose-data-is-neither-null-nor-an-object-is-called-empty-rather-than-malformed) | An envelope whose `data` is neither null nor an object is called *empty* rather than *malformed* | true, deliberate | small, but two workers | nothing — decide whether the split is worth it |

**What the review already fixed, so you do not re-find it:** the direct Linkup backend silently validating a `{data, sources}` envelope into an all-defaults object; a billed search whose shape was rejected vanishing from the cost report; `pipelex validate` no longer catching an output class that cannot emit a JSON schema; the gateway's positional `.get("data")` unwrap; `JSONDecodeError` escaping unclassified; the misleading "try a different model" advice on an empty result; and `linkup/exceptions.py` not following the `<provider>_exceptions.py` convention.

---

## RF-1 — The live-`ValidationError` contract is inconsistent, and the plugin's own two arms disagree about it

**Not** "the plugin cannot adopt the shared helper" — it can, and on the object path it is a clean swap. The branch's review guide already frames the bare re-raise as deliberate, and that framing is right. What the review found is narrower and more interesting: **the intended adopter contradicts itself about whether a live `ValidationError` may escape workflow code**, and by its own comment the arm that lets it escape is the wrong one.

### Verified

The shared helper re-raises the bare `ValidationError` on the live path — `pipelex/cogt/content_generation/object_revalidation.py`:

```python
try:
    return object_class.model_validate(raw_data)
except ValidationError as exc:
    if is_mock_built:
        raise DryRunObjectFidelityError.for_object_class(object_class.__name__) from exc
    raise
```

The plugin's **object** arm does exactly the same — so it can adopt the helper as-is:

```bash
sed -n '52,78p' ../pipelex-temporal/pipelex_temporal/tprl_content_generation/content_generator_in_workflow.py
# ...    Scoped to the dry path only — a LIVE provider's invalid output keeps its existing ``ValidationError``.
#     raw_data = raw_obj.model_dump(mode="json", serialize_as_any=True)
#     if not is_mock_built:
#         return object_class.model_validate(raw_data)
```

Its **search** arm does the opposite, and says why:

```bash
sed -n '548,561p' ../pipelex-temporal/pipelex_temporal/tprl_content_generation/content_generator_in_workflow.py
# # ... a malformed structured response raises a bare ValidationError here in
# # workflow code. Left raw it is neither WorkflowExecutionError nor PipelexError, so Temporal
# # treats it as a workflow-task failure and retries forever, hanging the submitter — the exact
# # failure mode this seam exists to prevent.
#         try:
#             return output_structure_class.model_validate(result_dict)
#         except ValidationError as exc:
#             ...
#             raise ContentGenerationError(msg) from exc
```

Both arms run in workflow code. If that comment is correct — and it has an integration test behind it — then the object arm has the same hang hazard and does nothing about it. If the object arm is fine, the search arm's conversion is unnecessary. They cannot both be right.

### Why this lands here and not only in that repo

The plugin sweep is already on the books as "swap the copies for the shared helper". Doing that swap **as written** propagates the inconsistency into the shared home: the helper would become the single documented source of a live-error contract that the plugin's search arm has to override anyway, without the helper saying so. Whoever does the sweep should resolve the disagreement first, not preserve it.

### There is a second half, in this repo

In-process, that same bare `ValidationError` is now the **primary live failure mode** of structured search — "the provider returned a payload that doesn't match your class" — and it escapes the Pipelex error taxonomy entirely: no `error_type`, no `error_domain`, no `type_uri`. Until this branch, structured search was broken on both backends, so that outcome was never reachable; it is now.

### Options

1. **Give the helper an explicit live-failure contract** — an `on_validation_error` callable, or a typed error class parameter. The plugin passes its `ContentGenerationError` on both arms; this repo passes a typed content-generation error. The disagreement resolves in one place and the in-repo taxonomy hole closes with it.
2. **Keep the bare `raise`, decide the plugin question separately.** Legitimate — but then the helper's docstring must say that a submitter running in workflow code MUST NOT let the bare error escape, because right now nothing in the shared home warns the next adopter.

Either way, the plugin's two arms need to agree before the sweep lands.

---

## RF-2 — `by_alias` and `dump_mode` reach no live path here, and the plugin's copy diverges on the announced fix

Disclosed in the CHANGELOG, so this is not a surprise — but the *shape* of the divergence is worse than "not adopted yet" and is worth stating plainly.

### Verified

The branch's own audit says nothing in this repo reaches the conversion arm ([`boundary-revalidation-round-trip-audit.md`](boundary-revalidation-round-trip-audit.md), "Who reaches the conversion"): every in-repo path hits the `isinstance` short-circuit. The boundary arm's only caller is out of repo:

```bash
grep -rn "await search_gen_structured(" ../pipelex-temporal/pipelex_temporal/
# .../tprl_content_generation/act_search_generate.py:23:    return await search_gen_structured(search_object_assignment=search_object_assignment)
```

(Grep for `search_gen_structured\b` instead and the word boundary matches inside `act_search_gen_structured`, burying the one real call site under the activity's own name.)

And the plugin's copy of the conversion still dumps without `by_alias`:

```bash
grep -n "model_dump(mode=" ../pipelex-temporal/pipelex_temporal/tprl_content_generation/content_generator_in_workflow.py
# 71:    raw_data = raw_obj.model_dump(mode="json", serialize_as_any=True)
```

`dump_mode` likewise has no production caller anywhere — only tests pass a non-default value.

### Why it matters more than "pending"

Before the extraction the two copies differed only in `dump_mode`. They now differ **on the exact defect the CHANGELOG announces as fixed**: a field named `json` / `copy` / `schema` / `construct` still breaks the round trip on the distributed arm, which is the *only* arm that reaches that code. The divergence is invisible to both repos' CI.

The one live path in this package that does get the fix is `dry_search_gen_structured` — reached only through the boundary arm, which again only the plugin calls.

**Do this together with RF-1**, in the plugin sweep, and re-read the CHANGELOG entry's framing when it lands.

---

## RF-3 — The test gaps this branch left

Priority order. The first one is the one that matters.

### (a) `by_alias=True` on the dry boundary search mock is untested

`pipelex/cogt/content_generation/dry_mock.py`:

```python
return build_mock_object(boundary_class).model_dump(mode="json", by_alias=True)
```

No test builds a `SearchObjectAssignment` from a class whose properties the rebuild renames, so **deleting `by_alias=True` here leaves the whole suite green** while re-introducing the `Field required` failure the branch set out to fix. The sibling fix in `revalidate_leaf_object` *is* pinned, which makes this an asymmetry rather than an accepted gap:

```bash
grep -rln "construct: str\|json: str" tests/
# tests/integration/pipelex/cogt/content_generation/test_boundary_roundtrip_fidelity.py   ← only the object arm
```

Fix: a boundary-dry case in `test_leaf_dry_object_mocks.py` using a `StructuredContent` with shadowing field names, asserting the returned dict is keyed by the schema property names and validates back into the original class.

### (b) The live in-process search arm's return value is never asserted

`tests/integration/pipelex/cogt/content_generation/test_object_class_passthrough.py`:

```python
await search_gen_structured_object(_live_search_assignment(), output_class=HintedName)

assert mock_worker.search_structured.await_args.kwargs["schema"] is HintedName
```

The result is discarded. Its dry twin asserts the value, so the once-only-validation contract and the `is_mock_built=False` negative path (a malformed provider dict must raise `ValidationError`, never `DryRunObjectFidelityError`) are unpinned on the live arm.

### (c) The SDK-exception branch of `_search_structured` is untested on both backends

```bash
grep -c "_search_sourced_answer" tests/unit/pipelex/providers/linkup/test_linkup_search_worker_semantic.py   # 1
grep -c "_search_structured"     tests/unit/pipelex/providers/linkup/test_linkup_search_worker_semantic.py   # 0
```

The semantic tests that parametrize every Linkup SDK exception only ever drive the sourced-answer arm. The structured arm's `try` now wraps a differently-shaped call (serialized schema, `include_sources=False`), so its error classification and `from exc` chaining ride on nothing. Parametrizing the existing tests over both arms is the cheap fix.

### (d) The gateway test never asserts the caller's schema reaches the relay

The Linkup contract test pins that the real schema — including a `json_schema_extra` hint a rebuild would drop — crosses the wire. Its gateway counterpart mocks `_call_relay` wholesale and never inspects what was sent, so item 2's contract is verified on one backend only, and the gateway is the one the hosted runner uses.

---

## RF-4 — No request timeout ever reaches the Linkup SDK

### Verified

```bash
grep -n "timeout" pipelex/providers/linkup/linkup_search_worker.py pipelex/providers/linkup/linkup_extract_worker.py
# (none)
```

The SDK's `async_search` takes `timeout: float | None = None` and passes it straight to `httpx`, whose docs say `timeout=None` disables timeouts entirely — connect, read, write and pool. So a slow or hung provider blocks the task indefinitely.

The design clearly assumes a timeout exists: the worker catches `LinkupTimeoutError` and classifies it. **The condition that raises it cannot be reached.**

Pre-existing, and it affects the sourced-answer and extract paths too — but the structured call site was rewritten on this branch, which is why it surfaced now.

Fix needs a decision, which is why it is deferred rather than patched: where does the value come from — a search setting, a provider config key, or a shared inference default? Once that is settled the code is one keyword argument per call site.

---

## RF-5 — The LLM path's schema check is implicit, and a plausible optimisation would delete it

This is a **trap**, recorded so the next person to "clean up" a redundant call does not spring it.

### Verified

`ObjectAssignment.make_for_class` computes a schema that the in-process path never reads:

```bash
grep -n "model_json_schema" pipelex/cogt/content_generation/assignment_models.py
# 95:            object_class_schema=object_class.model_json_schema(),
# 184:            output_class_schema=output_class.model_json_schema(),
```

`resolve_object_class` returns the live class immediately when one is in hand — which it always is from `ContentGenerator` — so `object_class_schema` is dead on both the live and the dry in-process LLM paths. It looks exactly like the waste this branch removed on the search arm by not building a `SearchObjectAssignment` at all. It measures around 290 µs per call for a modest nested model: noise beside a live LLM round trip, but roughly a fifth of the leaf's cost on the dry-run path `pipelex validate` walks per pipe.

### Why you cannot just delete it

That call is what still *incidentally* proves the output class can emit a JSON schema on the LLM path. The search arm now has an explicit check:

```bash
grep -rn "_validate_schema_is_generable" pipelex/
# dry_mock.py:465:    _validate_schema_is_generable(output_class=output_class)
# dry_mock.py:470:def _validate_schema_is_generable(*, output_class: type[BaseModel]) -> None:
```

The LLM arm has none. Deleting the assignment's schema call without adding the explicit check there would re-open, on the LLM path, precisely the hole the review just closed on the search path: polyfactory mocks an undescribable class happily, `pipelex validate` passes, and the live run dies inside the worker on a bare `PydanticInvalidForJsonSchema` — a `RuntimeError`, so no model attribution, no remedy, no error identity.

**Do them together or not at all:** add `_validate_schema_is_generable` to the LLM dry arm first, then the optimisation is safe.

---

## RF-6 — Dry search leaves report no usage

Carried over from the branch's own deferral list, which recorded it with no durable home. This section is that home.

### Verified

None of `dry_search_gen_sourced_answer`, `dry_search_gen_structured`, `dry_search_gen_structured_object` emits a usage event, where the dry LLM leaves report a synthetic job via `report_dry_llm_job` / `report_mock_usage_llm_job`:

```bash
grep -n "report_dry_llm_job\|report_mock_usage_llm_job\|def dry_search" pipelex/cogt/content_generation/dry_mock.py
# 146:def report_dry_llm_job(...)
# 158:def report_mock_usage_llm_job(...)
# 411:def dry_search_gen_sourced_answer(...)
# 419:def dry_search_gen_structured(...)
# 441:def dry_search_gen_structured_object(...)
```

So a dry run's cost/usage report shows zero search calls for a method that will make one per run.

Pre-existing — dry search never reported — and not introduced by this branch.

Deferred because it is a small **design**, not a mechanical patch: it means choosing the synthetic-search-job conventions (model name / id placeholders, whether the per-request 1M-token cost convention applies, and the dry vs `is_mock_usage` variants), and improvising those would bake in a shape the cost report has to live with.

---

## RF-7 — The relay's envelope contract is unpinned on the producing side

Cross-repo; needs a `pipelex-relay` PR.

### Verified

The relay produces the envelope:

```bash
grep -n "include_sources" ../pipelex-relay/pipelex_relay/services/web_searcher.py
# 97:            include_sources=True,
```

Its own unit test asserts the **opposite** shape — a bare payload:

```bash
grep -n "search_structured" ../pipelex-relay/tests/unit/pipelex_relay/api/test_web_search.py
# 32:        mock_instance.search_structured = mocker.AsyncMock(return_value={"key": "value", "items": [1, 2, 3]})
```

So the contract the gateway worker consumes is encoded nowhere on the producing side, and the one test that touches it encodes something else.

### Why it is now lower-stakes than it was

The review changed the gateway worker to recognise the envelope **structurally** rather than demand it, so a relay that stops asking for sources no longer breaks every gateway structured search — the two sides are decoupled and this is no longer a coordinated deploy. What remains is that the relay could change its response shape with nothing to notice.

Worth doing anyway, and cheap: a relay-side regression test pinning `{data, sources}`, plus a line in the relay's README or CHANGELOG naming the shape. The hazard is amplified by this branch's own reasoning — it changed the *direct* backend to `include_sources=False` because "a structured result has nowhere to put sources", and someone applying that same reasoning to the relay is the likeliest way this moves.

---

## RF-8 — An envelope whose `data` is neither null nor an object is called *empty* rather than *malformed*

Raised by a review bot on the v0.42.0 release PR (#1078) against `linkup_search_worker.py`. Verified true as a mechanic, judged **not worth fixing there** — recorded here rather than patched under a release.

### Verified

Both workers make the malformed-vs-empty split the extractor's docstring promises, and both make it the same way:

```bash
sed -n '178,182p' pipelex/providers/linkup/linkup_search_worker.py
# payload = extract_structured_search_payload(response=response, schema=schema)
# if payload is not None: return payload
# if isinstance(response, dict):   ← empty; else → malformed
```

`extract_structured_search_payload` returns `None` in exactly two places (`structured_search_payload.py`): the response is not a dict at all, or it *is* the envelope and `payload["data"]` is not a dict. The `isinstance` line excludes the first, so the empty branch is reachable iff an envelope arrived carrying `data` of `None`, `list`, `str`, `int`, `float` or `bool`. Only `data: null` is genuinely "the search found nothing"; a list or a scalar is a provider contract breach — the schema always crosses as `model_json_schema()`, which is always `"type": "object"` — and gets `CHANGE_INPUT` / "try a broader query" advice it does not deserve.

The extractor's own docstring closes that sub-split on purpose: *"an envelope whose `data` is null **or not an object** (the search simply found nothing…)"*. So this is a documented simplification, not an oversight.

### Why it was not fixed on the release PR

- Blast radius is the advice string and the message wording, on a path that already raises a classified error in the right family. Nothing is silently wrong.
- The only shape observed in practice is `data: null`, which is classified correctly today. `data: {}` never reaches the branch at all — it is a dict, so it is returned as the payload and the leaf decides.
- `gateway_search_worker.py` is structurally identical here, so fixing linkup alone would *create* a divergence where there is currently none. The change is two workers plus the shared helper plus both contract suites.

### If you do it

Put the predicate in the module that owns the envelope rule, not in the call sites: a `structured_search_payload` helper returning "envelope present **and** `data` is null", and swap the `isinstance(response, dict)` line in both workers for it. Inlining `response["data"] is None` at each call site instead hard-codes the helper's internals in two places and breaks the day the helper grows a third `None` case. Then tighten the extractor docstring's "null or not an object" → "null", or it becomes the drifted artifact. Make the fall-through message name the offending `data` type rather than the outer `dict`.

**Do not** reach for a three-way outcome enum + result type + `match/case` in both workers. That is the shape the docstring literally describes, but it is a lot of new machinery to change an advice string on a shape never observed.

### Two coverage gaps found while verifying this

Both are real, independent of whether RF-8 itself is ever done:

1. **The shared rule has no direct test.** `pipelex/cogt/search/structured_search_payload.py` is exercised only indirectly, through the two worker contract suites. It is the one piece of logic both backends share, and the alias defect fixed on #1078 lived in it.
2. **The linkup suite is missing the `DataAndSources` case.** `test_gateway_structured_search_contract.py` pins `test_an_output_class_that_declares_data_and_sources_is_not_unwrapped` — "the one shape a positional `.get('data')` unwrap would silently corrupt" — and its linkup counterpart has no equivalent, despite running the same shared rule. The aliased variants added on #1078 landed on the gateway side only, for the same reason.

---

## Provenance

Findings came from a `/review` pass on `refactor/Follow-ups`: specialist reviewers (testing, maintainability, security, performance, api-contract), a red-team pass, an independent fresh-context adversarial pass, and a Codex adversarial pass. Claims that survived were re-verified by hand — the silent-envelope corruption, the schema-generability regression and the `validate_by_alias` edge were each proven or disproven by running pydantic directly rather than by reading. Several confident-sounding findings did **not** survive and are deliberately absent: `by_alias=True` was attacked with `serialization_alias`≠`validation_alias`, `AliasChoices`, `AliasPath`, `extra="allow"` and the real spec classes without producing a regression, and the "json dump mode breaks strict types" claim is already the deliberately-deferred residue recorded in the branch's own notes.
