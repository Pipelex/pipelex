import asyncio
import base64
import hashlib
import hmac
import json
import logging
import socket
from collections.abc import Callable
from datetime import UTC, datetime

import httpx
import pytest
from mthds.protocol.problem.registry import CoreCode
from pytest_mock import MockerFixture

from pipelex.cogt.exceptions import InferenceErrorCategory, LLMCompletionError
from pipelex.cogt.inference.error_classification import ProviderErrorMetadata
from pipelex.cogt.inference.provider_name import ProviderName
from pipelex.errors.problem import PipelexProblem, ProblemView, caller_view_of
from pipelex.pipe_run import caller_webhook_delivery as delivery_module
from pipelex.pipe_run.caller_webhook_delivery import (
    CALLER_WEBHOOK_SECRET_ENV,
    CallerWebhookFailure,
    CallerWebhookOutcome,
    deliver_caller_webhooks,
)
from pipelex.pipe_run.delivery_assignment import CallerWebhookTarget, DeliveryStatus
from pipelex.tools.network.exceptions import SsrfBlockedError

_SECRET_KEY = bytes(range(32))
_SECRET = "whsec_" + base64.b64encode(_SECRET_KEY).decode("ascii")
_PREVIOUS_SECRET_KEY = bytes(range(32, 64))
_PREVIOUS_SECRET = "whsec_" + base64.b64encode(_PREVIOUS_SECRET_KEY).decode("ascii")
_FINISHED_AT = datetime(2026, 10, 22, 11, 59, 58, 250000, tzinfo=UTC)
_RUN_ID = "plr-caller-hooks"
_UP_URL = "https://up.example.com/hooks/run?token=up-s3cr3t"
_DOWN_URL = "https://down.example.com/hooks/run?token=down-s3cr3t"

_Handler = Callable[[httpx.Request], httpx.Response]


def _failed_run_problem() -> PipelexProblem:
    """A failed run's problem in the operator's view, with the provider's own answer among its diagnostics."""
    error = LLMCompletionError(
        message="provider returned 429",
        error_category=InferenceErrorCategory.TRANSIENT,
        provider_metadata=ProviderErrorMetadata(
            provider=ProviderName.OPENAI,
            sdk_exception_type="RateLimitError",
            message="429 Too Many Requests",
            status_code=429,
            retry_after_seconds=2.5,
        ),
    ).with_error_code(CoreCode.PROVIDER_RATE_LIMITED)
    error.with_params(model="gpt-4o-mini", provider=ProviderName.OPENAI)
    return error.to_problem(view=ProblemView.OPERATOR, pipeline_run_id=_RUN_ID)


def _route_calls(mocker: MockerFixture, *, handler: _Handler) -> list[httpx.Request]:
    """Answer every call the delivery sends with ``handler``, through the client the delivery builds, and record each one."""
    calls: list[httpx.Request] = []

    def recording_handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return handler(request)

    mocker.patch.object(delivery_module, "SsrfGuardedTransport", return_value=httpx.MockTransport(recording_handler))
    return calls


def _no_waits(mocker: MockerFixture) -> list[float]:
    """Skip the retry waits, recording each one the delivery asked for."""
    waits: list[float] = []
    mocker.patch.object(delivery_module, "sleep", new=mocker.AsyncMock(side_effect=waits.append))
    return waits


def _ticking_clock(mocker: MockerFixture, *, start: int) -> None:
    """A send clock that moves on one second per reading, so each attempt carries its own timestamp."""
    readings = iter(range(start, start + 1000))
    mocker.patch.object(delivery_module, "time", side_effect=lambda: float(next(readings)))


def _verifies(*, request: httpx.Request, secret_key: bytes) -> bool:
    """Whether one of the call's signatures is the HMAC-SHA256, under ``secret_key``, of its id, timestamp and body."""
    signed_content = f"{request.headers['webhook-id']}.{request.headers['webhook-timestamp']}.".encode() + request.content
    expected = base64.b64encode(hmac.new(secret_key, signed_content, hashlib.sha256).digest()).decode("ascii")
    return any(signature == f"v1,{expected}" for signature in request.headers["webhook-signature"].split(" "))


async def _deliver(
    *, urls: list[str], status: DeliveryStatus = DeliveryStatus.FAILED, problem: PipelexProblem | None = None
) -> list[CallerWebhookOutcome]:
    return await deliver_caller_webhooks(
        targets=[CallerWebhookTarget(url=url) for url in urls],
        pipeline_run_id=_RUN_ID,
        status=status,
        problem=problem,
        finished_at=_FINISHED_AT,
    )


@pytest.mark.asyncio(loop_scope="class")
class TestCallerWebhookDelivery:
    async def test_a_failed_run_sends_its_caller_view_problem_in_the_run_finished_event(
        self, mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The body is the compact `run.finished` event: when the run ended, the attempt, and the run as its caller reads it."""
        monkeypatch.setenv(CALLER_WEBHOOK_SECRET_ENV, _SECRET)
        calls = _route_calls(mocker, handler=lambda _request: httpx.Response(204))
        problem = _failed_run_problem()

        (outcome,) = await _deliver(urls=[_UP_URL], problem=problem)

        (call,) = calls
        assert call.headers["content-type"] == "application/json"
        event = json.loads(call.content)
        assert event == {
            "type": "run.finished",
            "timestamp": "2026-10-22T11:59:58.250Z",
            "attempt": 1,
            "data": {"pipeline_run_id": _RUN_ID, "status": "failed", "error": caller_view_of(problem=problem).to_wire()},
        }
        # The caller's view: no diagnostics, no provider answer, and no `status` member, as the protocol's problem writes it.
        assert "diagnostics" not in call.content.decode()
        assert "Too Many Requests" not in call.content.decode()
        assert "status" not in event["data"]["error"]
        # Compact JSON, the exact bytes the signature covers.
        assert call.content == json.dumps(event, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        assert outcome == CallerWebhookOutcome(delivery_id=call.headers["webhook-id"], server_address="up.example.com", attempt_count=1)

    async def test_a_completed_run_sends_no_error(self, mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch) -> None:
        """A completed run's data is its id and its status alone, never a `null` error nor its output."""
        monkeypatch.setenv(CALLER_WEBHOOK_SECRET_ENV, _SECRET)
        calls = _route_calls(mocker, handler=lambda _request: httpx.Response(200))

        await _deliver(urls=[_UP_URL], status=DeliveryStatus.COMPLETED)

        (call,) = calls
        assert json.loads(call.content)["data"] == {"pipeline_run_id": _RUN_ID, "status": "completed"}

    async def test_a_failed_run_without_a_problem_reads_as_unexpected(self, mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch) -> None:
        """Every failed run's event carries a problem, `runtime.unexpected` when the delivery was handed none."""
        monkeypatch.setenv(CALLER_WEBHOOK_SECRET_ENV, _SECRET)
        calls = _route_calls(mocker, handler=lambda _request: httpx.Response(200))

        await _deliver(urls=[_UP_URL], problem=None)

        (call,) = calls
        error = json.loads(call.content)["data"]["error"]
        assert error["code"] == CoreCode.RUNTIME_UNEXPECTED
        assert error["pipeline_run_id"] == _RUN_ID

    async def test_every_attempt_keeps_the_delivery_id_and_signs_its_own_timestamp(
        self, mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A retry keeps `webhook-id` and `data`, counts `attempt` from 1 when the host names no attempt of its own, and is
        signed anew at its own send time, under every live secret.
        """
        monkeypatch.setenv(CALLER_WEBHOOK_SECRET_ENV, f"{_SECRET} {_PREVIOUS_SECRET}")
        answers = iter([httpx.Response(503), httpx.Response(500), httpx.Response(200)])
        calls = _route_calls(mocker, handler=lambda _request: next(answers))
        waits = _no_waits(mocker)
        _ticking_clock(mocker, start=1792670401)
        target = CallerWebhookTarget(url=_UP_URL)

        (outcome,) = await deliver_caller_webhooks(
            targets=[target],
            pipeline_run_id=_RUN_ID,
            status=DeliveryStatus.COMPLETED,
            problem=None,
            finished_at=_FINISHED_AT,
        )

        assert outcome.is_delivered
        assert outcome.attempt_count == 3
        assert waits == [1.0, 5.0]
        assert [call.headers["webhook-id"] for call in calls] == [target.delivery_id] * 3
        assert [call.headers["webhook-timestamp"] for call in calls] == ["1792670401", "1792670402", "1792670403"]
        events = [json.loads(call.content) for call in calls]
        assert [event["attempt"] for event in events] == [1, 2, 3]
        assert all(event["data"] == events[0]["data"] for event in events)
        for call in calls:
            assert _verifies(request=call, secret_key=_SECRET_KEY)
            assert _verifies(request=call, secret_key=_PREVIOUS_SECRET_KEY)
            assert call.headers["webhook-signature"].count(" ") == 1

    @pytest.mark.parametrize(
        ("host_attempt", "expected_attempts"),
        [
            pytest.param(1, [1, 2, 3], id="first_host_attempt"),
            pytest.param(2, [4, 5, 6], id="second_host_attempt"),
            pytest.param(3, [7, 8, 9], id="third_host_attempt"),
        ],
    )
    async def test_a_step_numbers_its_attempts_after_the_hosts_earlier_steps(
        self,
        mocker: MockerFixture,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
        host_attempt: int,
        expected_attempts: list[int],
    ) -> None:
        """A step's calls carry increasing numbers that start after every call the host's earlier steps could have made,
        while `attempt_count` counts this step's calls alone and the log lines name the number each call carried.
        """
        monkeypatch.setenv(CALLER_WEBHOOK_SECRET_ENV, _SECRET)
        calls = _route_calls(mocker, handler=lambda _request: httpx.Response(503))
        _no_waits(mocker)

        with caplog.at_level(logging.DEBUG, logger=delivery_module.__name__):
            (outcome,) = await deliver_caller_webhooks(
                targets=[CallerWebhookTarget(url=_UP_URL)],
                pipeline_run_id=_RUN_ID,
                status=DeliveryStatus.COMPLETED,
                problem=None,
                finished_at=_FINISHED_AT,
                host_attempt=host_attempt,
            )

        assert [json.loads(call.content)["attempt"] for call in calls] == expected_attempts
        assert outcome.attempt_count == 3
        assert outcome.failure == CallerWebhookFailure.HTTP_STATUS
        attempt_records = [record for record in caplog.records if record.getMessage() == "A caller webhook attempt failed"]
        assert [vars(record).get("event_attempt") for record in attempt_records] == expected_attempts
        assert [vars(record).get("attempt_count") for record in attempt_records] == [1, 2, 3]
        (failure_record,) = [record for record in caplog.records if record.getMessage() == "A caller webhook could not be delivered"]
        assert vars(failure_record).get("event_attempt") == expected_attempts[-1]
        assert vars(failure_record).get("attempt_count") == 3

    async def test_a_step_run_again_never_repeats_an_attempt_under_its_webhook_id(
        self, mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A host that runs the step again, its first run lost after a call was acknowledged, continues the count under the
        same `webhook-id`: increasing, never repeated, and skipping the calls the first run never made.
        """
        monkeypatch.setenv(CALLER_WEBHOOK_SECRET_ENV, _SECRET)
        answers = iter([httpx.Response(200), httpx.Response(503), httpx.Response(204)])
        calls = _route_calls(mocker, handler=lambda _request: next(answers))
        _no_waits(mocker)
        target = CallerWebhookTarget(url=_UP_URL)

        outcomes: list[CallerWebhookOutcome] = []
        with caplog.at_level(logging.INFO, logger=delivery_module.__name__):
            for host_attempt in (1, 2):
                outcomes += await deliver_caller_webhooks(
                    targets=[target],
                    pipeline_run_id=_RUN_ID,
                    status=DeliveryStatus.COMPLETED,
                    problem=None,
                    finished_at=_FINISHED_AT,
                    host_attempt=host_attempt,
                )

        assert {call.headers["webhook-id"] for call in calls} == {target.delivery_id}
        assert [json.loads(call.content)["attempt"] for call in calls] == [1, 4, 5]
        assert [outcome.attempt_count for outcome in outcomes] == [1, 2]
        assert all(outcome.is_delivered for outcome in outcomes)
        delivered_records = [record for record in caplog.records if record.getMessage() == "A caller webhook was delivered"]
        assert [vars(record).get("event_attempt") for record in delivered_records] == [1, 5]
        assert [vars(record).get("attempt_count") for record in delivered_records] == [1, 2]

    @pytest.mark.parametrize("host_attempt", [0, -1])
    @pytest.mark.parametrize("urls", [pytest.param([_UP_URL], id="one_target"), pytest.param([], id="no_target")])
    async def test_a_host_attempt_below_one_is_refused_before_anything_is_sent(
        self, mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch, host_attempt: int, urls: list[str]
    ) -> None:
        """The host's attempt is counted from 1: anything lower is the host's fault, refused before a secret is read."""
        monkeypatch.setenv(CALLER_WEBHOOK_SECRET_ENV, _SECRET)
        calls = _route_calls(mocker, handler=lambda _request: httpx.Response(200))
        secret_spy = mocker.spy(delivery_module, "caller_webhook_secret_keys")

        with pytest.raises(ValueError, match="counted from 1"):
            await deliver_caller_webhooks(
                targets=[CallerWebhookTarget(url=url) for url in urls],
                pipeline_run_id=_RUN_ID,
                status=DeliveryStatus.COMPLETED,
                problem=None,
                finished_at=_FINISHED_AT,
                host_attempt=host_attempt,
            )

        assert calls == []
        secret_spy.assert_not_called()

    async def test_each_url_is_delivered_on_its_own(
        self, mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """One receiver's failure neither delays nor fails another's delivery, and each delivery has its own id."""
        monkeypatch.setenv(CALLER_WEBHOOK_SECRET_ENV, _SECRET)
        calls = _route_calls(mocker, handler=lambda request: httpx.Response(500 if request.url.host == "down.example.com" else 200))
        waits = _no_waits(mocker)

        with caplog.at_level(logging.INFO, logger=delivery_module.__name__):
            down_outcome, up_outcome = await _deliver(urls=[_DOWN_URL, _UP_URL], problem=_failed_run_problem())

        assert up_outcome.is_delivered
        assert up_outcome.attempt_count == 1
        assert down_outcome.failure == CallerWebhookFailure.HTTP_STATUS
        assert down_outcome.attempt_count == 3
        assert down_outcome.receiver_status == 500
        assert waits == [1.0, 5.0]
        assert sum(1 for call in calls if call.url.host == "up.example.com") == 1
        assert up_outcome.delivery_id != down_outcome.delivery_id
        (failure_record,) = [record for record in caplog.records if record.getMessage() == "A caller webhook could not be delivered"]
        assert failure_record.levelno == logging.WARNING
        assert vars(failure_record).get("server.address") == "down.example.com"
        assert vars(failure_record).get("delivery_failure") == CallerWebhookFailure.HTTP_STATUS
        assert vars(failure_record).get("http.response.status_code") == 500
        # The receivers are named by their host alone: a URL's query may carry a credential.
        assert "s3cr3t" not in caplog.text
        assert "s3cr3t" not in json.dumps([vars(record) for record in caplog.records], default=str)

    async def test_a_redirect_fails_the_attempt_and_is_never_followed(self, mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch) -> None:
        """A `3xx` is a failed attempt: the signed event never goes on to the place a receiver points at."""
        monkeypatch.setenv(CALLER_WEBHOOK_SECRET_ENV, _SECRET)
        calls = _route_calls(mocker, handler=lambda _request: httpx.Response(307, headers={"location": "https://elsewhere.example.com/collect"}))
        _no_waits(mocker)

        (outcome,) = await _deliver(urls=[_UP_URL])

        assert outcome.failure == CallerWebhookFailure.HTTP_STATUS
        assert outcome.receiver_status == 307
        assert {call.url.host for call in calls} == {"up.example.com"}
        assert len(calls) == 3

    @pytest.mark.parametrize(
        ("transport_error", "expected_failure"),
        [
            pytest.param(
                httpx.ConnectError("Connection refused by https://down.example.com/?token=down-s3cr3t"),
                CallerWebhookFailure.UNREACHABLE,
                id="unreachable",
            ),
            pytest.param(httpx.ReadTimeout("read timed out"), CallerWebhookFailure.TIMEOUT, id="timeout"),
        ],
    )
    async def test_a_transport_failure_is_retried_then_recorded(
        self,
        mocker: MockerFixture,
        monkeypatch: pytest.MonkeyPatch,
        transport_error: httpx.TransportError,
        expected_failure: CallerWebhookFailure,
    ) -> None:
        """A receiver that cannot be reached or answers too late fails each attempt, and the delivery ends failed, never raising."""
        monkeypatch.setenv(CALLER_WEBHOOK_SECRET_ENV, _SECRET)

        def failing_handler(_request: httpx.Request) -> httpx.Response:
            raise transport_error

        calls = _route_calls(mocker, handler=failing_handler)
        _no_waits(mocker)

        (outcome,) = await _deliver(urls=[_DOWN_URL])

        assert outcome.failure == expected_failure
        assert outcome.attempt_count == 3
        assert outcome.receiver_status is None
        assert len(calls) == 3

    async def test_an_attempt_past_its_budget_fails(self, mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch) -> None:
        """A receiver still silent when the attempt's budget runs out fails the attempt as a time-out."""
        monkeypatch.setenv(CALLER_WEBHOOK_SECRET_ENV, _SECRET)
        mocker.patch.object(delivery_module, "ATTEMPT_BUDGET_SECONDS", 0.05)
        mocker.patch.object(delivery_module, "RETRY_WAITS_SECONDS", ())

        async def silent_handler(_request: httpx.Request) -> httpx.Response:
            await asyncio.sleep(5)
            return httpx.Response(200)

        mocker.patch.object(delivery_module, "SsrfGuardedTransport", return_value=httpx.MockTransport(silent_handler))

        (outcome,) = await _deliver(urls=[_DOWN_URL])

        assert outcome.failure == CallerWebhookFailure.TIMEOUT
        assert outcome.attempt_count == 1

    async def test_a_host_resolving_to_a_private_address_is_refused_once_and_reported(
        self, mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The SSRF guard refuses the destination at connect time: a security event is logged and nothing is retried."""
        monkeypatch.setenv(CALLER_WEBHOOK_SECRET_ENV, _SECRET)

        def metadata_address(*_args: object, **_kwargs: object) -> list[tuple[int, int, int, str, tuple[str, int]]]:
            return [(int(socket.AF_INET), int(socket.SOCK_STREAM), 6, "", ("169.254.169.254", 443))]

        mocker.patch("socket.getaddrinfo", side_effect=metadata_address)
        security_event_spy = mocker.spy(delivery_module, "emit_security_event")
        waits = _no_waits(mocker)

        (outcome,) = await deliver_caller_webhooks(
            targets=[CallerWebhookTarget(url="https://rebound.example.com/hook")],
            pipeline_run_id=_RUN_ID,
            status=DeliveryStatus.COMPLETED,
            problem=None,
            finished_at=_FINISHED_AT,
            extras={"org": "acme"},
        )

        assert outcome.failure == CallerWebhookFailure.REFUSED_ADDRESS
        assert outcome.attempt_count == 1
        assert waits == []
        security_event_spy.assert_called_once()
        assert isinstance(security_event_spy.call_args.kwargs["error"], SsrfBlockedError)
        assert security_event_spy.call_args.kwargs["extras"] == {"org": "acme"}

    @pytest.mark.parametrize(
        "configured_secret",
        [
            pytest.param(None, id="unset"),
            pytest.param("   ", id="blank"),
            pytest.param("not-a-whsec-secret", id="malformed"),
            pytest.param(f"{_SECRET} whsec_###", id="one_of_two_malformed"),
        ],
    )
    async def test_without_a_usable_secret_nothing_is_sent(
        self,
        mocker: MockerFixture,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
        configured_secret: str | None,
    ) -> None:
        """No call goes out unsigned: every delivery is recorded failed, and the operator's fault is logged once as an error."""
        if configured_secret is None:
            monkeypatch.delenv(CALLER_WEBHOOK_SECRET_ENV, raising=False)
        else:
            monkeypatch.setenv(CALLER_WEBHOOK_SECRET_ENV, configured_secret)
        calls = _route_calls(mocker, handler=lambda _request: httpx.Response(200))

        with caplog.at_level(logging.INFO, logger=delivery_module.__name__):
            outcomes = await _deliver(urls=[_UP_URL, _DOWN_URL])

        assert calls == []
        assert [outcome.failure for outcome in outcomes] == [CallerWebhookFailure.SECRET_UNAVAILABLE] * 2
        assert [outcome.attempt_count for outcome in outcomes] == [0, 0]
        (error_record,) = [record for record in caplog.records if record.levelno >= logging.ERROR]
        assert vars(error_record).get("env_var") == CALLER_WEBHOOK_SECRET_ENV
        assert "###" not in caplog.text

    async def test_no_target_reads_no_secret(self, mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch) -> None:
        """A run without caller webhooks needs no secret and sends nothing."""
        monkeypatch.delenv(CALLER_WEBHOOK_SECRET_ENV, raising=False)
        calls = _route_calls(mocker, handler=lambda _request: httpx.Response(200))

        assert await _deliver(urls=[]) == []
        assert calls == []

    async def test_a_delivery_id_has_the_contracts_form(self) -> None:
        """`whd_` and ASCII letters, digits and underscores, at most 64 characters, fixed when the target is built."""
        target = CallerWebhookTarget(url=_UP_URL)
        assert target.delivery_id.startswith("whd_")
        assert len(target.delivery_id) <= 64
        assert target.delivery_id.removeprefix("whd_").isalnum()
        assert CallerWebhookTarget.model_validate(target.model_dump()).delivery_id == target.delivery_id
        assert CallerWebhookTarget(url=_UP_URL).delivery_id != target.delivery_id

    @pytest.mark.parametrize("delivery_id", ["abc", "whd_", "whd_has-dash", "whd_" + "a" * 61])
    async def test_a_delivery_id_outside_the_contracts_form_is_refused(self, delivery_id: str) -> None:
        with pytest.raises(ValueError, match="delivery_id"):
            CallerWebhookTarget(url=_UP_URL, delivery_id=delivery_id)

    async def test_a_view_of_the_problem_never_reaches_the_event_but_the_callers(self) -> None:
        """The event's error is the caller's view whatever view the delivery was handed."""
        problem = _failed_run_problem()
        caller_problem = caller_view_of(problem=problem)
        assert delivery_module.run_finished_data(pipeline_run_id=_RUN_ID, status=DeliveryStatus.FAILED, problem=problem) == (
            delivery_module.run_finished_data(pipeline_run_id=_RUN_ID, status=DeliveryStatus.FAILED, problem=caller_problem)
        )

    async def test_the_event_timestamp_is_utc_with_z(self) -> None:
        moment = datetime.fromisoformat("2026-10-22T13:59:58.250+02:00")
        assert delivery_module.event_timestamp(moment=moment) == "2026-10-22T11:59:58.250Z"

    async def test_the_body_carries_characters_outside_ascii_as_utf8(self) -> None:
        body = delivery_module.run_finished_body(finished_at="2026-10-22T11:59:58Z", attempt=2, data={"pipeline_run_id": "réunion-東京"})
        assert "réunion-東京".encode() in body
        assert b"\\u" not in body

    async def test_the_caller_delivery_waits_little(self) -> None:
        """The short schedule stays well inside the run's delivery step: three attempts, at most a minute in all."""
        attempts = delivery_module.ATTEMPTS_PER_STEP
        assert attempts == len(delivery_module.RETRY_WAITS_SECONDS) + 1 == 3
        assert delivery_module.ATTEMPT_BUDGET_SECONDS * attempts + sum(delivery_module.RETRY_WAITS_SECONDS) <= 60
