"""Wire round-trip for ``PipeRunParams`` with the nested ``CogtRunParams`` carrier (eng review D2).

``WfPipeRouter`` receives ``pipe_run_params`` inside its workflow arg, so the nested carrier must
survive the Temporal payload converter — and ``run_mode`` (a delegating property, deliberately not
a serialized field) must read back correctly from the restored nested model.
"""

import pytest

from pipelex.cogt.content_generation.cogt_run_params import CogtRunParams
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.pipe_run.pipe_run_params import PipeRunParams
from pipelex.temporal.temporal_data_converter import BaseModelPayloadConverter


@pytest.mark.temporal
class TestDataConverterForPipeRunParams:
    def test_cogt_run_params_round_trip(
        self,
        payload_converter: BaseModelPayloadConverter,
    ):
        pipe_run_params = PipeRunParams(
            run_mode=PipeRunMode.DRY,
            is_mock_usage=True,
            pipe_stack_limit=20,
            pipe_stack=["root", "child"],
        )

        payload = payload_converter.to_payload(pipe_run_params)
        assert payload
        restored: PipeRunParams = payload_converter.from_payload(payload, type_hint=PipeRunParams)

        assert restored == pipe_run_params
        assert restored.run_mode.is_dry
        assert restored.is_mock_usage
        # The derived carrier reads the restored fields — what generators stamp on assignments.
        assert restored.cogt_run_params == CogtRunParams(run_mode=PipeRunMode.DRY, is_mock_usage=True)
