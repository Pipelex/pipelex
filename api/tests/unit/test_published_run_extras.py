"""The published run request schemas carry every extension field the routes read.

`/execute` and `/start` read their extensions through `PipelineApiExtras`, while the OpenAPI
artifact publishes them from two separate documentation models. A field added to the first and
not the second is honored on the wire yet absent from the contract, so no generated client can
send it, and nothing else fails.
"""

from pipelex_api.schemas.models import PipelexApiExecuteRequest, PipelexApiStartRequest, PipelineApiExtras


class TestPublishedRunExtras:
    def test_start_request_publishes_every_extra(self) -> None:
        assert set(PipelineApiExtras.model_fields) <= set(PipelexApiStartRequest.model_fields)

    def test_execute_request_publishes_every_extra(self) -> None:
        """`/execute` reads every extension `/start` reads, its caller-chosen run id and its caller webhooks included."""
        assert set(PipelineApiExtras.model_fields) <= set(PipelexApiExecuteRequest.model_fields)
