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

from pipelex.cogt.model_backends.model_spec_document import (
    MODEL_SPEC_DEFAULTS_TABLE,
    InferenceModelSpecFileNode,
    describe_model_spec_document_rejection,
)
from pipelex.cogt.model_backends.model_spec_keys import is_header_shaped, is_legal_header_name
from pipelex.migration.exceptions import MigrationRegistryError
from pipelex.migration.fingerprint import SurfaceFingerprint, compute_fingerprint
from pipelex.suggested_fix import WILDCARD_SEGMENT
from pipelex.system.configuration.config_loader import BACKENDS_DIR_NAME, INFERENCE_DIR_NAME
from pipelex.system.configuration.config_surface import (
    INFERENCE_BACKEND_CONFIG_SURFACE_ID,
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

    COPIED_DOCUMENT = "copied_document"
    """A document shipped in the package and **copied** into the user's directory rather than merged
    beneath it — one inference backend definition per file. The values come from the model's own field
    defaults, applied to each entry as it is read, so an added key is absorbed exactly as it is for a
    packaged document; what is different is that the user's file stands alone, with nothing under it."""

    @property
    def is_layered_beneath_the_users_file(self) -> bool:
        """Whether a user's file is read *on top of* our document, or on its own.

        The one place it decides something: a migrated document is checked against the current schema
        the way it is really read, and for a layered surface that means beneath the reference
        document. A copied document has nothing beneath it, and merging two of them — one user's
        backend file over the reference copy of another — would validate a hybrid no machine has,
        turning both a false pass and a false failure into possibilities.
        """
        match self:
            case DefaultsLayerKind.PACKAGED_DOCUMENT | DefaultsLayerKind.MODEL_DEFAULTS:
                return True
            case DefaultsLayerKind.COPIED_DOCUMENT:
                return False


class DocumentShape(StrEnum):
    """What one of a surface's files *is*, as a document.

    Three things read it, and they have to agree or the gate goes green over a file that does not
    boot: what the fingerprint records, what "the current schema accepts this document" means, and
    which unnamed keys the diagnosis is willing to leave unexplained.
    """

    WHOLE_DOCUMENT = "whole_document"
    """The file is one instance of `config_model`: its root keys are ours and enumerable."""

    MODEL_SPEC_TABLES = "model_spec_tables"
    """The file is an inference backend definition — a `[defaults]` table plus one root table per
    model name, where `config_model` describes one such table rather than the whole document. Neither
    half validates alone; only their merge does, which is why this shape has a validator of its own."""

    @property
    def document_root_is_open(self) -> bool:
        """Whether the document's own root keys belong to the user."""
        match self:
            case DocumentShape.WHOLE_DOCUMENT:
                return False
            case DocumentShape.MODEL_SPEC_TABLES:
                return True


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

    document_shape: DocumentShape = DocumentShape.WHOLE_DOCUMENT
    """What one of this surface's files is, as a document — one instance of `config_model`, or a table
    per user-chosen key. See `DocumentShape`; everything the fingerprint, the ledger check and the
    diagnosis do differently for a backend definition file follows from this one declaration."""

    defaults_layer_kind: DefaultsLayerKind
    packaged_document_path: Path | None = None

    reference_document_path: Path | None = None
    """The shipped document a **copied-document** surface snapshots as its reference.

    Deliberately not a reuse of `packaged_document_path`, whose name means *merged beneath the user's
    file* — which this is not. What it is for: a later, non-pre-history entry is replayed over
    `defaults@N.toml`, so the surface owes the chain one real starting document even though nothing is
    layered beneath a user's file at boot."""

    kit_template_path: Path | None = None
    """The sparse starter file `pipelex init` copies into a configuration directory.

    A **convergence and neutrality witness only**, never a snapshot: it is read live, so there is
    no fixture to maintain and no golden to go stale. It earns its place beside the complete
    reference document because the two are different shapes — the complete document has every key
    set, the template has almost none — and an operation that misbehaves on an absent key would
    pass over one and fail over the other."""

    kit_template_dir: Path | None = None
    """The kit directory whose files `pipelex init` copies, when a surface's starter is a whole
    directory rather than one file.

    Every file in it that this surface claims becomes a witness, which is more of them than any other
    surface has and costs nothing: they are read live, and they are exactly the documents a fresh
    machine starts from. It is a *directory* and not a resolved list because building the registry
    must touch no filesystem — a registry that read a directory at construction would make every
    consumer, including the ones that never fingerprint anything, depend on the package layout."""

    @model_validator(mode="after")
    def check_the_surface_claims_some_file(self) -> Self:
        if self.base_file is None and self.tier_glob is None:
            msg = f"surface '{self.surface_id}': claims no file — a surface with no base file must claim its files by a tier glob"
            raise ValueError(msg)
        return self

    @model_validator(mode="after")
    def check_defaults_layer_is_reachable(self) -> Self:
        """Each defaults-layer kind names exactly the source it reads, and no other.

        The pairing is what makes `render_reference_document` and `read_defaults_document` total: each
        branch asserts the path its kind requires, and a surface that named the wrong one — or none —
        would fail at the first regeneration instead of at registry build, which is where a
        declaration error belongs.
        """
        declared_paths = {
            DefaultsLayerKind.PACKAGED_DOCUMENT: self.packaged_document_path,
            DefaultsLayerKind.COPIED_DOCUMENT: self.reference_document_path,
        }
        for kind, path in declared_paths.items():
            if (path is not None) != (self.defaults_layer_kind is kind):
                msg = (
                    f"surface '{self.surface_id}': defaults_layer_kind '{self.defaults_layer_kind}' and the "
                    f"document path declared for '{kind}' ({path!r}) disagree — each kind names the one "
                    f"document it reads, and a model-defaults surface names none"
                )
                raise ValueError(msg)
        return self

    @model_validator(mode="after")
    def check_the_kit_starter_is_one_thing(self) -> Self:
        if self.kit_template_path is not None and self.kit_template_dir is not None:
            msg = (
                f"surface '{self.surface_id}': names both a kit template file and a kit template directory — "
                f"the kit ships a surface one starter, either a file or a directory of them"
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
            document_root_is_open=self.document_shape.document_root_is_open,
        )

    def validate_document(self, *, document: dict[str, Any]) -> str | None:
        """Why the current schema refuses this document, or `None` when it accepts it.

        The seam the transform check asks *is a migrated file still loadable?* through, and the only
        place a surface's document shape decides what "loadable" means. For a whole document that is
        `config_model` validating it. For a backend definition file it is what the loader itself does
        — pop `[defaults]`, split the header-shaped keys off each model table, merge, validate the
        merge — because neither half validates alone and a check that projected the shape its own way
        could pass a document that does not boot.

        A **reason string rather than an exception**, on purpose: the caller reports it as one issue
        among many in its own vocabulary, and a new error class here would earn nothing while costing
        the error-identity snapshot and a generated reference page.
        """
        match self.document_shape:
            case DocumentShape.WHOLE_DOCUMENT:
                try:
                    self.config_model.model_validate(document)
                except ValidationError as exc:
                    return f"{self.config_model.__name__} rejects it — {exc}"
                return None
            case DocumentShape.MODEL_SPEC_TABLES:
                return describe_model_spec_document_rejection(document=document)

    def admits_unnamed_key(self, *, node_path: tuple[str, ...], document_node_path: tuple[str, ...], key: str) -> bool:
        """Whether a key the fingerprint cannot resolve is nevertheless one this surface expects.

        The diagnosis reports every path a migrated file carries that the current schema cannot
        explain, on **every** run, so a key class we ship and endorse must not be reported. A backend
        file has exactly one: a per-model request header (`x-portkey-provider`), which is a legal key
        by *shape* rather than by name and therefore resolves against no recorded path.

        Deliberately narrower than "the model allows extras": a typo (`promting_target`) is still
        named, because it is not header-shaped. A hyphenated spelling of a known field (`max-tokens`)
        *is* admitted here on purpose — the loader already rejects it by name with the right advice,
        and this channel has nothing to add to that.

        **And narrower than the schema path can express, which is why the document path is here
        too.** `[defaults]` and a model table are the same node to the fingerprint — both are the `*`
        beneath an open root — but they are not the same to the loader: a model table goes through
        `split_model_spec_keys`, and `[defaults]` is copied into every model of the file *unsplit*.
        So a header in `[defaults]` is `extra_forbidden` on every model, and admitting it here would
        report the one file that cannot boot as the one file with nothing to explain — on the command
        the boot error sends that reader to.

        Args:
            node_path: The containing table's path in the *fingerprint's* vocabulary, where an open
                node's children collapse to `*`.
            document_node_path: The containing table's path as the document spells it, which is what
                tells `[defaults]` from a model the user named.
            key: The unresolved key itself.
        """
        match self.document_shape:
            case DocumentShape.WHOLE_DOCUMENT:
                return False
            case DocumentShape.MODEL_SPEC_TABLES:
                return (
                    node_path == (WILDCARD_SEGMENT,)
                    and document_node_path != (MODEL_SPEC_DEFAULTS_TABLE,)
                    and is_header_shaped(key=key)
                    and is_legal_header_name(key=key)
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
            case DefaultsLayerKind.COPIED_DOCUMENT:
                # Likewise guaranteed by the validator above.
                assert self.reference_document_path is not None
                return self.reference_document_path.read_text(encoding="utf-8")
            case DefaultsLayerKind.MODEL_DEFAULTS:
                document: str = tomlkit.dumps(self.read_defaults_document())  # pyright: ignore[reportUnknownMemberType]
                return document

    def reference_documents(self) -> list[tuple[str, str]]:
        """Every document a replay must be neutral over, as `(label, text)` pairs.

        All of them are at the current schema by construction — the packaged defaults layer or the
        document the model's own defaults synthesize, plus whatever starter the kit ships — so none is
        a fixture anyone has to keep up to date.

        A surface whose kit starter is a whole directory is witnessed by every file in it that the
        surface claims, minus the one that is already the reference document: witnessing a document
        twice proves nothing, and reading it under two labels would report one defect as two.
        """
        documents = [("reference document", self.render_reference_document())]
        if self.kit_template_path is not None:
            documents.append(("kit template", self.kit_template_path.read_text(encoding="utf-8")))
        for path in self._kit_template_directory_files():
            documents.append((f"kit template '{path.name}'", path.read_text(encoding="utf-8")))
        return documents

    def _kit_template_directory_files(self) -> list[Path]:
        """The files of `kit_template_dir` this surface claims, sorted, minus its reference document.

        Read here rather than at registry build, so that constructing the registry touches no
        filesystem. A directory the package does not ship is empty rather than an error: the caller is
        collecting witnesses, and a missing one is the gate's own packaging problem, which the
        reference document's absence reports first and by name.
        """
        if self.kit_template_dir is None or not self.kit_template_dir.is_dir():
            return []
        return [
            path
            for path in sorted(self.kit_template_dir.iterdir())
            if path.is_file()
            and path != self.reference_document_path
            and (self.base_file == path.name or (self.tier_glob is not None and fnmatch(path.name, self.tier_glob)))
        ]

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
            case DefaultsLayerKind.COPIED_DOCUMENT:
                # **No defaults document, and none must be faked.** The reference document is one
                # backend definition among several, not a layer beneath the others, so reading it here
                # would attribute one file's values to every file of the surface — and the fingerprint
                # would record them as the defaults a migrated file may rely on.
                #
                # The rule the defaults layer exists to enforce holds anyway, for a better reason:
                # `check_defaults_layer` demands a value for every *required* path, and this surface
                # has none — every path of it sits under a `*` segment, and the projection beneath that
                # segment has no required field. So an added key is absorbed because nothing is
                # required of a file, not because a document supplies it.
                return {}
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
            # **Every `*.toml` directly in `inference/backends/`, and nothing else.**
            #
            # Not `inference/backends.toml`: it sits one level up, it is a different document
            # altogether — a table per backend, not per model — and no schema change has broken it.
            # The two `.md` files that live in the backend directory fall out by extension.
            #
            # Not `inference/deck/`: the model decks already have a manifest-driven sync with an
            # `x_custom_*` carve-out for what the user owns, and a second mechanism replaying a
            # ledger over the same files would be two tools writing one directory. Not
            # `inference/routing_profiles.toml` either: it has neither mechanism, but it also has no
            # break to repair, and a surface is claimed when there is something to carry forward.
            #
            # What *is* in scope is the schema of a backend file — which keys a model table may carry
            # — and not its content: which models a machine defines is the machine's business.
            Surface(
                surface_id=INFERENCE_BACKEND_CONFIG_SURFACE_ID,
                title="Inference backend model definitions",
                base_file=None,
                tier_glob="*.toml",
                subdirectory=Path(INFERENCE_DIR_NAME) / BACKENDS_DIR_NAME,
                config_model=InferenceModelSpecFileNode,
                document_shape=DocumentShape.MODEL_SPEC_TABLES,
                defaults_layer_kind=DefaultsLayerKind.COPIED_DOCUMENT,
                # `portkey.toml` of the kit, because it is the one shipped backend file that
                # exercises both halves of the document shape — a `[defaults]` block *and*
                # header-shaped per-model keys — and it is where the per-model occurrences of the key
                # the first entry deletes actually were. A richer starting document is the one a
                # later, non-pre-history entry is replayed over.
                reference_document_path=_KIT_CONFIGS_DIR / INFERENCE_DIR_NAME / BACKENDS_DIR_NAME / "portkey.toml",
                kit_template_dir=_KIT_CONFIGS_DIR / INFERENCE_DIR_NAME / BACKENDS_DIR_NAME,
            ),
        ]
    )
