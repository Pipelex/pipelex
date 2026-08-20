"""The MTHDS Test Corpus entry-validation gate: every entry means what its manifest claims.

Contract: ``docs/specs/mthds-test-corpus.md`` (workspace root), section "Gates" →
"Corpus-side: entry validation".

It drives the in-process validation engine — the one behind ``pipelex validate bundle`` — and
never a hosted API: the corpus is defined against the local runtime, and a deployed API lags
it, so an API verdict would call a correct entry invalid on the day its feature lands.

The gate runs over **every** entry regardless of tier, so an ``inference``-tier entry that
stopped validating is caught in the default suite without spending a token.
"""

from pathlib import Path

import pytest

from pipelex.pipeline.exceptions import ValidateBundleError
from pipelex.pipeline.validate_bundle import validate_bundle
from pipelex.test_extras.mthds_corpus.loader import CorpusEntry, iter_entries
from pipelex.test_extras.mthds_corpus.manifest import EntryValidity

_VALID_ENTRIES = list(iter_entries(validity=EntryValidity.VALID))
_INVALID_ENTRIES = list(iter_entries(validity=EntryValidity.INVALID))


def _entry_id(entry: CorpusEntry) -> str:
    return entry.name


@pytest.mark.asyncio(loop_scope="class")
class TestMthdsCorpusEntries:
    @pytest.mark.parametrize("entry", _VALID_ENTRIES, ids=_entry_id)
    async def test_valid_entry_validates(self, entry: CorpusEntry) -> None:
        result = await validate_bundle(mthds_file_path=entry.bundle_path, library_dirs=[entry.directory])

        assert result.blueprints, f"Corpus entry '{entry.name}' produced no blueprint"

    @pytest.mark.parametrize("entry", _INVALID_ENTRIES, ids=_entry_id)
    async def test_invalid_entry_fails_with_exactly_its_declared_error(self, entry: CorpusEntry) -> None:
        """Red both ways: when the entry fails differently, and when it accidentally validates.

        An invalid entry is surgically authored to trigger exactly one error, so a widened blast
        radius (two errors now, one of them the declared one) fails here too — that is the point
        of the discipline, not an accident of the assertion.
        """
        with pytest.raises(ValidateBundleError) as raised:
            await validate_bundle(mthds_file_path=entry.bundle_path, library_dirs=[entry.directory])

        observed = [item.error_type for item in raised.value.to_error_report().validation_errors or []]
        assert observed == [entry.manifest.expected_error], (
            f"Corpus entry '{entry.name}' declares expected_error={entry.manifest.expected_error!r} but produced {observed!r}"
        )

    async def test_the_invalid_arm_bites_when_a_declared_error_stops_being_produced(self, tmp_path: Path) -> None:
        """The arm above is red when an invalid entry stops meaning what it claims — shown, not assumed.

        Every corpus entry passes that arm, which is exactly what makes its failure mode
        unobservable in the suite: nothing in a green run demonstrates that a *wrong* declaration
        would be caught. So the arm's comparison is run here in both directions over a bundle whose
        single fault is known — equal to the declaration a correct entry would carry, unequal to the
        one a drifted entry would. It also pins the machinery the arm rests on: that a broken bundle
        raises, and that the raised error projects the exact wire `error_type` an `expected_error`
        is compared against.
        """
        bundle_path = tmp_path / "bundle.mthds"
        bundle_path.write_text(
            """domain      = "harbour_moorings"
description = "Write the note telling a vessel where and when to moor"
main_pipe   = "write_berth_note"

[pipe.write_berth_note]
type        = "PipeLLM"
description = "Write the berth note for a vessel"
inputs      = { vessel = "Text" }
output      = "Text"
prompt      = "Write the berth note for $vessel arriving on the $tide tide."
""",
            encoding="utf-8",
        )

        with pytest.raises(ValidateBundleError) as raised:
            await validate_bundle(mthds_file_path=bundle_path, library_dirs=[tmp_path])

        declared_by_a_correct_entry = "missing_input_variable"
        declared_by_a_drifted_entry = "unknown_pipe_type"

        observed = [item.error_type for item in raised.value.to_error_report().validation_errors or []]
        assert observed == [declared_by_a_correct_entry]
        assert observed != [declared_by_a_drifted_entry]
