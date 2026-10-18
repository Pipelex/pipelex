import json
import logging
from collections.abc import Sequence
from typing import Any, ClassVar, Self, cast, overload

import pytest
from mthds.protocol.problem.answers import MAX_BODY_NESTING, decode_json, nests_deeper_than
from mthds.protocol.problem.models import ProblemItem
from mthds.protocol.problem.registry import CoreCode, StepKind
from pydantic import BaseModel, model_validator
from pytest_mock import MockerFixture
from typing_extensions import override

from pipelex.base_exceptions import PipelexError
from pipelex.cogt.exceptions import InferenceErrorCategory, LLMCompletionError
from pipelex.cogt.inference.error_classification import ProviderErrorMetadata, UserAction, UserActionKind
from pipelex.cogt.inference.provider_name import ProviderName
from pipelex.errors.error_code_declaration import ErrorCodeDeclaration
from pipelex.errors.error_codes import ErrorCode, error_code_spec
from pipelex.errors.problem import (
    MAX_PROBLEM_TEXT_LENGTH,
    MISSING_REQUIRED_PARAMS_MESSAGE,
    TRUNCATION_MARKER,
    UNKNOWN_CODE_ITEM_DETAIL,
    PipelexProblem,
    ProblemView,
    caller_view_of,
    make_location,
    make_problem,
    make_problem_item,
    problem_metadata,
)
from pipelex.errors.registry.pipelex_codes import PipelexErrorCode
from tests.unit.pipelex.errors.test_data import ProblemViewsTestData


class _MisconfiguredError(PipelexError):
    error_code: ClassVar[ErrorCodeDeclaration] = CoreCode.RUNTIME_MISCONFIGURED


class _TemplateRefusalError(PipelexError):
    error_code: ClassVar[ErrorCodeDeclaration] = CoreCode.METHOD_TEMPLATE_INVALID


class _AmbiguousPipeError(PipelexError):
    error_code: ClassVar[ErrorCodeDeclaration] = CoreCode.REQUEST_PIPE_AMBIGUOUS


class _UnreadableSequence(Sequence[str]):
    """A sequence of a raise site's own whose items cannot be read: reading one raises what no validation catches."""

    @override
    def __len__(self) -> int:
        return 2

    @overload
    def __getitem__(self, index: int) -> str: ...

    @overload
    def __getitem__(self, index: slice) -> Sequence[str]: ...

    @override
    def __getitem__(self, index: int | slice) -> str | Sequence[str]:
        msg = "this sequence cannot be read"
        raise KeyError(msg)


def _cyclic_list() -> list[Any]:
    cyclic: list[Any] = []
    cyclic.append(cyclic)
    return cyclic


class _NodeHolder(BaseModel):
    error: PipelexProblem | None = None


class _RefusedAsAWholeParams(BaseModel):
    """A parameters model whose refusal names no parameter, as a model-level validator's does."""

    pipe: str | None = None
    template: str | None = None
    finding: str | None = None

    @model_validator(mode="after")
    def _refuse_the_set(self) -> Self:
        msg = "the parameters are refused together"
        raise ValueError(msg)


class _LaxBlobsParams(BaseModel):
    """A parameters model laxer than the problem's own, which types each missing blob as a SHA-256."""

    missing_blobs: list[str] | None = None


def _all_codes() -> list[ErrorCode]:
    return [*CoreCode, *PipelexErrorCode]


def _nulls_in(value: Any, *, path: str = "") -> list[str]:
    """The paths of every member of ``value``, at any depth, written as ``None``."""
    if value is None:
        return [path or "<root>"]
    if isinstance(value, dict):
        found: list[str] = []
        for key, item in cast("dict[str, Any]", value).items():
            found.extend(_nulls_in(item, path=f"{path}.{key}"))
        return found
    if isinstance(value, list):
        found = []
        for index_item, item in enumerate(cast("list[Any]", value)):
            found.extend(_nulls_in(item, path=f"{path}[{index_item}]"))
        return found
    return []


class TestProblemViews:
    def test_the_caller_view_has_no_diagnostics_and_the_operator_view_has_them(self) -> None:
        error = _MisconfiguredError(ProblemViewsTestData.OPERATOR_MESSAGE).with_params(component=ProblemViewsTestData.COMPONENT)

        operator = error.to_problem(view=ProblemView.OPERATOR)
        caller = error.to_problem(view=ProblemView.CALLER)

        assert operator.diagnostics is not None
        assert operator.diagnostics.error_class == "_MisconfiguredError"
        assert operator.diagnostics.message == ProblemViewsTestData.OPERATOR_MESSAGE
        assert caller.diagnostics is None
        assert "diagnostics" not in caller.to_wire()
        assert ProblemViewsTestData.OPERATOR_MESSAGE not in str(caller.to_wire())
        # The same code, domain, verdict and sentence in both views.
        assert (caller.code, caller.domain, caller.retry, caller.detail) == (operator.code, operator.domain, operator.retry, operator.detail)
        assert caller.detail == error_code_spec(CoreCode.RUNTIME_MISCONFIGURED).detail

    def test_an_operator_code_aims_its_step_at_the_reader(self) -> None:
        """The operator reads the actor's step; the caller, who cannot fix the deployment, reads the other one."""
        error = _MisconfiguredError(ProblemViewsTestData.OPERATOR_MESSAGE).with_params(component=ProblemViewsTestData.COMPONENT)

        operator = error.to_problem(view=ProblemView.OPERATOR)
        caller = error.to_problem(view=ProblemView.CALLER)

        assert operator.next_step.kind == StepKind.FIX_CONFIGURATION
        assert operator.next_step.detail == f"Set or correct the configuration of '{ProblemViewsTestData.COMPONENT}', then restart the runtime."
        assert caller.next_step.kind == StepKind.REPORT
        assert caller.next_step.detail == "Report this to whoever runs the runtime."

    def test_an_operator_only_parameter_rides_the_operator_diagnostics_alone(self) -> None:
        error = _MisconfiguredError(ProblemViewsTestData.OPERATOR_MESSAGE).with_params(component=ProblemViewsTestData.COMPONENT)

        operator = error.to_problem(view=ProblemView.OPERATOR)
        caller = error.to_problem(view=ProblemView.CALLER)

        assert operator.params is None
        assert operator.diagnostics is not None
        assert operator.diagnostics.params == {"component": ProblemViewsTestData.COMPONENT}
        assert caller.params is None
        assert ProblemViewsTestData.COMPONENT not in str(caller.to_wire())

    def test_the_caller_view_of_the_operator_view_is_the_caller_view(self) -> None:
        for error in (
            _MisconfiguredError(ProblemViewsTestData.OPERATOR_MESSAGE).with_params(component=ProblemViewsTestData.COMPONENT),
            _TemplateRefusalError("the template does not parse").with_params(pipe="summarize", template="prompt", finding="unexpected '}'"),
        ):
            projected = caller_view_of(problem=error.to_problem(view=ProblemView.OPERATOR))
            assert projected.to_wire() == error.to_problem(view=ProblemView.CALLER).to_wire()

    def test_the_detail_is_rendered_from_the_code_and_its_parameters(self) -> None:
        error = _TemplateRefusalError("the raise site's own words").with_params(pipe="summarize", template="prompt", finding="unexpected '}'")

        caller = error.to_problem(view=ProblemView.CALLER)

        assert caller.detail == "The template 'prompt' of pipe 'summarize' is invalid (unexpected '}')."
        assert caller.params is not None
        assert caller.params.as_wire() == {"pipe": "summarize", "template": "prompt", "finding": "unexpected '}'"}
        assert "the raise site's own words" not in str(caller.to_wire())

    @pytest.mark.builds_problems_without_required_params(
        reason="builds a problem lacking its parameters, to check that its sentence falls back on the title"
    )
    def test_a_template_missing_a_parameter_falls_back_on_the_title(self, caplog: pytest.LogCaptureFixture) -> None:
        """Rendering is total: a missing parameter costs the sentence, never the problem, and the raise site is logged."""
        error = _TemplateRefusalError("no parameters given")

        with caplog.at_level(logging.WARNING, logger="pipelex.errors.problem"):
            caller = error.to_problem(view=ProblemView.CALLER)

        spec = error_code_spec(CoreCode.METHOD_TEMPLATE_INVALID)
        assert caller.detail == spec.title
        assert caller.next_step.kind == spec.actor_step
        assert caller.next_step.detail
        assert any(record.getMessage() == "A problem's sentence could not be rendered from its template" for record in caplog.records)

    def test_a_withheld_name_reads_its_own_sentences_in_every_view(self, caplog: pytest.LogCaptureFixture) -> None:
        """A template refusal without its `name` says what happened without it, in each view and in the caller view of the operator's.

        The name is withheld by rule, which no raise site is at fault for, so nothing is logged about the parameter it
        lacks, and no sentence falls back on the title or the generic step.
        """
        with caplog.at_level(logging.WARNING, logger="pipelex.errors.problem"):
            operator = make_problem(code=CoreCode.SECURITY_TEMPLATE_REFUSED, view=ProblemView.OPERATOR, params={"pipe": "say"})
            caller = make_problem(code=CoreCode.SECURITY_TEMPLATE_REFUSED, view=ProblemView.CALLER, params={"pipe": "say"})
            item = make_problem_item(code=CoreCode.SECURITY_TEMPLATE_REFUSED, params={"pipe": "say"})

        detail = "A template of pipe 'say' looked a name up from the run's data, and the template sandbox refused that name."
        step = "Change the templates of pipe 'say' so that the run's data no longer chooses the names they look up, then run the method again."
        assert operator.detail == caller.detail == item.detail == detail
        assert operator.next_step.detail == caller.next_step.detail == caller_view_of(problem=operator).next_step.detail == step
        messages = [record.getMessage() for record in caplog.records]
        assert "A problem lacks a parameter its code requires" not in messages
        assert "A problem's sentence could not be rendered from its template" not in messages

    @pytest.mark.builds_problems_without_required_params(reason="builds a template refusal lacking its pipe, to check that it is still logged")
    def test_a_withheld_code_still_logs_another_parameter_it_lacks(self, caplog: pytest.LogCaptureFixture) -> None:
        """Only the parameter withheld by rule goes unreported: a refusal lacking its `pipe` is still a raise site to fix."""
        with caplog.at_level(logging.WARNING, logger="pipelex.errors.problem"):
            make_problem(code=CoreCode.SECURITY_TEMPLATE_REFUSED, view=ProblemView.CALLER, params={})

        lacking = [getattr(record, "params", None) for record in caplog.records if record.getMessage() == MISSING_REQUIRED_PARAMS_MESSAGE]
        assert lacking == [["pipe"]]

    def test_an_undeclared_or_mistyped_parameter_is_dropped(self, caplog: pytest.LogCaptureFixture) -> None:
        error = _TemplateRefusalError("refused").with_params(pipe="summarize", template="prompt", finding="bad", undeclared="secret value")

        with caplog.at_level(logging.WARNING, logger="pipelex.errors.problem"):
            caller = error.to_problem(view=ProblemView.CALLER)

        assert caller.params is not None
        assert "undeclared" not in caller.params.as_wire()
        assert "secret value" not in str(caller.to_wire())
        assert any(record.getMessage() == "An error gives a parameter its code does not declare" for record in caplog.records)

    @pytest.mark.builds_problems_without_required_params(
        reason="builds every code's problem with no parameter, to check that none holds a null member"
    )
    @pytest.mark.parametrize("view", list(ProblemView))
    def test_no_problem_holds_a_null_member(self, view: ProblemView) -> None:
        """Every code, in every view, with no parameter given: no member at any depth is written as null."""
        for code in _all_codes():
            problem = make_problem(code=code, view=view)
            assert _nulls_in(problem.to_wire()) == [], code
            assert _nulls_in(problem.model_dump(mode="json")) == [], code
            nested = _NodeHolder(error=problem).model_dump(mode="json")
            assert _nulls_in(nested["error"]) == [], code

    @pytest.mark.parametrize("view", list(ProblemView))
    def test_a_problem_built_from_a_rich_error_holds_no_null_member(self, view: ProblemView) -> None:
        error = LLMCompletionError(
            ProblemViewsTestData.OPERATOR_MESSAGE,
            error_category=InferenceErrorCategory.CONFIGURATION,
            provider_metadata=ProviderErrorMetadata(
                provider=ProviderName.OPENAI, sdk_exception_type="AuthenticationError", status_code=401, message="invalid key"
            ),
        )
        error.model_handle = "gpt-4o-mini"

        problem = error.to_problem(view=view, request_id="req-1", pipeline_run_id="run-1")

        assert _nulls_in(problem.to_wire()) == []

    def test_a_message_is_bounded(self) -> None:
        """An oversized exception message is capped, its head kept, in the operator's diagnostics."""
        oversized = "Validation failed: " + "x" * (MAX_PROBLEM_TEXT_LENGTH * 50)
        error = LLMCompletionError(oversized, error_category=InferenceErrorCategory.UNKNOWN)

        operator = error.to_problem(view=ProblemView.OPERATOR)

        assert operator.diagnostics is not None
        message = operator.diagnostics.message
        assert len(message) <= MAX_PROBLEM_TEXT_LENGTH
        assert message.startswith("Validation failed: ")
        assert message.endswith(TRUNCATION_MARKER)

    def test_a_provider_message_and_a_text_parameter_are_bounded(self) -> None:
        oversized = "y" * (MAX_PROBLEM_TEXT_LENGTH * 3)
        provider_error = LLMCompletionError(
            "provider refused",
            error_category=InferenceErrorCategory.CONFIGURATION,
            provider_metadata=ProviderErrorMetadata(
                provider=ProviderName.OPENAI, sdk_exception_type="BadRequestError", status_code=400, message=oversized
            ),
        )
        template_error = _TemplateRefusalError("refused").with_params(pipe="summarize", template="prompt", finding=oversized)

        operator = provider_error.to_problem(view=ProblemView.OPERATOR)
        caller = template_error.to_problem(view=ProblemView.CALLER)

        assert operator.diagnostics is not None
        assert operator.diagnostics.provider is not None
        assert operator.diagnostics.provider.message is not None
        assert len(operator.diagnostics.provider.message) <= MAX_PROBLEM_TEXT_LENGTH
        assert caller.params is not None
        assert len(caller.params.as_wire()["finding"]) <= MAX_PROBLEM_TEXT_LENGTH

    def test_an_inference_failure_keeps_a_next_step_in_the_caller_view(self) -> None:
        """No view drops the step: a classified inference failure tells its caller what to do."""
        error = LLMCompletionError(
            "provider said: invalid key sk-...",
            error_category=InferenceErrorCategory.CONFIGURATION,
            user_action=UserAction(kind=UserActionKind.CHECK_CREDENTIALS, detail="Verify the API key."),
        )

        caller = error.to_problem(view=ProblemView.CALLER)

        # A configuration failure is the operator's to fix, so its caller is told to report it.
        assert caller.code == CoreCode.RUNTIME_MISCONFIGURED
        assert caller.next_step.kind == StepKind.REPORT
        assert caller.next_step.detail == "Report this to whoever runs the runtime."
        assert "sk-" not in str(caller.to_wire())

    @pytest.mark.builds_problems_without_required_params(reason="builds every code's problem with no parameter, to check the steps alone")
    def test_no_step_points_at_text_a_caller_cannot_see(self) -> None:
        """Every step of every code stands alone: none sends its reader to an error message the view may not show."""
        for code in _all_codes():
            for view in ProblemView:
                step_detail = make_problem(code=code, view=view).next_step.detail.lower()
                for phrase in ProblemViewsTestData.HIDDEN_TEXT_PHRASES:
                    assert phrase not in step_detail, (code, view, step_detail)

    def test_a_gateway_refusal_reads_without_the_provider_text(self) -> None:
        """The provider's specifics stay the operator's, and the caller's step and detail still read in full."""
        error = LLMCompletionError(
            ProblemViewsTestData.GATEWAY_MESSAGE,
            error_category=InferenceErrorCategory.CONFIGURATION,
            provider_metadata=ProviderErrorMetadata(
                provider=ProviderName.GATEWAY,
                sdk_exception_type="BadRequestError",
                status_code=400,
                message=ProblemViewsTestData.GATEWAY_PROVIDER_TEXT,
            ),
        )
        error.model_handle = "acme/large"

        caller = error.to_problem(view=ProblemView.CALLER)
        operator = error.to_problem(view=ProblemView.OPERATOR)

        assert ProblemViewsTestData.GATEWAY_PROVIDER_TEXT not in str(caller.to_wire())
        assert caller.detail
        assert caller.next_step.detail
        assert operator.diagnostics is not None
        assert operator.diagnostics.provider is not None
        assert operator.diagnostics.provider.message == ProblemViewsTestData.GATEWAY_PROVIDER_TEXT

    @pytest.mark.builds_problems_without_required_params(reason="builds problems with a retry delay alone, to check which delays are kept")
    def test_an_unusable_retry_delay_is_left_out(self) -> None:
        for delay in (float("inf"), float("nan"), -1.0):
            problem = make_problem(code=CoreCode.PROVIDER_RATE_LIMITED, view=ProblemView.CALLER, retry_after=delay)
            assert problem.retry_after is None
        assert make_problem(code=CoreCode.PROVIDER_RATE_LIMITED, view=ProblemView.CALLER, retry_after=3.5).retry_after == 3.5
        # A code whose verdict is not `yes` never carries a delay.
        assert make_problem(code=CoreCode.RUNTIME_UNEXPECTED, view=ProblemView.CALLER, retry_after=3.5).retry_after is None

    @pytest.mark.builds_problems_without_required_params(
        reason="gives parameters the code refuses as a whole, which are dropped, to check that they are"
    )
    def test_a_parameter_set_refused_as_a_whole_is_dropped(self, mocker: MockerFixture, caplog: pytest.LogCaptureFixture) -> None:
        """A refusal naming no parameter, a model-level one, drops them all: the error is reported, never replaced."""
        spec = error_code_spec(CoreCode.METHOD_TEMPLATE_INVALID).model_copy(
            update={"params_model": _RefusedAsAWholeParams, "param_names": frozenset({"pipe", "template", "finding"})}
        )
        mocker.patch("pipelex.errors.problem.error_code_spec", return_value=spec)

        with caplog.at_level(logging.WARNING, logger="pipelex.errors.problem"):
            problem = make_problem(code=CoreCode.METHOD_TEMPLATE_INVALID, view=ProblemView.CALLER, params={"pipe": "summarize", "template": "x"})

        assert problem.code == CoreCode.METHOD_TEMPLATE_INVALID
        # The code declares parameters, so the member is present, holding none of those refused.
        assert problem.params is not None
        assert problem.params.as_wire() == {}
        assert problem.detail == spec.title
        assert any(record.getMessage() == "An error gives parameters its code refuses as a whole" for record in caplog.records)

    @pytest.mark.builds_problems_without_required_params(reason="gives a parameter the wire refuses, which is dropped, to check that it is")
    def test_a_parameter_the_wire_refuses_is_dropped(self, mocker: MockerFixture) -> None:
        """A value the code's model takes but the problem's own `params` model refuses never fails the problem."""
        spec = error_code_spec(CoreCode.REQUEST_BLOBS_MISSING).model_copy(update={"params_model": _LaxBlobsParams})
        mocker.patch("pipelex.errors.problem.error_code_spec", return_value=spec)

        problem = make_problem(code=CoreCode.REQUEST_BLOBS_MISSING, view=ProblemView.CALLER, params={"missing_blobs": ["not-a-sha256"]})

        assert problem.code == CoreCode.REQUEST_BLOBS_MISSING
        # The code declares parameters, so the member is present, holding none of those refused.
        assert problem.params is not None
        assert problem.params.as_wire() == {}

    @pytest.mark.parametrize(
        ("wire", "expected_kind", "expected_detail"),
        [
            (ProblemViewsTestData.UNKNOWN_OPERATOR_PROBLEM, StepKind.REPORT, "Report this problem with its request id."),
            (
                ProblemViewsTestData.UNKNOWN_METHOD_PROBLEM,
                StepKind.CHANGE_METHOD,
                "Correct the method as the problem describes, then validate it again.",
            ),
        ],
    )
    def test_the_caller_view_of_an_unknown_code_fails_closed(self, wire: dict[str, Any], expected_kind: StepKind, expected_detail: str) -> None:
        """A code this process does not know keeps no operator sentence: its caller reads a generic step, nested ones included."""
        operator = PipelexProblem.model_validate(wire)
        outer = make_problem(
            code=CoreCode.RUN_FAILED, view=ProblemView.OPERATOR, params={"pipeline_run_id": "run-1", "run_status": "failed"}
        ).model_copy(update={"run_error": operator})

        for caller in (caller_view_of(problem=operator), caller_view_of(problem=outer).run_error):
            assert caller is not None
            assert caller.code == wire["code"]
            assert caller.next_step.kind == expected_kind
            assert caller.next_step.detail == expected_detail
            assert ProblemViewsTestData.PRIVATE_HOST_FILE not in str(caller.to_wire())
            assert caller.diagnostics is None

    def test_the_metadata_view_holds_no_sentence(self) -> None:
        error = _TemplateRefusalError("refused").with_params(pipe="summarize", template="prompt", finding="unexpected '}'")
        problem = error.to_problem(view=ProblemView.OPERATOR, request_id="req-1", pipeline_run_id="run-1")

        metadata = problem_metadata(problem=problem).to_wire()

        assert metadata["code"] == "method.template_invalid"
        assert metadata["request_id"] == "req-1"
        assert metadata["pipeline_run_id"] == "run-1"
        assert "summarize" not in str(metadata)
        assert problem.detail not in str(metadata)
        assert problem.next_step.detail not in str(metadata)

    def test_a_problem_nested_to_the_readers_limit_is_written_back(self) -> None:
        """A problem a reader accepts, an extension member nested to the body's limit included, is written by every write path."""
        nested: Any = "leaf"
        for _ in range(MAX_BODY_NESTING - 2):
            nested = {"inner": nested}
        operator_wire = make_problem(code=CoreCode.RUNTIME_UNEXPECTED, view=ProblemView.OPERATOR).to_wire()
        body = json.dumps({**operator_wire, "run_error": {**operator_wire, "extension": nested}})
        assert not nests_deeper_than(body, limit=MAX_BODY_NESTING)
        assert nests_deeper_than(body, limit=MAX_BODY_NESTING - 1)

        problem = PipelexProblem.model_validate(decode_json(body).value)

        assert json.loads(json.dumps(problem.to_wire())) == json.loads(body)
        assert problem.as_wire() == problem.to_wire()
        caller = caller_view_of(problem=problem)
        assert caller.run_error is not None
        assert caller.run_error.to_wire()["extension"] == nested
        assert "diagnostics" not in caller.to_wire()

    @pytest.mark.parametrize("view", list(ProblemView))
    def test_an_item_never_carries_an_operator_only_parameter(self, view: ProblemView) -> None:
        """An item built by hand is the same in every view: its operator-only parameter and the sentence quoting it are gone."""
        hand_built = ProblemItem.model_validate(ProblemViewsTestData.HAND_BUILT_OPERATOR_ITEM)
        expected_detail = error_code_spec(CoreCode.RUNTIME_MISCONFIGURED).detail

        built = make_problem(code=CoreCode.METHOD_INVALID, view=view, errors=[hand_built])
        # A stored record whose items no `make_problem` built, which its reader projects to the caller's view.
        stored = make_problem(code=CoreCode.METHOD_INVALID, view=ProblemView.OPERATOR).model_copy(update={"errors": [hand_built]})

        for problem in (built, caller_view_of(problem=stored)):
            assert problem.errors is not None
            assert problem.errors[0].as_wire() == {"code": "runtime.misconfigured", "detail": expected_detail, "location": {"pipe": "summarize"}}
            assert ProblemViewsTestData.PRIVATE_HOST_FILE not in str(problem.to_wire())

    def test_a_null_an_extension_member_holds_is_written_as_read(self) -> None:
        """Only a member a model declares is left out when null: an extension member's null survives every write and the caller view."""
        operator_wire = make_problem(code=CoreCode.RUNTIME_UNEXPECTED, view=ProblemView.OPERATOR).to_wire()
        item_wire = {**ProblemViewsTestData.HAND_BUILT_OPERATOR_ITEM, **ProblemViewsTestData.NULL_HOLDING_ITEM_EXTENSIONS}
        body = {
            **operator_wire,
            **ProblemViewsTestData.NULL_HOLDING_EXTENSIONS,
            "errors": [item_wire],
            "run_error": {**operator_wire, **ProblemViewsTestData.NULL_HOLDING_EXTENSIONS},
        }
        problem = PipelexProblem.model_validate(body)

        caller = caller_view_of(problem=problem)
        writes = {
            "to_wire": problem.to_wire(),
            "model_dump": problem.model_dump(mode="json"),
            "nested": _NodeHolder(error=problem).model_dump(mode="json")["error"],
            "caller": caller.to_wire(),
            "caller_dump": caller.model_dump(mode="json"),
            "round_trip": PipelexProblem.model_validate(json.loads(json.dumps(problem.to_wire()))).to_wire(),
        }
        for write_name, wire in writes.items():
            for name, value in ProblemViewsTestData.NULL_HOLDING_EXTENSIONS.items():
                assert wire[name] == value, write_name
                assert wire["run_error"][name] == value, write_name
            assert wire["errors"][0]["vendor"] == {"hint": None}, write_name
            # A declared member with no value is still left out, the item's and the nested problem's included.
            assert "suggestions" not in wire["errors"][0], write_name
            assert "request_id" not in wire, write_name
            assert "params" not in wire["run_error"], write_name

    @pytest.mark.parametrize("view", list(ProblemView))
    def test_an_item_whose_code_is_unknown_fails_closed_for_the_caller(self, view: ProblemView) -> None:
        """The caller reads no parameter of an item whose code this process does not know, and a sentence quoting none."""
        unknown_item = ProblemItem.model_validate(ProblemViewsTestData.UNKNOWN_CODE_ITEM)
        built = make_problem(code=CoreCode.METHOD_INVALID, view=view, errors=[unknown_item])
        stored = make_problem(code=CoreCode.METHOD_INVALID, view=ProblemView.OPERATOR).model_copy(update={"errors": [unknown_item]})

        match view:
            case ProblemView.CALLER:
                for problem in (built, caller_view_of(problem=stored)):
                    assert problem.errors is not None
                    assert problem.errors[0].as_wire() == {
                        "code": "method.future_fault",
                        "detail": UNKNOWN_CODE_ITEM_DETAIL,
                        "location": {"pipe": "summarize"},
                    }
                    assert ProblemViewsTestData.PRIVATE_HOST_FILE not in str(problem.to_wire())
            case ProblemView.OPERATOR:
                assert built.errors is not None
                assert built.errors[0].as_wire() == ProblemViewsTestData.UNKNOWN_CODE_ITEM

    @pytest.mark.builds_problems_without_required_params(reason="gives a required parameter a value the wire refuses, which is dropped, to check that it is")
    @pytest.mark.parametrize(
        "unreadable",
        [
            pytest.param(_cyclic_list(), id="cyclic_list"),
            pytest.param(_UnreadableSequence(), id="sequence_whose_items_raise"),
            pytest.param([["summarize.a"], ["summarize.b"]], id="list_of_lists"),
        ],
    )
    def test_a_value_that_is_no_parameter_value_is_dropped_without_replacing_the_error(
        self, unreadable: object, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A malformed raise-site value is a parameter of the wrong type: it is dropped and logged, and the error keeps its code."""
        error = _AmbiguousPipeError("ambiguous").with_params(pipe="summarize", candidates=unreadable)

        with caplog.at_level(logging.WARNING, logger="pipelex.errors.problem"):
            problem = error.to_problem(view=ProblemView.CALLER)

        assert problem.code == CoreCode.REQUEST_PIPE_AMBIGUOUS
        assert problem.params is not None
        assert problem.params.as_wire() == {"pipe": "summarize"}
        assert any(record.getMessage() == "An error gives a parameter of the wrong type for its code" for record in caplog.records)

    @pytest.mark.builds_problems_without_required_params(reason="gives a parameter the wire refuses, which is dropped, to check that it is")
    @pytest.mark.parametrize(
        ("code", "params"),
        [
            (PipelexErrorCode.DOCGEN_PRINT_TIMEOUT, {"limit": float("inf")}),
            (PipelexErrorCode.DOCGEN_PRINT_TIMEOUT, {"limit": float("nan")}),
            (CoreCode.RUN_TIMED_OUT, {"timeout": float("inf")}),
        ],
    )
    def test_a_number_json_cannot_write_is_dropped(self, code: ErrorCode, params: dict[str, Any], caplog: pytest.LogCaptureFixture) -> None:
        """An infinity or NaN never renders into a sentence it would then vanish from: it is a parameter of the wrong type."""
        with caplog.at_level(logging.WARNING, logger="pipelex.errors.problem"):
            problem = make_problem(code=code, view=ProblemView.CALLER, params=params)

        # The code declares parameters, so the member is present, holding none of those refused.
        assert problem.params is not None
        assert problem.params.as_wire() == {}
        assert problem.detail == error_code_spec(code).title
        assert "inf" not in problem.detail
        json.dumps(problem.to_wire(), allow_nan=False)
        assert any(record.getMessage() == "An error gives a parameter of the wrong type for its code" for record in caplog.records)

    def test_a_lone_item_restating_its_problem_is_folded_into_it(self) -> None:
        """One fault carries no list: the item's parameters and location become the problem's."""
        item = make_problem_item(
            code=CoreCode.MODEL_UNKNOWN,
            params={"model": "gpt-5.1", "model_type": "llm", "suggestions": []},
            location=make_location(pipe="write", field="model"),
        )

        problem = make_problem(code=CoreCode.MODEL_UNKNOWN, view=ProblemView.CALLER, errors=[item])

        assert problem.errors is None
        assert problem.params is not None
        assert problem.params.as_wire() == {"model": "gpt-5.1", "model_type": "llm", "suggestions": []}
        assert problem.location is not None
        assert problem.location.as_wire() == {"pipe": "write", "field": "model"}

    def test_a_lone_item_carrying_suggestions_or_a_fix_stays_listed(self) -> None:
        """A problem has no member for an item's suggestions or its fix: the item gives the problem its facts and stays listed."""
        item = make_problem_item(
            code=CoreCode.MODEL_UNKNOWN,
            params={"model": "gpt-5.1", "model_type": "llm", "suggestions": ["gpt-5"]},
            location=make_location(pipe="write", field="model"),
            suggestions=["gpt-5"],
            suggested_fix=ProblemViewsTestData.RENAME_MODEL_FIX,
        )

        wire = make_problem(code=CoreCode.MODEL_UNKNOWN, view=ProblemView.CALLER, errors=[item]).to_wire()

        assert wire["params"] == {"model": "gpt-5.1", "model_type": "llm", "suggestions": ["gpt-5"]}
        assert wire["location"] == {"pipe": "write", "field": "model"}
        (listed,) = wire["errors"]
        assert listed["suggestions"] == ["gpt-5"]
        assert listed["suggested_fix"] == ProblemViewsTestData.RENAME_MODEL_FIX
