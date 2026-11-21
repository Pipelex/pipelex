import pytest

from pipelex.system.exceptions import RunParameterError
from pipelex.system.job_metadata import JobMetadata, RunMetadata, validate_method_id


def _run_metadata(*, method_id: str | None = None, method_address: str | None = None, capture_pipe_codes: bool | None = None) -> RunMetadata:
    return RunMetadata(
        user_id="user-42",
        pipeline_run_id="run-1",
        storage_scope="tenant/run-1",
        read_scope=None,
        method_id=method_id,
        method_address=method_address,
        capture_pipe_codes=capture_pipe_codes,
    )


class TestJobMetadataRunMethod:
    def test_a_run_names_no_method_and_states_no_setting_by_default(self) -> None:
        run_metadata = _run_metadata()

        assert run_metadata.method_id is None
        assert run_metadata.method_address is None
        assert run_metadata.capture_pipe_codes is None

    @pytest.mark.parametrize("method_id", ["mt_abc123", "3f2b8c4e-0d1a-4e5b-9a7c-2b1d0e9f8a7b", "M" * 128])
    def test_a_usable_method_id_is_kept(self, method_id: str) -> None:
        assert _run_metadata(method_id=method_id).method_id == method_id
        assert validate_method_id(value=method_id) == method_id

    @pytest.mark.parametrize("method_id", ["", "mt_abc@3", "mt abc", "mt_abc\nforged=1", "M" * 129])
    def test_an_unusable_method_id_is_refused(self, method_id: str) -> None:
        with pytest.raises(RunParameterError, match="Invalid method_id"):
            validate_method_id(value=method_id)
        with pytest.raises(ValueError, match="Invalid method_id"):
            _run_metadata(method_id=method_id)

    def test_the_runs_method_its_setting_and_the_pipe_id_cross_a_process_boundary(self) -> None:
        """A worker rebuilds the job metadata from its JSON, and its activities' spans read these fields off it."""
        job_metadata = JobMetadata(
            run_metadata=_run_metadata(method_id="mt_abc", method_address="github.com/acme/methods", capture_pipe_codes=True),
            pipe_code="extract_invoice",
            pipe_id="f" * 32,
        )

        rebuilt = JobMetadata.model_validate_json(job_metadata.model_dump_json())

        assert rebuilt.run_metadata.method_id == "mt_abc"
        assert rebuilt.run_metadata.method_address == "github.com/acme/methods"
        assert rebuilt.run_metadata.capture_pipe_codes is True
        assert rebuilt.pipe_id == "f" * 32

    def test_a_child_copy_replaces_the_pipe_id_and_keeps_the_runs_method(self) -> None:
        job_metadata = JobMetadata(run_metadata=_run_metadata(method_id="mt_abc", capture_pipe_codes=False), pipe_id="a" * 32)

        child = job_metadata.copy_with_update(otel_context=None, pipe_id="b" * 32)

        assert child.pipe_id == "b" * 32
        assert child.run_metadata.method_id == "mt_abc"
        assert child.run_metadata.capture_pipe_codes is False
