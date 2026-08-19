import pytest
from pydantic import ValidationError

from pipelex.runtime_bridge.delivery_mode import DeliveryMode
from pipelex.runtime_bridge.payloads import PipelexPipeDispatchAck, PipelexPipeRunInput, PipelexPipeRunOutput


class TestInputOutputModels:
    def test_input_defaults_match_design(self):
        payload = PipelexPipeRunInput(storage_scope="test/scope", user_id="test-user", pipe_code="some_pipe")
        assert payload.pipe_code == "some_pipe"
        assert payload.inputs == {}
        assert payload.output_name is None
        assert payload.pipeline_run_id is None
        # `user_id` and `storage_scope` are REQUIRED and non-nullable — this is
        # the wire boundary where a missing identity used to become "anonymous"
        # and a missing scope used to be derived from it, pointing every such run
        # at one shared namespace.
        assert payload.user_id == "test-user"
        assert payload.storage_scope == "test/scope"
        assert payload.library_crate_dump is None
        assert payload.orchestration_mode == "direct"
        assert payload.delivery is DeliveryMode.BLOCKING
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
            storage_scope="test/scope",
            pipe_code="some_pipe",
            inputs={"foo": "bar"},
            orchestration_mode="temporal",
            delivery=DeliveryMode.FIRE_AND_FORGET,
            pipeline_run_id="run-123",
            user_id="alice",
        )
        round_tripped = PipelexPipeRunInput.model_validate(original.model_dump(mode="json"))
        assert round_tripped == original

    def test_output_required_fields(self):
        with pytest.raises(ValidationError):
            PipelexPipeRunOutput.model_validate({"output_dict": {}})  # missing pipeline_run_id and main_stuff_name

    def test_output_requires_main_stuff_name(self):
        """A completed run always delivers a main stuff, so the boundary DTO requires its name."""
        with pytest.raises(ValidationError):
            PipelexPipeRunOutput.model_validate(
                {
                    "output_dict": {},
                    "pipeline_run_id": "run-1",
                }
            )

    def test_output_forbids_extra_fields(self):
        with pytest.raises(ValidationError):
            PipelexPipeRunOutput.model_validate(
                {
                    "output_dict": {},
                    "main_stuff_name": "main",
                    "pipeline_run_id": "run-1",
                    "rogue_field": 42,
                }
            )

    def test_output_rejects_is_completed(self):
        """The completed-run DTO has no is_completed flag: a fire-and-forget dispatch returns a PipelexPipeDispatchAck instead."""
        with pytest.raises(ValidationError):
            PipelexPipeRunOutput.model_validate(
                {
                    "output_dict": {},
                    "main_stuff_name": "main",
                    "pipeline_run_id": "run-1",
                    "is_completed": True,
                }
            )

    def test_output_round_trip_via_json(self):
        original = PipelexPipeRunOutput(
            output_dict={"foo": "bar"},
            main_stuff_name="main",
            pipeline_run_id="run-1",
            workflow_id=None,
            graph_spec_dump=None,
        )
        round_tripped = PipelexPipeRunOutput.model_validate(original.model_dump(mode="json"))
        assert round_tripped == original

    def test_dispatch_ack_requires_both_ids(self):
        """A fire-and-forget ack is ids-only, and both ids are required — a genuine enqueue always has a workflow id."""
        ack = PipelexPipeDispatchAck(pipeline_run_id="run-1", workflow_id="wf-1")
        assert ack.pipeline_run_id == "run-1"
        assert ack.workflow_id == "wf-1"
        with pytest.raises(ValidationError):
            PipelexPipeDispatchAck.model_validate({"pipeline_run_id": "run-1"})
        with pytest.raises(ValidationError):
            PipelexPipeDispatchAck.model_validate({"workflow_id": "wf-1"})

    def test_dispatch_ack_forbids_output_fields(self):
        """The ack must not smuggle completed-run fields."""
        with pytest.raises(ValidationError):
            PipelexPipeDispatchAck.model_validate(
                {
                    "pipeline_run_id": "run-1",
                    "workflow_id": "wf-1",
                    "output_dict": {},
                }
            )


class TestTheWireRefusesAnUnusableScope:
    """A bridge payload crosses a process boundary, so its scope is whatever the other side sent.

    Requiring the field is not the same as validating it: `storage_scope: str`
    accepted `../other/run` happily, and the value then travelled until
    something pasted it into a storage key. Validating at construction makes a
    traversal a payload-decoding error naming the field, at the edge, before any
    storage call — which is the same reason `user_id` is required here.
    """

    @pytest.mark.parametrize(
        "bad_scope",
        [
            pytest.param("../other/run", id="traversal-leading"),
            pytest.param("tenant/../other", id="traversal-interior"),
            pytest.param("/tenant/run", id="leading-slash-absolute-key"),
            pytest.param("tenant/run/", id="trailing-slash-empty-final-segment"),
            pytest.param("", id="empty"),
            pytest.param("a/b/c/d", id="four-segments-would-swallow-the-leaf"),
            pytest.param("tenant/run\n", id="trailing-newline"),
        ],
    )
    def test_an_unsafe_scope_is_refused_at_construction(self, bad_scope: str):
        with pytest.raises(ValidationError):
            PipelexPipeRunInput(storage_scope=bad_scope, user_id="test-user", pipe_code="some_pipe")

    def test_a_usable_scope_still_passes(self):
        payload = PipelexPipeRunInput(storage_scope="org_a/mt_b/run_c", user_id="test-user", pipe_code="some_pipe")
        assert payload.storage_scope == "org_a/mt_b/run_c"
