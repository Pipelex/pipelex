"""A managed gateway backend missing its `${…}` variables is disabled; every other backend still stops the boot.

The kit ships `[pipelex_manifold]` declared and enabled, so joining the beta is setting two variables
rather than editing a config file. That only works if an installation that has *not* joined boots
normally, which is why a managed gateway backend whose variables are unset is disabled with a warning
naming it.

**The scoping is the point of these tests, not a detail.** The tolerance sits on a code path every
backend shares, so a global version of it would mean a user who typos `ANTHROPIC_API_KEY` stops
getting a boot failure and starts getting a silently missing backend that resurfaces much later as a
model-resolution error — a behaviour change on the Portkey-cloud path and on every direct-SDK path,
which the two-gateways work must not make.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from pipelex.cogt.exceptions import InferenceBackendCredentialsError
from pipelex.cogt.model_backends.backend import MANIFOLD_MODEL_SPECS_SECTION, PipelexBackend
from pipelex.cogt.model_backends.backend_library import InferenceBackendLibrary
from pipelex.tools.secrets.env_secrets_provider import EnvSecretsProvider

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture

    from pipelex.cogt.model_backends.gateway_config import GatewayConfig

# A name no environment has, so the substitution fails for the reason under test rather than by luck.
UNSET_VAR = "PIPELEX_TEST_VARIABLE_THAT_IS_NEVER_SET"

MANAGED_BACKEND_TOML = f"""
[pipelex_manifold]
enabled = true
model_specs_section = "{MANIFOLD_MODEL_SPECS_SECTION}"
endpoint = "${{{UNSET_VAR}}}"
api_key = "sk-not-a-real-key"
"""

BYOK_BACKEND_TOML = f"""
[anthropic]
enabled = true
api_key = "${{{UNSET_VAR}}}"
"""


def _load(tmp_path: Path, *, body: str, managed_gateway_configs: dict[str, GatewayConfig] | None = None) -> InferenceBackendLibrary:
    backends_dir = tmp_path / "backends"
    backends_dir.mkdir(exist_ok=True)
    library_path = tmp_path / "backends.toml"
    library_path.write_text(body, encoding="utf-8")
    library = InferenceBackendLibrary.make_empty()
    library.load(
        secrets_provider=EnvSecretsProvider(),
        backends_library_path=str(library_path),
        backends_dir_path=str(backends_dir),
        managed_gateway_configs=managed_gateway_configs,
        lenient=False,
    )
    return library


class TestAManagedBackendMissingItsVariables:
    def test_it_is_disabled_with_a_warning_naming_the_backend_and_the_variable(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """The remedy is the warning, so it has to name what to set and where to turn it off."""
        warning = mocker.patch("pipelex.cogt.model_backends.backend_library.log.warning")

        library = _load(tmp_path, body=MANAGED_BACKEND_TOML, managed_gateway_configs={})

        assert library.get_inference_backend(backend_name=PipelexBackend.MANIFOLD) is None
        warning.assert_called_once()
        said = str(warning.call_args.args[0])
        assert PipelexBackend.MANIFOLD in said
        assert UNSET_VAR in said

    def test_a_byok_backend_missing_its_variables_still_stops_the_boot(self, tmp_path: Path) -> None:
        """Unchanged, deliberately: a typo in an API-key variable must stay loud."""
        with pytest.raises(InferenceBackendCredentialsError) as refused:
            _load(tmp_path, body=BYOK_BACKEND_TOML)

        assert refused.value.key_name == UNSET_VAR


class TestAManagedBackendWithNoPublishedSection:
    def test_it_is_disabled_rather_than_refused(self, tmp_path: Path) -> None:
        """The config builder already warned by name as it skipped the section; the loader just drops it.

        A mapping that was supplied and simply has no entry for this backend is the user's situation.
        The caller's omission — no mapping at all — keeps its own loud refusal, tested below.
        """
        body = MANAGED_BACKEND_TOML.replace(f"${{{UNSET_VAR}}}", "https://manifold.example.com")

        library = _load(tmp_path, body=body, managed_gateway_configs={})

        assert library.get_inference_backend(backend_name=PipelexBackend.MANIFOLD) is None

    def test_no_managed_configs_at_all_is_the_callers_error(self, tmp_path: Path) -> None:
        """Reachable only by loading the library directly without the configs the boot always builds."""
        body = MANAGED_BACKEND_TOML.replace(f"${{{UNSET_VAR}}}", "https://manifold.example.com")

        with pytest.raises(Exception, match="managed_gateway_configs"):
            _load(tmp_path, body=body, managed_gateway_configs=None)
