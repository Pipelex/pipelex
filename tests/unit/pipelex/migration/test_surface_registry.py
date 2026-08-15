"""Unit tests for the surface registry — what a registry may declare, refused when it loads.

Which ledger runs over a file must never be an accident of iteration order, and a surface whose
defaults layer does not exist has no business claiming one. Both are load-time refusals rather
than run-time diagnoses, because by the time a migration is walking a user's directory it is too
late to discover that two surfaces both want the file it is holding.
"""

from pathlib import Path

import pytest
from pydantic import BaseModel, ValidationError

from pipelex.migration.exceptions import MigrationRegistryError
from pipelex.migration.surfaces import DefaultsLayerKind, Surface, SurfaceRegistry


class _Defaulted(BaseModel):
    label: str = "hello"


class _Required(BaseModel):
    label: str


def _surface(*, surface_id: str, base_file: str, tier_glob: str | None = None) -> Surface:
    return Surface(
        surface_id=surface_id,
        title=surface_id,
        base_file=base_file,
        tier_glob=tier_glob,
        config_model=_Defaulted,
        defaults_layer_kind=DefaultsLayerKind.MODEL_DEFAULTS,
    )


class TestSurfaceDeclarations:
    def test_a_packaged_document_surface_must_name_its_document(self) -> None:
        with pytest.raises(ValidationError, match="disagree"):
            Surface(
                surface_id="x",
                title="x",
                base_file="x.toml",
                config_model=_Defaulted,
                defaults_layer_kind=DefaultsLayerKind.PACKAGED_DOCUMENT,
            )

    def test_a_model_defaults_surface_must_not_name_one(self) -> None:
        with pytest.raises(ValidationError, match="disagree"):
            Surface(
                surface_id="x",
                title="x",
                base_file="x.toml",
                config_model=_Defaulted,
                defaults_layer_kind=DefaultsLayerKind.MODEL_DEFAULTS,
                packaged_document_path=Path("somewhere.toml"),
            )

    def test_a_model_defaults_surface_whose_model_needs_arguments_has_no_defaults_layer(self) -> None:
        """The failure is named where it happens rather than surfacing later as a missing value.

        A model that cannot be built from nothing supplies no defaults at all, and without a
        defaults layer an added key breaks every existing file with no structural operation able
        to repair it.
        """
        surface = Surface(
            surface_id="x",
            title="x",
            base_file="x.toml",
            config_model=_Required,
            defaults_layer_kind=DefaultsLayerKind.MODEL_DEFAULTS,
        )
        with pytest.raises(MigrationRegistryError, match="supplies no defaults at all"):
            surface.read_defaults_document()

    def test_a_synthesized_document_drops_keys_toml_cannot_express(self) -> None:
        class _WithOptional(BaseModel):
            label: str = "hello"
            absent: str | None = None

        surface = Surface(
            surface_id="x",
            title="x",
            base_file="x.toml",
            config_model=_WithOptional,
            defaults_layer_kind=DefaultsLayerKind.MODEL_DEFAULTS,
        )
        assert surface.read_defaults_document() == {"label": "hello"}

    def test_a_synthesized_document_drops_nulls_inside_lists_of_tables_too(self) -> None:
        """A list of nested models is a real shape (telemetry's OTLP exporters); a `None` inside one
        item would fail TOML serialization exactly as a top-level one would.
        """

        class _Exporter(BaseModel):
            endpoint: str = "http://localhost"
            headers: str | None = None

        class _WithExporters(BaseModel):
            exporters: list[_Exporter] = [_Exporter()]

        surface = Surface(
            surface_id="x",
            title="x",
            base_file="x.toml",
            config_model=_WithExporters,
            defaults_layer_kind=DefaultsLayerKind.MODEL_DEFAULTS,
        )
        assert surface.read_defaults_document() == {"exporters": [{"endpoint": "http://localhost"}]}
        assert "headers" not in surface.render_reference_document()


class TestRegistryConsistency:
    def test_two_surfaces_sharing_an_id_are_refused(self) -> None:
        with pytest.raises(ValidationError, match="share the surface id"):
            SurfaceRegistry(
                surfaces=[
                    _surface(surface_id="same", base_file="a.toml"),
                    _surface(surface_id="same", base_file="b.toml"),
                ]
            )

    def test_two_surfaces_sharing_a_base_file_are_refused(self) -> None:
        with pytest.raises(ValidationError, match="share the base file"):
            SurfaceRegistry(
                surfaces=[
                    _surface(surface_id="a", base_file="same.toml"),
                    _surface(surface_id="b", base_file="same.toml"),
                ]
            )

    def test_two_surfaces_sharing_a_tier_glob_are_refused(self) -> None:
        """A file claimed by two globs has no rule to separate them, unlike a glob and an exact name."""
        with pytest.raises(ValidationError, match="share the tier glob"):
            SurfaceRegistry(
                surfaces=[
                    _surface(surface_id="a", base_file="a.toml", tier_glob="shared_*.toml"),
                    _surface(surface_id="b", base_file="b.toml", tier_glob="shared_*.toml"),
                ]
            )

    def test_a_base_file_matching_another_surfaces_glob_is_fine(self) -> None:
        """This is the real configuration: `pipelex_service.toml` matches `pipelex_*.toml`.

        Exact filenames claim before globs across all surfaces, so the resolution rule separates
        them — which is exactly why it exists, and why this is not a registry error.
        """
        registry = SurfaceRegistry(
            surfaces=[
                _surface(surface_id="a", base_file="pipelex.toml", tier_glob="pipelex_*.toml"),
                _surface(surface_id="b", base_file="pipelex_service.toml"),
            ]
        )
        assert len(registry.surfaces) == 2

    def test_an_unknown_surface_id_is_named_in_the_error(self) -> None:
        registry = SurfaceRegistry(surfaces=[_surface(surface_id="a", base_file="a.toml")])
        with pytest.raises(MigrationRegistryError, match="no surface 'nope'"):
            registry.surface_for_id(surface_id="nope")
