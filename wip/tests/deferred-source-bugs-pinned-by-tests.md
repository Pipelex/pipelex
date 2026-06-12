# Deferred: source bugs and quirks pinned by the coverage-grind tests

Outcome of the post-grind code review (2026-06-12, branch `feature/Add-tests`). The coverage grind (TODOS.md Phases C/D/E) deliberately wrote tests that pin **current** behavior — including behavior the review then judged to be wrong at the source. None of these defects were introduced by the test PR, but each pinning test turns the eventual source fix into a test-flip, so the fixes are captured here instead of being slipped into the test branch. Each item names the pinning tests so the fixer knows exactly what to update alongside the source change.

Ordered by severity.

## 1. OpenAI image moderation mapping is inverted

- **Source:** `pipelex/plugins/openai/openai_img_gen_factory.py` — `moderation_for_openai_image` returns `"low"` when `is_moderated=True` and `"auto"` when `False`.
- **Why it's wrong:** OpenAI's gpt-image `moderation` parameter semantics are `"auto"` = standard filtering, `"low"` = LESS restrictive. The field is documented as "Enable content moderation" (`docs/configuration/config-technical/cogt-config.md`), and the FAL-side AVAILABLE taxonomy maps the same flag straight to `enable_safety_checker = is_moderated` (True = more safety). So a user enabling moderation gets the least-restrictive setting — the exact inversion of intent, on a live production path.
- **Fix:** swap the mapping (`True → "auto"`, `False → "low"`), or better: make the intent explicit in the return values and docstring.
- **Pinning test to flip:** `tests/unit/pipelex/cogt/img_gen/test_img_gen_args_inference_safety.py` — the OPENAI_MODERATION parametrize rows asserting `(True, {"moderation": "low"})` / `(False, {"moderation": "auto"})`.

## 2. GCP storage `lazy_validate` accepts uri_format without a real `{hash}` placeholder

- **Source:** `pipelex/tools/storage/storage_config.py` — `StorageGcpConfig.lazy_validate` checks `"hash" not in self.uri_format` (bare substring) while its own error message promises a `{hash}` placeholder check. The S3 twin checks the literal `"{hash}"`.
- **Why it's wrong:** a uri_format like `assets/myhash/file` passes GCP validation but contains no substitution slot; `generated_content_factory.py` then does `uri_format.format(hash=..., ...)`, which renders the SAME constant URI for every stored object → silent bucket-wide overwrites. This is the exact misconfiguration `lazy_validate` exists to catch. Not just message cosmetics.
- **Fix:** align GCP on the literal `"{hash}"` check. While there: GCP's aggregated error message also lacks the `- ` line prefixes and the docs URL that S3's has — fix in the same pass.
- **Pinning test to flip:** `tests/unit/pipelex/tools/storage/test_storage_gcp_config.py::test_lazy_validate_accepts_bare_hash_substring_without_braces` (delete or invert it; its docstring documents the asymmetry).

## 3. Bundle-spec string-concept arm maps the string into `structure`

- **Source:** `pipelex/builder/bundle_spec.py` — `to_blueprint()`'s string-concept arm builds `ConceptBlueprint(description=<concept KEY>, structure=<string VALUE>)`.
- **Why it's wrong:** the blueprint consumer (`ConceptFactory.make_from_blueprint`) classifies a `str` structure as STRUCTURE_WITH_CLASSNAME and hard-fails unless the string names a registered `StuffContent` subclass — so a natural-language value like `"A short summary of a document"` raises `ConceptFactoryError` at load time, and `description=<PascalCase key>` is meaningless as a description. The blueprint layer's own bare-string handling (MTHDS TOML `Concept1 = "Definition"`) treats the string as the **description**, and `PipelexBundleBlueprint.concept` is typed `dict[str, ConceptBlueprint | str]` so a plain pass-through was available.
- **Current blast radius:** effectively dead code, because bug #4 below makes string concepts unconstructible through normal validation — but fixing #4 without fixing this arm arms the failure.
- **Fix:** map the string to the description (or pass the raw string through to the blueprint dict). Fix together with #4.
- **Pinning test to flip:** `tests/unit/pipelex/builder/test_bundle_spec_to_blueprint.py` — the string-concept exact-equality assert (`description=key, structure=value`).

## 4. `ConceptSpec.model_validate_spec` crashes on non-dict input, breaking the `ConceptSpec | str` union

- **Source:** `pipelex/builder/concept/concept_spec.py` — the `mode="before"` model validator calls `values.get(...)` without an `isinstance(values, dict)` guard.
- **Why it's wrong:** validating a plain string against the `ConceptSpec | str` union raises a bare `AttributeError` (pydantic only converts ValueError/AssertionError), so the union never falls through to `str` — a `PipelexBundleSpec` with a string concept reference cannot be constructed via normal validation at all, despite `to_blueprint()` and `rendered_pretty()` both having dedicated string arms.
- **Fix:** the same `isinstance(values, dict)` guard `ConceptBlueprint.validate_mutually_exclusive_fields` already has. Fix together with #3.
- **Test follow-ups at fix time:**
  - Add a strict xfail NOW (or at fix time, red→green) demonstrating the broken path: `@pytest.mark.xfail(raises=AttributeError, strict=True)` on a `PipelexBundleSpec.model_validate(... concept={"Summary": "..."})` — otherwise the fix lands with no signal and the `model_construct` workarounds linger.
  - Sweep the `model_construct(...)` workaround sites in `test_bundle_spec_to_blueprint.py` / `test_bundle_spec_rendered_pretty.py` back to normal construction (each site carries an explanatory comment pointing at this bug).
  - Independent of the fix: the construction-failure test (`test_bundle_blueprint_construction_failure_wrapped`) never needed `model_construct` — native-concept shadowing triggers on the concept KEY alone, so it can use a real `ConceptSpec` value under the `"Text"` key today.

## 5. Mistral `make_simple_messages` sends the system message AFTER the user message

- **Source:** `pipelex/plugins/mistral/mistral_factory.py` — appends `UserMessage` first, then `SystemMessage`, contradicting its own docstring ("a system message (if provided) and followed by a user message") and the sibling `make_simple_messages_openai_typed`, which puts system first.
- **Why it's wrong:** every Mistral chat request ships as `[user, system]`; system instructions arriving after the user turn are weighted poorly or rejected by stricter API validation.
- **Fix:** prepend the system message, matching the docstring and the OpenAI-typed sibling.
- **Pinning test to flip:** `tests/unit/pipelex/plugins/mistral/test_mistral_factory_messages.py` — the ordering test carries an explicit "pins current behavior AS-IS" docstring, so the fixer has a clear marker.

## 6. `StorageProviderConfig.storage_path` ignores `method` and raises a misleading message

- **Source:** `pipelex/tools/storage/storage_config.py` — the `storage_path` property only checks `self.local`, raising "local config is required when method is local" even when `method` is S3/GCP, and happily returns a local path under a non-local method.
- **Why it's wrong:** an operator on `method=s3` who hits a `storage_path` consumer gets an error telling them their method is local — wrong debugging direction. Unlike the neighboring `uri_format` property, there's no method dispatch.
- **Fix:** make the property method-aware (or at least make the message accurate: "local config is required to access storage_path").
- **Pinning tests to flip:** `tests/unit/pipelex/tools/storage/test_storage_provider_config.py` — the test pinning method-blindness and the one pinning the misleading message.

## 7. LocalObserver lets a payload's own `event_type` overwrite the event name

- **Source:** `pipelex/observer/local_observer.py` — `_write_to_jsonl` merges `{"event_type": event_type, **payload}`, so a payload carrying `event_type` silently replaces the lifecycle event name in the written record (the filename keeps the true event; the record lies).
- **Why it matters:** a record in `after_failing_run.jsonl` can claim any event_type, breaking event-type-based filtering for JSONL consumers. Low severity, but the safer merge order (event name wins) is a one-line flip.
- **Test follow-up regardless of fix:** the pinning test (`tests/unit/pipelex/observer/test_local_observer.py::test_payload_event_type_key_wins_over_event_name`) lacks the explicit "pins current behavior AS-IS" docstring marker the mistral test has — add the marker so a future fixer doesn't read it as a spec.

## Test-quality cleanups (no source impact, batch when convenient)

- **Pipelex-boot opt-out for pure test dirs:** many of the new pure-logic modules (tools/misc, tools/storage, plugins factories, model_deck_check, backend_credentials) pay the autouse module-scoped `Pipelex.make()` from `tests/conftest.py` without using it. Precedent exists: `tests/unit/pipelex/system/pipelex_service/conftest.py` overrides `reset_pipelex_config_fixture` with a no-op. A one-file conftest per pure directory shaves seconds off every suite run.
- **Hoist duplicated scaffolds where a shared home already exists:** the three `graph/test_graph_rendering_*.py` files rebuild the same bundle-write + `dry_run_pipeline` AsyncMock scaffold (and `graph/conftest.py` already exports shared helpers); `make_llm_spec` is copied across the three `builder/test_bundle_spec_*.py` files (builder subpackages use `test_data.py` modules for exactly this); the storage trio re-implements the S3/GCP config builders in `test_storage_provider_config.py`.
- **Minor in-file dedup:** `test_storage_s3_config.py`'s standalone braced-hash test duplicates a parametrize row; `test_storage_provider_config.py` carries the same 4-row method table twice; `test_local_observer.py`'s str/Path constructor twins could be one parametrized test; `test_model_deck_check.py` rebuilds the full ModelDeck inside every parametrized case (class-scoped fixture would do); `NESTED_TOML_CONTENT` is duplicated across two toml_sync files; `test_inputs_ops.py`'s fixture dict carries an unused `get_library_manager` key; the mistral messages tests use id()-keyed side_effect closures with asserts inside mocks where positional `side_effect=[...]` + post-hoc assertions would fail more readably.
