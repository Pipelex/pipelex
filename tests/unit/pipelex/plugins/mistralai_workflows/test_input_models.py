import pytest
from pydantic import ValidationError

from pipelex.plugins.mistralai_workflows.bridge import PipelexPipeRunInput, PipelexPipeRunOutput
from pipelex.plugins.mistralai_workflows.execution_mode import PipelexExecutionMode


class TestInputOutputModels:
    def test_input_defaults_match_design(self):
        payload = PipelexPipeRunInput(pipe_code="some_pipe")
        assert payload.pipe_code == "some_pipe"
        assert payload.inputs == {}
        assert payload.output_name is None
        assert payload.pipeline_run_id is None
        assert payload.user_id is None
        assert payload.library_crate_dump is None
        assert payload.execution_mode is PipelexExecutionMode.DIRECT
        assert payload.delivery_assignment_dump is None

    def test_input_forbids_extra_fields(self):
        with pytest.raises(ValidationError):
            PipelexPipeRunInput.model_validate(
                {
                    "pipe_code": "some_pipe",
                    "unexpected": "field",
                }
            )

    def test_input_requires_pipe_code(self):
        with pytest.raises(ValidationError):
            PipelexPipeRunInput.model_validate({})

    def test_input_round_trip_via_json(self):
        original = PipelexPipeRunInput(
            pipe_code="some_pipe",
            inputs={"foo": "bar"},
            execution_mode=PipelexExecutionMode.TEMPORAL_BLOCKING,
            pipeline_run_id="run-123",
            user_id="alice",
        )
        round_tripped = PipelexPipeRunInput.model_validate(original.model_dump(mode="json"))
        assert round_tripped == original

    def test_output_required_fields(self):
        with pytest.raises(ValidationError):
            PipelexPipeRunOutput.model_validate({"output_dict": {}})  # missing pipeline_run_id and is_completed

    def test_output_forbids_extra_fields(self):
        with pytest.raises(ValidationError):
            PipelexPipeRunOutput.model_validate(
                {
                    "output_dict": {},
                    "pipeline_run_id": "run-1",
                    "is_completed": True,
                    "rogue_field": 42,
                }
            )

    def test_output_round_trip_via_json(self):
        original = PipelexPipeRunOutput(
            output_dict={"foo": "bar"},
            main_stuff_name="main",
            pipeline_run_id="run-1",
            workflow_id=None,
            is_completed=True,
            graph_spec_dump=None,
        )
        round_tripped = PipelexPipeRunOutput.model_validate(original.model_dump(mode="json"))
        assert round_tripped == original
