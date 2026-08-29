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
- `RemoteConfigFetcher._build_unavailable_error` (`pipelex/system/pipelex_service/remote_config_fetcher.py:196-204`) reports "Pipelex Gateway is enabled but the remote configuration is unreachable" and recommends disabling `pipelex_gateway` — reachable on a manifold-only machine whose first offline dry-run finds no cache, where the backend it names is already off.

This is the same family as the backend attribution the pull request added to `GatewayUnknownModelError`: a message that assumes there is one managed service. It was left out of that change deliberately, as a coherent wording sweep rather than something bundled into a correctness fix, and because the naming a second dialect deserves in user-facing copy is a product decision rather than a mechanical rename.

## D3 — the search worker indexes source dicts raw

`ManifoldSearchWorker._search_sourced_answer` (`pipelex/providers/manifold/manifold_search_worker.py:82-93`) checks `answer` carefully — `isinstance(answer, str)`, then a `ManifoldSearchResponseError` carrying a category and a user action — and then builds `sources` by indexing each entry directly: `source["name"]`, `source["url"]`, `source["snippet"]`, after a `cast` that asserts a shape nothing verified. A `sources` list carrying an entry that is not an object, or an object missing one of those three keys, raises a bare `KeyError` or `TypeError`.

That is precisely the failure mode `ManifoldNativeClient`'s own docstring names as the thing to avoid (`pipelex/providers/manifold/manifold_native_client.py:88-92`): an exception that is neither a `PipelexError` nor annotated with the model escapes the Temporal error bridge and is retried against a search that has already been paid for.

**Two corrections to keep in view.** This is not new and it is not manifold-specific: `GatewaySearchWorker._search_sourced_answer` (`pipelex/providers/gateway/gateway_search_worker.py:86-95`) does the identical thing, and additionally reads `result_dict["answer"]` unguarded where the manifold worker guards it. So the manifold path is strictly the better of the two, and a fix belongs to both or to a shared helper — which is also why it was not bundled into a pull request whose whole shape is "the manifold package imports nothing from the gateway one".

**Why it waited.** It needs a malformed response from our own service to fire, the pull request already raised the bar for the response fields it touched, and the honest fix is a sweep across both workers rather than a patch to the new one — which would leave the shipped path worse than the beta path.

**What the fix looks like.** A `ManifoldSearchSource` pydantic model beside the request schemas in `manifold_schemas.py`, validated per entry, with a malformed entry raising `ManifoldSearchResponseError` the way a missing `answer` already does. The gateway worker gets the same treatment against its own exception class when the sweep happens.

## D4 — init decides managed-ness by name, the boot by declaration

The boot's question is structural: a backend is a managed gateway backend when it declares a `model_specs_section` (`pipelex/cogt/model_backends/backend.py:52-68`, `resolve_model_specs_section`; the field is `InferenceBackendBlueprint.model_specs_section`, `pipelex/cogt/model_backends/backend_factory.py:19`, read off the raw `backends.toml` table with no allow-list on the name). `enabled_managed_gateway_sections` (`pipelex/system/pipelex_service/pipelex_service_config.py:78`) answers it, and both the boot's terms gate and `pipelex init agreement` (`_init_agreement`) ask it. The other init sites ask by name instead, through `MANAGED_GATEWAY_BACKEND_NAMES` (`backend.py:49`): `_check_gateway_terms_if_needed` (`pipelex/cli/commands/init/command.py:168`), `customize_backends_config`'s prompt and decline-removal (`pipelex/cli/commands/init/backends.py:152,163`), `disable_managed_gateway_backends` (`backends.py:92`), and the agent flow's `accept_gateway_terms` handling (`pipelex/cli/agent_cli/commands/init_cmd.py:221`).

The consequence, for a backend that declares a section under a name the constant does not list: the boot puts the installation behind the terms, `pipelex init agreement` prompts for them, but declining leaves that backend enabled — `disable_managed_gateway_backends` iterates the constant, so its own docstring's promise, *"has to leave no managed backend enabled"*, is not kept — and the next inference boot refuses with `GatewayTermsNotAcceptedError`. `pipelex init config` and `pipelex-agent init` prompt for nothing on such an installation while still marking inference setup complete.

A second, name-independent mismatch sits on the same lines: `get_selected_backend_keys` (`backends.py:70`) counts a backend as enabled only on a literal `enabled = true`, defaulting to disabled when the key is absent, whereas the boot reads truthiness with default-enabled (`pipelex_service_config.py:106`, and the loader it mirrors). A `[pipelex_manifold]` table with `enabled = 1`, or with no `enabled` key, is live to the boot and invisible to the init terms prompt even though its name is in the constant.

**What the reporting bot got wrong.** It said init "provides no way to accept" the terms for such a backend. `pipelex init agreement` is that way, and it asks the boot's question — pinned by `tests/unit/pipelex/cli/commands/test_init_agreement_any_managed_gateway.py`. The gap is in the disable-after-refusal path and in the two flows that prompt during setup, not in acceptance.

**Why it waited.** No product path declares a third section: the published configuration carries two, and a future one lands in this repository together with the constant. The kit template always writes literal booleans, so the truthiness mismatch bites only a hand-edited file. And the constant was the deliberate shape of the round-1 fix for callers that hold only backend names — the picker's selection, the agent request's `backends` list — so replacing it is a design change rather than a repair.

**What the fix looks like.** A helper in `init/backends.py` that derives the managed backend names from the tomlkit document the init code already holds, by applying `resolve_model_specs_section` to each table, so the four sites ask the boot's question over the same file and the constant retires from init. `get_selected_backend_keys` reads `enabled` the loader's way. The trap: make the code match `disable_managed_gateway_backends`'s docstring, not the reverse.

## Declined

### `ManifoldCompletionsFactory.make_simple_messages` duplicates the OpenAI message builder

Verified and declined. The override (`pipelex/providers/manifold/manifold_completions_factory.py:47-104`) re-states the base class's system-text, user-text and image handling to change seven lines of document encoding, and `OpenAICompletionsFactory` exposes no narrower seam for it. But it is byte-identical to `GatewayCompletionsFactory`'s override save for three comments, `PortkeyCompletionsFactory` carries a third copy on `dev`, and the module docstring (lines 3-14) records why subclassing the gateway factory was rejected: inheriting the Portkey extract parsing and header build would make retiring that package an untangling rather than a deletion. `tests/unit/pipelex/providers/manifold/test_manifold_completions_messages.py:148-178` is an explicit drift guard asserting the manifold and gateway overrides produce equal messages. A `_make_document_part` hook in `OpenAICompletionsFactory` that the three subclasses override would collapse the copies; it is a cleanup across `openai/`, `gateway/`, `portkey/` and `manifold/`, and the moment for it is the Portkey path's retirement, when two of the three copies disappear anyway.
