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

**A finding says which file it is in, and whether it stops the boot.** The shapes that do are the ones the boot
refuses: a retired backend, or a backend still naming `model_specs_section`, left enabled; and an active routing
profile that sends models to a retired backend, or a retired profile no file defines. Everything else — a disabled
table, a profile nobody activates, the files beside the backends, the service file — is inert, and is found so that the
cleanup leaves nothing of that release behind. Whether a machine's boot is refused is `former_release_boot_blockers`
over the exact sequences that boot reads: a per-directory reading can be wrong both ways, since a project's own base
hides the home's, and an `active` in one directory can name a profile defined in the other.

**What the cleanup does to the routing profiles is planned per boot, and checked before anything is written.** A
profile goes from a file whose own `default` is a retired backend, unless the boot reading it still has the profile
alive — a file before keeps it, or a file after gives it a live `default` — and then only that `default` goes. A file
both boots read keeps whatever either boot needs. Then each way of moving the `active` keys the release spoiled is tried
on each boot's library as the cleanup would leave it (`_routing_plan`): no plan may stop a boot that starts today or
change the profile it starts on, a profile left with nothing to route by counts as gone, and the project's own override
may be given an `active` of its own so that a change one boot needs does not reach the other. Where nothing can suit
both boots, the shared file is left as it is, for a hand edit, and the findings say so (`FormerReleaseFindings.hand_edits`).

See `docs/migration-ledger.md` → "A former release's configuration".
"""

import copy
import itertools
from collections.abc import Mapping, Sequence
from enum import StrEnum
from pathlib import Path
from typing import Any, NamedTuple, cast

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from pipelex.base_exceptions import PipelexUnexpectedError
from pipelex.cogt.model_routing.routing_profile_factory import RoutingProfileLibraryBlueprint
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
from pipelex.tools.misc.toml_utils import load_toml_from_content, load_toml_from_path

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
_FALLBACK_ORDER_KEY = "fallback_order"
_ENABLED_KEY = "enabled"

_OVERRIDE_FILE_NAMES = frozenset({BACKENDS_OVERRIDE_FILE_NAME, ROUTING_PROFILES_OVERRIDE_FILE_NAME})


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
    """The active routing profile sends models to a retired backend, by default or by a route, or is a retired profile
    no file defines. Stops the boot that reads it."""

    PROJECT_ACTIVE_ROUTING_PROFILE = "project_active_routing_profile"
    """Not something the release left, but the change that keeps the project's boot whole: the project's override is
    given an `active` of its own, because the file the project's boot reads it from is read by the boot outside the
    project too, and has to change for one boot and not the other."""

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
                | FormerReleaseFindingKind.PROJECT_ACTIVE_ROUTING_PROFILE
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
    """For an active routing profile: whether the cleanup moves `active` off the profile it names, because a boot reading
    the file would otherwise be left on a profile that is gone, or has nothing left to route by. When the profile stays
    whole for every boot reading the file, the `active` is left as it is, and so it is when moving it would change
    the profile another boot starts on."""

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
            case FormerReleaseFindingKind.PROJECT_ACTIVE_ROUTING_PROFILE:
                return (
                    f"the project's boot is to start on the routing profile '{self.subject}', and the file it reads 'active' from is "
                    f"read by the boot outside the project too: {where} is given an 'active' of its own"
                )


class FormerReleaseFindings(BaseModel):
    """Everything a former release left in one configuration directory."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    config_dir: Path
    findings: list[FormerReleaseFinding] = Field(default_factory=list[FormerReleaseFinding])
    hand_edits: dict[Path, str] = Field(default_factory=dict[Path, str])
    """The files here the cleanup leaves as they are, each with what to change by hand and why: a file both boots
    read, whose `active` would have to change for one boot and stay for the other."""

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
    routing_plan = _routing_plan(
        sequences=inference_merge_sequences(
            config_dirs=directories, file_name=ROUTING_PROFILES_FILE_NAME, override_file_name=ROUTING_PROFILES_OVERRIDE_FILE_NAME
        ),
        contents=None,
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
        findings.extend(finding for finding in routing_plan.findings if finding.file_path in routing_files)
        hand_edits = {path: hand_edit for path, hand_edit in routing_plan.hand_edits.items() if path in routing_files}
        all_findings.append(FormerReleaseFindings(config_dir=config_dir, findings=findings, hand_edits=hand_edits))
    return all_findings


def former_release_boot_blockers(
    *,
    backends_library_paths: Sequence[Path],
    routing_profile_library_paths: Sequence[Path],
    contents: Mapping[Path, str | None] | None = None,
) -> list[FormerReleaseFinding]:
    """What a former release left that would stop a boot reading exactly these files.

    The boot merges a base file with the overrides of the home and the project directories, so a base in one directory
    can be lifted by an override in the other; reading the same sequences the boot reads is what keeps this from
    refusing a boot that would have succeeded, or passing one that will not. It reads, and plans nothing: the boot
    runs it on every start.

    Args:
        backends_library_paths: The `backends.toml` merge sequence the boot reads, base first.
        routing_profile_library_paths: The `routing_profiles.toml` merge sequence the boot reads, base first.
        contents: Documents to read in place of the files at their paths, `None` for a file read as absent: the
            files as a cleanup would leave them, for a check before it writes.

    Returns:
        The blocking findings, the backend library's first; empty when nothing a former release left stops the boot.
    """
    backend_findings = backend_library_findings(sequences=[list(backends_library_paths)], contents=contents)
    routing_sequences = [list(routing_profile_library_paths)]
    routing_documents = _read_documents(sequences=routing_sequences, contents=contents)
    verdicts = _active_verdicts(sequences=_read_sequences(sequences=routing_sequences, documents=routing_documents), documents=routing_documents)
    return [finding for finding in [*backend_findings, *verdicts.values()] if finding.blocks_boot]


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
    """The message of the one error a boot raises on what a former release left: what stops it, and the remedies.

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


def backend_library_findings(*, sequences: Sequence[Sequence[Path]], contents: Mapping[Path, str | None] | None = None) -> list[FormerReleaseFinding]:
    """The retired backend tables and `model_specs_section` keys in the `backends.toml` merge sequences.

    Each file holding one is reported once; whether it stops the boot is read off the merged document of each sequence
    the file is read in, so an override that disables a table lifts the finding in the base too. `contents` stands in
    for the files at its paths, `None` for a file read as absent.
    """
    documents = _read_documents(sequences=sequences, contents=contents)
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


class RoutingBoot(NamedTuple):
    """One boot's routing profile library, judged as the boot would load it."""

    loads: bool
    """The library validates and defines the profile it makes active."""

    active: str | None
    """The profile `active` names, whether or not the library defines it."""

    routes: bool
    """The active profile routes something: a `default`, a route, or a `fallback_order`."""

    refused: bool
    """What a former release left stops it: the active profile sends models to a retired backend by its default or a
    route, or it is a retired profile no file defines."""

    @property
    def starts(self) -> bool:
        """The boot gets past its routing profile library."""
        return self.loads and not self.refused

    @property
    def is_whole(self) -> bool:
        """The boot starts, and its active profile sends a model somewhere."""
        return self.starts and self.routes

    def regresses_to(self, *, after: "RoutingBoot") -> bool:
        """Whether a boot that started on this library would start differently on `after`: not at all, on another
        active profile, or on one that no longer routes anything.
        """
        if not self.starts:
            return False
        return not after.starts or after.active != self.active or (self.routes and not after.routes)


def routing_boots(*, sequences: Sequence[Sequence[Path]], contents: Mapping[Path, str | None] | None = None) -> list[RoutingBoot]:
    """Each boot's routing profile library judged as the boot would load it: the files at the paths, or `contents`.

    A file that is not there, or does not parse, is read as absent, as the cleanup's planning reads it.
    """
    documents = _read_documents(sequences=sequences, contents=contents)
    return [_boot_of(documents=[documents[path] for path in sequence]) for sequence in _read_sequences(sequences=sequences, documents=documents)]


class _ProfileFate(StrEnum):
    """What the cleanup does to one profile table in one file."""

    KEPT = "kept"
    LOSES_ITS_DEFAULT = "loses_its_default"
    REMOVED = "removed"

    @property
    def preservation(self) -> int:
        """How much of the table stays: the order in which a file read by two boots takes the fate either gives it."""
        match self:
            case _ProfileFate.REMOVED:
                return 0
            case _ProfileFate.LOSES_ITS_DEFAULT:
                return 1
            case _ProfileFate.KEPT:
                return 2


_Fates = dict[tuple[Path, str], tuple[_ProfileFate, str | None]]

#: The boots a machine has, in the order `inference_merge_sequences` lists their sequences.
_BOOT_NAMES = ("the boot outside the project", "the project's boot")


class _Libraries(NamedTuple):
    """The routing profile documents every boot of the machine reads, and what each boot made of them before."""

    sequences: list[list[Path]]
    documents: dict[Path, dict[str, Any]]
    before: list[RoutingBoot]
    verdicts: dict[Path, FormerReleaseFinding]
    """Each file whose `active` names a profile a former release left, as `_active_verdicts` reads it."""

    project_override: Path | None
    """The project's override when it exists: the one file only the project's boot reads after the files both boots
    read, where the project is given an `active` of its own."""

    project_override_path: Path | None
    """Where the project's override is, or would be: the file a hand edit gives the project its own `active` in."""

    @property
    def shared(self) -> frozenset[Path]:
        """The files more than one boot reads."""
        if len(self.sequences) < 2:
            return frozenset()
        return frozenset(self.sequences[0]) & frozenset(self.sequences[1])


class _ActivePlan(NamedTuple):
    """What the cleanup does to the `active` keys: the files it moves off their profile, and the project override it pins."""

    moves: frozenset[Path]
    pin: tuple[Path, str] | None

    def edit_of(self, *, path: Path) -> str:
        if path in self.moves:
            return "move"
        if self.pin is not None and self.pin[0] == path:
            return f"pin {self.pin[1]}"
        return "keep"


class _Candidate(NamedTuple):
    """One way of moving the `active` keys, with each boot's library as it would leave it."""

    plan: _ActivePlan
    boots: list[RoutingBoot]
    regressions: list[int]
    score: tuple[int, int, int, int]


class _RoutingPlan(NamedTuple):
    findings: list[FormerReleaseFinding]
    hand_edits: dict[Path, str]


def _routing_plan(*, sequences: Sequence[Sequence[Path]], contents: Mapping[Path, str | None] | None) -> _RoutingPlan:
    """What the cleanup does to the routing profile files, decided per boot and checked before anything is written.

    Each profile table's fate is decided in each sequence that reads its file, and a file two boots read keeps what
    either needs (`_profile_fates`). Then every way of moving the `active` keys a former release spoiled is tried on
    each boot's library as the cleanup would leave it (`_choose_actives`): none may stop a boot that starts today, or
    change the profile it starts on; of the rest, the one that leaves the most boots whole wins. Where a file both boots
    read would have to change for one boot and stay for the other, and the project's override cannot make up the
    difference, that file is left as it is, for a hand edit, and the plan is made again without touching it.
    """
    documents = _read_documents(sequences=sequences, contents=contents)
    read_sequences = _read_sequences(sequences=sequences, documents=documents)
    project_override_path = sequences[1][-1] if len(sequences) > 1 else None
    project_override = (
        project_override_path
        if project_override_path is not None and project_override_path in documents and project_override_path not in read_sequences[0]
        else None
    )
    libraries = _Libraries(
        sequences=read_sequences,
        documents=documents,
        before=[_boot_of(documents=[documents[path] for path in sequence]) for sequence in read_sequences],
        verdicts=_active_verdicts(sequences=read_sequences, documents=documents),
        project_override=project_override,
        project_override_path=project_override_path,
    )
    first_fates = _profile_fates(libraries=libraries, frozen={})
    fates = first_fates
    frozen: dict[Path, str] = {}
    while True:
        plan, conflicts = _choose_actives(libraries=libraries, fates=fates, frozen=frozen)
        if not conflicts:
            break
        frozen.update(conflicts)
        fates = _profile_fates(libraries=libraries, frozen=frozen)
    findings = _plan_findings(libraries=libraries, fates=fates, first_fates=first_fates, frozen=frozen, plan=plan)
    return _RoutingPlan(findings=findings, hand_edits=frozen)


def _plan_findings(
    *, libraries: _Libraries, fates: _Fates, first_fates: _Fates, frozen: Mapping[Path, str], plan: _ActivePlan
) -> list[FormerReleaseFinding]:
    """The findings the plan makes: each `active`, the project's own one, then each profile table, file by file.

    A file left for a hand edit is reported with what the release left in it, as the plan would have removed it had
    the file been free; the cleanup then leaves it as it is, with the reason.
    """
    findings: list[FormerReleaseFinding] = []
    for path, document in libraries.documents.items():
        verdict = libraries.verdicts.get(path)
        active = document.get(ACTIVE_KEY)
        if verdict is not None:
            findings.append(verdict.model_copy(update={"profile_is_removed": path in plan.moves}))
        elif isinstance(active, str) and (path in plan.moves or path in frozen):
            findings.append(
                FormerReleaseFinding(
                    kind=FormerReleaseFindingKind.ACTIVE_ROUTING_PROFILE, file_path=path, subject=active, profile_is_removed=path in plan.moves
                )
            )
        if plan.pin is not None and plan.pin[0] == path:
            findings.append(FormerReleaseFinding(kind=FormerReleaseFindingKind.PROJECT_ACTIVE_ROUTING_PROFILE, file_path=path, subject=plan.pin[1]))
    for path, document in libraries.documents.items():
        file_fates = first_fates if path in frozen else fates
        for profile_name, profile in _profiles_of(document=document).items():
            fate, retired_backend = file_fates[path, profile_name]
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


def _profile_fates(*, libraries: _Libraries, frozen: Mapping[Path, str]) -> _Fates:
    """What becomes of each profile table of each file, with the retired backend that decides it.

    Decided in each sequence that reads the file (`_fate_in_sequence`); a file read by both boots takes the fate that
    keeps the most of the table, since a profile one boot still needs cannot go from a file it reads, and a profile left
    in a boot that does not need it, without a retired default, is harmless there. A file left for a hand edit keeps
    every table. Then no boot may be left with a part of a profile and none of its description, which the boot
    refuses: the table that held it, which a sequence removed while a shared file kept another part, keeps it and loses
    only its retired `default` (`_descriptions_lost`), and the fates are decided again.
    """
    forced: set[tuple[Path, str]] = set()
    while True:
        fates = _fates_once(libraries=libraries, frozen=frozen, forced=forced)
        lost = _descriptions_lost(libraries=libraries, fates=fates) - forced
        if not lost:
            return fates
        forced |= lost


def _fates_once(*, libraries: _Libraries, frozen: Mapping[Path, str], forced: set[tuple[Path, str]]) -> _Fates:
    fates: _Fates = {}
    for path in _in_reading_order(sequences=libraries.sequences):
        for profile_name, profile in _profiles_of(document=libraries.documents[path]).items():
            if path in frozen:
                fates[path, profile_name] = (_ProfileFate.KEPT, None)
                continue
            readings = [
                _fate_in_sequence(
                    path=path, profile_name=profile_name, profile=profile, sequence=sequence, documents=libraries.documents, fates=fates
                )
                for sequence in libraries.sequences
                if path in sequence
            ]
            fate, retired_backend = max(readings, key=lambda reading: reading[0].preservation)
            if fate is _ProfileFate.REMOVED and (path, profile_name) in forced:
                fate = _ProfileFate.LOSES_ITS_DEFAULT
            fates[path, profile_name] = (fate, retired_backend)
    return fates


def _fate_in_sequence(
    *, path: Path, profile_name: str, profile: dict[str, Any], sequence: list[Path], documents: dict[Path, dict[str, Any]], fates: _Fates
) -> tuple[_ProfileFate, str | None]:
    """What one sequence asks of one profile table, the files it reads before this one being decided already.

    A table whose own `default` is a retired backend goes, unless the profile stays alive without it: a file read
    before this one keeps a definition of it, or a file read after gives it a live `default`. Then only the `default`
    goes, and the routes the user tuned stay. A table with no `default` of its own and no `description`, whose every
    earlier definition goes, is a part of a profile that no longer exists, and goes too: left alone, it would be a
    profile with no description, which the boot refuses.
    """
    index = sequence.index(path)
    earlier = [neighbour for neighbour in sequence[:index] if profile_name in _profiles_of(document=documents[neighbour])]
    later = [neighbour for neighbour in sequence[index + 1 :] if profile_name in _profiles_of(document=documents[neighbour])]
    kept_earlier = any(fates[neighbour, profile_name][0] is not _ProfileFate.REMOVED for neighbour in earlier)
    own_default = profile.get(_DEFAULT_KEY)
    if _names_a_retired_backend(value=own_default):
        later_live_default = any(
            _names_a_live_backend(value=_profiles_of(document=documents[neighbour])[profile_name].get(_DEFAULT_KEY)) for neighbour in later
        )
        fate = _ProfileFate.LOSES_ITS_DEFAULT if kept_earlier or later_live_default else _ProfileFate.REMOVED
        return fate, cast("str", own_default)
    if earlier and not kept_earlier and own_default is None and _DESCRIPTION_KEY not in profile:
        return _ProfileFate.REMOVED, fates[earlier[0], profile_name][1]
    return _ProfileFate.KEPT, None


def _descriptions_lost(*, libraries: _Libraries, fates: _Fates) -> set[tuple[Path, str]]:
    """The tables to keep for their description: in some sequence, a profile left by a part with no description of its own.

    That happens when a file two boots read keeps a part of the profile for one boot, while the other boot's own
    definition of it goes. The definition holding the description then stays, losing only its retired `default`: the
    one in a file only that boot reads, the last read, when there is one.
    """
    shared = libraries.shared
    lost: set[tuple[Path, str]] = set()
    for sequence in libraries.sequences:
        names = dict.fromkeys(name for path in sequence for name in _profiles_of(document=libraries.documents[path]))
        for profile_name in names:
            tables = [
                (path, _profiles_of(document=libraries.documents[path])[profile_name])
                for path in sequence
                if profile_name in _profiles_of(document=libraries.documents[path])
            ]
            staying = [table for path, table in tables if _table_stays(profile=table, fate=fates[path, profile_name][0])]
            if not staying or any(_DESCRIPTION_KEY in table for table in staying):
                continue
            holders = [path for path, table in tables if _DESCRIPTION_KEY in table]
            if holders:
                unshared = [path for path in holders if path not in shared]
                lost.add(((unshared or holders)[-1], profile_name))
    return lost


def _table_stays(*, profile: dict[str, Any], fate: _ProfileFate) -> bool:
    """Whether a table is still in its file once cleaned: one that loses its `default` and holds nothing else goes."""
    match fate:
        case _ProfileFate.KEPT:
            return True
        case _ProfileFate.LOSES_ITS_DEFAULT:
            return any(key != _DEFAULT_KEY for key in profile)
        case _ProfileFate.REMOVED:
            return False


def _choose_actives(*, libraries: _Libraries, fates: _Fates, frozen: Mapping[Path, str]) -> tuple[_ActivePlan, dict[Path, str]]:
    """The `active` keys to move, and the files to leave for a hand edit because no move suits both boots.

    A file whose `active` names a profile the release left, or one the cleanup removes or leaves with nothing to route
    by, may move off it: a base to the profile the kit makes active, an override by losing the key so the file read
    before it decides. The project's override may be given an `active` of its own, when the project's boot reads one
    the cleanup has to change, or one that names what a former release left. Every combination is tried on each boot's
    library as it would be left, and the plans that would stop a boot that starts today, or change the profile it
    starts on, are out. Of the rest, the one leaving the most boots whole wins, then the one leaving no `active` naming
    a profile that is gone, then the one without the project's own `active`, then the one moving the fewest.

    A boot the former release stops that the chosen plan leaves stopped, while another plan would have started it, is a
    conflict: the files both boots read where the two plans differ are returned for a hand edit.
    """
    no_change = _ActivePlan(moves=frozenset(), pin=None)
    after_fates = _documents_after(libraries=libraries, fates=fates, frozen=frozen, plan=no_change, kit=None)
    setters = {path: document[ACTIVE_KEY] for path, document in libraries.documents.items() if isinstance(document.get(ACTIVE_KEY), str)}
    movable = [
        path
        for path, active in setters.items()
        if path not in frozen
        and (
            _is_implicated(libraries=libraries, path=path, active=active, after_fates=after_fates)
            or _is_exposed(libraries=libraries, path=path, active=active, after_fates=after_fates)
        )
    ]
    kit = _kit_default_profile() if movable else None
    candidates = [
        _evaluate(libraries=libraries, fates=fates, frozen=frozen, plan=plan, kit=kit, setters=setters)
        for plan in _possible_plans(libraries=libraries, setters=setters, movable=movable, kit=kit)
    ]
    acceptable = [candidate for candidate in candidates if not candidate.regressions]
    if not acceptable:
        return no_change, _untouchable(libraries=libraries, candidate=candidates[0], after_fates=after_fates, frozen=frozen)
    best = max(acceptable, key=lambda candidate: candidate.score)
    conflicts: dict[Path, str] = {}
    for index, sequence in enumerate(libraries.sequences):
        if best.boots[index].is_whole or not libraries.before[index].refused:
            continue
        fixing = [candidate for candidate in candidates if candidate.boots[index].is_whole]
        if not fixing:
            continue
        fix = max(fixing, key=lambda candidate: candidate.score)
        for path in sequence:
            if path in libraries.shared and fix.plan.edit_of(path=path) != best.plan.edit_of(path=path):
                conflicts[path] = _conflict_hand_edit(libraries=libraries, path=path, stopped=index)
    return best.plan, conflicts


def _possible_plans(
    *, libraries: _Libraries, setters: Mapping[Path, str], movable: list[Path], kit: tuple[str, dict[str, Any]] | None
) -> list[_ActivePlan]:
    """Every combination of moves, each with and without the project's own `active`, fewest moves first."""
    pin_values = _pin_values(libraries=libraries, setters=setters, kit=kit)
    project_sequence = libraries.sequences[1] if len(libraries.sequences) > 1 else []
    project_setters = [path for path in project_sequence if path in setters]
    project_reads_a_spoiled_active = bool(project_setters) and project_setters[-1] in movable
    plans: list[_ActivePlan] = []
    for size in range(len(movable) + 1):
        for moves in itertools.combinations(movable, size):
            plans.append(_ActivePlan(moves=frozenset(moves), pin=None))
            if libraries.project_override is None or libraries.project_override in moves:
                continue
            moves_what_the_project_reads = any(path in libraries.shared and path in project_sequence for path in moves)
            if not (project_reads_a_spoiled_active or moves_what_the_project_reads):
                continue
            plans.extend(_ActivePlan(moves=frozenset(moves), pin=(libraries.project_override, value)) for value in pin_values)
    return plans


def _pin_values(*, libraries: _Libraries, setters: Mapping[Path, str], kit: tuple[str, dict[str, Any]] | None) -> list[str]:
    """What the project's own `active` may name: what its boot starts on today, what a file it reads names, the kit's."""
    if libraries.project_override is None:
        return []
    values = [libraries.before[1].active, *(setters[path] for path in libraries.sequences[1] if path in setters)]
    if kit is not None:
        values.append(kit[0])
    current = setters.get(libraries.project_override)
    return [value for value in dict.fromkeys(values) if value is not None and value != current]


def _evaluate(
    *,
    libraries: _Libraries,
    fates: _Fates,
    frozen: Mapping[Path, str],
    plan: _ActivePlan,
    kit: tuple[str, dict[str, Any]] | None,
    setters: Mapping[Path, str],
) -> _Candidate:
    after = _documents_after(libraries=libraries, fates=fates, frozen=frozen, plan=plan, kit=kit)
    boots = [_boot_of(documents=[after[path] for path in sequence]) for sequence in libraries.sequences]
    regressions = [index for index, (before, boot) in enumerate(zip(libraries.before, boots, strict=True)) if before.regresses_to(after=boot)]
    dangling = sum(1 for path in setters if _names_a_profile_gone_everywhere(libraries=libraries, path=path, after=after))
    score = (sum(1 for boot in boots if boot.is_whole), -dangling, -int(plan.pin is not None), -len(plan.moves))
    return _Candidate(plan=plan, boots=boots, regressions=regressions, score=score)


def _names_a_profile_gone_everywhere(*, libraries: _Libraries, path: Path, after: dict[Path, dict[str, Any]]) -> bool:
    """Whether a file's `active`, as the plan leaves it, names a profile no boot reading the file defines any more."""
    active = after[path].get(ACTIVE_KEY)
    if not isinstance(active, str):
        return False
    return all(
        active not in _profiles_of(document=_merged(documents=[after[member] for member in sequence]))
        for sequence in libraries.sequences
        if path in sequence
    )


def _is_implicated(*, libraries: _Libraries, path: Path, active: str, after_fates: dict[Path, dict[str, Any]]) -> bool:
    """Whether a file's `active` is the cleanup's to move: it names what a former release left, or a profile the cleanup
    removes, or leaves with nothing to route by, in a boot that reads it.
    """
    if path in libraries.verdicts:
        return True
    for sequence in libraries.sequences:
        if path not in sequence:
            continue
        profiles_before = _profiles_of(document=_merged(documents=[libraries.documents[member] for member in sequence]))
        profiles_after = _profiles_of(document=_merged(documents=[after_fates[member] for member in sequence]))
        if active not in profiles_before:
            continue
        if active not in profiles_after or (
            _routes_something(profile=profiles_before[active]) and not _routes_something(profile=profiles_after[active])
        ):
            return True
    return False


def _is_exposed(*, libraries: _Libraries, path: Path, active: str, after_fates: dict[Path, dict[str, Any]]) -> bool:
    """Whether a file's `active` names a profile no file defines, or one with nothing to route by, in a boot the former
    release stops.

    Such an `active` is shadowed today by a later one naming what the release left, or is what the boot reads once the
    release's routes go; once the later one moves, it is the one the boot reads, so it may move too, and a profile with
    nothing to route by counts as gone for that boot. In a boot the release does not stop, such an `active` is the
    user's own, and stays for them to see.
    """
    for index, sequence in enumerate(libraries.sequences):
        if path not in sequence or not libraries.before[index].refused:
            continue
        profiles = _profiles_of(document=_merged(documents=[after_fates[member] for member in sequence]))
        if active not in profiles or not _routes_something(profile=profiles[active]):
            return True
    return False


def _untouchable(
    *, libraries: _Libraries, candidate: _Candidate, after_fates: dict[Path, dict[str, Any]], frozen: Mapping[Path, str]
) -> dict[Path, str]:
    """The files to leave as they are when even keeping every `active` would stop a boot that starts today: the ones the
    cleanup would change in that boot's sequence.
    """
    untouchable: dict[Path, str] = {}
    for index in candidate.regressions:
        for path in libraries.sequences[index]:
            if path not in frozen and after_fates[path] != libraries.documents[path]:
                untouchable[path] = (
                    f"cleaning this file would stop {_BOOT_NAMES[index] if len(libraries.sequences) > 1 else 'the boot'} from starting as it does "
                    f"now. By hand, remove what a former release left in it, keeping each routing profile you use whole, then run "
                    f"'{MIGRATE_COMMAND}' again"
                )
    return untouchable


def _conflict_hand_edit(*, libraries: _Libraries, path: Path, stopped: int) -> str:
    """Why a file both boots read is left for a hand edit, and the edit that settles it."""
    active = libraries.documents[path].get(ACTIVE_KEY)
    started = 1 - stopped
    return (
        f"both {_BOOT_NAMES[0]} and {_BOOT_NAMES[1]} read this file, and its 'active', '{active}', cannot change for one without "
        f"changing for the other: {_BOOT_NAMES[stopped]} cannot run a model with it once the former release's profiles and routes "
        f"are gone, and {_BOOT_NAMES[started]} would no longer start as it does. By hand, give the project an 'active' of its own "
        f"in '{libraries.project_override_path}', then make this file's suit {_BOOT_NAMES[0]}, and run '{MIGRATE_COMMAND}' again"
    )


def _documents_after(
    *, libraries: _Libraries, fates: _Fates, frozen: Mapping[Path, str], plan: _ActivePlan, kit: tuple[str, dict[str, Any]] | None
) -> dict[Path, dict[str, Any]]:
    """Each document as the cleanup would leave it: the same edits `former_release_cleanup.cleaned_text` makes, on the parsed document.

    A table that goes, a retired `default` and every retired route; a table left with nothing once its `default` went;
    an `active` moved off its profile — a base onto the kit's default profile, which is added when the file did not
    define it, an override by losing the key — and the project's own `active`. A file left for a hand edit stays as it is.
    """
    after: dict[Path, dict[str, Any]] = {}
    for path, document in libraries.documents.items():
        if path in frozen:
            after[path] = document
            continue
        cleaned = copy.deepcopy(document)
        profiles = cast("dict[str, Any]", cleaned.get(ROUTING_PROFILES_KEY))
        for profile_name, profile in _profiles_of(document=document).items():
            fate = fates[path, profile_name][0]
            if fate is _ProfileFate.REMOVED:
                del profiles[profile_name]
                continue
            kept = cast("dict[str, Any]", profiles[profile_name])
            if fate is _ProfileFate.LOSES_ITS_DEFAULT:
                kept.pop(_DEFAULT_KEY, None)
            for route_table, route_pattern, _ in retired_routes_of(profile=profile):
                cast("dict[str, Any]", kept[route_table]).pop(route_pattern, None)
            if not _table_stays(profile=profile, fate=fate):
                del profiles[profile_name]
        if path in plan.moves:
            if path.name in _OVERRIDE_FILE_NAMES:
                cleaned.pop(ACTIVE_KEY, None)
            elif kit is not None:
                kit_default, kit_profile = kit
                existing = cleaned.get(ROUTING_PROFILES_KEY)
                if kit_default not in _profiles_of(document=document) and (existing is None or isinstance(existing, dict)):
                    cleaned[ROUTING_PROFILES_KEY] = {kit_default: copy.deepcopy(kit_profile), **cast("dict[str, Any]", existing or {})}
                cleaned[ACTIVE_KEY] = kit_default
        if plan.pin is not None and plan.pin[0] == path:
            cleaned[ACTIVE_KEY] = plan.pin[1]
        after[path] = cleaned
    return after


def _kit_default_profile() -> tuple[str, dict[str, Any]]:
    """The profile the kit makes active, by name and as the kit defines it."""
    kit_default = kit_default_routing_profile_name()
    kit_profiles = _profiles_of(document=load_toml_from_path(kit_routing_profile_library_path()))
    if kit_default not in kit_profiles:
        msg = (
            f"the kit's routing profile library '{kit_routing_profile_library_path()}' does not define its active profile "
            f"'{kit_default}' — packaging bug"
        )
        raise PipelexUnexpectedError(msg)
    return kit_default, kit_profiles[kit_default]


def _boot_of(*, documents: Sequence[dict[str, Any]]) -> RoutingBoot:
    """One sequence's routing profile library, judged as the boot would load it."""
    merged = _merged(documents=list(documents))
    active = merged.get(ACTIVE_KEY)
    active_name = active if isinstance(active, str) else None
    profiles = _profiles_of(document=merged)
    refused = active_name is not None and _is_refused(active=active_name, profiles=profiles)
    try:
        RoutingProfileLibraryBlueprint.model_validate(merged)
    except ValidationError:
        return RoutingBoot(loads=False, active=active_name, routes=False, refused=refused)
    if active_name is None or active_name not in profiles:
        return RoutingBoot(loads=False, active=active_name, routes=False, refused=refused)
    return RoutingBoot(loads=True, active=active_name, routes=_routes_something(profile=profiles[active_name]), refused=refused)


def _is_refused(*, active: str, profiles: dict[str, dict[str, Any]]) -> bool:
    """Whether the boot refuses this active profile for what a former release left in it: the refusal `_active_verdict` names."""
    if active not in profiles:
        return active in RETIRED_ROUTING_PROFILE_NAMES
    profile = profiles[active]
    return _names_a_retired_backend(value=profile.get(_DEFAULT_KEY)) or any(route[0] == _ROUTES_KEY for route in retired_routes_of(profile=profile))


def _routes_something(*, profile: dict[str, Any]) -> bool:
    """Whether a profile sends any model somewhere: a `default`, a route, or a `fallback_order`. Optional routes alone
    reach only backends that happen to be enabled, and are not counted.
    """
    return bool(profile.get(_DEFAULT_KEY)) or bool(profile.get(_ROUTES_KEY)) or bool(profile.get(_FALLBACK_ORDER_KEY))


def _active_verdicts(*, sequences: list[list[Path]], documents: dict[Path, dict[str, Any]]) -> dict[Path, FormerReleaseFinding]:
    """Each file whose `active` names a profile sending models to a retired backend, or a retired profile no file defines.

    Every such file is reported, because each is something the cleanup may have to move; only the last file of a
    sequence to set `active` is the one that boot reads, so only its finding can stop the boot. A file read in two
    sequences is reported once, with what either says. Optional routes are not counted: one naming a disabled backend
    is inert, and the boot never refuses it. Whether the cleanup moves the `active` is the plan's to say
    (`profile_is_removed`).
    """
    found: dict[Path, FormerReleaseFinding] = {}
    for sequence in sequences:
        merged_profiles = _profiles_of(document=_merged(documents=[documents[path] for path in sequence]))
        setters = [(path, documents[path][ACTIVE_KEY]) for path in sequence if ACTIVE_KEY in documents[path]]
        for index, (path, active) in enumerate(setters):
            if not isinstance(active, str):
                continue
            finding = _active_verdict(path=path, active=active, is_read_by_the_boot=index == len(setters) - 1, merged_profiles=merged_profiles)
            if finding is not None:
                found[path] = _combined(earlier=found.get(path), later=finding)
    return {path: found[path] for path in documents if path in found}


def _active_verdict(*, path: Path, active: str, is_read_by_the_boot: bool, merged_profiles: dict[str, dict[str, Any]]) -> FormerReleaseFinding | None:
    """One file's `active`, judged over one sequence: whether it names a profile a former release left."""
    defined = active in merged_profiles
    merged_default = merged_profiles[active].get(_DEFAULT_KEY) if defined else None
    default_is_retired = _names_a_retired_backend(value=merged_default)
    is_a_retired_name = not defined and active in RETIRED_ROUTING_PROFILE_NAMES
    # Optional routes are left out: the boot refuses a route to a backend it cannot reach, never an optional one.
    retired_route = (
        next((route for route in retired_routes_of(profile=merged_profiles[active]) if route[0] == _ROUTES_KEY), None)
        if defined and not default_is_retired
        else None
    )
    if not (default_is_retired or is_a_retired_name or retired_route):
        return None
    retired_backend = cast("str", merged_default) if default_is_retired else (retired_route[2] if retired_route else None)
    return FormerReleaseFinding(
        kind=FormerReleaseFindingKind.ACTIVE_ROUTING_PROFILE,
        file_path=path,
        subject=active,
        route_pattern=retired_route[1] if retired_route else None,
        route_table=retired_route[0] if retired_route else None,
        retired_backend=retired_backend,
        blocks_boot=is_read_by_the_boot,
    )


def _combined(*, earlier: FormerReleaseFinding | None, later: FormerReleaseFinding) -> FormerReleaseFinding:
    """One file's `active` judged over two sequences: the stronger reading, a retired default or name over a route."""
    if earlier is None:
        return later
    primary = later if earlier.route_pattern is not None and later.route_pattern is None else earlier
    return primary.model_copy(update={"blocks_boot": earlier.blocks_boot or later.blocks_boot})


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


def _read_documents(*, sequences: Sequence[Sequence[Path]], contents: Mapping[Path, str | None] | None) -> dict[Path, dict[str, Any]]:
    """Each file of the sequences that exists and parses, with its document, each once, in the order first met.

    A path `contents` names is read from there instead: its text, or nothing for a file read as absent.
    """
    documents: dict[Path, dict[str, Any]] = {}
    for sequence in sequences:
        for path in sequence:
            if path in documents:
                continue
            if contents is not None and path in contents:
                text = contents[path]
                if text is None:
                    continue
                try:
                    documents[path] = load_toml_from_content(text)
                except TomlError:
                    continue
                continue
            if not path.is_file():
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
