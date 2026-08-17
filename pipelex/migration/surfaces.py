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
from fnmatch import fnmatch
from pathlib import Path
from typing import Any, cast

import tomlkit
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from typing_extensions import Self

from pipelex.migration.exceptions import MigrationRegistryError
from pipelex.migration.fingerprint import SurfaceFingerprint, compute_fingerprint
from pipelex.system.configuration.config_surface import (
    PIPELEX_CONFIG_SURFACE_ID,
    PIPELEX_SERVICE_CONFIG_SURFACE_ID,
    TELEMETRY_CONFIG_SURFACE_ID,
)
from pipelex.system.configuration.configs import PipelexConfig
from pipelex.system.pipelex_service.pipelex_service_agreement import PIPELEX_SERVICE_CONFIG_FILE_NAME
from pipelex.system.pipelex_service.pipelex_service_config import PipelexServiceConfig
from pipelex.system.telemetry.telemetry_config import TELEMETRY_CONFIG_FILE_NAME, TelemetryConfig
from pipelex.tools.misc.toml_utils import load_toml_from_path

PIPELEX_CONFIG_FILE_NAME = "pipelex.toml"

# The package directory, `pipelex/` — this module sits one level under it.
_PACKAGE_ROOT = Path(__file__).resolve().parent.parent
_KIT_CONFIGS_DIR = _PACKAGE_ROOT / "kit" / "configs"


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

    base_file: str | None = None
    """The one file of the family that is distinguished by name, when there is one.

    A family whose members are all alike — the inference backend definitions, one file per backend
    — has none, and claims its files by `tier_glob` alone."""

    tier_glob: str | None = None

    subdirectory: Path = Path()
    """The directory, relative to a configuration directory, whose files this surface claims.

    Empty for a surface that lives directly in `~/.pipelex/` or `.pipelex/`. A surface that owns a
    subdirectory owns it *one level deep and to the exclusion of every other surface*, which is
    what makes `inference/backends/pipelex_gateway.toml` safe: its name matches the main
    configuration's tier glob exactly, and only the directory it sits in says it is not a
    `pipelex.toml` tier file."""

    config_model: type[BaseModel]
    defaults_layer_kind: DefaultsLayerKind
    packaged_document_path: Path | None = None

    kit_template_path: Path | None = None
    """The sparse starter file `pipelex init` copies into a configuration directory.

    A **convergence and neutrality witness only**, never a snapshot: it is read live, so there is
    no fixture to maintain and no golden to go stale. It earns its place beside the complete
    reference document because the two are different shapes — the complete document has every key
    set, the template has almost none — and an operation that misbehaves on an absent key would
    pass over one and fail over the other."""

    @model_validator(mode="after")
    def check_the_surface_claims_some_file(self) -> Self:
        if self.base_file is None and self.tier_glob is None:
            msg = f"surface '{self.surface_id}': claims no file — a surface with no base file must claim its files by a tier glob"
            raise ValueError(msg)
        return self

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

    def fingerprint_at(self, *, schema_version: int) -> SurfaceFingerprint:
        """This surface's live models, projected and labelled with the schema version they are at.

        It lives on the surface because the surface is what holds both halves the projection needs
        — the model tree and the defaults layer it is read against. Both readers want the same
        answer for different reasons: the regenerator writes it into the golden chain, and a
        migration run asks it which paths the current schema knows.
        """
        return compute_fingerprint(
            surface_id=self.surface_id,
            schema_version=schema_version,
            config_model=self.config_model,
            defaults_document=self.read_defaults_document(),
        )

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

    def reference_documents(self) -> list[tuple[str, str]]:
        """Every document a replay must be neutral over, as `(label, text)` pairs.

        Both are at the current schema by construction — one is the packaged defaults layer or the
        document the model's own defaults synthesize, the other is the starter template the kit
        ships — so neither is a fixture anyone has to keep up to date.
        """
        documents = [("reference document", self.render_reference_document())]
        if self.kit_template_path is not None:
            documents.append(("kit template", self.kit_template_path.read_text(encoding="utf-8")))
        return documents

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
    """Recursively drop keys whose value is `None`, which TOML cannot express.

    Descends through nested mappings and through lists — a list of nested models is a real shape,
    and a `None` inside one item fails serialization exactly as a top-level one would. Only
    mapping keys are dropped; a list keeps every item.
    """
    kept: dict[str, Any] = {}
    for key, value in mapping.items():
        if value is None:
            continue
        kept[key] = _without_none_values(value=value)
    return kept


def _without_none_values(*, value: Any) -> Any:
    if isinstance(value, dict):
        return _drop_none_values(mapping=cast("dict[str, Any]", value))
    if isinstance(value, list):
        return [_without_none_values(value=item) for item in cast("list[Any]", value)]
    return value


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

        **A name collides only within one directory.** A base file and a glob are both claims over
        a directory's own listing, so the same spelling in two directories is two different claims
        — and `*.toml` in particular is the whole language of a surface that owns a directory,
        which the second such surface must not have to narrow for the registry's sake.
        """
        _reject_duplicates(values=[surface.surface_id for surface in self.surfaces], label="surface id")
        _reject_duplicates_per_directory(
            values=[(surface.subdirectory, surface.base_file) for surface in self.surfaces if surface.base_file is not None],
            label="base file",
        )
        _reject_duplicates_per_directory(
            values=[(surface.subdirectory, surface.tier_glob) for surface in self.surfaces if surface.tier_glob is not None],
            label="tier glob",
        )
        return self

    def surface_for_id(self, *, surface_id: str) -> Surface:
        for surface in self.surfaces:
            if surface.surface_id == surface_id:
                return surface
        msg = f"no surface '{surface_id}' in this registry"
        raise MigrationRegistryError(msg)

    def surface_for_file(self, *, subdirectory: Path, file_name: str) -> Surface | None:
        """Which surface owns a file, by the directory it sits in and its name, or `None`.

        > **A file is claimed by the pair (directory, name).** Only the surfaces that own the
        > directory the file sits in are candidates; among those, exact filenames claim before
        > globs.

        Both halves are load-bearing and each answers a real collision. Without the *name* rule,
        `pipelex_service.toml` is both the base file of one surface and a match for another's
        `pipelex_*.toml`. Without the *directory* rule, `inference/backends/pipelex_gateway.toml`
        is a `pipelex_*.toml` match too — and it is an inference backend definition, so the main
        configuration's ledger would be replayed over it and rewrite it.

        Args:
            subdirectory: The file's directory, relative to a configuration directory. Empty for a
                file sitting directly in one.
            file_name: The file's own name, with no directory part.

        Raises:
            MigrationRegistryError: two surfaces' globs both claim this file. That the registry
                itself cannot decide — whether two glob languages overlap is not decidable
                cheaply, and the registry has no files to look at. Here there is one, so the
                contract's *a file claimed by two globs is a registry error* becomes enforceable,
                by name, on the file that proves it.
        """
        candidates = [surface for surface in self.surfaces if surface.subdirectory == subdirectory]
        for surface in candidates:
            if surface.base_file == file_name:
                return surface
        claimants = [surface for surface in candidates if surface.tier_glob is not None and fnmatch(file_name, surface.tier_glob)]
        if len(claimants) > 1:
            named = ", ".join(f"'{surface.surface_id}' ({surface.tier_glob})" for surface in claimants)
            msg = f"registry error: '{file_name}' is claimed by the tier globs of {named} — a file belongs to exactly one surface"
            raise MigrationRegistryError(msg)
        return claimants[0] if claimants else None

    def files_by_surface_in_directory(self, *, directory: Path) -> list[tuple[Surface, Path]]:
        """Every file one configuration directory holds that a surface claims, with its surface.

        The walk is **each surface's own directory under this one, one level deep**: the
        configuration directory itself for the surfaces that live in it, and `directory /
        subdirectory` for a surface that owns one. A directory no surface owns — `inference/deck/`
        — is never entered at all, which is the property that keeps the walk from wandering into
        the parts of a configuration directory that are not configuration surfaces.

        A directory that does not exist is skipped rather than refused, and that goes for both
        levels: the global `~/.pipelex/` and a project's `.pipelex/` are both optional, and a
        machine that has never touched an inference backend has no `inference/` under either.
        """
        claimed: list[tuple[Surface, Path]] = []
        for subdirectory in sorted({surface.subdirectory for surface in self.surfaces}):
            owned_directory = directory / subdirectory
            if not owned_directory.is_dir():
                continue
            for path in sorted(owned_directory.iterdir()):
                if not path.is_file():
                    continue
                surface = self.surface_for_file(subdirectory=subdirectory, file_name=path.name)
                if surface is not None:
                    claimed.append((surface, path))
        return claimed


def _reject_duplicates(*, values: list[str], label: str) -> None:
    seen: set[str] = set()
    for value in values:
        if value in seen:
            msg = f"registry error: two surfaces share the {label} '{value}'"
            raise ValueError(msg)
        seen.add(value)


def _reject_duplicates_per_directory(*, values: list[tuple[Path, str]], label: str) -> None:
    """The same rule as `_reject_duplicates`, scoped to one directory.

    A base file and a tier glob are claims over a directory's own listing, so two surfaces collide
    on one only when they own the same directory.
    """
    seen: set[tuple[Path, str]] = set()
    for subdirectory, value in values:
        if (subdirectory, value) in seen:
            msg = f"registry error: two surfaces share the {label} '{value}' in the same directory '{subdirectory.as_posix()}'"
            raise ValueError(msg)
        seen.add((subdirectory, value))


def build_config_surface_registry() -> SurfaceRegistry:
    """The real registry: the configuration surfaces the `pipelex` package owns.

    A function rather than a module constant, so that nothing imports the real configuration
    models by merely importing this module, and so that every consumer has to state which
    registry it means.
    """
    return SurfaceRegistry(
        surfaces=[
            Surface(
                surface_id=PIPELEX_CONFIG_SURFACE_ID,
                title="The main Pipelex configuration",
                base_file=PIPELEX_CONFIG_FILE_NAME,
                tier_glob="pipelex_*.toml",
                config_model=PipelexConfig,
                defaults_layer_kind=DefaultsLayerKind.PACKAGED_DOCUMENT,
                packaged_document_path=_PACKAGE_ROOT / PIPELEX_CONFIG_FILE_NAME,
                kit_template_path=_KIT_CONFIGS_DIR / PIPELEX_CONFIG_FILE_NAME,
            ),
            Surface(
                surface_id=TELEMETRY_CONFIG_SURFACE_ID,
                title="Telemetry destinations and capture settings",
                base_file=TELEMETRY_CONFIG_FILE_NAME,
                tier_glob="telemetry_*.toml",
                config_model=TelemetryConfig,
                defaults_layer_kind=DefaultsLayerKind.MODEL_DEFAULTS,
                kit_template_path=_KIT_CONFIGS_DIR / TELEMETRY_CONFIG_FILE_NAME,
            ),
            Surface(
                surface_id=PIPELEX_SERVICE_CONFIG_SURFACE_ID,
                title="Pipelex service agreement and onboarding state",
                base_file=PIPELEX_SERVICE_CONFIG_FILE_NAME,
                config_model=PipelexServiceConfig,
                defaults_layer_kind=DefaultsLayerKind.MODEL_DEFAULTS,
                kit_template_path=_KIT_CONFIGS_DIR / PIPELEX_SERVICE_CONFIG_FILE_NAME,
            ),
        ]
    )
