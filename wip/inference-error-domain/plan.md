---
status: active
item: L-260831-17614f
---

# Derive `error_domain` for the `CogtError` family from `InferenceErrorCategory`

## Verdict on [L-260831-17614f](http://localhost:4747/i/L-260831-17614f)

The item is justified, and the codebase already expects the fix. Verified on `dev` (2026-08-31):

- `CogtError` (`pipelex/cogt/exceptions.py`) declares `error_category`, `user_action`, `provider_metadata`, `model_handle`, `backend_name` — and no `error_domain`. Reproduced: `LLMCompletionError("boom", error_category=CONTENT).to_error_report()` → `domain: None | status: 500 | category: content | retryable: False`.
- `error_domain_to_http_status` (`pipelex/base_exceptions.py`) maps `None` → 500, so every caller-fixable inference failure (content-policy refusal, bad prompt parameter, malformed prompt image, gateway request-limit refusal once `feature/Gateway-request-limits` lands) answers as a server error. Only the provider-429 passthrough escapes.
- The wrapper layer was *built* for this and is currently fed nothing: `PipelineExecutionError`'s docstring (`pipelex/pipeline/exceptions.py`) says it "inherits `error_domain` … from the wrapped `__cause__` chain … and only falls back to a generic RUNTIME / UNKNOWN classification when the cause chain surfaces none". The cause chain surfaces none, always — the fallback fires on every inference failure. The enrichment plumbing (`_enrich_error_report_from_cause`, `report.error_domain or cause_report.error_domain`) needs zero changes; only the leaf family must start supplying a domain.
- It matches the established direction: [L-260829-643af2](http://localhost:4747/i/L-260829-643af2) (`error_domain=input` on `MethodRefError`) and [L-260829-fa8267](http://localhost:4747/i/L-260829-fa8267) (entry-lookup failures → INPUT) are the same move on neighboring families.

## Design

### The mapping — a property on `InferenceErrorCategory`

Add `InferenceErrorCategory.error_domain`, an exhaustive `match` like the existing `is_retryable`:

| Category | Domain | HTTP effect |
|---|---|---|
| `CONTENT` | `INPUT` | **500 → 422** — the behavior change |
| `CONFIGURATION` | `CONFIG` | 500, unchanged — report becomes truthful |
| `TRANSIENT`, `CAPACITY`, `AMBIGUOUS` | `RUNTIME` | 500, unchanged |
| `UNKNOWN` | `None` | 500, unchanged — "could not classify" must not assert a domain |

`UNKNOWN → None` is deliberate: `RUNTIME` would be a false claim, and unclassified already renders 500. `CAPACITY → RUNTIME` does not disturb the provider-429 passthrough, which `ErrorReport.http_status` checks before the domain.

### The derivation — in `CogtError.to_error_report()`

Derive from the **effective** category the report ends up carrying, so `error_domain` and `error_category` can never disagree on the wire:

```python
effective_category = self.error_category or base_report.error_category
derived_domain = effective_category.error_domain if effective_category is not None else None
# in the model_copy update:
"error_domain": self.error_domain or derived_domain or base_report.error_domain,
```

Precedence: an explicit class-level `error_domain` wins (the `pipelex/cogt/content_generation/exceptions.py` classes already declaring `INPUT` keep it), then the category derivation, then the cause chain. This is the same wrapper-wins-when-set semantics the method already uses for every other field.

### Semantics check on `CONTENT → INPUT`

`ErrorDomain.INPUT` means "the caller can fix it". Every `CONTENT`-classified class is a property of the submitted material — `LLMPromptSpecError`, `LLMPromptParameterError`, `PromptImageFactoryError`, `PromptImageFormatError`, `PromptDocumentFactoryError`, `ImgGenPromptError`, `ImgGenParameterError` — plus provider content-policy refusals from `classify_inference_error`. On the hosted API the method and its inputs are both caller-side, so 422 is right. If a specific class turns out misclassified, that is a category fix on that class, not a reason to abandon the derivation.

## Implementation steps

1. **`InferenceErrorCategory.error_domain` property** in `pipelex/cogt/exceptions.py` (exhaustive `match`, returns `ErrorDomain | None`). Import `ErrorDomain` — already imported transitively via `base_exceptions`; add the explicit name.
2. **Derivation in `CogtError.to_error_report()`** as above.
3. **Tests** (red-green):
   - Parametrized category → domain test, exhaustive over the enum.
   - `LLMCompletionError(category=CONTENT)` report: `error_domain == INPUT`, `http_status == 422`.
   - `CONFIGURATION` leaf → `CONFIG`, 500; `UNKNOWN` leaf → domain `None`, 500.
   - Explicit declaration wins: a `content_generation` INPUT class with a non-CONTENT category keeps INPUT.
   - Chain test: `PipelineExecutionError` wrapping a `CONTENT`-categorized `CogtError` surfaces `INPUT` / 422 through the wrapper (this pins the docstring's promise, which today is vacuously untested).
   - Consistency invariant: for any `CogtError` with a category and no explicit domain, `report.error_domain == report.error_category.error_domain`.
4. **Sweep existing tests** that pin `error_domain is None` or 500 for cogt/inference errors — at least `tests/unit/pipelex/exceptions/test_wrapper_error_enrichment.py`, `tests/unit/pipelex/providers/azure_rest/test_azure_worker_error_handling.py`, `tests/unit/pipelex/test_error_report_disclosure_mode.py`, plus whatever `make agent-test` reddens.
5. **Docs**: update `docs/under-the-hood/error-model.md` — the Layer-1 classification section, the `error_domain_to_http_status` section, and the class-tree annotations gain the category→domain derivation. No `gei`/`gep` needed (no class added or renamed).
6. **Changelog**: `Unreleased`, marked breaking — content-classified inference failures now report `error_domain: input` and answer HTTP 422 instead of 500.
7. **Cross-repo verification** (read-only, same session): grep `pipelex-api` for hand-mapped inference statuses (it consumes `ErrorReport.http_status`, so it should pick the change up for free) and confirm `pipelex-server/transport/` remains untouched (grep for `error_domain` already comes back empty there). File ledger items only if a consumer hand-maps.

## Implementation record

Ratified and executed on `dev`. Every step above landed as written; what follows is only what the plan could not know in advance.

**The derivation reads `self.error_category`, not the plan's `effective_category`.** The plan proposed deriving from `self.error_category or base_report.error_category`, but `ErrorReport.error_category` is typed `str` — and `model_copy(update=...)` bypasses validation, so what is actually in that field is whatever the previous layer put there. Calling `.error_domain` on it is not type-safe. The shipped form is `self.error_domain or own_domain or base_report.error_domain`, where `own_domain` derives from this error's own typed category, and it produces identical results for every case: an error with no category of its own inherits both fields from the cause chain in the same precedence order, so the two can still never disagree. The consistency invariant test pins that.

**`UNKNOWN` is not in `CATEGORY_RETRYABLE_CASES`.** The existing category table in `tests/unit/pipelex/cogt/test_data.py` was never exhaustive. The new `CATEGORY_DOMAIN_CASES` is, and `test_category_domain_cases_cover_every_category` asserts the exhaustiveness against `set(InferenceErrorCategory)`, so a future category cannot be added without deciding its domain.

**The "explicit declaration wins" precedence needed a synthetic subject.** The plan expected `pipelex/cogt/content_generation/exceptions.py` to supply one, but its three `INPUT`-domain classes are `PipelexError` subclasses, not `CogtError` — they never reach this derivation at all. No `CogtError` subclass declares an `error_domain` today, so the precedence is pinned by a test-only leaf (`_ExplicitInputDomainError`) declaring `INPUT` against a `CONFIGURATION` category.

**A pre-existing bug found next door, and fixed.** `PipelineInputContentError` (`pipelex/pipeline/exceptions.py`) declared `caller_facing_message = True` — the name of the *report field*, not of the class-level flag `_authors_caller_facing_message`. The declaration was inert, so the class's caller-facing message (which names the caller's own url) was replaced by the internal-error placeholder under STRICT disclosure. Fixed, and pinned in the class-level-metadata sweep. Mutation-verified: reverting the flag name reddens the new row.

**Review found the flag could not sit on that class as it stood, and split the family.** One class, two raise sites, two very different messages: `input_normalizer.py`'s blank-url arm states only the accepted schemes, while its unreadable-path arm interpolates `resolved_uri.path` and `type(exc).__name__`. Making the *class* caller-facing let the second one through STRICT too, which turns the report into an existence/permission oracle over the runner's filesystem — `PermissionError` on a path that exists reads differently from `FileNotFoundError` on one that does not — for any authenticated caller of a deployment leaving `is_upload_local_content_enabled` on (the shipped default, and what `pipelex-api`'s own `.pipelex/pipelex.toml` ships; `pipelex-server/api-hosted` sets it `false` in all three env configs after an earlier local-file-disclosure incident, so the hosted plane was never exposed). `PipelineInputUrlMissingError` now carries the blank-url message and the flag; `PipelineInputContentError` keeps the unreadable-path message and no flag. Pinned in both directions, in the metadata sweep and in `test_input_normalizer.py`, and mutation-verified: putting the flag back on the base class reddens both.

**The review also caught a generated artifact the first pass left stale.** `ModelChoiceNotFoundError`'s explicit `error_domain = INPUT` changes its generated error page, and `make gep` had not been re-run. Regenerated alongside the new class's page.

**Cross-repo verification came back clean.** `pipelex-server/transport/` mentions `error_domain` nowhere. `pipelex-api` consumes `ErrorReport.http_status` and picks the change up for free — its `_ERROR_TYPE_STATUS_OVERRIDES` map holds only `MethodRefError` subclasses (the separate [L-260829-643af2](http://localhost:4747/i/L-260829-643af2)) plus two pipeline/temporal classes, none of them `CogtError`, so there is no hand-mapping to unwind and no ledger item to file.

**The sweep in step 4 was incomplete, and only the full suite found it.** `tests/unit/pipelex/cli/test_agent_output.py::test_agent_error_error_domain_and_category_coexist` went red. The cause was a real design collision, not a stale assertion: `agent_error()` reads the domain report-first and falls back to an `AGENT_ERROR_DOMAINS` lookup, and three of that dict's entries are `CogtError` subclasses whose derived domain now pre-empts the lookup. Two agreed with the dict (`ModelDeckPresetValidatonError`, `GatewayUnknownModelError` — both `CONFIGURATION` → `config`) and were removed as unreachable. One conflicted: `ModelChoiceNotFoundError` was mapped `input` there, deliberately, with a matching "check the model name for typos" hint — and derived `config`. Resolved on the class, not in the test: it now declares `error_domain = ErrorDomain.INPUT` explicitly, which the derivation's precedence honours. The category stays `CONFIGURATION`, correctly — the two fields answer different questions here, and the explicit declaration is exactly the escape hatch that precedence exists for.

The module's own rule ("a class that self-describes must NOT appear in these dicts", enforced by `test_agent_output_drift.py`) already covered the class-level-attribute case but was blind to derivation, since `cls.error_domain` is genuinely `None` on those classes. A new arm, `test_category_derived_error_domain_not_duplicated_in_dict`, closes that — mutation-verified by re-adding `GatewayUnknownModelError` and watching it fail. The coexist test itself was rewritten rather than deleted: its premise (lookup domain + report category composing) is still reachable, but now only through an `UNKNOWN`-categorized cause, which is the one category that asserts no domain.

**One consequence the plan did not anticipate: the validate hook's routing improves.** `docs/specs/hook-lint-pipeline.md` routes `error_domain ∈ {config, runtime}` to WARN and everything else — including an absent domain — to BLOCK. A `CONFIGURATION`-categorized failure surfacing through dry-run validate (a model-deck miss, missing credentials, an unknown gateway model) used to fall through to the default block, telling the agent to edit a `.mthds` file that was not at fault; it now warns, which is what that spec's own rationale asks for. `CONTENT`-categorized ones keep blocking, as they did before. The routing rule itself is unchanged, so no spec edit was needed.

## Out of scope

- The gateway request-limit classification itself — that is [L-260831-adcf35](http://localhost:4747/i/L-260831-adcf35), in flight on `feature/Gateway-request-limits` (worktree `_two`). This plan is independent and lands on `dev`; the two compose without ordering constraints.
- Re-auditing whether each class's `error_category` is correct. The derivation faithfully translates today's classification; category fixes are their own diffs.
- `MethodRefError` ([L-260829-643af2](http://localhost:4747/i/L-260829-643af2)) and entry-lookup domains ([L-260829-fa8267](http://localhost:4747/i/L-260829-fa8267)) — same direction, separate items.
