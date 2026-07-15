"""Manifest (drift.toml) and ack (.drift/acks/) models and their TOML I/O.

The manifest is human-authored and validated strictly (unknown fields are errors).
Ack files are tool-written by `drift ack` and committed; one file per contract so
merge conflicts stay scoped to the contract they concern.
"""

from __future__ import annotations

import re
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from tomlkit.exceptions import TOMLKitError

from pipelex.cli.dev_cli.commands.drift.exceptions import DriftAckError, DriftManifestError
from pipelex.tools.misc.toml_utils import load_toml_with_tomlkit, save_toml_to_path

MANIFEST_FILENAME = "drift.toml"
ACKS_DIR_RELATIVE = Path(".drift") / "acks"
CONTRACT_ID_PATTERN = re.compile(r"^[a-z0-9-]+$")


class DriftContract(BaseModel):
    """One declared review obligation: when triggers change, review targets must be re-examined."""

    model_config = ConfigDict(extra="forbid")

    description: str
    triggers: list[str] = Field(min_length=1)
    exclude: list[str] = Field(default_factory=list)
    review: list[str] = Field(min_length=1)
    verify_commands: list[str] = Field(default_factory=list)


class DriftManifest(BaseModel):
    """The parsed drift.toml: contract declarations keyed by contract id."""

    model_config = ConfigDict(extra="forbid")

    version: int
    contracts: dict[str, DriftContract]

    @field_validator("contracts")
    @classmethod
    def validate_contract_ids(cls, value: dict[str, DriftContract]) -> dict[str, DriftContract]:
        for contract_id in value:
            if not CONTRACT_ID_PATTERN.match(contract_id):
                msg = f"Invalid contract id '{contract_id}': ids must match [a-z0-9-]+ (they become ack filenames and TOML keys)"
                raise ValueError(msg)
        return value


class DriftAck(BaseModel):
    """The recorded fulfillment of one contract's review, committed under .drift/acks/.

    `digest` alone carries validity; `reviewed_by`/`reviewed_at`/`rationale` are audit
    context, and `trigger_files` exists so `drift plan` can report per-file changes.
    """

    model_config = ConfigDict(extra="forbid")

    contract: str
    digest: str
    reviewed_by: str
    reviewed_at: str
    rationale: str
    trigger_files: dict[str, str] = Field(default_factory=dict)


def load_manifest(repo_root: Path) -> DriftManifest:
    """Load and validate drift.toml from the repo root.

    Raises:
        DriftManifestError: If the manifest is missing, unparseable, or schema-invalid.
    """
    manifest_path = repo_root / MANIFEST_FILENAME
    if not manifest_path.is_file():
        msg = f"No {MANIFEST_FILENAME} found at repo root '{repo_root}' — create one to declare drift contracts"
        raise DriftManifestError(msg)
    try:
        document = load_toml_with_tomlkit(manifest_path)
    except TOMLKitError as exc:
        msg = f"Failed to parse {MANIFEST_FILENAME}: {exc}"
        raise DriftManifestError(msg) from exc
    try:
        return DriftManifest.model_validate(document.unwrap())
    except ValidationError as exc:
        msg = f"{MANIFEST_FILENAME} is schema-invalid: {exc}"
        raise DriftManifestError(msg) from exc


def ack_file_path(repo_root: Path, *, contract_id: str) -> Path:
    """Path of the ack file for a contract id."""
    return repo_root / ACKS_DIR_RELATIVE / f"{contract_id}.toml"


def load_ack(ack_path: Path) -> DriftAck:
    """Load and validate one ack file.

    Raises:
        DriftAckError: If the ack file is unparseable or schema-invalid.
    """
    try:
        document = load_toml_with_tomlkit(ack_path)
    except TOMLKitError as exc:
        msg = f"Failed to parse ack file '{ack_path}': {exc}"
        raise DriftAckError(msg) from exc
    try:
        return DriftAck.model_validate(document.unwrap())
    except ValidationError as exc:
        msg = f"Ack file '{ack_path}' is schema-invalid: {exc}"
        raise DriftAckError(msg) from exc


def load_all_acks(repo_root: Path) -> dict[str, DriftAck]:
    """Load every ack under .drift/acks/, keyed by filename stem.

    The stem is the key (not the ack's `contract` field) so that a mismatch between
    the two can be detected by `drift check`.
    """
    acks_dir = repo_root / ACKS_DIR_RELATIVE
    if not acks_dir.is_dir():
        return {}
    acks: dict[str, DriftAck] = {}
    for ack_path in sorted(acks_dir.glob("*.toml")):
        acks[ack_path.stem] = load_ack(ack_path)
    return acks


def save_ack(ack: DriftAck, *, repo_root: Path) -> None:
    """Write an ack file atomically (temp file + os.replace)."""
    target_path = ack_file_path(repo_root, contract_id=ack.contract)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = target_path.with_name(f".{target_path.name}.tmp")
    save_toml_to_path(ack.model_dump(), path=temp_path)
    Path(temp_path).replace(target_path)
