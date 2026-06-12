"""Protocol-level `validate` on :class:`PipelexMTHDSProtocol`.

Pins the runnability verdict on the protocol surface: `pending_signatures` (qualified refs of
pipes still declared as ``PipeSignature`` in the assembled library) and
``is_runnable = not pending_signatures`` — mirroring the agent-CLI / builder validate envelopes —
so a top-down build driving the runtime through the MTHDS Protocol can see what remains to
implement. Also pins the wrapper's library-lifecycle contract: ``validate_bundle`` deliberately
leaves its validation library open and current on success, and the protocol wrapper (a long-lived
entry point) must restore the caller's current-library and tear the validation library down.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from pipelex.hub import clear_current_library, get_current_library_id_or_none, get_library_manager, set_current_library
from pipelex.pipeline.bundle_validator import DryRunStatus
from pipelex.pipeline.exceptions import ValidateBundleError
from pipelex.pipeline.runner import PipelexMTHDSProtocol
from pipelex.pipeline.validation_report import PipelexValidationReport

if TYPE_CHECKING:
    from collections.abc import Callable

    from pytest_mock import MockerFixture

_SIGNATURE_ONLY_DIR = Path(__file__).parents[3] / "e2e" / "pipelex" / "pipes" / "additive_multi_file_library" / "signature_only"

_COMPLETE_MTHDS = """
domain = "protocol_validate"
description = "Minimal complete bundle for protocol-validate tests"

[concept.Summary]
description = "A summary"

[pipe.summarize]
type = "PipeLLM"
description = "Summarize a text"
inputs = { doc = "Text" }
output = "Summary"
prompt = "Summarize $doc"
"""


def _signature_only_contents() -> list[str]:
    return [
        (_SIGNATURE_ONLY_DIR / "concepts.mthds").read_text(encoding="utf-8"),
        (_SIGNATURE_ONLY_DIR / "header.mthds").read_text(encoding="utf-8"),
    ]


@pytest.mark.asyncio(loop_scope="class")
class TestProtocolValidate:
    async def test_complete_bundle_is_runnable(self, load_empty_library: Callable[[], str]) -> None:
        """A complete bundle reports nothing pending and is runnable; the structural artifacts are populated."""
        load_empty_library()
        try:
            runner = PipelexMTHDSProtocol()
            report = await runner.validate(mthds_contents=[_COMPLETE_MTHDS])

            assert isinstance(report, PipelexValidationReport)
            assert report.pending_signatures == []
            assert report.is_runnable is True
            assert report.bundle_blueprint.domain == "protocol_validate"
            # `pipe_structures` and `validated_pipes` are keyed/identified by namespaced pipe_ref.
            assert report.pipe_structures["protocol_validate.summarize"].output.concept_code == "protocol_validate.Summary"
            assert {(entry["pipe_ref"], entry["status"]) for entry in report.validated_pipes} == {
                ("protocol_validate.summarize", DryRunStatus.SUCCESS)
            }
            assert report.graph_spec is None
        finally:
            clear_current_library()

    async def test_pending_signatures_reported_on_lenient_path(self, load_empty_library: Callable[[], str]) -> None:
        """An unsatisfied header validated with ``allow_signatures=True`` is reported as pending — not yet runnable."""
        load_empty_library()
        try:
            runner = PipelexMTHDSProtocol()
            report = await runner.validate(mthds_contents=_signature_only_contents(), allow_signatures=True)

            assert isinstance(report, PipelexValidationReport)
            assert report.pending_signatures == ["research.find_key_findings"]
            assert report.is_runnable is False
        finally:
            clear_current_library()

    async def test_strict_mode_raises_on_unsatisfied_signature(self, load_empty_library: Callable[[], str]) -> None:
        """With the strict default (``allow_signatures=False``), an unsatisfied signature raises instead of reporting."""
        load_empty_library()
        try:
            runner = PipelexMTHDSProtocol()
            with pytest.raises(ValidateBundleError):
                await runner.validate(mthds_contents=_signature_only_contents())
        finally:
            clear_current_library()

    async def test_success_restores_outer_library_and_tears_down_validation_library(
        self,
        load_empty_library: Callable[[], str],
        mocker: MockerFixture,
    ) -> None:
        """On success, the wrapper restores the caller's current-library and tears the validation library down.

        ``validate_bundle`` deliberately leaves its validation library OPEN and current on success
        (the CLI surfaces consume it before process exit) — the protocol wrapper must not.
        """
        outer_library_id = load_empty_library()
        set_current_library(library_id=outer_library_id)
        try:
            library_manager = get_library_manager()
            open_library_spy = mocker.spy(library_manager, "open_library")
            teardown_spy = mocker.spy(library_manager, "teardown")

            runner = PipelexMTHDSProtocol()
            await runner.validate(mthds_contents=[_COMPLETE_MTHDS])

            assert get_current_library_id_or_none() == outer_library_id
            validation_library_id, _ = open_library_spy.spy_return
            latest_teardown = teardown_spy.call_args_list[-1]
            assert latest_teardown.kwargs["library_id"] == validation_library_id
        finally:
            clear_current_library()

    async def test_success_clears_when_no_outer_library(self) -> None:
        """With no outer current-library, a successful validate leaves no current library behind."""
        clear_current_library()
        runner = PipelexMTHDSProtocol()
        await runner.validate(mthds_contents=[_COMPLETE_MTHDS])
        assert get_current_library_id_or_none() is None
