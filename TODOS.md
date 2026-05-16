# TODO — Fix: inference errors reach `ErrorReport` with `model` / `provider` = `None`

> **Branch:** work on `fix/error-report-model-provider` (already created off `feature/Error-handling-2`).
> **Scope:** one focused change — one mechanism, applied across the four inference-worker families. Not a multi-phase plan.
> **Discipline:** RED (failing test) → GREEN (minimal fix) → REFACTOR. `make agent-check` after each step; `make agent-test` before wrapping up.

---

## ▶ Start here — cold-start context

The error-handling Phase-2 work (archived at [wip/error-handling/archive-error-handling-2.md](wip/error-handling/archive-error-handling-2.md)) built a structured `ErrorReport` that flows from a failing inference worker all the way to the CLI / HTTP boundary. Two of its fields — `model` and `provider` — are **never populated for a real production failure**. This TODO is the follow-up the Phase 8 archive notes flagged as "a separate, smaller follow-up" and that the LLM-retry-loop fix ([wip/error-handling/todos-llm-retry-loop-bypass.md](wip/error-handling/todos-llm-retry-loop-bypass.md)) listed as out of scope.

**The bug.** `CogtError.to_error_report()` (`pipelex/cogt/exceptions.py`, ~lines 60-72) builds the `ErrorReport` with:

```python
model=getattr(self, "model_handle", None),
provider=getattr(self, "backend_name", None),
```

It **duck-types** — it reads whatever `model_handle` / `backend_name` attributes happen to be set on the exception. The inference-*failure* errors (`LLMCompletionError`, `ImgGenGenerationError`, `ExtractJobFailureError`, `SearchJobFailureError`, `ExtractOutputError`) are plain `CogtError` subclasses with no `__init__` — they set neither attribute. So in production, every LLM / img-gen / extract / search failure produces an `ErrorReport` with `model = None` and `provider = None`. An agent or an HTTP consumer gets a transient failure it cannot attribute to a model or a provider.

**Why no existing test catches it.** The Phase 8 full-chain test `tests/integration/pipelex/cli/agent_cli/test_run_error_chain.py` (lines ~52-56) papers over it: it constructs the error and then **manually `setattr`s** the two attributes —

```python
transient_error = LLMCompletionError(WORKER_ERROR_MESSAGE, error_category=InferenceErrorCategory.TRANSIENT)
setattr(transient_error, "model_handle", WORKER_MODEL)   # noqa: B010
setattr(transient_error, "backend_name", WORKER_PROVIDER)  # noqa: B010
```

— with a comment that these are "the duck-typed attributes `CogtError.to_error_report()` reads via `getattr`". The test then asserts `model` / `provider` survive the wrapping chain (lines ~92-93). It passes, but only because the test itself does what production never does. The `# noqa: B010` is the smell.

---

## Verified facts (checked against the code)

**`to_error_report()` and the error classes** — `pipelex/cogt/exceptions.py`:

- `CogtError.error_category` is declared as a class attribute (~line 40, `error_category: InferenceErrorCategory | None = None`). `model_handle` / `backend_name` are **not** declared anywhere on `CogtError`.
- `to_error_report()` reads them via `getattr(self, ..., None)` (~lines 68-69).
- The inference-failure leaf classes carry no `__init__`: `LLMCompletionError` (~line 248), `ImgGenGenerationError` (~line 292), `ExtractJobFailureError` (~line 304), `SearchJobFailureError` (~line 308), `ExtractOutputError` (~line 232).
- The **precedent** — several `CogtError` subclasses already carry `model_handle` as a real `__init__` param and set `self.model_handle`: `ModelNotFoundError`, `ModelWaterfallError`, `LLMHandleNotFoundError`, `ImgGenHandleNotFoundError`, `ExtractHandleNotFoundError`, `SearchHandleNotFoundError`, `ModelDeckPresetValidatonError`. `InferenceBackendCredentialsError` carries `backend_name` the same way. These already produce a populated `ErrorReport` and are **not in scope** — leave them.

**Raise sites are scattered.** `LLMCompletionError` is constructed in ~70 places across `pipelex/plugins/{anthropic,openai,mistral,google,bedrock}/...` plus the shared `pipelex/plugins/openai/openai_error_classification.py`. `ImgGenGenerationError` / `ExtractJobFailureError` / `SearchJobFailureError` are scattered similarly across the img-gen / extract / search workers. There is no single global construction chokepoint — each provider has its own `_classify_*` / `_raise_categorized_*` method with many `raise` points.

**But every worker has the model + provider in scope.** Each worker holds `self.inference_model` (an `InferenceModelSpec`) with `.name` (the model handle) and `.backend_name` (the provider). So model + provider are available at *every* raise site already — they are just never threaded onto the error.

- LLM: `inference_model` lives on `LLMWorkerInternalAbstract` (`pipelex/cogt/llm/llm_worker_internal_abstract.py`, set ~line 32). The **public** entry points `gen_text` / `gen_object` live one level up on `LLMWorkerAbstract` (`pipelex/cogt/llm/llm_worker_abstract.py`) and **already wrap** the call to the abstract `_gen_text` / `_gen_object` in a `try` / `except` (currently `except Exception`, re-raises after ending the OTel span). `LLMWorkerAbstract` does not see `inference_model`, but it exposes `_get_request_model_name()` → `inference_model.name` and `_get_provider_name()` → `inference_model.backend_name` (overridden in `LLMWorkerInternalAbstract`, ~lines 58-66). The base `_get_provider_name()` default returns the literal `"unknown"` for external plugins that don't override it.
- Img-gen / extract / search: `ImgGenWorkerAbstract`, `ExtractWorkerAbstract`, `SearchWorkerAbstract` each hold `self.inference_model` **directly on the abstract** and expose public methods (`gen_image` / `gen_image_list`, `extract_pages`, `search_sourced_answer` / `search_structured`). Unlike the LLM abstract, these do **not** currently wrap their abstract impl call in a `try` / `except` — a small one would need to be added.

**`provider` is partially recoverable already.** `ProviderErrorMetadata.provider` (in `pipelex/cogt/inference/error_classification.py`) is a required field, and every `extract_*_metadata()` helper hardcodes the provider name. So for any error that carries `provider_metadata`, the provider is already reachable via `error.provider_metadata.provider`. It is **not** reachable for errors built without metadata (e.g. response-shape validation failures, which the worker-classification track documents as carrying `provider_metadata=None`), and `model` is never carried anywhere.

---

## The open design decision (settle this first)

Pick how `model_handle` / `backend_name` get onto the error before writing code:

- **Option A — per-raise-site constructor params.** Add `model_handle` / `backend_name` as optional `__init__` params on the inference-failure leaf classes (or on `CogtError` itself) and pass them at every `raise` site (~70 for LLM alone, plus img-gen / extract / search). Honest and explicit, but high churn, and every *new* raise site must remember to pass them or silently regress.

- **Option B — centralized enrichment at the worker base class (recommended).**
  1. Declare `model_handle: str | None = None` and `backend_name: str | None = None` as class attributes on `CogtError`, mirroring how `error_category` is declared. Change `to_error_report()` to read `self.model_handle` / `self.backend_name` directly — drop the `getattr`. (The existing subclasses that set `self.model_handle` in `__init__` keep working unchanged — same attribute name.)
  2. At each worker family's public-method chokepoint, catch `CogtError`, and if `model_handle` / `backend_name` are still unset, fill them from the worker — LLM via `self._get_request_model_name()` / `self._get_provider_name()`; img-gen / extract / search via `self.inference_model.name` / `.backend_name` — then re-raise. ~8 enrichment points instead of ~70 raise sites; new raise sites are covered automatically; the worker layer is where model + provider are unambiguously known.

  **Recommendation: Option B.** Notes for the implementer:
  - The enrichment must catch `CogtError` *specifically*. The existing LLM `gen_text` / `gen_object` handler is `except Exception` (it ends the OTel span, then `raise`). Do **not** widen anything and do **not** add a new `except Exception` — add a dedicated `except CogtError` clause, or do the fill inside the existing handler guarded by `isinstance(exc, CogtError)`. Per the project error-handling rules, `except Exception` is forbidden outside a CLI/endpoint root.
  - Only fill when the value is `None` — never overwrite a `model_handle` an inner error already set (e.g. `LLMModelNotFoundError`).
  - Skip filling `backend_name` when `_get_provider_name()` returns the `"unknown"` default, so reports for external plugins don't carry a literal `"unknown"` provider.
  - Img-gen / extract / search need a small `try` / `except CogtError` added around the abstract-impl call in their public methods — see the LLM abstract for the shape.

Record the decision in the commit message / a short note here. Whatever the choice, **apply it consistently** to all four worker families (LLM, img-gen, extract, search).

---

## RED

- [ ] Write a worker-level test for one LLM provider (Anthropic or OpenAI-completions are good picks — both have a clear SDK try/except). Mock the provider SDK call to raise a recognized SDK exception; call the worker's `gen_text` (and/or `gen_object`); catch the resulting `LLMCompletionError`; assert `exc.to_error_report().model` equals the worker's model handle and `.provider` equals its backend name. This fails today: both come back `None`. Check for an existing worker error-classification unit test under `tests/unit/pipelex/plugins/` (or `tests/unit/pipelex/cogt/`) to extend rather than starting fresh.
- [ ] Cover the img-gen, extract, and search families too (one provider each is enough; parametrize where cheap).

## GREEN

- [ ] Apply the chosen option (recommended: B) so a `CogtError` from any inference worker reaches `to_error_report()` with `model_handle` / `backend_name` populated. Minimal change to make the RED tests pass.
- [ ] Run `make agent-check`.

## REFACTOR

- [ ] Confirm all four worker families (LLM, img-gen, extract, search) enrich at their chokepoint — sweep, don't stop at LLM.
- [ ] Clean up `tests/integration/pipelex/cli/agent_cli/test_run_error_chain.py`: with `model_handle` / `backend_name` now declared on `CogtError`, replace the `setattr(...)  # noqa: B010` workaround with plain typed attribute assignment. (Or, better, re-point that test so the failure is injected at the SDK boundary inside a real worker instead of mocking `ContentGenerator.make_llm_text` — then it needs no manual set at all. Optional, larger.)
- [ ] Run `make agent-test`. Run the worker error-classification unit tests and the Phase 8 full-chain test.
- [ ] Update the CHANGELOG (`### Fixed`) — inference-failure `ErrorReport`s now carry `model` / `provider` in production.
- [ ] Flip the relevant note in [wip/error-handling/README.md](wip/error-handling/README.md) (metadata-model / worker-classification track) — the "model/provider come back `None` in production" gap is closed.
- [ ] Archive this `TODOS.md` into `wip/error-handling/` (e.g. `todos-error-report-model-provider.md`).

---

## Out of scope

- `CogtError` subclasses that already carry `model_handle` / `backend_name` via their own `__init__` (`ModelNotFoundError`, `LLMHandleNotFoundError`, `InferenceBackendCredentialsError`, etc.) — these already produce populated reports. Don't touch them; just make sure the enrichment never overwrites a value they already set.
- Non-inference error paths still keyed by string dicts in `agent_output.py` — a separate track noted in [wip/error-handling/README.md](wip/error-handling/README.md). Not this task.
- External LLM plugins that don't override `_get_provider_name()` (it returns `"unknown"`) — the enrichment simply skips them; surfacing a real provider for third-party plugins is their plugin's responsibility, not a regression here.
