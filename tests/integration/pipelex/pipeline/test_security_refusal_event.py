from __future__ import annotations

import io
import json
import logging
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

import pytest
from mthds.protocol.problem.registry import CoreCode, ProblemDomain

from pipelex.base_exceptions import PipelexError
from pipelex.errors.error_codes import error_code_spec
from pipelex.errors.security_event import SECURITY_EVENT_MESSAGE, SECURITY_EVENT_NAME
from pipelex.errors.security_target import SecurityTargetClass, SecurityTargetKind
from pipelex.pipeline.exceptions import PipelineExecutionError
from pipelex.pipeline.runner import PipelexMTHDSProtocol
from pipelex.system.pipe_run_mode import PipeRunMode
from pipelex.system.storage_scope import LOCAL_STORAGE_SCOPE
from pipelex.tools.log.json_log_sink import JsonLogSink
from pipelex.tools.uri.exceptions import UriReadRefusedError
from tests.integration.pipelex.pipeline.test_data import SecurityRefusalTestData

if TYPE_CHECKING:
    from collections.abc import Generator

    from mthds.protocol.pipeline_inputs import PipelineInputs

SECURITY_EVENT_LOGGER = "pipelex.errors.security_event"


@contextmanager
def _security_event_lines() -> Generator[list[dict[str, Any]]]:
    """The security events logged in the block, as the ``json`` sink serializes them."""
    buffer = io.StringIO()
    handler = JsonLogSink(stream=buffer).handler
    logger = logging.getLogger(SECURITY_EVENT_LOGGER)
    previous_level = logger.level
    logger.setLevel(logging.WARNING)
    logger.addHandler(handler)
    lines: list[dict[str, Any]] = []
    try:
        yield lines
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous_level)
        handler.close()
        lines.extend(json.loads(line) for line in buffer.getvalue().splitlines() if line)


def _scoped_runner() -> PipelexMTHDSProtocol:
    return PipelexMTHDSProtocol(
        pipe_run_mode=PipeRunMode.DRY,
        user_id="test-user",
        storage_scope=SecurityRefusalTestData.STORAGE_SCOPE,
        read_scope=SecurityRefusalTestData.READ_SCOPE,
        extras=SecurityRefusalTestData.EXTRAS,
    )


async def _refused_run(*, runner: PipelexMTHDSProtocol, bundle: str, inputs: PipelineInputs) -> tuple[PipelexError, list[dict[str, Any]]]:
    with _security_event_lines() as lines, pytest.raises(PipelexError) as exc_info:
        await runner.execute(mthds_contents=[bundle], inputs=inputs)
    return exc_info.value, lines


def _compose_bundle(*, template: str) -> str:
    return SecurityRefusalTestData.COMPOSE_MTHDS.replace(SecurityRefusalTestData.COMPOSE_MTHDS_SLOT, template)


def _assert_is_the_event(*, line: dict[str, Any], code: CoreCode, error_type: str, target_kind: SecurityTargetKind) -> None:
    assert line["message"] == SECURITY_EVENT_MESSAGE
    assert line["event.name"] == SECURITY_EVENT_NAME
    assert line["error.code"] == code
    assert line["error.domain"] == error_code_spec(code).domain
    assert line["error.type"] == error_type
    assert line["security.target"] == target_kind
    assert line["run.extras.org_id"] == SecurityRefusalTestData.EXTRAS["org_id"]
    assert "exception" not in line


@pytest.mark.asyncio(loop_scope="class")
class TestSecurityRefusalEvent:
    async def test_a_refusal_mid_run_fails_the_run_under_its_code_and_logs_one_event(self) -> None:
        """A key of another tenant read by a step: the method's `security.method_url_refused`, one event naming the run, never the key."""
        error, lines = await _refused_run(
            runner=_scoped_runner(),
            bundle=SecurityRefusalTestData.FORGED_IMAGE_MTHDS,
            inputs={"where": SecurityRefusalTestData.FOREIGN_KEY},
        )

        assert isinstance(error, PipelineExecutionError)
        assert error.resolve_error_code() == CoreCode.SECURITY_METHOD_URL_REFUSED
        assert error_code_spec(CoreCode.SECURITY_METHOD_URL_REFUSED).domain == ProblemDomain.METHOD
        # Reported by the run's boundary, and not again by the runner's that wraps the failure.
        (line,) = lines
        _assert_is_the_event(
            line=line, code=CoreCode.SECURITY_METHOD_URL_REFUSED, error_type="UriReadRefusedError", target_kind=SecurityTargetKind.URL
        )
        assert line["security.target_class"] == SecurityTargetClass.FOREIGN_STORAGE_KEY
        assert line["pipeline_run_id"]
        assert SecurityRefusalTestData.FOREIGN_KEY not in json.dumps(line)
        assert "org_other" not in json.dumps(line)

    async def test_a_refusal_before_the_run_logs_its_event_too(self) -> None:
        """A local path passed as an input: the caller's `security.input_url_refused`, refused before any run, still one event."""
        error, lines = await _refused_run(
            runner=_scoped_runner(),
            bundle=SecurityRefusalTestData.DESCRIBE_IMAGE_MTHDS,
            inputs={"photo": SecurityRefusalTestData.LOCAL_PATH},
        )

        assert isinstance(error, UriReadRefusedError)
        assert error.resolve_error_code() == CoreCode.SECURITY_INPUT_URL_REFUSED
        (line,) = lines
        _assert_is_the_event(
            line=line, code=CoreCode.SECURITY_INPUT_URL_REFUSED, error_type="UriReadRefusedError", target_kind=SecurityTargetKind.URL
        )
        assert line["security.target_class"] == SecurityTargetClass.SCHEME
        assert SecurityRefusalTestData.LOCAL_PATH not in json.dumps(line)

    async def test_a_template_the_sandbox_refuses_at_render_logs_its_event(self) -> None:
        """A method's template reading a private name: `security.template_refused`, the method's, and an event quoting no template."""
        runner = PipelexMTHDSProtocol(pipe_run_mode=PipeRunMode.DRY, storage_scope=LOCAL_STORAGE_SCOPE, extras=SecurityRefusalTestData.EXTRAS)
        error, lines = await _refused_run(
            runner=runner,
            bundle=_compose_bundle(template=SecurityRefusalTestData.PRIVATE_READ_TEMPLATE),
            inputs={"topic": SecurityRefusalTestData.TOPIC},
        )

        assert isinstance(error, PipelineExecutionError)
        assert error.resolve_error_code() == CoreCode.SECURITY_TEMPLATE_REFUSED
        assert error_code_spec(CoreCode.SECURITY_TEMPLATE_REFUSED).domain == ProblemDomain.METHOD
        (line,) = lines
        _assert_is_the_event(
            line=line,
            code=CoreCode.SECURITY_TEMPLATE_REFUSED,
            error_type="Jinja2TemplateSecurityError",
            target_kind=SecurityTargetKind.TEMPLATE,
        )
        assert "security.target_class" not in line
        serialized = json.dumps(line)
        assert "_owner" not in serialized
        assert SecurityRefusalTestData.TOPIC not in serialized

    async def test_a_failure_no_security_rule_made_logs_no_event(self) -> None:
        runner = PipelexMTHDSProtocol(pipe_run_mode=PipeRunMode.DRY, storage_scope=LOCAL_STORAGE_SCOPE, extras=SecurityRefusalTestData.EXTRAS)
        error, lines = await _refused_run(
            runner=runner,
            bundle=_compose_bundle(template=SecurityRefusalTestData.MISSING_METHOD_TEMPLATE),
            inputs={"topic": SecurityRefusalTestData.TOPIC},
        )

        assert error.resolve_error_code() == CoreCode.PIPE_TEMPLATE_RENDER_FAILED
        assert lines == []
