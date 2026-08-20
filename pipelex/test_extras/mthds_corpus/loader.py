"""The MTHDS Test Corpus loader — how a consumer takes a view of the corpus.

Contract: ``docs/specs/mthds-test-corpus.md`` (workspace root), section "Loader API".
A consumer selects entries by the axes it declares rather than by path convention, so
reorganizing storage never breaks it.
"""

from collections.abc import Iterator
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from pipelex.builder.conventions import DEFAULT_INPUTS_FILE_NAME
from pipelex.cli.bundle_target_resolution import BundleTargetResolutionError, resolve_bundle_target_core
from pipelex.test_extras.mthds_corpus.exceptions import CorpusEntryError
from pipelex.test_extras.mthds_corpus.manifest import (
    MANIFEST_FILE_NAME,
    CorpusEntryManifest,
    EntryGranularity,
    EntryTier,
    EntryValidity,
)
from pipelex.test_extras.mthds_corpus.resources import entries_root
from pipelex.tools.misc.toml_utils import load_toml_from_path


class CorpusEntry(BaseModel):
    """One corpus entry: its manifest, its directory, and the paths a consumer needs."""

    model_config = ConfigDict(frozen=True)

    manifest: CorpusEntryManifest
    directory: Path
    bundle_path: Path
    inputs_path: Path | None

    @property
    def name(self) -> str:
        return self.manifest.name


def _resolve_bundle_path(*, directory: Path) -> Path:
    """Pick the entry's bundle file through the very resolution ``pipelex validate bundle <dir>`` runs.

    The contract says an entry directory is a valid CLI argument as it stands — either exactly one
    ``.mthds`` file, or several with a ``bundle.mthds`` entry point. That claim is made true by
    calling the CLI's own core rather than by keeping a corpus copy of its rules: a copy is how the
    two drift, and a hand-rolled glob had already lost the core's refusal to auto-detect a symlinked
    bundle. Only the rendering of a failure is ours.
    """
    resolved = resolve_bundle_target_core(str(directory), library_dir=None)
    if isinstance(resolved, BundleTargetResolutionError):
        candidates = ", ".join(candidate.name for candidate in resolved.candidate_files)
        detail = f" ({candidates})" if candidates else ""
        msg = f"Corpus entry '{directory.name}' does not resolve to a bundle: {resolved.kind}{detail}"
        raise CorpusEntryError(msg)
    return resolved.bundle_path


def load_entry(*, directory: Path) -> CorpusEntry:
    """Load one entry from its directory, enforcing the layout rules the contract pins."""
    manifest_path = directory / MANIFEST_FILE_NAME
    if not manifest_path.is_file():
        msg = f"Corpus entry '{directory.name}' has no '{MANIFEST_FILE_NAME}'"
        raise CorpusEntryError(msg)
    manifest = CorpusEntryManifest.model_validate(load_toml_from_path(manifest_path))
    if manifest.name != directory.name:
        msg = f"Corpus entry directory '{directory.name}' declares the name '{manifest.name}'; the two must match"
        raise CorpusEntryError(msg)
    inputs_path = directory / DEFAULT_INPUTS_FILE_NAME
    return CorpusEntry(
        manifest=manifest,
        directory=directory,
        bundle_path=_resolve_bundle_path(directory=directory),
        inputs_path=inputs_path if inputs_path.is_file() else None,
    )


def get_entry(*, name: str) -> CorpusEntry:
    """Load the one entry with this name — what a consumer that wants a specific method calls."""
    directory = entries_root() / name
    if not directory.is_dir():
        msg = f"There is no corpus entry named '{name}'"
        raise CorpusEntryError(msg)
    return load_entry(directory=directory)


def iter_entries(
    *,
    tags: frozenset[str] | None = None,
    tier: EntryTier | None = None,
    validity: EntryValidity | None = None,
    granularity: EntryGranularity | None = None,
) -> Iterator[CorpusEntry]:
    """Yield the corpus entries matching every filter given, in entry-name order.

    Filters compose conjunctively, and omitting one places no restriction on that axis:

    - ``tags`` matches an entry that covers **all** the requested tags.
    - ``tier`` matches an entry whose tier is the requested one or cheaper, which is what a
      consumer running at a given tier can actually execute.
    - ``validity`` and ``granularity`` match exactly.

    Ordering is entry-name lexicographic and stable, so parametrized test ids do not churn.
    """
    for directory in sorted(entries_root().iterdir(), key=lambda path: path.name):
        if not directory.is_dir():
            continue
        entry = load_entry(directory=directory)
        if tags is not None and not tags.issubset(entry.manifest.covers):
            continue
        if tier is not None and entry.manifest.tier.rank > tier.rank:
            continue
        if validity is not None and entry.manifest.validity != validity:
            continue
        if granularity is not None and entry.manifest.granularity != granularity:
            continue
        yield entry
