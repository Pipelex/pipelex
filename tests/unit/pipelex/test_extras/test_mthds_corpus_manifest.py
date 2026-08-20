"""The strict `entry.toml` model.

Contract: ``docs/specs/mthds-test-corpus.md`` (workspace root), section "The entry manifest".

Strictness is the point: an unknown key is an error rather than a forward-compatibility
affordance, so a new field is a change to the spec and to the model in the same commit.
"""

import pytest
from pydantic import ValidationError

from pipelex.test_extras.mthds_corpus.manifest import CorpusEntryManifest, EntryTier, EntryValidity

_MINIMAL_MANIFEST_FIELDS: dict[str, object] = {
    "name": "shipping_manifest_totals",
    "description": "A description.",
    "validity": "valid",
    "tier": "static",
    "granularity": "focused",
    "covers": ["native.text"],
}


def _manifest_fields(**overrides: object) -> dict[str, object]:
    return {**_MINIMAL_MANIFEST_FIELDS, **overrides}


class TestMthdsCorpusManifest:
    def test_minimal_manifest_parses(self) -> None:
        manifest = CorpusEntryManifest.model_validate(_manifest_fields())
        assert manifest.tier is EntryTier.STATIC
        assert manifest.validity is EntryValidity.VALID

    def test_unknown_key_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            CorpusEntryManifest.model_validate(_manifest_fields(unexpected_field="x"))

    def test_empty_covers_is_rejected(self) -> None:
        """An entry that covers nothing has no reason to exist."""
        with pytest.raises(ValidationError):
            CorpusEntryManifest.model_validate(_manifest_fields(covers=[]))

    def test_repeated_tag_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            CorpusEntryManifest.model_validate(_manifest_fields(covers=["native.text", "native.text"]))

    def test_non_snake_case_name_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            CorpusEntryManifest.model_validate(_manifest_fields(name="ShippingManifestTotals"))

    def test_invalid_entry_must_declare_its_expected_error(self) -> None:
        with pytest.raises(ValidationError):
            CorpusEntryManifest.model_validate(_manifest_fields(validity="invalid"))

    def test_valid_entry_must_not_declare_an_expected_error(self) -> None:
        """A valid entry carrying an expected error would be claiming both verdicts at once."""
        with pytest.raises(ValidationError):
            CorpusEntryManifest.model_validate(_manifest_fields(expected_error="missing_input_variable"))

    def test_tiers_rank_cheapest_first(self) -> None:
        assert EntryTier.STATIC.rank < EntryTier.DRY.rank < EntryTier.OFFLINE.rank < EntryTier.INFERENCE.rank
