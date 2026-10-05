"""A keyless boot knows every model a keyed boot knows, and resolves no credential.

Each test varies exactly one thing, whether credentials are present, by injecting a secrets provider
that holds no secret or one that holds every secret. So the verdicts do not depend on which keys the
developer or the CI runner happens to hold, which is the very dependency this module guards against:
a validation, which never calls a provider, used to fail on a machine without a backend's key and
pass on one with it.

The home configuration directory is moved to an empty one for every test, so the developer's own
overrides (a backend switched on or off, another routing profile) cannot change what is compared.
"""

from collections.abc import Generator
from pathlib import Path
from typing import cast

import pytest

from pipelex.base_exceptions import PipelexSetupError
from pipelex.cogt.exceptions import InferenceBackendCredentialsError
from pipelex.cogt.model_backends.backend import PipelexBackend
from pipelex.cogt.models.model_deck import ModelDeck
from pipelex.cogt.models.model_manager import ModelManager
from pipelex.pipelex import Pipelex
from pipelex.pipeline.validate_bundle import validate_bundle
from pipelex.runtime_hub import get_model_deck, get_models_manager
from pipelex.system.environment import PIPELEX_HOME_ENV_KEY
from pipelex.system.runtime import IntegrationMode, runtime_manager
from tests.helpers.recording_secrets_provider import RecordingSecretsProvider

SEARCH_PRESETS_BUNDLE = """
domain      = "keyless_search"
description = "PipeSearch through the deck's search presets and its default"

[pipe.search_with_the_standard_preset]
type        = "PipeSearch"
description = "Search with the standard preset"
inputs      = { topic = "Text" }
output      = "SearchResult"
model       = "$standard"
prompt      = "What is $topic?"

[pipe.search_with_the_deep_preset]
type        = "PipeSearch"
description = "Search with the deep preset"
inputs      = { topic = "Text" }
output      = "SearchResult"
model       = "$deep"
prompt      = "What are the main details about $topic?"

[pipe.search_with_the_default_model]
type        = "PipeSearch"
description = "Search with the deck's default model"
inputs      = { topic = "Text" }
output      = "SearchResult"
prompt      = "Who makes $topic?"
"""

BARE_HANDLE_BUNDLE = """
domain      = "keyless_bare_handle"
description = "A PipeLLM pinning a model by its bare handle"

[pipe.summarize_with_a_pinned_model]
type        = "PipeLLM"
description = "Summarize with a model named by its handle"
inputs      = { text = "Text" }
output      = "Text"
model       = "claude-4-sonnet"
prompt      = "Summarize: $text"
"""


def _test_integration_mode() -> IntegrationMode:
    """CI mode on CI runners (no terms acceptance), PYTEST locally — mirrors the global conftest boot."""
    return IntegrationMode.CI if runtime_manager.is_ci_testing else IntegrationMode.PYTEST


@pytest.fixture(scope="module", autouse=True)
def reset_pipelex_config_fixture() -> Generator[None, None, None]:
    """Override the global module fixture: this module boots and tears down per test."""
    yield
    Pipelex.teardown_if_needed()


@pytest.fixture
def pipelex_home(tmp_path: Path) -> Path:
    return tmp_path / "pipelex_home"


@pytest.fixture(autouse=True)
def empty_pipelex_home(pipelex_home: Path, monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    monkeypatch.setenv(PIPELEX_HOME_ENV_KEY, str(pipelex_home))
    Pipelex.teardown_if_needed()
    yield
    Pipelex.teardown_if_needed()


def _boot(*, needs_inference: bool, secrets_provider: RecordingSecretsProvider) -> None:
    Pipelex.make(
        integration_mode=_test_integration_mode(),
        needs_inference=needs_inference,
        secrets_provider=secrets_provider,
    )


def _model_manager() -> ModelManager:
    return cast("ModelManager", get_models_manager())


def _deck_models_with_their_constraints(model_deck: ModelDeck) -> dict[str, tuple[str, object, object]]:
    return {
        name: (spec.backend_name, sorted(spec.listed_constraints), sorted(spec.valued_constraints.items()))
        for name, spec in model_deck.inference_models.items()
    }


class TestKeylessBootModelMetadata:
    def test_a_keyless_boot_without_keys_knows_what_a_keyed_boot_with_every_key_knows(self) -> None:
        keyless_provider = RecordingSecretsProvider.make_empty()
        _boot(needs_inference=False, secrets_provider=keyless_provider)
        keyless_library = _model_manager().inference_backend_library
        keyless_backends = sorted(keyless_library.list_backend_names())
        backend_var_names = {var_name for backend in keyless_library.root.values() for var_name in backend.unresolved_credential_vars}
        keyless_models = _deck_models_with_their_constraints(get_model_deck())
        Pipelex.teardown_if_needed()

        _boot(needs_inference=True, secrets_provider=RecordingSecretsProvider.make_credentialed())
        keyed_backends = sorted(_model_manager().inference_backend_library.list_backend_names())
        keyed_models = _deck_models_with_their_constraints(get_model_deck())

        assert keyless_backends == keyed_backends
        assert keyless_models == keyed_models
        # The boot reads other secrets, telemetry's among them; none of the backends' own was asked for.
        assert backend_var_names
        assert backend_var_names.isdisjoint(keyless_provider.looked_up)

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "bundle_content",
        [
            pytest.param(SEARCH_PRESETS_BUNDLE, id="search_presets"),
            pytest.param(BARE_HANDLE_BUNDLE, id="bare_handle"),
        ],
    )
    async def test_a_keyless_boot_without_keys_validates_a_bundle_naming_keyed_models(self, tmp_path: Path, bundle_content: str) -> None:
        bundle_path = tmp_path / "bundle.mthds"
        bundle_path.write_text(bundle_content)
        _boot(needs_inference=False, secrets_provider=RecordingSecretsProvider.make_empty())

        result = await validate_bundle(mthds_file_path=bundle_path)

        assert [pipe.code for pipe in result.pipes]

    def test_a_keyless_boot_refuses_to_hand_out_a_backend_it_did_not_credential(self) -> None:
        """Reached only by a keyless process executing live work for another one, as a Temporal worker can."""
        _boot(needs_inference=False, secrets_provider=RecordingSecretsProvider.make_empty())
        models_manager = _model_manager()
        library = models_manager.inference_backend_library
        uncredentialed = [backend for backend in library.root.values() if backend.unresolved_credential_vars]
        assert uncredentialed, "the project configuration enables no backend that needs a key"
        backend = uncredentialed[0]

        with pytest.raises(InferenceBackendCredentialsError) as exc_info:
            models_manager.get_required_inference_backend(backend.name)

        assert exc_info.value.backend_name == backend.name
        assert exc_info.value.key_name in backend.unresolved_credential_vars
        for var_name in backend.unresolved_credential_vars:
            assert var_name in str(exc_info.value)
        assert "needs_inference" in str(exc_info.value)
        # The control: a backend that needs no credential is handed out as before.
        assert models_manager.get_required_inference_backend(PipelexBackend.INTERNAL).name == PipelexBackend.INTERNAL

    def test_a_boot_that_needs_inference_still_refuses_to_start_without_a_key(self) -> None:
        """R1: only the keyless boot changed; the boot that needs inference stays fail-fast."""
        with pytest.raises(PipelexSetupError, match="Could not get credentials for inference backend"):
            _boot(needs_inference=True, secrets_provider=RecordingSecretsProvider.make_empty())

    @pytest.mark.parametrize("needs_inference", [True, False])
    def test_a_routing_profile_naming_a_disabled_backend_is_refused_on_both_boots(self, pipelex_home: Path, needs_inference: bool) -> None:
        """R3: once the keyless boot keeps every enabled backend, a profile it cannot route is a configuration error there too."""
        override_path = pipelex_home / "inference" / "routing_profiles_override.toml"
        override_path.parent.mkdir(parents=True)
        override_path.write_text('active = "all_vertexai"\n')

        with pytest.raises(PipelexSetupError, match="'vertexai'.*is not enabled"):
            _boot(needs_inference=needs_inference, secrets_provider=RecordingSecretsProvider.make_credentialed())
