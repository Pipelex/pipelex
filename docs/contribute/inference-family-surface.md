---
description: Every place a new inference family, and a new backend for it, has to be wired in — and which omissions fail silently.
---

# Inference family surface

An inference family is a kind of model call — LLM completion, image generation, extraction, web search, judgment. Adding one is not one package: the family's name is spelled in several enums, its usage flows through reporting and cost, its models live in a deck, and each of those places is separate, with nothing inferring one from another. This page is the checklist, written from the judgment family's addition, and a sibling of [the registration surface](registration-surface.md) for pipe kinds.

Most of the list is enforced by the type checker: the matches over the family enums are exhaustive with no `case _`, so adding the enum value walks you to their arms. The entries marked **silent** are the ones nothing walks you to, and they are the reason this page exists.

## A new family

1. **The family's package**, `pipelex/cogt/<family>/`, mirroring `pipelex/cogt/search/`: the question/request and answer models, the setting and its model-choice union, the job, the job factory, the usage report, the worker contract (`<Family>WorkerAbstract` with one template method and one abstract hook) and the worker factory, which resolves its worker through the inference-backend registry and holds no `match` over SDK strings.

2. **The family enums, together.** `InferenceFamily` in `pipelex/plugins/inference_backend_registry.py`, `ModelType` in `pipelex/cogt/model_backends/model_type.py`, `InferenceErrorFamily` in `pipelex/cogt/inference/error_render.py` with an entry in both its failure-class and not-found-class tables, and `ModelCategory` in `pipelex/builder/operations/models_ops.py`, which is what `pipelex-agent models` and `check-model` list from.

3. **The error classes** in `pipelex/cogt/exceptions.py`: a job failure, a model-not-found (subclassing `ModelNotFoundError`) and a handle-not-found. Then regenerate the error pages and the identity snapshot (`make gep`, `make gei`); the snapshot test fails until you do.

4. **The job identity** in `pipelex/system/job_metadata.py`: a `JobCategory` member, a `UnitJobId` member and its display arm.

5. **The deck.** A `<Family>DeckBlueprint`, its flat fields on `ModelDeck`, the setting getter, the preset validator, the choice check, the suggestion arms, and the model manager's handle collection and flattening. The kit deck is `pipelex/kit/configs/inference/deck/<n>_<family>_deck.toml` — the numeric prefix is what makes `pipelex update` manage it — mirrored into the repository's own `.pipelex/inference/deck/`.

6. **Reporting and cost.** The usage and cost-report classes join both unions in `pipelex/reporting/reporting_types.py`, `ReportingManager` gets its dispatch arm, and `CostRegistry.compute_cost_report` gets an arm in its `match`, which closes with `assert_never` so a family that falls through fails the type check. Update the `model_type` comment on `ModelUsageSpec` in `pipelex/graph/graphspec.py` to say how the family is billed.

7. **The content-generation leaf.** An assignment model in `pipelex/cogt/content_generation/assignment_models.py`, a `<family>_generate.py` module whose coroutine opens with the dry branch, the dry mock in `dry_mock.py`, and the method on `ContentGeneratorProtocol` with its `@override` in `ContentGenerator`. A host runtime's durable execution needs an activity and a queue for the new leaf in its own plugin.

8. **Test infrastructure.** A pytest marker in `pyproject.toml` and its term in the default deselect expression; the family in every table of `pipelex/cli/dev_cli/commands/preprocess_test_models_cmd.py`; a `<family>_models` key on every profile in `.pipelex-dev/test_profiles.toml`; a combo getter in `tests/integration/pipelex/fixtures/model_selection.py`, a combo fixture in `combo_fixtures.py` and its re-export in `tests/integration/pipelex/conftest.py`.

9. **The migration golden.** A new `ModelType` value changes the inference-backend surface's fingerprint; `make umig` records it, and the real-surfaces test fails until you do.

10. **Silent: fakes that stand in for the deck.** Any test double that impersonates `ModelDeck` by attribute — the fake deck in `tests/unit/pipelex/cli/test_agent_models_cmd.py` is one — needs the new family's presets, aliases and waterfalls, or every case using it fails with an `AttributeError` far from the cause.

11. **Silent: the MTHDS protocol's model categories.** `PipelexMTHDSProtocol.models()` in `pipelex/pipeline/runner.py` types each preset by the protocol's own `ModelCategory`. A family the protocol cannot name is skipped there rather than raised on; the protocol has to learn the member before the family's presets are visible through it.

12. **Silent: a default the gateway does not serve fails every boot.** The model manager checks, at boot, every handle a deck's presets and choice defaults name against the Pipelex Gateway's specs when the active routing profile sends that handle there. A family whose models only a bring-your-own-key backend serves must therefore ship **no** `choice_default` and **no** preset in the kit deck — an alias is fine, because aliases are not walked. Getting this wrong fails the boot of every installation, whether or not it ever uses the family.

## A new backend for a family

1. **The provider package**, `pipelex/providers/<vendor>/`: the plugin, the worker, the translation to and from the vendor's vocabulary, and a `<vendor>_exceptions.py`. The vendor's own limits are enforced in the translation, not in a blueprint.

2. **Error classification.** An `extract_<vendor>_metadata` function and a `ProviderName` member in `pipelex/cogt/inference/`, with the member added to every exhaustive match over `ProviderName` and to the parity test in `tests/unit/pipelex/cogt/inference/test_provider_classification_parity.py`. When the vendor's status codes cannot separate its failures, the worker branches on the body before handing the rest to the shared classifier.

3. **Registration.** The plugin joins `KERNEL_BUILTIN_PLUGINS` in `pipelex/providers/builtins.py`. Its `make_worker` closure calls `require_sdk` before importing the worker, and imports no SDK at module level. Record the `register` method's subject grant before `make agent-check`, whose keyword-only fixer would otherwise rewrite it into a signature the plugin protocol refuses.

4. **Configuration.** The backend's table in the kit's `backends.toml`, its model file under `backends/`, and an `all_<vendor>` routing profile — which is also what the integration combo fixtures route to — all mirrored into `.pipelex/inference/`. Its API key variable goes in `.env.example`.

5. **Silent: the default routing profile.** Under `all_pipelex_gateway` every handle routes to the gateway by default, and a handle the gateway does not serve is silently dropped from the deck — so a user who has the vendor's key still cannot use its models. Give the managed profiles an `optional_routes` entry sending the vendor's models to its backend; an optional route applies only while that backend is enabled.

6. **Silent: the CI placeholder list.** CI runners hold no provider keys, and every test module boots live, so each variable an enabled kit backend references must be in `ENV_VAR_KEYS_WHICH_MAY_NEED_PLACEHOLDERS_IN_CI` in `pipelex/test_extras/shared_pytest_plugins.py`. `tests/unit/pipelex/test_extras/test_ci_placeholder_keys.py` now fails when one is missing.

7. **Plugin surface tests.** The `(family, sdk)` pair in `tests/unit/pipelex/plugins/test_inference_backend_coverage.py`, a missing-extra guard test mirroring Linkup's, the SDK's import name in the blocked list of `tests/unit/pipelex/plugins/test_import_light_boot.py`, and an arm in `tests/integration/pipelex/system/test_keyless_boot_forced_dry.py` showing that a keyless boot does not need the key.

8. **Live tests** under a test profile of their own, marked with the family's marker and `inference`, so that `make ti PROF=<profile>` runs them and every other profile skips them.
