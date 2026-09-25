# Two inference-provider bugs found while surveying per-request API keys

Found on 2026-08-18 while surveying the SDK credential paths for `feature/API-key-per-request` (see `wip/api_keys/sdk-per-request-key-survey.md`). Neither is in that feature's scope, so they are filed here instead. **Both are recorded from the survey only — whoever fixes them still has to do the research.** In particular, no fix has been designed, no test has been written, and the blast radius of each has not been mapped beyond what is stated below.

## Bug 1 — the Google structured-output path silently discards its whole generation config

**What we observed.** `GoogleLLMWorker._gen_object` (`pipelex/providers/google/google_llm_worker.py:255-274`) builds a `genai_types.GenerateContentConfig` carrying `system_instruction`, `temperature`, `max_output_tokens` and `candidate_count`, then hands it to instructor as the `generation_config=` kwarg on `create_with_completion`.

Instructor's genai adapter (`instructor/providers/gemini/utils.py`, `update_genai_kwargs`, around line 275) pops that value and then tests each field with `if openai_key in generation_config`. Our value is a **pydantic object**, not a dict. Pydantic's `BaseModel.__iter__` yields `(key, value)` tuples, so `"temperature" in some_config` compares a string against tuples and is never true. Every field is skipped, and the adapter goes on to build `types.GenerateContentConfig(**generation_config)` from its own `base_config` alone.

**Verified by execution** against the pinned versions (`google-genai` 1.75.0, `instructor` 1.15.1):

```python
from google.genai import types as t
from instructor.providers.gemini.utils import update_genai_kwargs

cfg = t.GenerateContentConfig(temperature=0.3, max_output_tokens=999, system_instruction="SYS")
print('temperature' in cfg)        # -> False
out = update_genai_kwargs({"generation_config": cfg}, {"response_mime_type": "application/json"})
print(list(out.keys()))            # -> ['response_mime_type', 'safety_settings']
```

**Impact.** Every structured Gemini generation runs at Google's default temperature, with no max-token cap, and with no system instruction. The non-structured path is unaffected — `_gen_text` calls `generate_content(config=…)` on the client directly (`google_llm_worker.py:217`) and does not go through instructor.

**Notes for whoever fixes it.** Passing a plain dict instead of the pydantic object would recover the whitelisted fields (`max_tokens`, `temperature`, `n`, `top_p`, `stop`, `seed`, `presence_penalty`, `frequency_penalty` — mapped via `OPENAI_TO_GEMINI_MAP`), but `system_instruction` is set by instructor itself from the message list, and anything outside the whitelist — including `http_options` — is dropped either way. So a dict is a partial recovery, not a full one; bypassing instructor's kwarg mapping, or fixing it upstream, may be the real answer. Worth checking whether the other instructor-wrapped workers (openai, anthropic, mistral) have an analogous silent-drop, since they were not examined for this.

**Why the API-key survey cares.** This is also the reason the Google structured path has no per-request key seam: `http_options` cannot be threaded through instructor's mapping, so a per-request Gemini key needs a per-credential `genai.Client` and therefore a per-credential `from_genai` wrapper.

## Bug 2 — the Vertex AI access token is minted once at boot and never refreshed

**What we observed.** `InferenceBackendFactory.make_inference_backend` has a special case for the `vertexai` backend that calls `VertexAIFactory.make_endpoint_and_api_key(extra_config=…)` (`pipelex/cogt/model_backends/backend_factory.py`). That in turn calls `_make_api_key(...)` (`pipelex/providers/openai/vertexai_factory.py:42`), which loads a GCP service-account credentials file and mints an **OAuth access token**, returning it as the backend's `api_key`.

That string is then frozen onto `InferenceBackend.api_key` for the life of the process, and baked into the cached `openai.AsyncOpenAI` client at first use.

**Impact.** GCP OAuth access tokens are short-lived (on the order of an hour). Any process that outlives the token — every server, every Temporal worker, any long-running CLI session — will start failing Vertex calls with 401s, with no path to recovery short of a restart. Short-lived processes (a one-shot CLI run) never see it, which is presumably why it has not surfaced.

**Notes for whoever fixes it.** The credential is structurally a *refreshable* token, not a static API key, so the fix is a resolution seam rather than a longer expiry — `google.auth`'s `Credentials` object knows how to refresh itself, and the current code throws that object away after reading `.token` once. This overlaps directly with the per-request-key work: a design that resolves the credential at request time rather than at boot fixes this as a side effect. Not verified: the exact token lifetime in our GCP configuration, and whether any deployed environment actually has the `vertexai` backend enabled today.
