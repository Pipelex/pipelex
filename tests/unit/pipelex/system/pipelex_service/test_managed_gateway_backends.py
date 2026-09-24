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
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from pipelex.cogt.model_backends.backend import (
    MANIFOLD_MODEL_SPECS_SECTION,
    PipelexBackend,
    resolve_model_specs_section,
)
from pipelex.system.pipelex_service.managed_gateway_configs import build_managed_gateway_configs
from pipelex.system.pipelex_service.pipelex_service_config import enabled_managed_gateway_sections
from pipelex.system.pipelex_service.remote_config import RemoteConfig

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture

# A second managed section, standing in for the next managed service the kit could ship.
OTHER_SECTION = "other_model_specs"
OTHER_BACKEND = "pipelex_other"


def _remote_config(**sections: object) -> RemoteConfig:
    """The published artifact, carrying whichever model-specs sections a test hands it."""
    return RemoteConfig(**sections)  # pyright: ignore[reportArgumentType]


def _write_backends(tmp_path: Path, body: str) -> Path:
    """Write the base document at a config dir and return that dir, which is what the readers take.

    The reader below takes a `config_dir` and resolves the document under it — the base
    `inference/backends.toml` plus any `inference/backends_override.toml` — so a test pins a
    directory rather than a file.
    """
    inference_dir = tmp_path / "inference"
    inference_dir.mkdir(parents=True, exist_ok=True)
    (inference_dir / "backends.toml").write_text(body, encoding="utf-8")
    return tmp_path


class TestResolveModelSpecsSection:
    def test_a_declared_section_makes_a_backend_managed(self) -> None:
        assert resolve_model_specs_section(backend_name="whatever", declared_section="some_section") == "some_section"

    def test_every_backend_without_a_declaration_reads_its_own_file(self) -> None:
        """No section means not managed, which is every BYOK backend and the internal one — and no
        name resolves to a section it did not declare, the manifold's included.
        """
        assert resolve_model_specs_section(backend_name="anthropic", declared_section=None) is None
        assert resolve_model_specs_section(backend_name=PipelexBackend.MANIFOLD, declared_section=None) is None


class TestEnabledManagedGatewaySections:
    def test_it_maps_each_enabled_managed_backend_to_its_section(self, tmp_path: Path) -> None:
        config_dir = _write_backends(
            tmp_path,
            f'[pipelex_manifold]\nmodel_specs_section = "{MANIFOLD_MODEL_SPECS_SECTION}"\nendpoint = "https://gw.example.com"\n\n'
            f'[{OTHER_BACKEND}]\nmodel_specs_section = "{OTHER_SECTION}"\n\n'
            f'[anthropic]\napi_key = "sk-x"\n',
        )

        assert enabled_managed_gateway_sections(config_dir=config_dir) == {
            PipelexBackend.MANIFOLD: MANIFOLD_MODEL_SPECS_SECTION,
            OTHER_BACKEND: OTHER_SECTION,
        }

    @pytest.mark.parametrize("enabled_value", ["false", "0"])
    def test_a_disabled_backend_is_absent_reading_enabled_the_way_the_loader_does(self, tmp_path: Path, enabled_value: str) -> None:
        """Truthiness, not the literal `true` — the same reading the backend library applies."""
        config_dir = _write_backends(
            tmp_path, f'[pipelex_manifold]\nenabled = {enabled_value}\nmodel_specs_section = "{MANIFOLD_MODEL_SPECS_SECTION}"\n'
        )

        assert enabled_managed_gateway_sections(config_dir=config_dir) == {}

    @pytest.mark.parametrize("enabled_value", ["1", '"yes"'])
    def test_an_enabled_value_the_loader_reads_as_true_is_enabled_here_too(self, tmp_path: Path, enabled_value: str) -> None:
        """The two readers of `backends.toml` must agree, or the boot fetches no specs for a backend
        the loader then insists is enabled.
        """
        config_dir = _write_backends(
            tmp_path, f'[pipelex_manifold]\nenabled = {enabled_value}\nmodel_specs_section = "{MANIFOLD_MODEL_SPECS_SECTION}"\n'
        )

        assert enabled_managed_gateway_sections(config_dir=config_dir) == {PipelexBackend.MANIFOLD: MANIFOLD_MODEL_SPECS_SECTION}

    def test_the_override_is_read_over_the_base(self, tmp_path: Path) -> None:
        """The personal override is the loader's document too, so the gate must see it."""
        config_dir = _write_backends(tmp_path, f'[pipelex_manifold]\nenabled = false\nmodel_specs_section = "{MANIFOLD_MODEL_SPECS_SECTION}"\n')
        (config_dir / "inference" / "backends_override.toml").write_text("[pipelex_manifold]\nenabled = true\n", encoding="utf-8")

        assert enabled_managed_gateway_sections(config_dir=config_dir) == {PipelexBackend.MANIFOLD: MANIFOLD_MODEL_SPECS_SECTION}

    def test_a_byok_backend_is_never_managed(self, tmp_path: Path) -> None:
        config_dir = _write_backends(tmp_path, '[anthropic]\napi_key = "sk-x"\n\n[openai]\napi_key = "sk-y"\n')

        assert enabled_managed_gateway_sections(config_dir=config_dir) == {}

    def test_a_missing_file_is_no_managed_backends_rather_than_a_refusal(self, tmp_path: Path) -> None:
        assert enabled_managed_gateway_sections(config_dir=tmp_path / "absent") == {}

    def test_an_override_cannot_stand_in_for_the_base(self, tmp_path: Path) -> None:
        """No document, no managed backend."""
        inference_dir = tmp_path / "inference"
        inference_dir.mkdir(parents=True)
        (inference_dir / "backends_override.toml").write_text(
            f'[pipelex_manifold]\nenabled = true\nmodel_specs_section = "{MANIFOLD_MODEL_SPECS_SECTION}"\n', encoding="utf-8"
        )

        assert enabled_managed_gateway_sections(config_dir=tmp_path) == {}


class TestBuildManagedGatewayConfigs:
    def test_each_backend_gets_its_own_section_unmerged(self) -> None:
        """Two services, two spec maps: a handle one serves and the other does not is legitimate."""
        remote_config = _remote_config(
            **{
                OTHER_SECTION: {"gpt-5": {"model_id": "gpt-5"}},
                MANIFOLD_MODEL_SPECS_SECTION: {"claude-4-sonnet": {"model_id": "claude-4-sonnet"}},
            }
        )

        configs = build_managed_gateway_configs(
            remote_config=remote_config,
            managed_gateway_sections={
                OTHER_BACKEND: OTHER_SECTION,
                PipelexBackend.MANIFOLD: MANIFOLD_MODEL_SPECS_SECTION,
            },
        )

        assert set(configs) == {OTHER_BACKEND, PipelexBackend.MANIFOLD}
        assert set(configs[OTHER_BACKEND].model_specs) == {"gpt-5"}
        assert set(configs[PipelexBackend.MANIFOLD].model_specs) == {"claude-4-sonnet"}

    def test_a_section_the_artifact_does_not_carry_is_disabled_by_name(self, mocker: MockerFixture) -> None:
        """Disabled with a named warning, not fatal: the kit can ship a managed backend declared.

        The warning is the whole remedy here, so it has to name both the backend and the section it
        was looking for — otherwise a user who has not joined the beta reads that *something* was
        disabled and has nowhere to go.
        """
        warning = mocker.patch("pipelex.system.pipelex_service.managed_gateway_configs.log.warning")
        remote_config = _remote_config(**{OTHER_SECTION: {"gpt-5": {"model_id": "gpt-5"}}})

        configs = build_managed_gateway_configs(
            remote_config=remote_config,
            managed_gateway_sections={
                OTHER_BACKEND: OTHER_SECTION,
                PipelexBackend.MANIFOLD: MANIFOLD_MODEL_SPECS_SECTION,
            },
        )

        assert set(configs) == {OTHER_BACKEND}
        warning.assert_called_once()
        said = str(warning.call_args.args[0])
        assert PipelexBackend.MANIFOLD in said
        assert MANIFOLD_MODEL_SPECS_SECTION in said


class TestTheSectionLookupIsConfinedToTheArtifact:
    """`model_specs_section` is text from the user's own `backends.toml`, so the lookup it drives
    must only ever reach the artifact's own content.

    A bare `getattr` on the model answers for pydantic's machinery as well, and two of those
    attributes are plain dicts — so they pass a `isinstance(..., dict)` shape check and travel on as
    if the service had published them. The failure that produces is not a refusal but a
    `GatewayConfig` built over pydantic internals, which surfaces much later as an unintelligible
    model-spec error naming neither the backend nor the mistake.
    """

    def test_a_published_section_is_found(self) -> None:
        sections: dict[str, dict[str, object]] = {
            OTHER_SECTION: {},
            MANIFOLD_MODEL_SPECS_SECTION: {"claude-4-sonnet": {"model_id": "claude-4-sonnet"}},
        }
        remote_config = _remote_config(**sections)

        section = remote_config.get_model_specs_section(MANIFOLD_MODEL_SPECS_SECTION)

        assert section is not None
        assert set(section) == {"claude-4-sonnet"}

    @pytest.mark.parametrize("attribute_name", ["model_config", "model_fields"])
    def test_a_pydantic_internal_is_not_a_section(self, attribute_name: str) -> None:
        """Both are real dict attributes of any v2 model, and neither is anything the service published."""
        manifold_only: dict[str, dict[str, object]] = {MANIFOLD_MODEL_SPECS_SECTION: {}}
        remote_config = _remote_config(**manifold_only)

        # Read off the class: instance access to `model_fields` is deprecated in pydantic v2.11,
        # and the point being made is about the attribute existing as a dict at all.
        assert isinstance(getattr(RemoteConfig, attribute_name), dict)
        assert remote_config.get_model_specs_section(attribute_name) is None

    def test_a_published_key_that_is_not_a_spec_map_is_not_a_section(self) -> None:
        """The artifact carries keys for other consumers too, and one of the wrong shape is not a section."""
        sections: dict[str, object] = {MANIFOLD_MODEL_SPECS_SECTION: {}, "aws_region": "eu-west-3"}
        remote_config = _remote_config(**sections)

        assert remote_config.get_model_specs_section("aws_region") is None

    def test_an_unknown_name_is_simply_absent(self) -> None:
        manifold_only: dict[str, dict[str, object]] = {MANIFOLD_MODEL_SPECS_SECTION: {}}
        remote_config = _remote_config(**manifold_only)

        assert remote_config.get_model_specs_section("no_such_section") is None
