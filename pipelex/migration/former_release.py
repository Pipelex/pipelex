"""What a former release left in the configuration directories, found by reading them and nothing else.

Releases up to v0.72 ran models through the Pipelex Gateway and offered Pipelex Manifold as a private beta. The
installations they set up still carry what that took: a `pipelex_gateway` and a `pipelex_manifold` table in
`inference/backends.toml`, each with a per-backend file beside the others, routing profiles that send every model to
one of them (`active = "all_pipelex_gateway"` above all), a `model_specs_section` key naming specs the remote
configuration used to serve, the `pipelex_service.toml` that recorded the Gateway's terms acceptance, and the
`pipelex_gateway_models*.md` model lists. The runtime no longer has either backend, so an enabled table or an active
profile pointing at one stops every boot with a refusal about one file that says nothing of the release behind it.

`detect_former_release_across` is the one reading of that state. The boot, `pipelex doctor`, `pipelex init`'s inspect
stage and the `pipelex migrate` cleanup (`former_release_cleanup.py`) all ask it or `former_release_boot_blockers`,
which reads the same way, so what one of them calls a former release's configuration is what every other one finds and
removes. It reads, and it never writes or imports anything from the CLI.

**The documents are read as the boot merges them, across directories.** A boot reads one base `backends.toml` and one
base `routing_profiles.toml` — the project's when it has one, the home's otherwise — then the home's override, then the
project's (`inference_merge_sequences`). A profile one directory defines can be made active by a file in the other, and
an override can retarget a profile its base defines, so each finding is decided over every sequence its file is read
in, never over its own directory alone.

**A finding says which file it is in, and whether it stops the boot.** Only two shapes do: a retired backend, or a
backend still naming `model_specs_section`, left enabled; and an active routing profile that sends models to a retired
backend. Everything else — a disabled table, a profile nobody activates, the files beside the backends, the service
file — is inert, and is found so that the cleanup leaves nothing of that release behind. Whether a machine's boot is
refused is `former_release_boot_blockers` over the exact sequences that boot reads: a per-directory reading can be
wrong both ways, since a project's own base hides the home's, and an `active` in one directory can name a profile
defined in the other.

**What the cleanup does to a routing profile is decided per file.** A profile goes from a file whose own `default` is a
retired backend, unless another file still gives it a live one: then only that `default` goes, and the user's routes
stay. A part of a profile left in an override, whose definition goes from every file before it, goes with it. An
`active` naming a profile that goes moves off it in every file that sets it.

See `docs/migration-ledger.md` → "A former release's configuration".
"""

import copy
from collections.abc import Sequence
from enum import StrEnum
from pathlib import Path
from typing import Any, cast

from pydantic import BaseModel, ConfigDict, Field

from pipelex.base_exceptions import PipelexUnexpectedError
from pipelex.core.validation import MIGRATE_COMMAND
from pipelex.kit.paths import RETIRED_SERVICE_FILE_NAME, get_kit_configs_dir
from pipelex.system.configuration.config_loader import (
    BACKENDS_DIR_NAME,
    BACKENDS_FILE_NAME,
    BACKENDS_OVERRIDE_FILE_NAME,
    INFERENCE_DIR_NAME,
    ROUTING_PROFILES_FILE_NAME,
    ROUTING_PROFILES_OVERRIDE_FILE_NAME,
)
from pipelex.tools.misc.exceptions import TomlError
from pipelex.tools.misc.json_utils import deep_update
from pipelex.tools.misc.toml_utils import load_toml_from_path

#: The command that sets Pipelex up, which offers the cleanup first when it finds what a former release left.
INIT_COMMAND = "pipelex init"

#: The backends a former release shipped that this one no longer has: the Pipelex Gateway and Pipelex Manifold.
RETIRED_BACKEND_NAMES: frozenset[str] = frozenset({"pipelex_gateway", "pipelex_manifold"})

#: The routing profiles a former release shipped to send every model to one of them. Recognized by name only where the
#: file read holds no definition of the profile: an override naming one over a base in another directory.
RETIRED_ROUTING_PROFILE_NAMES: frozenset[str] = frozenset({"all_pipelex_gateway", "all_pipelex_manifold"})

#: The `backends.toml` key that named the remote-configuration section holding a backend's model specs.
MODEL_SPECS_SECTION_KEY = "model_specs_section"

#: The model lists a former release copied beside the backend files, a Markdown one and its plain-text twin.
GATEWAY_MODELS_REFERENCE_GLOB = "pipelex_gateway_models*.md"

#: The routing profile tables that route a pattern to a backend. `fallback_order` is not one: a disabled or absent
#: backend in it is skipped, so it never stops a boot and is left as written.
ROUTE_TABLE_KEYS: tuple[str, ...] = ("routes", "optional_routes")

#: The keys of a routing profile document the cleanup addresses.
ROUTING_PROFILES_KEY = "profiles"
ACTIVE_KEY = "active"

_ROUTES_KEY = "routes"
_DEFAULT_KEY = "default"
_DESCRIPTION_KEY = "description"
_ENABLED_KEY = "enabled"


class FormerReleaseFindingKind(StrEnum):
    """One kind of thing a former release left behind."""

    RETIRED_BACKEND_TABLE = "retired_backend_table"
    """A `pipelex_gateway` or `pipelex_manifold` table in `backends.toml` or its override. Stops the boot when enabled."""

    MODEL_SPECS_SECTION_KEY = "model_specs_section_key"
    """A `model_specs_section` key on another backend's table. Stops the boot when that backend is enabled."""

    RETIRED_BACKEND_FILE = "retired_backend_file"
    """`inference/backends/pipelex_gateway.toml` or `pipelex_manifold.toml`, a retired backend's per-model file."""

    GATEWAY_MODELS_REFERENCE = "gateway_models_reference"
    """A `pipelex_gateway_models*.md` list of the models the Gateway served, beside the backend files."""

    SERVICE_FILE = "service_file"
    """The `pipelex_service.toml` that recorded the Gateway's terms acceptance."""

    RETIRED_ROUTING_PROFILE = "retired_routing_profile"
    """A routing profile whose default backend is a retired one, or the part an override holds of one, which goes."""

    RETIRED_PROFILE_DEFAULT = "retired_profile_default"
    """The `default` of a routing profile that otherwise stays, naming a retired backend: an override retargeting a
    profile its base defines, or a base whose profile another file retargets to a live backend. Only the key goes."""

    ROUTE_TO_RETIRED_BACKEND = "route_to_retired_backend"
    """A route of a profile that otherwise stays, sending a pattern to a retired backend."""

    ACTIVE_ROUTING_PROFILE = "active_routing_profile"
    """The active routing profile sends models to a retired backend, by default or by a route. Stops the boot."""

    @property
    def is_a_file_of_its_own(self) -> bool:
        """Whether the finding is a whole file, which the cleanup removes, rather than something inside a document."""
        match self:
            case (
                FormerReleaseFindingKind.RETIRED_BACKEND_FILE
                | FormerReleaseFindingKind.GATEWAY_MODELS_REFERENCE
                | FormerReleaseFindingKind.SERVICE_FILE
            ):
                return True
            case (
                FormerReleaseFindingKind.RETIRED_BACKEND_TABLE
                | FormerReleaseFindingKind.MODEL_SPECS_SECTION_KEY
                | FormerReleaseFindingKind.RETIRED_ROUTING_PROFILE
                | FormerReleaseFindingKind.RETIRED_PROFILE_DEFAULT
                | FormerReleaseFindingKind.ROUTE_TO_RETIRED_BACKEND
                | FormerReleaseFindingKind.ACTIVE_ROUTING_PROFILE
            ):
                return False


class FormerReleaseFinding(BaseModel):
    """One thing a former release left, in one file.

    Every part of it is a path, a key, or one of the retired names this module knows: no value read from the file is
    carried, the rule every migration report holds to.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: FormerReleaseFindingKind = Field(strict=False)
    file_path: Path
    subject: str | None = None
    """The backend or routing profile the finding is about; `None` for a file found by its name alone."""

    route_pattern: str | None = None
    """The model pattern of a route to a retired backend: the route itself, or the one that makes an active profile retired."""

    route_table: str | None = None
    """Which of the profile's route tables holds that route, `routes` or `optional_routes`."""

    retired_backend: str | None = None
    """Which retired backend a routing profile or a route sends models to."""

    blocks_boot: bool = False
    """Whether this stops a boot that reads the file: the runtime refuses it rather than ignoring it."""

    profile_is_removed: bool = False
    """For an active routing profile: whether the cleanup removes the profile it names, so `active` has to move off it.
    When the profile stays, losing only a retired `default` or a route, the file's `active` is left as it is."""

    @property
    def description(self) -> str:
        """The finding as one sentence, for a report a person reads."""
        where = f"'{self.file_path}'"
        match self.kind:
            case FormerReleaseFindingKind.RETIRED_BACKEND_TABLE:
                state = "enables" if self.blocks_boot else "declares"
                return f"{where} {state} the '{self.subject}' backend, which this release no longer has"
            case FormerReleaseFindingKind.MODEL_SPECS_SECTION_KEY:
                state = "enabled " if self.blocks_boot else ""
                return (
                    f"the {state}'{self.subject}' backend in {where} still names '{MODEL_SPECS_SECTION_KEY}', "
                    "whose model specs are no longer downloaded"
                )
            case FormerReleaseFindingKind.RETIRED_BACKEND_FILE:
                return f"{where} holds the model settings of the '{self.subject}' backend, which this release no longer has"
            case FormerReleaseFindingKind.GATEWAY_MODELS_REFERENCE:
                return f"{where} lists the models the Pipelex Gateway served"
            case FormerReleaseFindingKind.SERVICE_FILE:
                return f"{where} recorded the Pipelex Gateway's terms acceptance, and nothing reads it any more"
            case FormerReleaseFindingKind.RETIRED_ROUTING_PROFILE:
                return f"{where} defines the routing profile '{self.subject}', which sends models to '{self.retired_backend}'"
            case FormerReleaseFindingKind.RETIRED_PROFILE_DEFAULT:
                return f"the routing profile '{self.subject}' in {where} sets its default backend to '{self.retired_backend}'"
            case FormerReleaseFindingKind.ROUTE_TO_RETIRED_BACKEND:
                return f"the routing profile '{self.subject}' in {where} routes '{self.route_pattern}' to '{self.retired_backend}'"
            case FormerReleaseFindingKind.ACTIVE_ROUTING_PROFILE:
                if self.route_pattern is not None:
                    return (
                        f"{where} makes '{self.subject}' the active routing profile, and it routes '{self.route_pattern}' to '{self.retired_backend}'"
                    )
                target = f"'{self.retired_backend}'" if self.retired_backend else "a backend this release no longer has"
                return f"{where} makes '{self.subject}' the active routing profile, and it sends models to {target}"


class FormerReleaseFindings(BaseModel):
    """Everything a former release left in one configuration directory."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    config_dir: Path
    findings: list[FormerReleaseFinding] = Field(default_factory=list[FormerReleaseFinding])

    @property
    def is_clean(self) -> bool:
        return not self.findings

    @property
    def blocks_boot(self) -> bool:
        """Whether a finding here stops one of the sequences it was read in.

        Never a machine's verdict: whether its boot is refused is `former_release_boot_blockers` over the files that
        boot merges, which a project's own base or the other directory's override can change both ways.
        """
        return any(finding.blocks_boot for finding in self.findings)

    @property
    def file_paths(self) -> list[Path]:
        """The files the findings are in, each once, in the order they were found."""
        seen: dict[Path, None] = {}
        for finding in self.findings:
            seen.setdefault(finding.file_path, None)
        return list(seen)


def backend_library_paths_in(*, config_dir: Path) -> list[Path]:
    """One directory's `backends.toml` and its personal override, in merge order."""
    inference_dir = config_dir / INFERENCE_DIR_NAME
    return [inference_dir / BACKENDS_FILE_NAME, inference_dir / BACKENDS_OVERRIDE_FILE_NAME]


def routing_profile_library_paths_in(*, config_dir: Path) -> list[Path]:
    """One directory's `routing_profiles.toml` and its personal override, in merge order."""
    inference_dir = config_dir / INFERENCE_DIR_NAME
    return [inference_dir / ROUTING_PROFILES_FILE_NAME, inference_dir / ROUTING_PROFILES_OVERRIDE_FILE_NAME]


def distinct_config_dirs(*, config_dirs: Sequence[Path]) -> list[Path]:
    """The directories, each once, in the order given: one named twice, or through a link, is read once."""
    seen: set[Path] = set()
    directories: list[Path] = []
    for config_dir in config_dirs:
        resolved = config_dir.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        directories.append(config_dir)
    return directories


def inference_merge_sequences(*, config_dirs: Sequence[Path], file_name: str, override_file_name: str) -> list[list[Path]]:
    """The merge sequences a boot reads one inference document from, over the home and a project directory.

    `config_dirs` is in tier order, as `ConfigLoader.existing_config_dirs` gives it: the home configuration directory,
    then the project's. A boot started outside the project reads the home's base and override; one started in it reads
    the project's base when the project has one and the home's otherwise, then the home's override, then the project's.
    That is `ConfigLoader._inference_file_paths`, which a test holds this derivation to. Over one directory, the one
    sequence is its base and its override.

    Args:
        config_dirs: The home directory, then the project's; a directory named twice counts once.
        file_name: The base file's name, `backends.toml` or `routing_profiles.toml`.
        override_file_name: Its override's name.

    Returns:
        One sequence per kind of boot, each base first: the home's alone, then the project's when there is one.
    """
    directories = distinct_config_dirs(config_dirs=config_dirs)
    if not directories:
        return []
    if len(directories) > 2:
        msg = f"a boot reads the home and one project directory, and was handed {len(directories)} directories — caller bug"
        raise PipelexUnexpectedError(msg)
    home_dir = directories[0]
    home_sequence = [home_dir / INFERENCE_DIR_NAME / file_name, home_dir / INFERENCE_DIR_NAME / override_file_name]
    if len(directories) == 1:
        return [home_sequence]
    project_inference_dir = directories[1] / INFERENCE_DIR_NAME
    project_base = project_inference_dir / file_name
    base = project_base if project_base.exists() else home_sequence[0]
    return [home_sequence, [base, home_sequence[1], project_inference_dir / override_file_name]]


def detect_former_release(*, config_dir: Path) -> FormerReleaseFindings:
    """Find what a former release left in one configuration directory standing alone.

    The reading of a machine with that one directory; `detect_former_release_across` reads the home and a project
    together, as their boot does, and is what the cleanup and the commands ask.
    """
    return detect_former_release_across(config_dirs=[config_dir])[0]


def detect_former_release_across(*, config_dirs: Sequence[Path]) -> list[FormerReleaseFindings]:
    """Find what a former release left in the home and project configuration directories, read as their boots read them.

    A pure read: nothing is written, and a directory or a file that is not there is simply clean. A document that does
    not parse is skipped rather than raised, because whether it parses is for the boot and the doctor to report, and
    the rest can still be judged.

    Args:
        config_dirs: The home directory, then the project's, as `ConfigLoader.existing_config_dirs` lists them.

    Returns:
        The findings of each distinct directory, clean ones included, in the order given; each in a stable order:
        the backend library, the files beside the backends, the service file, then the routing profile library.
    """
    directories = distinct_config_dirs(config_dirs=config_dirs)
    backend_findings = backend_library_findings(
        sequences=inference_merge_sequences(config_dirs=directories, file_name=BACKENDS_FILE_NAME, override_file_name=BACKENDS_OVERRIDE_FILE_NAME)
    )
    routing_findings = routing_profile_findings(
        sequences=inference_merge_sequences(
            config_dirs=directories, file_name=ROUTING_PROFILES_FILE_NAME, override_file_name=ROUTING_PROFILES_OVERRIDE_FILE_NAME
        )
    )
    all_findings: list[FormerReleaseFindings] = []
    for config_dir in directories:
        backend_files = set(backend_library_paths_in(config_dir=config_dir))
        routing_files = set(routing_profile_library_paths_in(config_dir=config_dir))
        findings = [finding for finding in backend_findings if finding.file_path in backend_files]
        findings.extend(_backend_directory_findings(backends_dir=config_dir / INFERENCE_DIR_NAME / BACKENDS_DIR_NAME))
        service_file = config_dir / RETIRED_SERVICE_FILE_NAME
        if service_file.is_file():
            findings.append(FormerReleaseFinding(kind=FormerReleaseFindingKind.SERVICE_FILE, file_path=service_file))
        findings.extend(finding for finding in routing_findings if finding.file_path in routing_files)
        all_findings.append(FormerReleaseFindings(config_dir=config_dir, findings=findings))
    return all_findings


def former_release_boot_blockers(
    *, backends_library_paths: Sequence[Path], routing_profile_library_paths: Sequence[Path]
) -> list[FormerReleaseFinding]:
    """What a former release left that would stop a boot reading exactly these files.

    The boot merges a base file with the overrides of the home and the project directories, so a base in one directory
    can be lifted by an override in the other; reading the same sequences the boot reads is what keeps this from
    refusing a boot that would have succeeded, or passing one that will not.

    Args:
        backends_library_paths: The `backends.toml` merge sequence the boot reads, base first.
        routing_profile_library_paths: The `routing_profiles.toml` merge sequence the boot reads, base first.

    Returns:
        The blocking findings, the backend library's first; empty when nothing a former release left stops the boot.
    """
    findings = backend_library_findings(sequences=[list(backends_library_paths)]) + routing_profile_findings(
        sequences=[list(routing_profile_library_paths)]
    )
    return [finding for finding in findings if finding.blocks_boot]


def kit_routing_profile_library_path() -> Path:
    """The kit's `routing_profiles.toml`, the one `pipelex init` copies."""
    return Path(str(get_kit_configs_dir())) / INFERENCE_DIR_NAME / ROUTING_PROFILES_FILE_NAME


def kit_default_routing_profile_name() -> str:
    """The routing profile the kit makes active, which the cleanup moves a retired active profile to.

    Read from the kit rather than spelled here, so the cleanup lands on whatever `pipelex init` would set up.
    """
    active = load_toml_from_path(kit_routing_profile_library_path()).get(ACTIVE_KEY)
    if not isinstance(active, str):
        msg = f"the kit's routing profile library '{kit_routing_profile_library_path()}' names no active profile — packaging bug"
        raise PipelexUnexpectedError(msg)
    return active


def describe_former_release_boot_refusal(*, blockers: Sequence[FormerReleaseFinding]) -> str:
    """The message of the one error a boot raises on what a former release left: what stops it, and the two remedies.

    Args:
        blockers: The findings that stop the boot, as `former_release_boot_blockers` returns them.
    """
    lines = [
        (
            "This configuration was set up by a former Pipelex release, which ran models through the Pipelex Gateway or "
            "Pipelex Manifold. This release has neither, so it cannot start on these files:"
        ),
        *(f"- {finding.description}" for finding in blockers),
        "",
        (
            f"Run `{MIGRATE_COMMAND}` to clean it up. It removes what that release left in the home configuration directory and "
            f"in the project's `.pipelex/`, keeps a copy of each file it changes or removes, and moves the active routing profile to "
            f"'{kit_default_routing_profile_name()}', which sends each model to the first enabled backend that serves it."
        ),
        (
            f"Or run `{INIT_COMMAND}`, which offers the same cleanup and then sets Pipelex up again: on the hosted Pipelex API "
            "with a Pipelex API key, or on this machine with your own provider keys."
        ),
    ]
    return "\n".join(lines)


def backend_library_findings(*, sequences: Sequence[Sequence[Path]]) -> list[FormerReleaseFinding]:
    """The retired backend tables and `model_specs_section` keys in the `backends.toml` merge sequences.

    Each file holding one is reported once; whether it stops the boot is read off the merged document of each sequence
    the file is read in, so an override that disables a table lifts the finding in the base too.
    """
    documents = _read_documents(sequences=sequences)
    read_sequences = _read_sequences(sequences=sequences, documents=documents)
    merged_documents = [(set(sequence), _merged(documents=[documents[path] for path in sequence])) for sequence in read_sequences]
    findings: list[FormerReleaseFinding] = []
    for path, document in documents.items():
        for backend_name, backend_table in document.items():
            if not isinstance(backend_table, dict):
                continue
            if backend_name in RETIRED_BACKEND_NAMES:
                kind = FormerReleaseFindingKind.RETIRED_BACKEND_TABLE
            elif MODEL_SPECS_SECTION_KEY in backend_table:
                kind = FormerReleaseFindingKind.MODEL_SPECS_SECTION_KEY
            else:
                continue
            blocks_boot = any(_is_enabled(document=merged, backend_name=backend_name) for members, merged in merged_documents if path in members)
            findings.append(FormerReleaseFinding(kind=kind, file_path=path, subject=backend_name, blocks_boot=blocks_boot))
    return findings


def routing_profile_findings(*, sequences: Sequence[Sequence[Path]]) -> list[FormerReleaseFinding]:
    """The retired profiles, retired defaults, routes to retired backends and retired active profiles in the `routing_profiles.toml` sequences.

    What goes from each profile table is decided per file over every sequence the file is read in (`_profile_fates`),
    and each `active` is judged over each sequence that reads it (`_active_profile_findings`).
    """
    documents = _read_documents(sequences=sequences)
    read_sequences = _read_sequences(sequences=sequences, documents=documents)
    fates = _profile_fates(sequences=read_sequences, documents=documents)
    findings = _active_profile_findings(sequences=read_sequences, documents=documents, fates=fates)
    for path, document in documents.items():
        for profile_name, profile in _profiles_of(document=document).items():
            fate, retired_backend = fates[path, profile_name]
            if fate is _ProfileFate.REMOVED:
                findings.append(
                    FormerReleaseFinding(
                        kind=FormerReleaseFindingKind.RETIRED_ROUTING_PROFILE, file_path=path, subject=profile_name, retired_backend=retired_backend
                    )
                )
                continue
            if fate is _ProfileFate.LOSES_ITS_DEFAULT:
                findings.append(
                    FormerReleaseFinding(
                        kind=FormerReleaseFindingKind.RETIRED_PROFILE_DEFAULT, file_path=path, subject=profile_name, retired_backend=retired_backend
                    )
                )
            for route_table, route_pattern, backend_name in retired_routes_of(profile=profile):
                findings.append(
                    FormerReleaseFinding(
                        kind=FormerReleaseFindingKind.ROUTE_TO_RETIRED_BACKEND,
                        file_path=path,
                        subject=profile_name,
                        route_pattern=route_pattern,
                        route_table=route_table,
                        retired_backend=backend_name,
                    )
                )
    return findings


def retired_routes_of(*, profile: dict[str, Any]) -> list[tuple[str, str, str]]:
    """The `(route table, pattern, backend)` routes and optional routes of one profile that name a retired backend, in file order."""
    retired: list[tuple[str, str, str]] = []
    for route_table_key in ROUTE_TABLE_KEYS:
        route_table = profile.get(route_table_key)
        if not isinstance(route_table, dict):
            continue
        for route_pattern, backend_name in cast("dict[str, Any]", route_table).items():
            if isinstance(backend_name, str) and backend_name in RETIRED_BACKEND_NAMES:
                retired.append((route_table_key, route_pattern, backend_name))
    return retired


class _ProfileFate(StrEnum):
    """What the cleanup does to one profile table in one file."""

    KEPT = "kept"
    LOSES_ITS_DEFAULT = "loses_its_default"
    REMOVED = "removed"


def _profile_fates(*, sequences: list[list[Path]], documents: dict[Path, dict[str, Any]]) -> dict[tuple[Path, str], tuple[_ProfileFate, str | None]]:
    """What becomes of each profile table of each file, with the retired backend that decides it.

    A table whose own `default` is a retired backend goes, unless the profile stays alive without it: a file read
    before this one keeps a definition of it, or a file read after gives it a live `default`. Then only the `default`
    goes, and the routes the user tuned stay. A table with no `default` of its own and no `description`, in a file
    whose every earlier definition of the profile goes, is a part of a profile that no longer exists, and goes too:
    left alone, it would be a profile with no description, which the boot refuses. Files are decided in the order
    they are read, so a file's earlier neighbours are always decided first.
    """
    fates: dict[tuple[Path, str], tuple[_ProfileFate, str | None]] = {}
    for path in _in_reading_order(sequences=sequences):
        earlier = _neighbours(path=path, sequences=sequences, before=True)
        later = _neighbours(path=path, sequences=sequences, before=False)
        for profile_name, profile in _profiles_of(document=documents[path]).items():
            earlier_definitions = [neighbour for neighbour in earlier if profile_name in _profiles_of(document=documents[neighbour])]
            kept_earlier = any(fates[neighbour, profile_name][0] is not _ProfileFate.REMOVED for neighbour in earlier_definitions)
            own_default = profile.get(_DEFAULT_KEY)
            if _names_a_retired_backend(value=own_default):
                later_live_default = any(
                    _names_a_live_backend(value=_profiles_of(document=documents[neighbour])[profile_name].get(_DEFAULT_KEY))
                    for neighbour in later
                    if profile_name in _profiles_of(document=documents[neighbour])
                )
                fate = _ProfileFate.LOSES_ITS_DEFAULT if kept_earlier or later_live_default else _ProfileFate.REMOVED
                fates[path, profile_name] = (fate, cast("str", own_default))
            elif earlier_definitions and not kept_earlier and own_default is None and _DESCRIPTION_KEY not in profile:
                fates[path, profile_name] = (_ProfileFate.REMOVED, fates[earlier_definitions[0], profile_name][1])
            else:
                fates[path, profile_name] = (_ProfileFate.KEPT, None)
    return fates


def _active_profile_findings(
    *,
    sequences: list[list[Path]],
    documents: dict[Path, dict[str, Any]],
    fates: dict[tuple[Path, str], tuple[_ProfileFate, str | None]],
) -> list[FormerReleaseFinding]:
    """Each file whose `active` names a profile sending models to a retired backend, or one the cleanup removes.

    Every such file is reported, because each is something the cleanup may have to move; only the last file of a
    sequence to set `active` is the one that boot reads, so only its finding can stop the boot. A file read in two
    sequences is reported once, with what either says. Optional routes are not counted: one naming a disabled backend
    is inert, and the boot never refuses it.
    """
    found: dict[Path, FormerReleaseFinding] = {}
    for sequence in sequences:
        merged_profiles = _profiles_of(document=_merged(documents=[documents[path] for path in sequence]))
        setters = [(path, documents[path][ACTIVE_KEY]) for path in sequence if ACTIVE_KEY in documents[path]]
        for index, (path, active) in enumerate(setters):
            if not isinstance(active, str):
                continue
            finding = _active_profile_finding(
                path=path,
                active=active,
                is_read_by_the_boot=index == len(setters) - 1,
                merged_profiles=merged_profiles,
                still_defined=any(
                    fates[neighbour, active][0] is not _ProfileFate.REMOVED
                    for neighbour in sequence
                    if active in _profiles_of(document=documents[neighbour])
                ),
            )
            if finding is not None:
                found[path] = _combined(earlier=found.get(path), later=finding)
    return [found[path] for path in documents if path in found]


def _active_profile_finding(
    *, path: Path, active: str, is_read_by_the_boot: bool, merged_profiles: dict[str, dict[str, Any]], still_defined: bool
) -> FormerReleaseFinding | None:
    """One file's `active`, judged over one sequence: whether it names a retired profile, and whether that profile goes."""
    defined = active in merged_profiles
    merged_default = merged_profiles[active].get(_DEFAULT_KEY) if defined else None
    default_is_retired = _names_a_retired_backend(value=merged_default)
    is_a_retired_name = not defined and active in RETIRED_ROUTING_PROFILE_NAMES
    removed = (defined and not still_defined) or is_a_retired_name
    # Optional routes are left out: the boot refuses a route to a backend it cannot reach, never an optional one.
    retired_route = (
        next((route for route in retired_routes_of(profile=merged_profiles[active]) if route[0] == _ROUTES_KEY), None)
        if defined and not default_is_retired
        else None
    )
    if not (default_is_retired or removed or retired_route):
        return None
    retired_backend = cast("str", merged_default) if default_is_retired else (retired_route[2] if retired_route else None)
    return FormerReleaseFinding(
        kind=FormerReleaseFindingKind.ACTIVE_ROUTING_PROFILE,
        file_path=path,
        subject=active,
        route_pattern=retired_route[1] if retired_route else None,
        route_table=retired_route[0] if retired_route else None,
        retired_backend=retired_backend,
        blocks_boot=is_read_by_the_boot and (default_is_retired or is_a_retired_name or retired_route is not None),
        profile_is_removed=removed,
    )


def _combined(*, earlier: FormerReleaseFinding | None, later: FormerReleaseFinding) -> FormerReleaseFinding:
    """One file's `active` judged over two sequences: the stronger reading, which either stopping the boot or removing the profile makes."""
    if earlier is None:
        return later

    def strength(*, finding: FormerReleaseFinding) -> int:
        return 2 if finding.profile_is_removed else 1 if finding.route_pattern is None else 0

    primary = earlier if strength(finding=earlier) >= strength(finding=later) else later
    return primary.model_copy(
        update={
            "blocks_boot": earlier.blocks_boot or later.blocks_boot,
            "profile_is_removed": earlier.profile_is_removed or later.profile_is_removed,
        }
    )


def _backend_directory_findings(*, backends_dir: Path) -> list[FormerReleaseFinding]:
    """The retired backends' per-model files and the Gateway's model lists, beside the backend files."""
    findings = [
        FormerReleaseFinding(
            kind=FormerReleaseFindingKind.RETIRED_BACKEND_FILE, file_path=backends_dir / f"{backend_name}.toml", subject=backend_name
        )
        for backend_name in sorted(RETIRED_BACKEND_NAMES)
        if (backends_dir / f"{backend_name}.toml").is_file()
    ]
    if backends_dir.is_dir():
        findings.extend(
            FormerReleaseFinding(kind=FormerReleaseFindingKind.GATEWAY_MODELS_REFERENCE, file_path=path)
            for path in sorted(backends_dir.glob(GATEWAY_MODELS_REFERENCE_GLOB))
            if path.is_file()
        )
    return findings


def _read_documents(*, sequences: Sequence[Sequence[Path]]) -> dict[Path, dict[str, Any]]:
    """Each file of the sequences that exists and parses, with its document, each once, in the order first met."""
    documents: dict[Path, dict[str, Any]] = {}
    for sequence in sequences:
        for path in sequence:
            if path in documents or not path.is_file():
                continue
            try:
                documents[path] = load_toml_from_path(path)
            except (OSError, TomlError, UnicodeDecodeError):
                continue
    return documents


def _read_sequences(*, sequences: Sequence[Sequence[Path]], documents: dict[Path, dict[str, Any]]) -> list[list[Path]]:
    """The sequences without the files that are not there or did not parse, which the boot reads as nothing."""
    return [[path for path in sequence if path in documents] for sequence in sequences]


def _in_reading_order(*, sequences: list[list[Path]]) -> list[Path]:
    """Every file of the sequences, each after every file read before it in any of them."""
    remaining = list(dict.fromkeys(path for sequence in sequences for path in sequence))
    ordered: list[Path] = []
    while remaining:
        ready = next(path for path in remaining if set(_neighbours(path=path, sequences=sequences, before=True)) <= set(ordered))
        ordered.append(ready)
        remaining.remove(ready)
    return ordered


def _neighbours(*, path: Path, sequences: list[list[Path]], before: bool) -> list[Path]:
    """The files read before (or after) this one, in any sequence that reads it, each once."""
    neighbours: dict[Path, None] = {}
    for sequence in sequences:
        if path not in sequence:
            continue
        index = sequence.index(path)
        for neighbour in sequence[:index] if before else sequence[index + 1 :]:
            neighbours.setdefault(neighbour, None)
    return list(neighbours)


def _merged(*, documents: list[dict[str, Any]]) -> dict[str, Any]:
    """The documents deep-merged in order, as the loaders merge a base and its overrides.

    Each is copied first: `deep_update` stores the tables of the first document it is given by reference, so merging
    the originals would let an override rewrite the base document every per-file finding is read from.
    """
    merged: dict[str, Any] = {}
    for document in documents:
        deep_update(merged, updates=copy.deepcopy(document))
    return merged


def _profiles_of(*, document: dict[str, Any]) -> dict[str, dict[str, Any]]:
    profiles = document.get(ROUTING_PROFILES_KEY)
    if not isinstance(profiles, dict):
        return {}
    return {
        profile_name: cast("dict[str, Any]", profile)
        for profile_name, profile in cast("dict[str, Any]", profiles).items()
        if isinstance(profile, dict)
    }


def _names_a_retired_backend(*, value: Any) -> bool:
    return isinstance(value, str) and value in RETIRED_BACKEND_NAMES


def _names_a_live_backend(*, value: Any) -> bool:
    return isinstance(value, str) and value not in RETIRED_BACKEND_NAMES


def _is_enabled(*, document: dict[str, Any], backend_name: str) -> bool:
    """Whether the backend loader would load this table: it is a table, and `enabled` is not false. It defaults to true."""
    backend_table = document.get(backend_name)
    if not isinstance(backend_table, dict):
        return False
    return bool(cast("dict[str, Any]", backend_table).get(_ENABLED_KEY, True))
