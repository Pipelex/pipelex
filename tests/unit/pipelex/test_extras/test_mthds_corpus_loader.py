"""Loading the corpus and taking a view of it.

Contract: ``docs/specs/mthds-test-corpus.md`` (workspace root), sections "Entry layout" and
"Loader API".

The bundles themselves are validated by the integration-tier entry gate; this module pins the
layout rules and the filter semantics a consumer selects on.
"""

import pytest

from pipelex.test_extras.mthds_corpus.exceptions import CorpusEntryError
from pipelex.test_extras.mthds_corpus.loader import get_entry, iter_entries
from pipelex.test_extras.mthds_corpus.manifest import EntryGranularity, EntryTier, EntryValidity


class TestMthdsCorpusLoader:
    def test_the_corpus_is_not_empty(self) -> None:
        """Anti-vacuity: every sweep below would pass trivially over an empty corpus."""
        assert list(iter_entries())

    def test_every_entry_loads_and_resolves_its_bundle(self) -> None:
        """Layout enforcement: the manifest name matches the directory, and the bundle resolves."""
        for entry in iter_entries():
            assert entry.manifest.name == entry.directory.name
            assert entry.bundle_path.is_file()

    def test_entries_are_yielded_in_name_order(self) -> None:
        names = [entry.name for entry in iter_entries()]
        assert names == sorted(names)

    def test_entry_names_are_unique(self) -> None:
        names = [entry.name for entry in iter_entries()]
        assert len(names) == len(set(names))

    def test_get_entry_returns_the_named_entry_and_refuses_an_unknown_one(self) -> None:
        first_name = next(iter(iter_entries())).name
        assert get_entry(name=first_name).name == first_name
        with pytest.raises(CorpusEntryError):
            get_entry(name="no_such_entry")

    def test_tag_filter_requires_every_requested_tag(self) -> None:
        for entry in iter_entries(tags=frozenset({"native.text"})):
            assert "native.text" in entry.manifest.covers
        assert not list(iter_entries(tags=frozenset({"native.no_such_tag"})))

    def test_tier_filter_is_a_ceiling_not_an_equality(self) -> None:
        """A consumer running at a tier runs everything it can afford, not only what costs exactly that."""
        for entry in iter_entries(tier=EntryTier.DRY):
            assert entry.manifest.tier.rank <= EntryTier.DRY.rank
        assert len(list(iter_entries(tier=EntryTier.INFERENCE))) == len(list(iter_entries()))

    def test_validity_and_granularity_filter_exactly(self) -> None:
        for entry in iter_entries(validity=EntryValidity.VALID):
            assert entry.manifest.validity is EntryValidity.VALID
        for entry in iter_entries(granularity=EntryGranularity.FOCUSED):
            assert entry.manifest.granularity is EntryGranularity.FOCUSED

    def test_filters_compose_conjunctively(self) -> None:
        selected = list(iter_entries(validity=EntryValidity.VALID, granularity=EntryGranularity.FOCUSED, tier=EntryTier.DRY))
        assert selected
        for entry in selected:
            assert entry.manifest.validity is EntryValidity.VALID
            assert entry.manifest.granularity is EntryGranularity.FOCUSED
            assert entry.manifest.tier.rank <= EntryTier.DRY.rank
