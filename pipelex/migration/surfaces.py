"""The surface registry — what a configuration surface is, and which ones exist.

The registry is built by a function and passed as a parameter, **never read from a module
constant**. That is deliberate and it is what keeps the gates honest: the gates' own tests point
the registry at small synthetic models, so gate *behaviour* is tested against something that
never moves. Wire the real models into the gate's test suite and every legitimate configuration
change turns the gate's tests red alongside the gate, and the fix everyone learns is "regenerate
the goldens" — which is how a gate goes permanently green while catching nothing.

See `docs/migration-ledger.md` → "Surfaces" and "Testing the gates without coupling them to the
configuration models".
"""

from enum import StrEnum
from pathlib import Path
from typing import Any

import tomlkit
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from typing_extensions import Self

from pipelex.migration.exceptions import MigrationRegistryError
from pipelex.system.configuration.configs import PipelexConfig
from pipelex.system.pipelex_service.pipelex_service_agreement import PIPELEX_SERVICE_CONFIG_FILE_NAME
from pipelex.system.pipelex_service.pipelex_service_config import PipelexServiceConfig
from pipelex.system.telemetry.telemetry_config import TELEMETRY_CONFIG_FILE_NAME, TelemetryConfig
from pipelex.tools.misc.toml_utils import load_toml_from_path

PIPELEX_CONFIG_FILE_NAME = "pipelex.toml"

# The package directory, `pipelex/` — this module sits one level under it.
_PACKAGE_ROOT = Path(__file__).resolve().parent.parent


def packaged_migration_dir() -> Path:
    """The directory holding the checked-in ledgers and golden chains — this module's own."""
    return Path(__file__).resolve().parent


class DefaultsLayerKind(StrEnum):
    """Where a surface's current-schema default values come from.

    Every in-scope surface must have one, because the defaults layer is what makes an additive
    schema change absorbable and therefore never a migration.
    """

    PACKAGED_DOCUMENT = "packaged_document"
    """A TOML document shipped in the package and merged beneath the user's files."""

    MODEL_DEFAULTS = "model_defaults"
    """Field-level defaults on the model; the reference document is synthesized from them."""


class Surface(BaseModel):
    """One artifact family with one schema version and one ledger."""

    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    surface_id: str
    title: str
    base_file: str
    tier_glob: str | None = None
    config_model: type[BaseModel]
    defaults_layer_kind: DefaultsLayerKind
    packaged_document_path: Path | None = None

    @model_validator(mode="after")
    def check_defaults_layer_is_reachable(self) -> Self:
        has_packaged_path = self.packaged_document_path is not None
        wants_packaged_path = self.defaults_layer_kind is DefaultsLayerKind.PACKAGED_DOCUMENT
        if has_packaged_path != wants_packaged_path:
            msg = (
                f"surface '{self.surface_id}': defaults_layer_kind '{self.defaults_layer_kind}' and "
                f"packaged_document_path {self.packaged_document_path!r} disagree — a packaged-document "
                f"surface names its document and a model-defaults surface does not"
            )
            raise ValueError(msg)
        return self

    def render_reference_document(self) -> str:
        """The surface's complete reference document as TOML text, ready to check in.

        For a packaged-document surface this is the shipped file verbatim; for a model-defaults
        surface it is the synthesized document serialized. Neither carries a generated-by banner,
        because the snapshot is not a report about a document — it *is* the document, and a later
        phase applies migration operations to it.
        """
        match self.defaults_layer_kind:
            case DefaultsLayerKind.PACKAGED_DOCUMENT:
                # Guaranteed present by the validator above.
                assert self.packaged_document_path is not None
                return self.packaged_document_path.read_text(encoding="utf-8")
            case DefaultsLayerKind.MODEL_DEFAULTS:
                document: str = tomlkit.dumps(self.read_defaults_document())  # pyright: ignore[reportUnknownMemberType]
                return document

    def read_defaults_document(self) -> dict[str, Any]:
        """The surface's complete reference document, as a plain mapping.

        For a packaged-document surface this is the shipped TOML. For a model-defaults surface
        it is synthesized by instantiating the model with nothing set, which is exactly the
        document the defaults layer contributes. Keys whose value is `None` are dropped: TOML
        has no null, so an unset optional is an absent key rather than a written one.
        """
        match self.defaults_layer_kind:
            case DefaultsLayerKind.PACKAGED_DOCUMENT:
                # Guaranteed present by the validator above; the assert keeps the type checker honest.
                assert self.packaged_document_path is not None
                return load_toml_from_path(path=self.packaged_document_path)
            case DefaultsLayerKind.MODEL_DEFAULTS:
                try:
                    instance = self.config_model()
                except ValidationError as exc:
                    # A model-defaults surface whose model cannot be built from nothing has no
                    # defaults layer at all, which is the one condition the whole vocabulary rests
                    # on: without it an added key breaks every existing file and no structural
                    # operation can repair it.
                    msg = (
                        f"surface '{self.surface_id}' declares its defaults layer as model defaults, but "
                        f"{self.config_model.__name__} cannot be built without arguments, so it supplies no "
                        f"defaults at all: {exc}"
                    )
                    raise MigrationRegistryError(msg) from exc
                return _drop_none_values(mapping=instance.model_dump(mode="json"))


def _drop_none_values(*, mapping: dict[str, Any]) -> dict[str, Any]:
    """Recursively drop keys whose value is `None`, which TOML cannot express."""
    kept: dict[str, Any] = {}
    for key, value in mapping.items():
        if value is None:
            continue
        if isinstance(value, dict):
            kept[key] = _drop_none_values(mapping=value)  # pyright: ignore[reportUnknownArgumentType]
        else:
            kept[key] = value
    return kept


class SurfaceRegistry(BaseModel):
    """The set of surfaces a gate or a migration run operates over."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    surfaces: list[Surface] = Field(min_length=1)

    @model_validator(mode="after")
    def check_no_surface_shadows_another(self) -> Self:
        """Reject a registry whose surfaces could claim the same file.

        Which ledger runs over a file must not be an accident of iteration order. Exact
        filenames claim before globs across all surfaces, so a base file matching another
        surface's glob is fine and resolved by that rule — but two surfaces sharing an id, a
        base file or a tier glob have no rule to separate them.
        """
        _reject_duplicates(values=[surface.surface_id for surface in self.surfaces], label="surface id")
        _reject_duplicates(values=[surface.base_file for surface in self.surfaces], label="base file")
        _reject_duplicates(
            values=[surface.tier_glob for surface in self.surfaces if surface.tier_glob is not None],
            label="tier glob",
        )
        return self

    def surface_for_id(self, *, surface_id: str) -> Surface:
        for surface in self.surfaces:
            if surface.surface_id == surface_id:
                return surface
        msg = f"no surface '{surface_id}' in this registry"
        raise MigrationRegistryError(msg)


def _reject_duplicates(*, values: list[str], label: str) -> None:
    seen: set[str] = set()
    for value in values:
        if value in seen:
            msg = f"registry error: two surfaces share the {label} '{value}'"
            raise ValueError(msg)
        seen.add(value)


def build_config_surface_registry() -> SurfaceRegistry:
    """The real registry: the configuration surfaces the `pipelex` package owns.

    A function rather than a module constant, so that nothing imports the real configuration
    models by merely importing this module, and so that every consumer has to state which
    registry it means.
    """
    return SurfaceRegistry(
        surfaces=[
            Surface(
                surface_id="pipelex-config",
                title="The main Pipelex configuration",
                base_file=PIPELEX_CONFIG_FILE_NAME,
                tier_glob="pipelex_*.toml",
                config_model=PipelexConfig,
                defaults_layer_kind=DefaultsLayerKind.PACKAGED_DOCUMENT,
                packaged_document_path=_PACKAGE_ROOT / PIPELEX_CONFIG_FILE_NAME,
            ),
            Surface(
                surface_id="telemetry-config",
                title="Telemetry destinations and capture settings",
                base_file=TELEMETRY_CONFIG_FILE_NAME,
                tier_glob="telemetry_*.toml",
                config_model=TelemetryConfig,
                defaults_layer_kind=DefaultsLayerKind.MODEL_DEFAULTS,
            ),
            Surface(
                surface_id="pipelex-service-config",
                title="Pipelex service agreement and onboarding state",
                base_file=PIPELEX_SERVICE_CONFIG_FILE_NAME,
                config_model=PipelexServiceConfig,
                defaults_layer_kind=DefaultsLayerKind.MODEL_DEFAULTS,
            ),
        ]
    )
