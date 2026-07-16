# LLM `max_tokens` model fallback in `_apply_constraints` is (almost) dead code

**Status:** Deferred design tradeoff (not a regression — pre-existing on `main`, moved byte-equivalently by the plugins refactor). Flagged by cubic on PR #1020.

## Current behavior

`LLMWorkerAbstract._apply_constraints` (`pipelex/cogt/llm/llm_worker_abstract.py`; previously identical in `llm_worker_internal_abstract.py` on `main`) computes a max-tokens fallback but only ships it when a *temperature* rule fires:

```python
max_tokens = original_params.max_tokens or self.inference_model.max_tokens
new_max_tokens = max_tokens
has_changes = False
# ... only temperature constraints set has_changes = True ...
if not has_changes:
    return None  # applied_job_params stays None → workers use the original params
return original_params.model_copy(update={"temperature": new_temperature, "max_tokens": new_max_tokens})
```

Every worker consumes `llm_job.applied_job_params or llm_job.job_params`, then sends `job_params.max_tokens or omit`. So when a job omits `max_tokens`:

- **No temperature constraint on the model** → no cap is sent; the provider default applies.
- **A temperature constraint fires** → the model's `max_tokens` from the spec IS sent as the request cap.

The cap a provider receives depends on an unrelated temperature rule — an inconsistency, though each individual outcome is defensible.

## Options

1. **Mark the fallback as a change** (cubic's suggestion: `has_changes = new_max_tokens != original_params.max_tokens`): the model spec's `max_tokens` is always sent explicitly when the job omits it. Consistent, "model constraints actually enforced" — but changes wire behavior for every provider/backend on every capless request.
2. **Remove the fallback**: `new_max_tokens = original_params.max_tokens` unchanged; when a temperature rule fires, the applied params keep the job's own (possibly absent) cap. Provider default semantics become uniform — also a wire behavior change, in the opposite direction, limited to constraint-firing models.
3. **Status quo**: keep the inconsistency documented here.

## Decision needed

Pick 1 or 2 in a normal dev cycle (not a release branch) with a targeted live-inference sanity pass, since either option changes what gets sent on the wire. Whichever way it goes, add a unit test on `_apply_constraints` pinning the chosen `max_tokens` semantics.
