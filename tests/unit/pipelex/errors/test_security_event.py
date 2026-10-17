from __future__ import annotations

import io
import json
import logging
from contextlib import contextmanager
from enum import StrEnum
from typing import TYPE_CHECKING, Any

import pytest
from mthds.protocol.problem.registry import CoreCode, ProblemDomain
from typing_extensions import override

from pipelex.base_exceptions import PipelexError, PipelexUnexpectedError
from pipelex.cogt.content_generation.exceptions import UnsafeSchemaError
from pipelex.cogt.doc_gen.exceptions import TemplateUrlRefusedError
from pipelex.core.bundle_resources.exceptions import BundleResourcePathError
from pipelex.errors.error_code_declaration import InheritsCause
from pipelex.errors.error_codes import ErrorCode, error_code_spec
from pipelex.errors.registry.pipelex_codes import PipelexErrorCode
from pipelex.errors.security_event import (
    SECURITY_EVENT_MESSAGE,
    SECURITY_EVENT_NAME,
    SECURITY_TARGET_KIND_BY_CODE,
    emit_security_event,
    log_security_event,
    mark_security_event_emitted,
)
from pipelex.errors.security_target import SecurityTargetClass, SecurityTargetKind
from pipelex.pipeline.exceptions import PipelineInputContentError
from pipelex.tools.jinja2.exceptions import Jinja2TemplateSecurityError
from pipelex.tools.log.json_log_sink import LOGGER_KEY, MESSAGE_KEY, SEVERITY_KEY, TIME_KEY, JsonLogSink
from pipelex.tools.log.log_context import bind_log_context
from pipelex.tools.network.exceptions import SsrfBlockedError
from pipelex.tools.storage.exceptions import StorageInvalidUriError
from pipelex.tools.uri.exceptions import UriReadRefusalReason, UriReadRefusedError

if TYPE_CHECKING:
    from collections.abc import Generator

SECURITY_EVENT_LOGGER = "pipelex.errors.security_event"

# What a refusal's message may quote, which its security event must never carry.
_SECRET_HOST = "billing-db.internal.example"
_SECRET_KEY = "pipelex-storage://org_other/mt_9/run_9/assets/payroll.pdf"
_SECRET_TEMPLATE = "{{ invoice['_owner'] }}"


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


def _ssrf_refusal() -> SsrfBlockedError:
    message = f"Refusing to connect to '{_SECRET_HOST}': it resolved to a disallowed (private/loopback/metadata) address."
    return SsrfBlockedError(message).with_security_target_class(SecurityTargetClass.PRIVATE)


class _ImpliedRefusalError(PipelexError):
    """A refusal that carries no code of its own and implies a security code, as an inference error implies its category's."""

    error_code = InheritsCause(fallback=CoreCode.RUNTIME_UNEXPECTED, others=(CoreCode.SECURITY_PROVIDER_URL_REFUSED,))

    @property
    @override
    def implied_error_code(self) -> ErrorCode | None:
        return CoreCode.SECURITY_PROVIDER_URL_REFUSED


class _FallbackRefusalError(PipelexError):
    """A refusal that takes its cause's code, and names a security code as its fallback when no cause carries one."""

    error_code = InheritsCause(fallback=CoreCode.SECURITY_METHOD_PATH_REFUSED)


def _chained(*, error: PipelexError, cause: BaseException) -> PipelexError:
    error.__cause__ = cause
    return error


class _Chaining(StrEnum):
    """How a refusal raised while another is handled holds the first one."""

    IMPLICIT = "implicit"
    FROM_NONE = "from_none"
    FROM_REFUSAL = "from_refusal"


def _refuse_again_while_handling(*, refusal: PipelexError, chaining: _Chaining) -> None:
    """Raise a new refusal of the same code while handling ``refusal``, as a second destination refused in its handler.

    ``chaining`` says how the new refusal holds the first: only as its ``__context__``, not at all, or as its ``__cause__``.
    """
    try:
        raise refusal
    except PipelexError as exc:
        msg = "Refusing to connect to the callback host."
        second_refusal = SsrfBlockedError(msg).with_security_target_class(SecurityTargetClass.LOOPBACK)
        match chaining:
            case _Chaining.IMPLICIT:
                raise second_refusal  # ruff: ignore[raise-without-from-inside-except] — chained only as its context, on purpose
            case _Chaining.FROM_NONE:
                raise second_refusal from None
            case _Chaining.FROM_REFUSAL:
                raise second_refusal from exc


def _refuse_another_while_handling(*, refusal: SsrfBlockedError) -> None:
    """Raise a refusal of another code while handling ``refusal``, chained to it only as its ``__context__``."""
    try:
        raise refusal
    except SsrfBlockedError:
        msg = "The schema of concept 'Invoice' carries x-python-* extensions."
        raise UnsafeSchemaError(msg)  # ruff: ignore[raise-without-from-inside-except] — chained only as its context, on purpose


def _wrapped(*, refusal: PipelexError) -> PipelineInputContentError:
    """The refusal under a wrapper that takes its cause's code, as every boundary a failure crosses wraps it."""
    try:
        raise refusal
    except PipelexError as exc:
        wrapper = PipelineInputContentError(f"The input 'photo' cannot be read: {exc.message}")
        wrapper.__cause__ = exc
        return wrapper


class TestSecurityEvent:
    def test_every_security_code_names_the_kind_of_target_it_refuses(self) -> None:
        """Both registries' security families, and nothing else, have a target kind, so a new security code cannot ship without one."""
        security_codes: set[ErrorCode] = {code for code in CoreCode if code.startswith("security.")}
        security_codes |= {code for code in PipelexErrorCode if code.startswith("pipelex.security.")}
        assert security_codes
        assert set(SECURITY_TARGET_KIND_BY_CODE) == security_codes

    @pytest.mark.parametrize(
        ("error", "code", "domain", "error_type", "target_kind", "target_class"),
        [
            pytest.param(
                UriReadRefusedError("The input 'photo' names a file this run may not read.", reason=UriReadRefusalReason.LOCAL_PATH),
                CoreCode.SECURITY_INPUT_URL_REFUSED,
                ProblemDomain.INPUT,
                "UriReadRefusedError",
                SecurityTargetKind.URL,
                SecurityTargetClass.SCHEME,
                id="read_scope_input",
            ),
            pytest.param(
                UriReadRefusedError(
                    "Image 1 of pipe 'describe' names a file this run may not read.", reason=UriReadRefusalReason.FOREIGN_STORAGE_KEY
                ).with_error_code(CoreCode.SECURITY_METHOD_URL_REFUSED),
                CoreCode.SECURITY_METHOD_URL_REFUSED,
                ProblemDomain.METHOD,
                "UriReadRefusedError",
                SecurityTargetKind.URL,
                SecurityTargetClass.FOREIGN_STORAGE_KEY,
                id="read_scope_method",
            ),
            pytest.param(
                _ssrf_refusal(),
                CoreCode.SECURITY_INPUT_URL_REFUSED,
                ProblemDomain.INPUT,
                "SsrfBlockedError",
                SecurityTargetKind.URL,
                SecurityTargetClass.PRIVATE,
                id="ssrf_input",
            ),
            pytest.param(
                _ssrf_refusal().with_error_code(CoreCode.SECURITY_PROVIDER_URL_REFUSED),
                CoreCode.SECURITY_PROVIDER_URL_REFUSED,
                ProblemDomain.RUNTIME,
                "SsrfBlockedError",
                SecurityTargetKind.URL,
                SecurityTargetClass.PRIVATE,
                id="ssrf_provider",
            ),
            pytest.param(
                UnsafeSchemaError("The schema of concept 'Invoice' carries x-python-* extensions."),
                CoreCode.SECURITY_SCHEMA_REFUSED,
                ProblemDomain.METHOD,
                "UnsafeSchemaError",
                SecurityTargetKind.SCHEMA,
                None,
                id="unsafe_schema",
            ),
            pytest.param(
                Jinja2TemplateSecurityError("Jinja2 render — refused by the template sandbox: A template may not read '_owner'."),
                CoreCode.SECURITY_TEMPLATE_REFUSED,
                ProblemDomain.METHOD,
                "Jinja2TemplateSecurityError",
                SecurityTargetKind.TEMPLATE,
                None,
                id="template_sandbox",
            ),
            pytest.param(
                BundleResourcePathError("The resource key escapes the bundle's root."),
                CoreCode.SECURITY_INPUT_PATH_REFUSED,
                ProblemDomain.INPUT,
                "BundleResourcePathError",
                SecurityTargetKind.PATH,
                None,
                id="bundle_resource_path",
            ),
            pytest.param(
                TemplateUrlRefusedError("The document template names a file outside the bundle.", refusal_code=None),
                CoreCode.SECURITY_METHOD_PATH_REFUSED,
                ProblemDomain.METHOD,
                "TemplateUrlRefusedError",
                SecurityTargetKind.PATH,
                None,
                id="doc_gen_template_path",
            ),
            pytest.param(
                _wrapped(refusal=StorageInvalidUriError("The storage key holds a path traversal.")),
                CoreCode.SECURITY_INPUT_PATH_REFUSED,
                ProblemDomain.INPUT,
                "StorageInvalidUriError",
                SecurityTargetKind.PATH,
                None,
                id="storage_key_traversal_under_its_wrapper",
            ),
            pytest.param(
                _wrapped(refusal=_ssrf_refusal()),
                CoreCode.SECURITY_INPUT_URL_REFUSED,
                ProblemDomain.INPUT,
                "SsrfBlockedError",
                SecurityTargetKind.URL,
                SecurityTargetClass.PRIVATE,
                id="ssrf_under_its_wrapper",
            ),
            pytest.param(
                _wrapped(refusal=_ImpliedRefusalError("The answer names an address this run may not fetch.")),
                CoreCode.SECURITY_PROVIDER_URL_REFUSED,
                ProblemDomain.RUNTIME,
                "_ImpliedRefusalError",
                SecurityTargetKind.URL,
                None,
                id="implied_code_under_its_wrapper",
            ),
            pytest.param(
                _wrapped(refusal=_chained(error=_FallbackRefusalError("The template names a file outside the bundle."), cause=OSError("denied"))),
                CoreCode.SECURITY_METHOD_PATH_REFUSED,
                ProblemDomain.METHOD,
                "_FallbackRefusalError",
                SecurityTargetKind.PATH,
                None,
                id="fallback_code_under_its_wrapper",
            ),
        ],
    )
    def test_a_refusal_fails_under_its_security_code_and_logs_its_event(
        self,
        error: PipelexError,
        code: ErrorCode,
        domain: ProblemDomain,
        error_type: str,
        target_kind: SecurityTargetKind,
        target_class: SecurityTargetClass | None,
    ) -> None:
        """The failure reports the security code with the domain of whoever caused it, and its event names the same, with the run and the org."""
        report = error.to_error_report()
        assert report.code == code
        # The registry domain of the code, who caused the refusal, which the problem document carries.
        assert error_code_spec(code).domain == domain

        with _security_event_lines() as lines:
            assert emit_security_event(error=error, pipeline_run_id="run_1", request_id="req_1", extras={"org_id": "org_abc", "plan": "pro"})

        (line,) = lines
        expected: dict[str, Any] = {
            SEVERITY_KEY: "WARNING",
            LOGGER_KEY: SECURITY_EVENT_LOGGER,
            MESSAGE_KEY: SECURITY_EVENT_MESSAGE,
            "event.name": SECURITY_EVENT_NAME,
            "error.code": code,
            "error.domain": domain,
            "error.type": error_type,
            "security.target": target_kind,
            "pipeline_run_id": "run_1",
            "request_id": "req_1",
            "run.extras.org_id": "org_abc",
            "run.extras.plan": "pro",
        }
        if target_class is not None:
            expected["security.target_class"] = target_class
        line.pop(TIME_KEY)
        # The exact record: nothing else rides it, so neither the message nor a traceback can carry content.
        assert line == expected

    @pytest.mark.parametrize(
        ("error", "secret"),
        [
            pytest.param(_wrapped(refusal=_ssrf_refusal()), _SECRET_HOST, id="ssrf_host"),
            pytest.param(
                UriReadRefusedError(f"The input 'photo' names {_SECRET_KEY}.", reason=UriReadRefusalReason.FOREIGN_STORAGE_KEY),
                _SECRET_KEY,
                id="foreign_storage_key",
            ),
            pytest.param(Jinja2TemplateSecurityError(f"Refused by the template sandbox: {_SECRET_TEMPLATE}"), _SECRET_TEMPLATE, id="template_text"),
        ],
    )
    def test_the_event_carries_no_content_even_when_the_message_does(self, error: PipelexError, secret: str) -> None:
        """A message quoting the URL, the key or the template stays off the event, logged while the failure is being handled."""
        assert secret in str(error) or (error.__cause__ is not None and secret in str(error.__cause__))
        emitted: list[bool] = []
        with _security_event_lines() as lines:
            try:
                raise error
            except PipelexError as exc:
                # Inside the `except`, as every boundary logs it: the exception being handled must not ride the record.
                emitted.append(emit_security_event(error=exc))

        assert emitted == [True]
        (line,) = lines
        serialized = json.dumps(line)
        assert secret not in serialized
        assert "exception" not in line
        assert line[MESSAGE_KEY] == SECURITY_EVENT_MESSAGE

    def test_a_refusal_is_reported_once_however_many_boundaries_it_crosses(self) -> None:
        refusal = _ssrf_refusal()
        wrapper = _wrapped(refusal=refusal)
        outer_wrapper = PipelineInputContentError("The run failed.")
        outer_wrapper.__cause__ = wrapper

        with _security_event_lines() as lines:
            assert emit_security_event(error=wrapper, pipeline_run_id="run_1")
            assert not emit_security_event(error=wrapper, pipeline_run_id="run_1")
            assert not emit_security_event(error=outer_wrapper)
            assert not emit_security_event(error=refusal)

        assert len(lines) == 1

    @pytest.mark.parametrize("chaining", list(_Chaining))
    @pytest.mark.parametrize("reported_as", ["refusal", "wrapper"])
    def test_a_new_refusal_of_the_same_code_is_reported_however_it_is_chained_to_a_reported_one(self, chaining: _Chaining, reported_as: str) -> None:
        """A wrapper restates the refusal it wraps; a new refusal is reported on its own, even of the same code.

        Such as a callback URL the delivery refuses while the run's own refusal of an input URL is being handled: both
        are `security.input_url_refused`, and each is a refusal of its own, whether the second holds the first as its
        context, not at all, or as its cause, and whether the first was reported bare or under a wrapper.
        """
        refusal = _ssrf_refusal()
        reported: PipelexError = _wrapped(refusal=refusal) if reported_as == "wrapper" else refusal
        with _security_event_lines() as lines:
            assert emit_security_event(error=reported)
            with pytest.raises(SsrfBlockedError) as exc_info:
                _refuse_again_while_handling(refusal=reported, chaining=chaining)
            second_refusal = exc_info.value
            assert emit_security_event(error=_wrapped(refusal=second_refusal))
            assert not emit_security_event(error=second_refusal)

        assert [line["security.target_class"] for line in lines] == [SecurityTargetClass.PRIVATE, SecurityTargetClass.LOOPBACK]
        assert [line["error.code"] for line in lines] == [CoreCode.SECURITY_INPUT_URL_REFUSED] * 2

    def test_a_distinct_refusal_raised_while_handling_a_reported_one_is_reported(self) -> None:
        """`__context__` only ties a refusal to the one it restates: another code, raised while handling the first, is its own."""
        refusal = _ssrf_refusal()
        with _security_event_lines() as lines:
            assert emit_security_event(error=refusal)
            with pytest.raises(UnsafeSchemaError) as exc_info:
                _refuse_another_while_handling(refusal=refusal)
            assert emit_security_event(error=exc_info.value)

        assert exc_info.value.__context__ is refusal
        assert [line["error.code"] for line in lines] == [CoreCode.SECURITY_INPUT_URL_REFUSED, CoreCode.SECURITY_SCHEMA_REFUSED]

    def test_a_failure_whose_event_was_logged_elsewhere_is_not_reported_again(self) -> None:
        """A host marks the error a transport rebuilt from a worker's report, whose worker logged the event."""
        rebuilt = _ssrf_refusal()
        mark_security_event_emitted(error=rebuilt)
        with _security_event_lines() as lines:
            assert not emit_security_event(error=rebuilt)
        assert lines == []

    @pytest.mark.parametrize(
        "error",
        [
            pytest.param(PipelexUnexpectedError("An invariant did not hold."), id="not_a_security_code"),
            pytest.param(
                Jinja2TemplateSecurityError("Refused by the template sandbox.").with_error_code(CoreCode.RUNTIME_UNEXPECTED),
                id="pipelex_own_template_is_runtime_unexpected",
            ),
            pytest.param(ValueError("not a Pipelex error"), id="not_a_pipelex_error"),
        ],
    )
    def test_a_failure_that_is_no_security_refusal_logs_no_event(self, error: BaseException) -> None:
        with _security_event_lines() as lines:
            assert not emit_security_event(error=error)
        assert lines == []

    def test_the_bound_log_context_names_the_run_when_the_caller_does_not(self) -> None:
        with _security_event_lines() as lines, bind_log_context(request_id="req_ctx", pipeline_run_id="run_ctx"):
            assert emit_security_event(error=_ssrf_refusal())

        (line,) = lines
        assert line["request_id"] == "req_ctx"
        assert line["pipeline_run_id"] == "run_ctx"

    def test_a_host_logs_an_event_for_a_refusal_it_decides_itself(self) -> None:
        """A host's own tenant-boundary refusal logs the same record, with no target kind outside the security families."""
        with _security_event_lines() as lines:
            log_security_event(code=PipelexErrorCode.ORG_MISMATCH, error_type="CrossOrgStorageAccessError", extras={"org_id": "org_abc"})

        (line,) = lines
        assert line["event.name"] == SECURITY_EVENT_NAME
        assert line["error.code"] == PipelexErrorCode.ORG_MISMATCH
        assert line["run.extras.org_id"] == "org_abc"
        assert "security.target" not in line
        assert "security.target_class" not in line
