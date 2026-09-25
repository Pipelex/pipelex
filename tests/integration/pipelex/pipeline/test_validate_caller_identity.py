"""Integration tests: a validation served for a known caller is attributed to that caller.

The unit suite pins each seam with mocks; these run the real validate pass — library load,
the dry-run sweep, the best-effort graph arm — to pin what the seams add up to: the sweep's
`PIPE_DRY_RUN` event is emitted with the caller in scope, and every dry run the pass performs
states that caller in its job metadata, so none of it falls back to the telemetry stream's
configured constant. A local runtime states `local`, which telemetry never attributes to a
person, so a local validation keeps reporting under the fallback.
"""

from typing import Any

import pytest
from pytest_mock import MockerFixture

from pipelex.pipe_run import dry_run_in_process
from pipelex.pipeline import bundle_validator
from pipelex.pipeline.runner import PipelexMTHDSProtocol
from pipelex.pipeline.validate_in_process import validate_bundles_in_process
from pipelex.runtime_hub import get_telemetry_manager
from pipelex.system.caller_identity import CallerIdentity, get_current_caller_identity
from pipelex.system.storage_scope import LOCAL_USER_ID
from pipelex.system.telemetry.events import EventName
from pipelex.system.telemetry.telemetry_identity import RunIdentityPolicy, TelemetryIdentity

_DOMAIN = "validate_caller_identity"
_MTHDS = f"""
domain = "{_DOMAIN}"
description = "Minimal bundle for caller-identity validation tests"
main_pipe = "echo_topic"

[concept.Topic]
description = "A topic"

[concept.Topic.structure]
name = {{ type = "text", description = "Topic name" }}

[pipe.echo_topic]
type = "PipeLLM"
description = "Pipe used only to dry-run through the validate pass"
inputs = {{ subject = "Text" }}
output = "Topic"
prompt = "Echo the $subject as a topic"
"""

_CALLER = CallerIdentity(user_id="caller-7", extras={"organization": "org_caller"})


def _record_callers(*, mocker: MockerFixture) -> tuple[list[CallerIdentity | None], Any, Any]:
    """Record the caller in scope at each `PIPE_DRY_RUN`, and spy on every dry run's job build."""
    callers_at_dry_run_event: list[CallerIdentity | None] = []

    def record(*_args: Any, **kwargs: Any) -> None:
        if kwargs.get("event_name") == EventName.PIPE_DRY_RUN:
            callers_at_dry_run_event.append(get_current_caller_identity())

    mocker.patch.object(get_telemetry_manager(), "track_event", side_effect=record)
    sweep_prepare_spy = mocker.spy(bundle_validator, "prepare_pipe_job")
    graph_prepare_spy = mocker.spy(dry_run_in_process, "prepare_pipe_job")
    return callers_at_dry_run_event, sweep_prepare_spy, graph_prepare_spy


@pytest.mark.asyncio(loop_scope="class")
class TestValidateCallerIdentity:
    async def test_a_hosted_validation_is_attributed_to_its_caller(self, mocker: MockerFixture) -> None:
        callers_at_dry_run_event, sweep_prepare_spy, graph_prepare_spy = _record_callers(mocker=mocker)

        report = await validate_bundles_in_process(mthds_contents=[_MTHDS], caller_identity=_CALLER)

        assert report.graph_spec is not None, "the graph arm must have dry-run the main pipe"
        assert callers_at_dry_run_event == [_CALLER]
        dry_run_calls = [*sweep_prepare_spy.call_args_list, *graph_prepare_spy.call_args_list]
        assert len(dry_run_calls) >= 2
        for dry_run_call in dry_run_calls:
            assert dry_run_call.kwargs["user_id"] == "caller-7"
            assert dry_run_call.kwargs["extras"] == {"organization": "org_caller"}
        assert get_current_caller_identity() is None

    async def test_the_protocol_validates_for_the_caller_it_was_built_for(self, mocker: MockerFixture) -> None:
        callers_at_dry_run_event, sweep_prepare_spy, _graph_prepare_spy = _record_callers(mocker=mocker)
        protocol = PipelexMTHDSProtocol(user_id="caller-7", extras={"organization": "org_caller"})

        await protocol.validate(mthds_contents=[_MTHDS])

        assert callers_at_dry_run_event == [_CALLER]
        assert sweep_prepare_spy.call_args.kwargs["user_id"] == "caller-7"

    async def test_a_local_validation_still_reports_under_the_fallback(self, mocker: MockerFixture) -> None:
        callers_at_dry_run_event, _sweep_prepare_spy, _graph_prepare_spy = _record_callers(mocker=mocker)

        await PipelexMTHDSProtocol().validate(mthds_contents=[_MTHDS])

        assert callers_at_dry_run_event == [CallerIdentity(user_id=LOCAL_USER_ID)]
        identity = TelemetryIdentity.make_from_caller_identity(
            caller_identity=callers_at_dry_run_event[0],
            fallback_distinct_id="configured-id",
            run_identity_policy=RunIdentityPolicy.DIRECT,
        )
        assert identity.distinct_id == "configured-id"
