"""What a former release left in a configuration directory, found by reading it and nothing else.

Releases up to v0.72 ran models through the Pipelex Gateway and offered Pipelex Manifold as a private beta. The
installations they set up still carry what that took: a `pipelex_gateway` and a `pipelex_manifold` table in
`inference/backends.toml`, each with a per-backend file beside the others, routing profiles that send every model to
one of them (`active = "all_pipelex_gateway"` above all), a `model_specs_section` key naming specs the remote
configuration used to serve, the `pipelex_service.toml` that recorded the Gateway's terms acceptance, and the
`pipelex_gateway_models*.md` model lists. The runtime no longer has either backend, so an enabled table or an active
profile pointing at one stops every boot with a refusal about one file that says nothing of the release behind it.

`detect_former_release` is the one reading of that state. The boot, `pipelex doctor`, `pipelex init`'s inspect stage
and the `pipelex migrate` cleanup (`former_release_cleanup.py`) all ask it, so what one of them calls a former
release's configuration is what every other one finds and removes. It reads, and it never writes or imports anything
from the CLI.

**A finding says which file it is in, and whether it stops the boot.** Only two shapes do: a retired backend, or a
backend still naming `model_specs_section`, left enabled; and an active routing profile that sends models to a retired
backend. Everything else — a disabled table, a profile nobody activates, the files beside the backends, the service
file — is inert, and is found so that the cleanup leaves nothing of that release behind. Whether a table is enabled
and which profile is active are read off the base file merged with its override, as the boot reads them;
`former_release_boot_blockers` reads them off exactly the files a boot merges, across the home and project
directories.

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
from pipelex.kit.paths import get_kit_configs_dir
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

#: The file a former release wrote to record the Gateway's terms acceptance. Nothing reads it any more.
SERVICE_FILE_NAME = "pipelex_service.toml"

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
    """A routing profile whose default backend is a retired one."""

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
        """Whether a boot reading this directory's files would be refused because of them."""
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


def detect_former_release(*, config_dir: Path) -> FormerReleaseFindings:
    """Find what a former release left in one configuration directory, `~/.pipelex/` or a project's `.pipelex/`.

    A pure read: nothing is written, and a directory or a file that is not there is simply clean. A document that does
    not parse is skipped rather than raised, because whether it parses is for the boot and the doctor to report, and
    the rest of the directory can still be judged.

    Args:
        config_dir: The configuration directory to read.

    Returns:
        The findings, in a stable order: the backend library, the files beside the backends, the service file, then
        the routing profile library.
    """
    findings = backend_library_findings(paths=backend_library_paths_in(config_dir=config_dir))
    findings.extend(_backend_directory_findings(backends_dir=config_dir / INFERENCE_DIR_NAME / BACKENDS_DIR_NAME))
    service_file = config_dir / SERVICE_FILE_NAME
    if service_file.is_file():
        findings.append(FormerReleaseFinding(kind=FormerReleaseFindingKind.SERVICE_FILE, file_path=service_file))
    findings.extend(routing_profile_findings(paths=routing_profile_library_paths_in(config_dir=config_dir)))
    return FormerReleaseFindings(config_dir=config_dir, findings=findings)


def former_release_boot_blockers(
    *, backends_library_paths: Sequence[Path], routing_profile_library_paths: Sequence[Path]
) -> list[FormerReleaseFinding]:
    """What a former release left that would stop a boot reading exactly these files.

    The boot merges a base file with the overrides of the home and the project directories, so a base in one directory
    can be lifted by an override in the other; reading the same sequences the boot reads is what keeps this from
    refusing a boot that would have succeeded.

    Args:
        backends_library_paths: The `backends.toml` merge sequence the boot reads, base first.
        routing_profile_library_paths: The `routing_profiles.toml` merge sequence the boot reads, base first.

    Returns:
        The blocking findings, the backend library's first; empty when nothing a former release left stops the boot.
    """
    findings = backend_library_findings(paths=backends_library_paths) + routing_profile_findings(paths=routing_profile_library_paths)
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


def backend_library_findings(*, paths: Sequence[Path]) -> list[FormerReleaseFinding]:
    """The retired backend tables and `model_specs_section` keys in a `backends.toml` merge sequence.

    Each file holding one is reported; whether it stops the boot is read off the merged document, so an override that
    disables a table lifts the finding in the base too.
    """
    documents = _read_documents(paths=paths)
    merged = _merged(documents=documents)
    findings: list[FormerReleaseFinding] = []
    for path, document in documents:
        for backend_name, backend_table in document.items():
            if not isinstance(backend_table, dict):
                continue
            if backend_name in RETIRED_BACKEND_NAMES:
                kind = FormerReleaseFindingKind.RETIRED_BACKEND_TABLE
            elif MODEL_SPECS_SECTION_KEY in backend_table:
                kind = FormerReleaseFindingKind.MODEL_SPECS_SECTION_KEY
            else:
                continue
            findings.append(
                FormerReleaseFinding(
                    kind=kind, file_path=path, subject=backend_name, blocks_boot=_is_enabled(document=merged, backend_name=backend_name)
                )
            )
    return findings


def routing_profile_findings(*, paths: Sequence[Path]) -> list[FormerReleaseFinding]:
    """The retired profiles, the routes to retired backends and a retired active profile in a `routing_profiles.toml` merge sequence.

    A profile is retired when its default, as merged, is a retired backend. A retired active profile is reported in
    each file that sets `active`, and the last one of the sequence to set it, the one the boot reads, stops the boot.
    """
    documents = _read_documents(paths=paths)
    merged = _merged(documents=documents)
    merged_profiles = _profiles_of(document=merged)
    retired_profiles = {
        profile_name: default
        for profile_name, profile in merged_profiles.items()
        if isinstance(default := profile.get(_DEFAULT_KEY), str) and default in RETIRED_BACKEND_NAMES
    }

    findings = _active_profile_findings(documents=documents, merged_profiles=merged_profiles, retired_profiles=retired_profiles)
    for path, document in documents:
        for profile_name, profile in _profiles_of(document=document).items():
            if profile_name in retired_profiles:
                findings.append(
                    FormerReleaseFinding(
                        kind=FormerReleaseFindingKind.RETIRED_ROUTING_PROFILE,
                        file_path=path,
                        subject=profile_name,
                        retired_backend=retired_profiles[profile_name],
                    )
                )
                continue
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


def _active_profile_findings(
    *, documents: list[tuple[Path, dict[str, Any]]], merged_profiles: dict[str, dict[str, Any]], retired_profiles: dict[str, str]
) -> list[FormerReleaseFinding]:
    """Each file whose `active` names a profile sending models to a retired backend, by default or by a route it must honour.

    Every such file is reported, because each is something the cleanup must move; only the last of the sequence to set
    `active` is the one the boot reads, so only its finding stops the boot. Optional routes are not counted: one naming
    a disabled backend is inert, and the boot never refuses it.
    """
    setters = [(path, document[ACTIVE_KEY]) for path, document in documents if ACTIVE_KEY in document]
    findings: list[FormerReleaseFinding] = []
    for index, (path, active) in enumerate(setters):
        if not isinstance(active, str):
            continue
        route_pattern: str | None = None
        route_table: str | None = None
        retired_backend: str | None
        if active in retired_profiles:
            retired_backend = retired_profiles[active]
        elif active in merged_profiles:
            # Optional routes are left out: the boot refuses a route to a backend it cannot reach, never an optional one.
            retired_route = next((route for route in retired_routes_of(profile=merged_profiles[active]) if route[0] == _ROUTES_KEY), None)
            if retired_route is None:
                continue
            route_table, route_pattern, retired_backend = retired_route
        elif active in RETIRED_ROUTING_PROFILE_NAMES:
            retired_backend = None
        else:
            continue
        findings.append(
            FormerReleaseFinding(
                kind=FormerReleaseFindingKind.ACTIVE_ROUTING_PROFILE,
                file_path=path,
                subject=active,
                route_pattern=route_pattern,
                route_table=route_table,
                retired_backend=retired_backend,
                blocks_boot=index == len(setters) - 1,
            )
        )
    return findings


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


def _read_documents(*, paths: Sequence[Path]) -> list[tuple[Path, dict[str, Any]]]:
    """Each file of a merge sequence that exists and parses, with its document, in merge order."""
    documents: list[tuple[Path, dict[str, Any]]] = []
    for path in paths:
        if not path.is_file():
            continue
        try:
            documents.append((path, load_toml_from_path(path)))
        except (OSError, TomlError, UnicodeDecodeError):
            continue
    return documents


def _merged(*, documents: list[tuple[Path, dict[str, Any]]]) -> dict[str, Any]:
    """The documents deep-merged in order, as the loaders merge a base and its overrides.

    Each is copied first: `deep_update` stores the tables of the first document it is given by reference, so merging
    the originals would let an override rewrite the base document every per-file finding is read from.
    """
    merged: dict[str, Any] = {}
    for _, document in documents:
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


def _is_enabled(*, document: dict[str, Any], backend_name: str) -> bool:
    """Whether the backend loader would load this table: it is a table, and `enabled` is not false. It defaults to true."""
    backend_table = document.get(backend_name)
    if not isinstance(backend_table, dict):
        return False
    return bool(cast("dict[str, Any]", backend_table).get(_ENABLED_KEY, True))
