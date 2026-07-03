"""Pure drift engine: glob matching, digest computation, plan-diff, and check evaluation.

Everything here operates on injected data (file lists, path→OID maps, parsed models)
— no git, no filesystem, no subprocesses. The git adapter feeds it the index state.
"""

from __future__ import annotations

import hashlib
import json
import re
from functools import cache
from typing import TYPE_CHECKING

from pydantic.dataclasses import dataclass

# Runtime import (not TYPE_CHECKING): pydantic dataclasses resolve their field annotations
# (DriftAck, DriftContract) against module globals when the class is built.
from pipelex.cli.dev_cli.commands.drift.models import DriftAck, DriftContract, DriftManifest  # noqa: TC001
from pipelex.types import StrEnum

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence

DIGEST_PREFIX = "sha256:"
GLOB_CHARS = ("*", "?")

# Ack files are rewritten by `drift ack` itself; if a trigger glob could match them, every
# ack would invalidate its own (or a sibling's) digest as soon as the ack file is staged —
# an unfixable open-contract loop. So the internal state directory is never trigger-matchable.
DRIFT_STATE_PREFIX = ".drift/"


def _normalize_pattern(pattern: str) -> str:
    """Strip trailing slashes: a directory pattern and its slashless form match the same files."""
    return pattern.rstrip("/")


@cache
def _pattern_to_regex(pattern: str) -> re.Pattern[str]:
    """Translate a glob pattern into a full-match regex.

    Semantics: `**/` spans any number of directories (including zero), a trailing `**`
    matches everything under the prefix, `*` and `?` never cross `/`. Character classes
    are not supported (`[` is literal). Matching is case-sensitive per POSIX.
    """
    regex_parts: list[str] = []
    index = 0
    while index < len(pattern):
        char = pattern[index]
        if char == "*":
            if pattern.startswith("**/", index):
                regex_parts.append("(?:[^/]+/)*")
                index += 3
            elif pattern.startswith("**", index):
                regex_parts.append(".*")
                index += 2
            else:
                regex_parts.append("[^/]*")
                index += 1
        elif char == "?":
            regex_parts.append("[^/]")
            index += 1
        else:
            regex_parts.append(re.escape(char))
            index += 1
    return re.compile("".join(regex_parts) + r"\Z")


def match_pattern(path: str, *, pattern: str) -> bool:
    """Check whether a tracked-file path matches one trigger/review pattern.

    A pattern without glob characters matches the exact path or, as a directory
    prefix, every tracked file under it (`docs/tools/cli/` and `docs/tools/cli`
    are equivalent).
    """
    normalized = _normalize_pattern(pattern)
    if not any(glob_char in normalized for glob_char in GLOB_CHARS):
        return path == normalized or path.startswith(normalized + "/")
    return _pattern_to_regex(normalized).match(path) is not None


def match_files(files: Iterable[str], *, patterns: Sequence[str], exclude: Sequence[str] = ()) -> list[str]:
    """Return the sorted subset of files matching any pattern and no exclude."""
    matched: list[str] = []
    for path in files:
        if not any(match_pattern(path, pattern=pattern) for pattern in patterns):
            continue
        if any(match_pattern(path, pattern=exclude_pattern) for exclude_pattern in exclude):
            continue
        matched.append(path)
    return sorted(matched)


def find_dead_patterns(files: Iterable[str], *, patterns: Sequence[str]) -> list[str]:
    """Return the patterns matching zero files, in their declared order (manifest rot detector)."""
    file_list = list(files)
    return [pattern for pattern in patterns if not any(match_pattern(path, pattern=pattern) for path in file_list)]


def compute_contract_digest(contract: DriftContract, *, contract_id: str, trigger_files: Mapping[str, str]) -> str:
    """Digest a contract: sha256 over a canonical JSON of its definition plus its trigger content.

    Canonicalization (what must NOT change the digest): object keys are sorted by json.dumps,
    glob lists are sorted (matching is order-independent), and defaulted fields serialize like
    their explicit-empty forms. verify_commands keep their order — it is execution order, hence
    part of the definition.
    """
    canonical = {
        "contract": {
            "id": contract_id,
            "description": contract.description,
            "triggers": sorted(contract.triggers),
            "exclude": sorted(contract.exclude),
            "review": sorted(contract.review),
            "verify_commands": list(contract.verify_commands),
        },
        "trigger_files": sorted(trigger_files.items()),
    }
    payload = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    return DIGEST_PREFIX + hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class TriggerFilesDiff:
    """Per-file changes between a stored ack map and the current index map."""

    added: list[str]
    removed: list[str]
    modified: list[str]

    @property
    def is_empty(self) -> bool:
        return not (self.added or self.removed or self.modified)


def diff_trigger_files(stored: Mapping[str, str], *, current: Mapping[str, str]) -> TriggerFilesDiff:
    """Diff the ack's stored trigger-file map against the current one (messaging only, no validity)."""
    added = sorted(path for path in current if path not in stored)
    removed = sorted(path for path in stored if path not in current)
    modified = sorted(path for path in current if path in stored and current[path] != stored[path])
    return TriggerFilesDiff(added=added, removed=removed, modified=modified)


@dataclass(frozen=True)
class ContractDigestResult:
    """The current digest of a contract plus the trigger-file map it was computed from."""

    digest: str
    trigger_files: dict[str, str]


def compute_current_digest(contract: DriftContract, *, contract_id: str, staged_oids: Mapping[str, str]) -> ContractDigestResult:
    """Match the contract's triggers against the index map and digest the result."""
    matchable = (path for path in staged_oids if not path.startswith(DRIFT_STATE_PREFIX))
    matched = match_files(matchable, patterns=contract.triggers, exclude=contract.exclude)
    trigger_files = {path: staged_oids[path] for path in matched}
    digest = compute_contract_digest(contract, contract_id=contract_id, trigger_files=trigger_files)
    return ContractDigestResult(digest=digest, trigger_files=trigger_files)


class DriftIssueKind(StrEnum):
    """Everything `drift check` can flag."""

    DEAD_TRIGGER_PATTERN = "dead_trigger_pattern"
    DEAD_REVIEW_TARGET = "dead_review_target"
    MISSING_ACK = "missing_ack"
    ORPHAN_ACK = "orphan_ack"
    ACK_CONTRACT_MISMATCH = "ack_contract_mismatch"
    DIGEST_MISMATCH = "digest_mismatch"

    @property
    def is_manifest_rot(self) -> bool:
        """Rot issues are fixed by editing drift.toml, not by re-acking."""
        match self:
            case DriftIssueKind.DEAD_TRIGGER_PATTERN | DriftIssueKind.DEAD_REVIEW_TARGET:
                return True
            case DriftIssueKind.MISSING_ACK | DriftIssueKind.ORPHAN_ACK | DriftIssueKind.ACK_CONTRACT_MISMATCH | DriftIssueKind.DIGEST_MISMATCH:
                return False


@dataclass(frozen=True)
class DriftIssue:
    """One check finding: what kind, on which contract, with an optional detail (pattern, field value)."""

    kind: DriftIssueKind
    contract_id: str
    detail: str = ""


def find_issues(manifest: DriftManifest, *, staged_oids: Mapping[str, str], acks: Mapping[str, DriftAck]) -> list[DriftIssue]:
    """Evaluate every check validation over injected index state; empty result means all green."""
    issues: list[DriftIssue] = []
    tracked_files = [path for path in staged_oids if not path.startswith(DRIFT_STATE_PREFIX)]
    for contract_id, contract in manifest.contracts.items():
        for pattern in find_dead_patterns(tracked_files, patterns=contract.triggers):
            issues.append(DriftIssue(kind=DriftIssueKind.DEAD_TRIGGER_PATTERN, contract_id=contract_id, detail=pattern))
        for pattern in find_dead_patterns(tracked_files, patterns=contract.review):
            issues.append(DriftIssue(kind=DriftIssueKind.DEAD_REVIEW_TARGET, contract_id=contract_id, detail=pattern))
        ack = acks.get(contract_id)
        if ack is None:
            issues.append(DriftIssue(kind=DriftIssueKind.MISSING_ACK, contract_id=contract_id))
            continue
        if ack.contract != contract_id:
            issues.append(DriftIssue(kind=DriftIssueKind.ACK_CONTRACT_MISMATCH, contract_id=contract_id, detail=ack.contract))
        digest_result = compute_current_digest(contract, contract_id=contract_id, staged_oids=staged_oids)
        if ack.digest != digest_result.digest:
            issues.append(DriftIssue(kind=DriftIssueKind.DIGEST_MISMATCH, contract_id=contract_id))
    for ack_stem in sorted(acks):
        if ack_stem not in manifest.contracts:
            issues.append(DriftIssue(kind=DriftIssueKind.ORPHAN_ACK, contract_id=ack_stem))
    return issues


@dataclass(frozen=True)
class ContractPlanPacket:
    """Everything `drift plan` renders for one open contract."""

    contract_id: str
    contract: DriftContract
    previous_ack: DriftAck | None
    diff: TriggerFilesDiff


def build_plan_packets(manifest: DriftManifest, *, staged_oids: Mapping[str, str], acks: Mapping[str, DriftAck]) -> list[ContractPlanPacket]:
    """Return a packet per open contract (no ack, or digest mismatch), in manifest order."""
    packets: list[ContractPlanPacket] = []
    for contract_id, contract in manifest.contracts.items():
        ack = acks.get(contract_id)
        digest_result = compute_current_digest(contract, contract_id=contract_id, staged_oids=staged_oids)
        if ack is not None and ack.digest == digest_result.digest:
            continue
        stored = ack.trigger_files if ack is not None else {}
        diff = diff_trigger_files(stored, current=digest_result.trigger_files)
        packets.append(ContractPlanPacket(contract_id=contract_id, contract=contract, previous_ack=ack, diff=diff))
    return packets
