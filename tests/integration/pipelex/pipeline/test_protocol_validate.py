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

from pipelex.interpreter_hub import clear_current_library, get_current_library_id_or_none, get_library_manager, set_current_library
from pipelex.libraries.exceptions import LibraryError
from pipelex.pipe_run.exceptions import DryRunError
from pipelex.pipeline.bundle_validator import DryRunStatus
from pipelex.pipeline.exceptions import PipeIOContractError, ValidateBundleError
from pipelex.pipeline.runner import PipelexMTHDSProtocol
from pipelex.pipeline.validation_report import PipelexValidationReport
from pipelex.validation_error_types import HintLintErrorType

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

_MAIN_PIPE_MTHDS = """
domain = "protocol_validate_graph"
description = "Bundle declaring a main_pipe, for the graph arm"
main_pipe = "outline_then_summarize"

[concept.Summary]
description = "A summary"

[pipe.outline_then_summarize]
type = "PipeSequence"
description = "Outline then summarize"
inputs = { doc = "Text" }
output = "Summary"
steps = [
  { pipe = "outline", result = "outline_text" },
  { pipe = "summarize", result = "summary" },
]

[pipe.outline]
type = "PipeLLM"
description = "Outline a text"
inputs = { doc = "Text" }
output = "Text"
prompt = "Outline $doc"

[pipe.summarize]
type = "PipeLLM"
description = "Summarize an outline"
inputs = { outline_text = "Text" }
output = "Summary"
prompt = "Summarize $outline_text"
"""


_HINTED_WARN_MTHDS = """
domain = "protocol_validate_hints"
description = "Bundle carrying an applicable hint and a warnable one, for the advisory hint lint"

[concept.Essay]
description = "An essay"
hints = { intent = "prose", emphasis = "strong" }

[pipe.write_essay]
type = "PipeLLM"
description = "Write an essay"
inputs = { topic = "Text" }
output = "Essay"
prompt = "Write about $topic"
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
            # `pipe_io_contracts` and `validated_pipes` are keyed/identified by namespaced pipe_ref.
            assert report.pipe_io_contracts["protocol_validate.summarize"].output.concept_ref == "protocol_validate.Summary"
            # `input_form` is assembled in the same library window and shares the contracts' key set.
            assert set(report.input_form) == set(report.pipe_io_contracts)
            assert [field.name for field in report.input_form["protocol_validate.summarize"].fields] == list(
                report.pipe_io_contracts["protocol_validate.summarize"].inputs
            )
            assert {(entry["pipe_ref"], entry["status"]) for entry in report.validated_pipes} == {
                ("protocol_validate.summarize", DryRunStatus.SUCCESS)
            }
            # No main_pipe declared → no graph.
            assert report.graph_spec is None
        finally:
            clear_current_library()

    async def test_hint_lint_warns_without_invalidating(self, load_empty_library: Callable[[], str]) -> None:
        """A warnable hint (unknown key) rides the advisory `warnings` channel; the bundle stays
        valid and runnable, and the applicable `intent` beside it warns nothing (spec: hints are
        non-normative — warn only, never reject; well-formed unknown content is preserved).
        """
        load_empty_library()
        try:
            runner = PipelexMTHDSProtocol()
            report = await runner.validate(mthds_contents=[_HINTED_WARN_MTHDS])

            assert isinstance(report, PipelexValidationReport)
            assert report.is_runnable is True
            hint_warnings = [warning for warning in report.warnings if warning.error_type == HintLintErrorType.HINT_UNKNOWN_KEY]
            assert len(hint_warnings) == 1
            assert hint_warnings[0].concept_code == "Essay"
            assert "emphasis" in hint_warnings[0].message
            assert [warning for warning in report.warnings if warning.error_type == HintLintErrorType.HINT_UNKNOWN_INTENT] == []
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

    async def test_graph_populated_on_main_pipe_bundle(
        self,
        load_empty_library: Callable[[], str],
        mocker: MockerFixture,
    ) -> None:
        """A bundle declaring a main_pipe gets a best-effort graph_spec covering the controller
        topology (D4) — and the REAL graph run leaves the library lifecycle intact (no mock here:
        pins that the in-process dry-run does not move the current-library under the wrapper).
        """
        outer_library_id = load_empty_library()
        set_current_library(library_id=outer_library_id)
        try:
            library_manager = get_library_manager()
            open_library_spy = mocker.spy(library_manager, "open_library")
            teardown_spy = mocker.spy(library_manager, "teardown")

            runner = PipelexMTHDSProtocol()
            report = await runner.validate(mthds_contents=[_MAIN_PIPE_MTHDS])

            assert isinstance(report, PipelexValidationReport)
            assert report.graph_spec is not None
            traced_pipe_codes = {node.pipe_code for node in report.graph_spec.nodes if node.pipe_code}
            assert {"outline_then_summarize", "outline", "summarize"} <= traced_pipe_codes
            # The graph arm does not disturb the rest of the report.
            assert report.is_runnable is True
            assert "protocol_validate_graph.outline_then_summarize" in report.pipe_io_contracts

            # Lifecycle with the real graph run: outer current-library restored, validation
            # library torn down.
            assert get_current_library_id_or_none() == outer_library_id
            validation_library_id, _ = open_library_spy.spy_return
            latest_teardown = teardown_spy.call_args_list[-1]
            assert latest_teardown.kwargs["library_id"] == validation_library_id
        finally:
            clear_current_library()

    async def test_explicit_graph_target_without_main_pipe_produces_graph(self, load_empty_library: Callable[[], str]) -> None:
        """Protocol validate can graph an explicit target even when the bundle has no main_pipe."""
        load_empty_library()
        try:
            runner = PipelexMTHDSProtocol()
            report = await runner.validate(mthds_contents=[_COMPLETE_MTHDS], extra={"graph_pipe_code": "summarize"})

            assert isinstance(report, PipelexValidationReport)
            assert report.graph_spec is not None
            traced_pipe_codes = {node.pipe_code for node in report.graph_spec.nodes if node.pipe_code}
            assert traced_pipe_codes == {"summarize"}
        finally:
            clear_current_library()

    async def test_explicit_graph_target_overrides_main_pipe(self, load_empty_library: Callable[[], str]) -> None:
        """Protocol validate graphs the explicit target rather than the declared main_pipe."""
        load_empty_library()
        try:
            runner = PipelexMTHDSProtocol()
            report = await runner.validate(mthds_contents=[_MAIN_PIPE_MTHDS], extra={"graph_pipe_code": "summarize"})

            assert isinstance(report, PipelexValidationReport)
            assert report.graph_spec is not None
            traced_pipe_codes = {node.pipe_code for node in report.graph_spec.nodes if node.pipe_code}
            assert traced_pipe_codes == {"summarize"}
            assert "outline_then_summarize" not in traced_pipe_codes
        finally:
            clear_current_library()

    async def test_unknown_explicit_graph_target_degrades_to_no_graph(self, load_empty_library: Callable[[], str]) -> None:
        """Unknown graph targets stay best-effort: validation succeeds with graph_spec=None."""
        load_empty_library()
        try:
            runner = PipelexMTHDSProtocol()
            report = await runner.validate(
                mthds_contents=[_MAIN_PIPE_MTHDS],
                extra={"graph_pipe_code": "protocol_validate_graph.does_not_exist"},
            )

            assert isinstance(report, PipelexValidationReport)
            assert report.graph_spec is None
            assert report.is_runnable is True
        finally:
            clear_current_library()

    async def test_graph_failure_mid_window_degrades_and_lifecycle_holds(
        self,
        load_empty_library: Callable[[], str],
        mocker: MockerFixture,
    ) -> None:
        """A graph-arm domain failure INSIDE the library window degrades to graph_spec=None with
        validation still successful, and the wrapper's restore/teardown guarantee still holds (D4).
        """
        outer_library_id = load_empty_library()
        set_current_library(library_id=outer_library_id)
        try:
            library_manager = get_library_manager()
            open_library_spy = mocker.spy(library_manager, "open_library")
            teardown_spy = mocker.spy(library_manager, "teardown")
            mocker.patch(
                "pipelex.pipe_run.dry_run_in_process.dry_run_pipe_in_process",
                side_effect=DryRunError("simulated graph dry-run failure"),
            )

            runner = PipelexMTHDSProtocol()
            report = await runner.validate(mthds_contents=[_MAIN_PIPE_MTHDS])

            assert isinstance(report, PipelexValidationReport)
            assert report.graph_spec is None
            assert report.is_runnable is True
            assert "protocol_validate_graph.outline_then_summarize" in report.pipe_io_contracts

            # Lifecycle: the caller's current-library is restored and the validation library torn down.
            assert get_current_library_id_or_none() == outer_library_id
            validation_library_id, _ = open_library_spy.spy_return
            latest_teardown = teardown_spy.call_args_list[-1]
            assert latest_teardown.kwargs["library_id"] == validation_library_id
        finally:
            clear_current_library()

    async def test_empty_contents_raises_structured_error(self) -> None:
        """An EMPTY mthds_contents list (not None) raises a structured ValidateBundleError, never a raw IndexError.

        Regression pin: the empty list passes ``validate_bundle``'s ``is not None`` param check, and
        pre-guard it flowed into ``select_primary_blueprint([])`` → ``IndexError`` on the protocol surface.
        """
        runner = PipelexMTHDSProtocol()
        with pytest.raises(ValidateBundleError, match="must not be empty"):
            await runner.validate(mthds_contents=[])

    async def test_strict_mode_reports_unsatisfied_signature(self, load_empty_library: Callable[[], str]) -> None:
        """Signatures are never an error (D-B): with the strict default (``allow_signatures=False``) an
        unsatisfied signature is reported as pending — not yet runnable — exactly as the lenient path
        does (strict ≡ lenient in the report body). The "is this a failure?" decision moves to the consumer.
        """
        load_empty_library()
        try:
            runner = PipelexMTHDSProtocol()
            report = await runner.validate(mthds_contents=_signature_only_contents())

            assert isinstance(report, PipelexValidationReport)
            assert report.pending_signatures == ["research.find_key_findings"]
            assert report.is_runnable is False
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

    async def test_teardown_failure_after_success_propagates(
        self,
        load_empty_library: Callable[[], str],
        mocker: MockerFixture,
    ) -> None:
        """A teardown raise after a SUCCESSFUL body propagates to the caller (never silently
        suppressed), with the caller's current-library already restored first.

        Also a regression pin for the body-success detection: the wrapper must key suppression
        on its OWN body outcome, not on ``sys.exc_info()`` — which also sees an exception the
        caller happens to be handling and would wrongly swallow the teardown failure here.
        """
        outer_library_id = load_empty_library()
        set_current_library(library_id=outer_library_id)
        try:
            library_manager = get_library_manager()
            mocker.patch.object(library_manager, "teardown", side_effect=LibraryError("simulated teardown failure"))

            runner = PipelexMTHDSProtocol()
            with pytest.raises(LibraryError, match="simulated teardown failure"):
                await runner.validate(mthds_contents=[_COMPLETE_MTHDS])

            assert get_current_library_id_or_none() == outer_library_id
        finally:
            clear_current_library()

    async def test_body_failure_mid_window_propagates_over_teardown_failure(
        self,
        load_empty_library: Callable[[], str],
        mocker: MockerFixture,
    ) -> None:
        """When the body fails INSIDE the library window and teardown ALSO fails, the BODY's
        error reaches the caller (the teardown error is suppressed and logged) and the caller's
        current-library is restored — the failure path of the wrapper's lifecycle contract.
        """
        outer_library_id = load_empty_library()
        set_current_library(library_id=outer_library_id)
        try:
            library_manager = get_library_manager()
            mocker.patch(
                "pipelex.pipeline.validate_in_process.build_pipe_io_contracts",
                side_effect=PipeIOContractError(message="simulated render failure"),
            )
            mocker.patch.object(library_manager, "teardown", side_effect=LibraryError("simulated teardown failure"))

            runner = PipelexMTHDSProtocol()
            with pytest.raises(PipeIOContractError, match="simulated render failure"):
                await runner.validate(mthds_contents=[_COMPLETE_MTHDS])

            assert get_current_library_id_or_none() == outer_library_id
        finally:
            clear_current_library()
