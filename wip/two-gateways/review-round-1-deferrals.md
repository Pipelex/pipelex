---
status: active
item: L-260825-577e2d
---

# Two managed gateways — review deferrals

Items surfaced by the automated review of the pull request that introduced the manifold dialect, verified against the code and deliberately not fixed in that pull request. Each one records what is actually wrong, what the reporting bot got wrong about it, and why it waited — so the session that picks it up does not have to re-derive any of it.

## D1 — `preprocess_test_models_cmd` reads a managed backend's TOML as a catalog

`_fetch_managed_gateway_models()` omits a backend's key entirely when its remote section is absent (`pipelex/cli/dev_cli/commands/preprocess_test_models_cmd.py:139-144`, a bare `continue`), so `managed_backends` is keyed by **fetch outcome** rather than by configuration. The membership test at `:179-180` then lets that backend fall through to `_extract_models_from_backend_toml` and emits its per-backend TOML as a model catalog.

That is the wrong predicate, and for a reason deeper than the report gives: for a managed backend the per-backend TOML is **never** a catalog. `pipelex/cogt/model_backends/backend_library.py:499-506` feeds that same file to `GatewayConfigMerger.merge` as *overrides* on top of the remote specs, keeping only `sdk` and `structure_method`. Reading it with `_group_handles_by_model_type` is a category error regardless of whether the backend is enabled.

Two corrections to the report, both worth carrying forward:

- **The trigger it names is unreachable for `pipelex_gateway`.** `backend_model_specs` is a required declared field on `RemoteConfig` (`pipelex/system/pipelex_service/remote_config.py:29`), so any fetch that validated carries it and the section lookup can never return `None` for the legacy gateway. The absent-section branch is reachable only for a section arriving through `extra="allow"`, which today means the manifold one.
- **The regression the pull request actually introduced is a different one.** The version before it was an unconditional `if backend_name == "pipelex_gateway": continue`; the change made that conditional on the fetch outcome. So a user who *disables* the gateway — a product-supported state, `disable_managed_gateway_backends()` in `pipelex/cli/commands/init/backends.py` — now gets `pipelex_gateway.toml` read as a catalog. Note that the fix the bot proposes would not restore this, because `enabled_managed_gateway_sections` excludes disabled backends by design.

**Why it waited.** This is a development-only fixture generator with no shipped runtime behind it. Both managed backend TOML files are comment-only today, so `_extract_models_from_backend_toml` returns empty lists for both and the emit site guards on non-empty — nothing is produced. `_generated_model_sets.py` is gitignored and `.pipelex-dev/model_availability.json` is not committed, so no artifact exhibits the bad pairing. When it does fire, the failure mode is a loud red integration test rather than a silent false pass. Decisively, the one-line fix closes only the latent absent-section half; the disabled-gateway half needs a different predicate, and fixing half a latent trap was not worth another lap of the pull request.

**What the fix looks like.** In `_fetch_managed_gateway_models`, keep the key and let the value be empty rather than skipping the backend, so membership means "this backend's TOML is an override file" rather than "the fetch produced something". Then decide separately whether a *disabled* managed backend should also be excluded from local discovery — that is the second predicate question, and this command ignores `enabled` uniformly for every ordinary backend, so changing it is a deliberate choice rather than an obvious repair.

**One trap for whoever takes it.** `tests/unit/pipelex/cli/dev/test_preprocess_test_models_cmd.py:72` currently pins the present shape, asserting that a backend whose section is absent is excluded from the returned mapping. That assertion has to be flipped, not added beside.

## D2 — managed-backend-blind user-facing strings

Several user-facing strings still name the Portkey-cloud service specifically, on paths that now serve either managed backend:

- `pipelex/cli/commands/doctor_cmd.py:1092-1094` gates on `enabled_managed_gateway_sections()` but reports the hardcoded "Pipelex Gateway is enabled but terms have not been accepted", which is wrong on a manifold-only machine.
- The terms panel itself asks about "the Pipelex Gateway terms of service" wherever it is raised, including now for a manifold-only selection.
- `AGENT_ERROR_HINTS["GatewayTermsNotAcceptedError"]` (`pipelex/cli/agent_cli/commands/agent_output.py:134`) recommends `pipelex init config` to accept the terms and suggests disabling `pipelex_gateway` — the first does not prompt, and the second is already off in the case that produces the error.

This is the same family as the backend attribution the pull request added to `GatewayUnknownModelError`: a message that assumes there is one managed service. It was left out of that change deliberately, as a coherent wording sweep rather than something bundled into a correctness fix, and because the naming a second dialect deserves in user-facing copy is a product decision rather than a mechanical rename.

## D3 — the search worker indexes source dicts raw

`ManifoldSearchWorker._search_sourced_answer` (`pipelex/providers/manifold/manifold_search_worker.py:82-93`) checks `answer` carefully — `isinstance(answer, str)`, then a `ManifoldSearchResponseError` carrying a category and a user action — and then builds `sources` by indexing each entry directly: `source["name"]`, `source["url"]`, `source["snippet"]`, after a `cast` that asserts a shape nothing verified. A `sources` list carrying an entry that is not an object, or an object missing one of those three keys, raises a bare `KeyError` or `TypeError`.

That is precisely the failure mode `ManifoldNativeClient`'s own docstring names as the thing to avoid (`pipelex/providers/manifold/manifold_native_client.py:88-92`): an exception that is neither a `PipelexError` nor annotated with the model escapes the Temporal error bridge and is retried against a search that has already been paid for.

**Two corrections to keep in view.** This is not new and it is not manifold-specific: `GatewaySearchWorker._search_sourced_answer` (`pipelex/providers/gateway/gateway_search_worker.py:86-95`) does the identical thing, and additionally reads `result_dict["answer"]` unguarded where the manifold worker guards it. So the manifold path is strictly the better of the two, and a fix belongs to both or to a shared helper — which is also why it was not bundled into a pull request whose whole shape is "the manifold package imports nothing from the gateway one".

**Why it waited.** It needs a malformed response from our own service to fire, the pull request already raised the bar for the response fields it touched, and the honest fix is a sweep across both workers rather than a patch to the new one — which would leave the shipped path worse than the beta path.

**What the fix looks like.** A `ManifoldSearchSource` pydantic model beside the request schemas in `manifold_schemas.py`, validated per entry, with a malformed entry raising `ManifoldSearchResponseError` the way a missing `answer` already does. The gateway worker gets the same treatment against its own exception class when the sweep happens.
