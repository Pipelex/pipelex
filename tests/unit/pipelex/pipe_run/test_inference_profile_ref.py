"""Pin the inference-profile ref as a payload-carried run directive (BYOK mechanism).

The ref selects an externally-stored inference configuration. It must ride the serialized
payload — ``PipeRunParams`` and the derived ``CogtRunParams`` carrier stamped on every cogt
assignment — so it survives process boundaries, default to None (the executing process's boot
configuration), and be immutable once written.
"""

import pytest
from pydantic import ValidationError

from pipelex.cogt.content_generation.cogt_run_params import CogtRunParams
from pipelex.pipe_run.inference_profile_ref import InferenceProfileRef
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.pipe_run.pipe_run_params import PipeRunParams
from pipelex.pipe_run.pipe_run_params_factory import PipeRunParamsFactory


def _make_ref() -> InferenceProfileRef:
    return InferenceProfileRef(owner_id="org_123", profile_id="ip_456", fingerprint="fp_abc")


class TestInferenceProfileRef:
    def test_defaults_to_none_on_both_models(self) -> None:
        """No ref means the server/boot configuration applies — the unchanged default."""
        run_params = PipeRunParams(run_mode=PipeRunMode.DRY, pipe_stack_limit=20)

        assert run_params.inference_profile_ref is None
        assert run_params.cogt_run_params.inference_profile_ref is None

    def test_wire_payload_without_the_field_validates(self) -> None:
        """A payload from an older writer (no such key) must validate despite extra="forbid"."""
        run_params = PipeRunParams.model_validate({"run_mode": "dry", "pipe_stack_limit": 20})

        assert run_params.inference_profile_ref is None

    def test_carrier_derives_the_ref(self) -> None:
        """The cogt-tier carrier mints the ref from the stored field — one copy of the facts."""
        ref = _make_ref()
        run_params = PipeRunParams(run_mode=PipeRunMode.DRY, pipe_stack_limit=20, inference_profile_ref=ref)

        cogt_run_params = run_params.cogt_run_params
        assert cogt_run_params.inference_profile_ref is ref

    def test_json_round_trip_preserves_ref(self) -> None:
        """The ref serializes whole with the payload — the wire is the source of truth (R1)."""
        ref = _make_ref()
        run_params = PipeRunParams(run_mode=PipeRunMode.DRY, pipe_stack_limit=20, inference_profile_ref=ref)

        rebuilt = PipeRunParams.model_validate_json(run_params.model_dump_json())
        assert rebuilt.inference_profile_ref == ref

        carrier = CogtRunParams.model_validate_json(run_params.cogt_run_params.model_dump_json())
        assert carrier.inference_profile_ref == ref
        assert carrier.inference_profile_ref is not None
        assert carrier.inference_profile_ref.ref_str == "org_123/ip_456@fp_abc"

    def test_frozen_field_rejects_in_place_mutation(self) -> None:
        """A post-construction swap would rebind a run to another owner's configuration."""
        run_params = PipeRunParams(run_mode=PipeRunMode.DRY, pipe_stack_limit=20, inference_profile_ref=_make_ref())

        with pytest.raises(ValidationError, match="frozen"):
            run_params.inference_profile_ref = None  # type: ignore[misc]  # the static read-only error is the runtime contract under test

    def test_stamping_via_model_copy_despite_frozen(self) -> None:
        """The orchestrator-seam stamp: `model_copy(update=...)` writes the frozen field on a copy."""
        ref = _make_ref()
        run_params = PipeRunParams(run_mode=PipeRunMode.DRY, pipe_stack_limit=20)

        stamped = run_params.model_copy(update={"inference_profile_ref": ref})
        assert stamped.inference_profile_ref is ref
        assert stamped.cogt_run_params.inference_profile_ref is ref
        assert run_params.inference_profile_ref is None

    def test_copies_preserve_the_ref(self) -> None:
        """Sub-pipe copy paths must carry the selection down unchanged."""
        ref = _make_ref()
        run_params = PipeRunParams(run_mode=PipeRunMode.DRY, pipe_stack_limit=20, inference_profile_ref=ref)

        assert run_params.make_deep_copy().inference_profile_ref == ref
        multiplicity_copy = PipeRunParams.copy_by_injecting_multiplicity(run_params, applied_output_multiplicity=3)
        assert multiplicity_copy.inference_profile_ref == ref

    def test_factory_passes_the_ref_through(self) -> None:
        """The single writer accepts the ref alongside the other run directives."""
        ref = _make_ref()
        run_params = PipeRunParamsFactory.make_run_params(pipe_run_mode=PipeRunMode.DRY, pipe_stack_limit=20, inference_profile_ref=ref)

        assert run_params.inference_profile_ref is ref

    def test_ref_model_is_frozen_and_forbids_extras(self) -> None:
        """The ref is an immutable value object; a typo'd key on a wire payload fails loud."""
        ref = _make_ref()

        with pytest.raises(ValidationError, match="frozen"):
            ref.profile_id = "other"  # type: ignore[misc]  # the static read-only error is the runtime contract under test
        with pytest.raises(ValidationError, match="fingreprint"):
            InferenceProfileRef(owner_id="org_123", profile_id="ip_456", fingerprint="fp_abc", fingreprint="typo")  # type: ignore[call-arg] # pyright: ignore[reportCallIssue]

    def test_ref_rejects_empty_fields(self) -> None:
        """An empty component would make the ref unusable for lookup or verification."""
        with pytest.raises(ValidationError, match="owner_id"):
            InferenceProfileRef(owner_id="", profile_id="ip_456", fingerprint="fp_abc")
        with pytest.raises(ValidationError, match="profile_id"):
            InferenceProfileRef(owner_id="org_123", profile_id="", fingerprint="fp_abc")
        with pytest.raises(ValidationError, match="fingerprint"):
            InferenceProfileRef(owner_id="org_123", profile_id="ip_456", fingerprint="")
