"""Which backends are *managed gateway* backends, and how the one artifact is sliced for them.

Three collaborating pieces, one question: a managed gateway backend takes its model specs from the
Pipelex service's published artifact rather than from a local per-backend TOML, and naming a section
is what declares it one.

- `resolve_model_specs_section` decides, per backend, whether there is a section and which;
- `enabled_managed_gateway_sections` answers it for a whole `backends.toml`, before the backend
  library can be loaded — the boot needs the answer first, because what it fetches is that load's
  input;
- `build_managed_gateway_configs` cuts the single fetched artifact into one configuration per
  managed backend, keeping them apart rather than merging them.

And the narrower question `is_pipelex_gateway_enabled` answers, which is not a special case of the
broad one and must not be folded into it — the last class here is why.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from pipelex.cogt.model_backends.backend import (
    LEGACY_GATEWAY_MODEL_SPECS_SECTION,
    MANIFOLD_MODEL_SPECS_SECTION,
    PipelexBackend,
    resolve_model_specs_section,
)
from pipelex.system.pipelex_service.managed_gateway_configs import build_managed_gateway_configs
from pipelex.system.pipelex_service.pipelex_service_config import enabled_managed_gateway_sections, is_pipelex_gateway_enabled
from pipelex.system.pipelex_service.remote_config import PipelexPosthogConfig, RemoteConfig

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture


def _remote_config(**sections: object) -> RemoteConfig:
    """The published artifact, carrying whichever model-specs sections a test hands it."""
    return RemoteConfig(
        posthog=PipelexPosthogConfig(project_api_key="", endpoint="https://dummy.example.com", is_geoip_enabled=False, is_debug_enabled=False),
        aws_region="eu-west-3",
        **sections,  # pyright: ignore[reportArgumentType]
    )


def _write_backends(tmp_path: Path, body: str) -> Path:
    backends_file = tmp_path / "backends.toml"
    backends_file.write_text(body, encoding="utf-8")
    return backends_file


class TestResolveModelSpecsSection:
    def test_a_declared_section_makes_a_backend_managed(self) -> None:
        assert resolve_model_specs_section(backend_name="whatever", declared_section="some_section") == "some_section"

    def test_the_legacy_gateway_resolves_to_its_section_without_declaring_one(self) -> None:
        """`backends.toml` is the user's own file, written before the field existed and never rewritten."""
        assert resolve_model_specs_section(backend_name=PipelexBackend.GATEWAY, declared_section=None) == LEGACY_GATEWAY_MODEL_SPECS_SECTION

    def test_an_explicit_declaration_wins_even_on_that_name(self) -> None:
        assert resolve_model_specs_section(backend_name=PipelexBackend.GATEWAY, declared_section="elsewhere") == "elsewhere"

    def test_every_other_backend_reads_its_own_file(self) -> None:
        """No section means not managed, which is every BYOK backend and the internal one."""
        assert resolve_model_specs_section(backend_name="anthropic", declared_section=None) is None
        assert resolve_model_specs_section(backend_name=PipelexBackend.MANIFOLD, declared_section=None) is None


class TestEnabledManagedGatewaySections:
    def test_it_maps_each_enabled_managed_backend_to_its_section(self, tmp_path: Path) -> None:
        backends_file = _write_backends(
            tmp_path,
            f'[pipelex_gateway]\napi_key = "pk-x"\n\n'
            f'[pipelex_manifold]\nmodel_specs_section = "{MANIFOLD_MODEL_SPECS_SECTION}"\nendpoint = "https://gw.example.com"\n\n'
            f'[anthropic]\napi_key = "sk-x"\n',
        )

        assert enabled_managed_gateway_sections(backends_file_path=backends_file) == {
            PipelexBackend.GATEWAY: LEGACY_GATEWAY_MODEL_SPECS_SECTION,
            PipelexBackend.MANIFOLD: MANIFOLD_MODEL_SPECS_SECTION,
        }

    @pytest.mark.parametrize("enabled_value", ["false", "0"])
    def test_a_disabled_backend_is_absent_reading_enabled_the_way_the_loader_does(self, tmp_path: Path, enabled_value: str) -> None:
        """Truthiness, not the literal `true` — the same reading the backend library applies."""
        backends_file = _write_backends(tmp_path, f'[pipelex_gateway]\nenabled = {enabled_value}\napi_key = "pk-x"\n')

        assert enabled_managed_gateway_sections(backends_file_path=backends_file) == {}

    def test_a_byok_backend_is_never_managed(self, tmp_path: Path) -> None:
        backends_file = _write_backends(tmp_path, '[anthropic]\napi_key = "sk-x"\n\n[openai]\napi_key = "sk-y"\n')

        assert enabled_managed_gateway_sections(backends_file_path=backends_file) == {}

    def test_a_missing_file_is_no_managed_backends_rather_than_a_refusal(self, tmp_path: Path) -> None:
        assert enabled_managed_gateway_sections(backends_file_path=tmp_path / "absent.toml") == {}


class TestTheTwoQuestionsAreNotTheSameQuestion:
    """Which managed backends are live, and whether the *legacy gateway* is — the boot asks both.

    They came apart the moment a second managed backend existed, and the boot line that must keep
    asking the narrow one is the telemetry decision: the distinct id is derived from
    `PIPELEX_GATEWAY_API_KEY`, which a manifold-only installation has no reason to hold. Asked the
    broad way, such an installation is required to produce a gateway key it does not have and fails
    to boot on `GatewayApiKeyMissingError` — a refusal with nothing in it naming manifold.

    The beta's own key cannot stand in either, and that is the second half of the verdict: for the
    private beta it is one token shared by every participant, so keying on it would report a single
    indistinguishable user rather than an identity.
    """

    def test_a_manifold_only_installation_is_managed_but_is_not_the_gateway(self, tmp_path: Path) -> None:
        backends_file = _write_backends(
            tmp_path,
            f"[pipelex_gateway]\nenabled = false\n\n"
            f'[pipelex_manifold]\nmodel_specs_section = "{MANIFOLD_MODEL_SPECS_SECTION}"\nendpoint = "https://mf.example.com"\n',
        )

        assert enabled_managed_gateway_sections(backends_file_path=backends_file) == {PipelexBackend.MANIFOLD: MANIFOLD_MODEL_SPECS_SECTION}
        assert not is_pipelex_gateway_enabled(backends_file_path=backends_file)

    def test_the_common_beta_case_keeps_both(self, tmp_path: Path) -> None:
        """A participant who leaves the legacy gateway on has a real key, and manifold runs ride on it."""
        backends_file = _write_backends(
            tmp_path,
            f'[pipelex_gateway]\napi_key = "pk-x"\n\n'
            f'[pipelex_manifold]\nmodel_specs_section = "{MANIFOLD_MODEL_SPECS_SECTION}"\nendpoint = "https://mf.example.com"\n',
        )

        assert set(enabled_managed_gateway_sections(backends_file_path=backends_file)) == {PipelexBackend.GATEWAY, PipelexBackend.MANIFOLD}
        assert is_pipelex_gateway_enabled(backends_file_path=backends_file)


class TestBuildManagedGatewayConfigs:
    def test_each_backend_gets_its_own_section_unmerged(self) -> None:
        """Two services, two spec maps: a handle one serves and the other does not is legitimate."""
        remote_config = _remote_config(
            **{
                LEGACY_GATEWAY_MODEL_SPECS_SECTION: {"gpt-5": {"model_id": "gpt-5"}},
                MANIFOLD_MODEL_SPECS_SECTION: {"claude-4-sonnet": {"model_id": "claude-4-sonnet"}},
            }
        )

        configs = build_managed_gateway_configs(
            remote_config=remote_config,
            managed_gateway_sections={
                PipelexBackend.GATEWAY: LEGACY_GATEWAY_MODEL_SPECS_SECTION,
                PipelexBackend.MANIFOLD: MANIFOLD_MODEL_SPECS_SECTION,
            },
        )

        assert set(configs) == {PipelexBackend.GATEWAY, PipelexBackend.MANIFOLD}
        assert set(configs[PipelexBackend.GATEWAY].model_specs) == {"gpt-5"}
        assert set(configs[PipelexBackend.MANIFOLD].model_specs) == {"claude-4-sonnet"}

    def test_the_region_belongs_to_the_legacy_slice_alone(self) -> None:
        """`aws_region` is a top-level key of the artifact, and only the direct-SDK Bedrock path reads it back."""
        empty_sections: dict[str, dict[str, object]] = {LEGACY_GATEWAY_MODEL_SPECS_SECTION: {}, MANIFOLD_MODEL_SPECS_SECTION: {}}
        remote_config = _remote_config(**empty_sections)

        configs = build_managed_gateway_configs(
            remote_config=remote_config,
            managed_gateway_sections={
                PipelexBackend.GATEWAY: LEGACY_GATEWAY_MODEL_SPECS_SECTION,
                PipelexBackend.MANIFOLD: MANIFOLD_MODEL_SPECS_SECTION,
            },
        )

        assert configs[PipelexBackend.GATEWAY].aws_region == "eu-west-3"
        assert configs[PipelexBackend.MANIFOLD].aws_region is None

    def test_a_section_the_artifact_does_not_carry_is_disabled_by_name(self, mocker: MockerFixture) -> None:
        """Disabled with a named warning, not fatal: the kit can ship a managed backend declared.

        The warning is the whole remedy here, so it has to name both the backend and the section it
        was looking for — otherwise a user who has not joined the beta reads that *something* was
        disabled and has nowhere to go.
        """
        warning = mocker.patch("pipelex.system.pipelex_service.managed_gateway_configs.log.warning")
        remote_config = _remote_config(**{LEGACY_GATEWAY_MODEL_SPECS_SECTION: {"gpt-5": {"model_id": "gpt-5"}}})

        configs = build_managed_gateway_configs(
            remote_config=remote_config,
            managed_gateway_sections={
                PipelexBackend.GATEWAY: LEGACY_GATEWAY_MODEL_SPECS_SECTION,
                PipelexBackend.MANIFOLD: MANIFOLD_MODEL_SPECS_SECTION,
            },
        )

        assert set(configs) == {PipelexBackend.GATEWAY}
        warning.assert_called_once()
        said = str(warning.call_args.args[0])
        assert PipelexBackend.MANIFOLD in said
        assert MANIFOLD_MODEL_SPECS_SECTION in said
