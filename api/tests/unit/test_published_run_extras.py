"""The published run request schemas carry every extension field the routes read.

`/execute` and `/start` read their extensions through `PipelineApiExtras`, while the OpenAPI
artifact publishes them from two separate documentation models. A field added to the first and
not the second is honored on the wire yet absent from the contract, so no generated client can
send it, and nothing else fails.
"""

from pipelex_api.schemas.models import PipelexApiExecuteRequest, PipelexApiStartRequest, PipelineApiExtras

# `/execute` generates its own run id and delivers nothing asynchronously, so it reads neither.
_START_ONLY_EXTRAS = {"pipeline_run_id", "callback_urls"}


class TestPublishedRunExtras:
    def test_start_request_publishes_every_extra(self) -> None:
        assert set(PipelineApiExtras.model_fields) <= set(PipelexApiStartRequest.model_fields)

    def test_execute_request_publishes_every_extra_it_reads(self) -> None:
        assert set(PipelineApiExtras.model_fields) - _START_ONLY_EXTRAS <= set(PipelexApiExecuteRequest.model_fields)
