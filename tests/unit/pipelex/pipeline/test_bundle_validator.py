"""Unit tests for the BundleValidator classify engine (Phase 2).

These pin the tolerant per-pipe classification, the D3 union catch + recursive SKIPPED
cause-walk, the strict-mode signature exclusion (signatures are never an error — D-B), the
single collect-all aggregate (no per-pipe early abort), and the per-sweep telemetry. The seams
(``prepare_pipe_job``) and the run primitive (``PipeRun``) are mocked here; the real composition
is exercised by the integration suite.
"""

import pytest
from polyfactory.exceptions import FactoryException
from pydantic import BaseModel, ValidationError
from pytest_mock import MockerFixture

from pipelex.base_exceptions import PipelexError
from pipelex.core.pipes.exceptions import PipeRunError
from pipelex.libraries.pipe.exceptions import PipeNotFoundError
from pipelex.pipe_run.exceptions import DryRunError
from pipelex.pipeline.bundle_validator import BundleValidator, DryRunStatus
from pipelex.system.pipe_run_mode import PipeRunMode
from pipelex.system.telemetry.events import EventName, EventProperty


class TestBundleValidator:
    def _make_pipe(self, mocker: MockerFixture, *, code: str, pipe_ref: str, is_signature: bool = False):
        pipe = mocker.MagicMock()
        pipe.code = code
        pipe.pipe_ref = pipe_ref
        pipe.is_signature = is_signature
        pipe.pipe_dependencies.return_value = set()
        pipe.validate_with_libraries.return_value = None
        return pipe

    def _patch_env(self, mocker: MockerFixture, *, allowed_to_fail: list[str] | None = None):
        """Patch the hub getters, ``prepare_pipe_job``, and the ``PipeRun`` class in bundle_validator.

        Returns ``(validator, telemetry_manager, prepare_mock, pipe_run)`` so callers can assert on the
        telemetry / seam / run interactions. ``pipe_run.run`` defaults to a success-returning
        ``AsyncMock`` — individual tests override its ``return_value`` / ``side_effect``. Patching the
        ``PipeRun`` symbol (rather than reaching into the instance's protected ``_pipe_run``) keeps the
        test off the validator's private surface.
        """
        telemetry_manager = mocker.patch("pipelex.pipeline.bundle_validator.get_telemetry_manager").return_value
        mock_get_config = mocker.patch("pipelex.pipeline.bundle_validator.get_config")
        mock_get_config.return_value.pipelex.dry_run_config.allowed_to_fail_pipes = allowed_to_fail or []
        prepare_mock = mocker.patch("pipelex.pipeline.bundle_validator.prepare_pipe_job")
        prepare_mock.return_value = mocker.MagicMock(name="pipe_job")
        pipe_run = mocker.MagicMock(name="pipe_run")
        pipe_run.run = mocker.AsyncMock(return_value=mocker.MagicMock(name="pipe_output"))
        mocker.patch("pipelex.pipeline.bundle_validator.PipeRun", return_value=pipe_run)
        return BundleValidator(), telemetry_manager, prepare_mock, pipe_run

    @pytest.mark.asyncio
    async def test_success_classification(self, mocker: MockerFixture) -> None:
        validator, _telemetry, _prepare, _pipe_run = self._patch_env(mocker)
        pipe = self._make_pipe(mocker, code="ok_pipe", pipe_ref="dom.ok_pipe")

        results = await validator.validate_pipes([pipe], library_id="lib-1")

        assert results["dom.ok_pipe"].status.is_success
        assert results["dom.ok_pipe"].pipe_ref == "dom.ok_pipe"
        assert results["dom.ok_pipe"].pipe_code == "ok_pipe"

    @pytest.mark.asyncio
    async def test_skipped_when_prepare_raises_bare_pipe_not_found(self, mocker: MockerFixture) -> None:
        # A cross-package unresolved dependency surfaces during mock-input build (prepare_pipe_job)
        # as a bare PipeNotFoundError — reclassify as SKIPPED, never SUCCESS, never a sweep abort.
        validator, _telemetry, prepare_mock, _pipe_run = self._patch_env(mocker)
        prepare_mock.side_effect = PipeNotFoundError("dep->other.missing not found")
        pipe = self._make_pipe(mocker, code="dep_pipe", pipe_ref="dom.dep_pipe")

        results = await validator.validate_pipes([pipe], library_id="lib-1")

        assert results["dom.dep_pipe"].status == DryRunStatus.SKIPPED
        assert not results["dom.dep_pipe"].status.is_success
        assert results["dom.dep_pipe"].error_message is not None
        assert "unresolved dependency" in results["dom.dep_pipe"].error_message

    @pytest.mark.asyncio
    async def test_skipped_when_run_raises_wrapped_pipe_not_found(self, mocker: MockerFixture) -> None:
        # Routing through PipeRun.run no longer surfaces a bare PipeNotFoundError: the run layer
        # re-raises and the router wraps it. The recursive __cause__ walk must still reclassify SKIPPED.
        validator, _telemetry, _prepare, pipe_run = self._patch_env(mocker)
        cause = PipeNotFoundError("dep->other.missing not found")
        wrapped = PipeRunError(message="run failed", run_mode=PipeRunMode.DRY, pipe_code="dep_pipe")
        wrapped.__cause__ = cause
        pipe_run.run = mocker.AsyncMock(side_effect=wrapped)
        pipe = self._make_pipe(mocker, code="dep_pipe", pipe_ref="dom.dep_pipe")

        results = await validator.validate_pipes([pipe], library_id="lib-1")

        assert results["dom.dep_pipe"].status == DryRunStatus.SKIPPED

    @pytest.mark.asyncio
    async def test_allowed_failure_returned_in_map_without_raising(self, mocker: MockerFixture) -> None:
        # A FactoryException (e.g. a PipeSignature mint) on an allowed-to-fail pipe is a handled FAILURE
        # carried in the returned map — the sweep does NOT raise because it is not an unexpected failure.
        validator, _telemetry, _prepare, pipe_run = self._patch_env(mocker, allowed_to_fail=["dom.allowed_pipe"])
        pipe_run.run = mocker.AsyncMock(side_effect=FactoryException("polyfactory could not build mock content"))
        pipe = self._make_pipe(mocker, code="allowed_pipe", pipe_ref="dom.allowed_pipe")

        results = await validator.validate_pipes([pipe], library_id="lib-1")

        assert results["dom.allowed_pipe"].status.is_failure
        assert results["dom.allowed_pipe"].error_message is not None
        assert "allowed_pipe" in results["dom.allowed_pipe"].error_message

    @pytest.mark.asyncio
    async def test_bare_code_in_allowed_to_fail_does_not_match_namespaced_ref(self, mocker: MockerFixture) -> None:
        # C-7: allowed_to_fail matches the namespaced pipe_ref, not the bare code. A config entry holding
        # only the bare code ("allowed_pipe") must NOT tolerate the namespaced pipe ("dom.allowed_pipe") —
        # the failure is unexpected and aggregates into a DryRunError. (The positive namespaced match is
        # pinned by test_allowed_failure_returned_in_map_without_raising.)
        validator, _telemetry, _prepare, pipe_run = self._patch_env(mocker, allowed_to_fail=["allowed_pipe"])
        pipe_run.run = mocker.AsyncMock(side_effect=FactoryException("polyfactory could not build mock content"))
        pipe = self._make_pipe(mocker, code="allowed_pipe", pipe_ref="dom.allowed_pipe")

        with pytest.raises(DryRunError) as exc_info:
            await validator.validate_pipes([pipe], library_id="lib-1")
        assert "dom.allowed_pipe" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_unexpected_validation_error_raises_dry_run_error(self, mocker: MockerFixture) -> None:
        # A pydantic ValidationError on a non-allowed pipe classifies FAILURE and is aggregated into a
        # single DryRunError (third-party-exception classify — FAILURE, not an escaping traceback).
        validator, _telemetry, _prepare, pipe_run = self._patch_env(mocker)

        class _Tiny(BaseModel):
            value: int

        with pytest.raises(ValidationError) as captured:
            _Tiny.model_validate({"value": "not-an-int"})
        pipe_run.run = mocker.AsyncMock(side_effect=captured.value)
        pipe = self._make_pipe(mocker, code="bad_pipe", pipe_ref="dom.bad_pipe")

        with pytest.raises(DryRunError) as exc_info:
            await validator.validate_pipes([pipe], library_id="lib-1")
        assert "dom.bad_pipe" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_widening_non_dependency_error_does_not_abort_remaining_pipes(self, mocker: MockerFixture) -> None:
        # D3 widening: a non-dependency PipelexError raised mid-run is a per-pipe FAILURE, NOT a sweep
        # abort. The narrow tuple the old path used would let it escape and abort before the next pipe;
        # the base-PipelexError catch keeps the loop going, so the second pipe still runs.
        validator, _telemetry, _prepare, pipe_run = self._patch_env(mocker)
        pipe_run.run = mocker.AsyncMock(side_effect=[PipelexError("unexpected domain failure"), mocker.MagicMock(name="ok_output")])
        failing_pipe = self._make_pipe(mocker, code="boom_pipe", pipe_ref="dom.boom_pipe")
        ok_pipe = self._make_pipe(mocker, code="ok_pipe", pipe_ref="dom.ok_pipe")

        with pytest.raises(DryRunError) as exc_info:
            await validator.validate_pipes([failing_pipe, ok_pipe], library_id="lib-1")

        # The second pipe ran (no abort) — both were executed before the aggregate raise.
        assert pipe_run.run.call_count == 2
        assert "dom.boom_pipe" in str(exc_info.value)
        assert "dom.ok_pipe" not in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_collect_all_unexpected_failures_reported(self, mocker: MockerFixture) -> None:
        # Collect-all, not first-failure-abort: a sweep with >= 2 non-allowed failures reports BOTH in one
        # aggregated error.
        validator, _telemetry, _prepare, pipe_run = self._patch_env(mocker)
        pipe_run.run = mocker.AsyncMock(side_effect=[PipelexError("fail one"), PipelexError("fail two")])
        pipe_a = self._make_pipe(mocker, code="a_pipe", pipe_ref="dom.a_pipe")
        pipe_b = self._make_pipe(mocker, code="b_pipe", pipe_ref="dom.b_pipe")

        with pytest.raises(DryRunError) as exc_info:
            await validator.validate_pipes([pipe_a, pipe_b], library_id="lib-1")
        message = str(exc_info.value)
        assert "dom.a_pipe" in message
        assert "dom.b_pipe" in message

    @pytest.mark.asyncio
    async def test_strict_mode_excludes_signature_pipes_from_sweep(self, mocker: MockerFixture) -> None:
        # Signatures are never an error (D-B): in strict mode a signature pipe is excluded from the sweep
        # entirely — not mock-run (the seam is never invoked) and absent from the returned status map (so
        # absent from validated_pipes). The unsatisfied set is reported library-wide via pending_signatures.
        validator, _telemetry, prepare_mock, _pipe_run = self._patch_env(mocker)
        signature_pipe = self._make_pipe(mocker, code="sig_pipe", pipe_ref="dom.sig_pipe", is_signature=True)

        results = await validator.validate_pipes([signature_pipe], library_id="lib-1", allow_signatures=False)

        assert results == {}
        prepare_mock.assert_not_called()

    @pytest.mark.asyncio
    async def test_lenient_mode_sweeps_signature_pipes(self, mocker: MockerFixture) -> None:
        # allow_signatures is sweep mechanics (D-B): in lenient mode a signature pipe IS swept (it dry-runs
        # trivially by minting a mock) and therefore appears in the returned status map / validated_pipes.
        validator, _telemetry, prepare_mock, _pipe_run = self._patch_env(mocker)
        signature_pipe = self._make_pipe(mocker, code="sig_pipe", pipe_ref="dom.sig_pipe", is_signature=True)

        results = await validator.validate_pipes([signature_pipe], library_id="lib-1", allow_signatures=True)

        assert results["dom.sig_pipe"].status.is_success
        prepare_mock.assert_called_once()

    @pytest.mark.asyncio
    async def test_wiring_error_propagates(self, mocker: MockerFixture) -> None:
        # The static wiring pass runs first and can raise (real validate_with_libraries raises
        # PipeValidationError) — a wiring failure aborts the sweep rather than being swallowed.
        validator, _telemetry, _prepare, _pipe_run = self._patch_env(mocker)
        wiring_pipe = self._make_pipe(mocker, code="wiring_pipe", pipe_ref="dom.wiring_pipe")
        # Stand-in for a wiring error (real validate_with_libraries raises PipeValidationError).
        wiring_pipe.validate_with_libraries.side_effect = RuntimeError("wiring failed")

        with pytest.raises(RuntimeError, match="wiring failed"):
            await validator.validate_pipes([wiring_pipe], library_id="lib-1", allow_signatures=False)

    @pytest.mark.asyncio
    async def test_one_pipe_dry_run_event_emitted_for_the_sweep(self, mocker: MockerFixture) -> None:
        validator, telemetry_manager, _prepare, _pipe_run = self._patch_env(mocker)
        pipes = [self._make_pipe(mocker, code=f"p{idx}", pipe_ref=f"dom.p{idx}") for idx in range(3)]

        await validator.validate_pipes(pipes, library_id="lib-1")

        telemetry_manager.track_event.assert_called_once_with(
            event_name=EventName.PIPE_DRY_RUN,
            properties={EventProperty.NB_PIPES: 3},
        )

    @pytest.mark.asyncio
    async def test_sweep_threads_unique_dry_run_id_into_prepare(self, mocker: MockerFixture) -> None:
        # Each sweep dry-runs its pipes under a UNIQUE per-sweep pipeline run id (a `dry_run_`-prefixed
        # uuid) threaded into prepare_pipe_job. The live registry is gone (usage rides on PipeOutput), so
        # there is no per-sweep cleanup to verify — but the id threading survives. Pin that prepare is
        # called with a `dry_run_`-prefixed id even when a pipe run raises an uncaught exception.
        validator, _telemetry, prepare, pipe_run = self._patch_env(mocker)
        pipe_run.run = mocker.AsyncMock(side_effect=KeyError("uncaught programming bug"))
        pipe = self._make_pipe(mocker, code="p", pipe_ref="dom.p")

        with pytest.raises(KeyError):
            await validator.validate_pipes([pipe], library_id="lib-1")

        threaded_id = prepare.call_args.kwargs["pipeline_run_id"]
        assert threaded_id.startswith("dry_run_")
