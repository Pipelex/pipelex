"""Per-repo bundle paths for the local / Temporal ``ErrorReport`` parity pair.

The parity-invariant fixtures (the injected failure + its expected classification) and the error
factories are the single shared source of truth in ``pipelex.test_extras.error_report_parity`` —
shipped in the open-core wheel so this repo's local arm and the closed ``pipelex-temporal``
plugin's Temporal arm import the *same* data and cannot silently diverge. Only the ``.mthds``
bundle each repo ships is genuinely per-repo, so that is all these subclasses add.
"""

from typing import ClassVar

from pipelex.test_extras.error_report_parity import ErrorReportParityTestData as SharedErrorReportParityTestData
from pipelex.test_extras.error_report_parity import SearchErrorReportParityTestData as SharedSearchErrorReportParityTestData


class ErrorReportParityTestData(SharedErrorReportParityTestData):
    """Local-arm view of the parity fixtures, pointing at this repo's ``native_text_sequence`` bundle."""

    BUNDLE_FILE: ClassVar[str] = "tests/integration/pipelex/error_handling/bundles/native_text_sequence.mthds"


class SearchErrorReportParityTestData(SharedSearchErrorReportParityTestData):
    """Local-arm view of the search parity fixtures, pointing at this repo's ``native_search`` bundle."""

    BUNDLE_FILE: ClassVar[str] = "tests/integration/pipelex/error_handling/bundles/native_search.mthds"
