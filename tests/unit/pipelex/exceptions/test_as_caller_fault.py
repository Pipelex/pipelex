from pipelex.base_exceptions import INTERNAL_ERROR_PLACEHOLDER, DisclosureMode, ErrorDomain, PipelexError
from pipelex.cogt.exceptions import InferenceErrorCategory, ModelNotFoundError
from pipelex.cogt.inference.error_classification import UserAction, UserActionKind
from pipelex.core.stuffs.exceptions import StuffFactoryError
from pipelex.pipe_run.exceptions import PipeRouterError
from pipelex.system.pipe_run_mode import PipeRunMode


class TestAsCallerFault:
    def test_classifies_this_error_only(self) -> None:
        """The raise site's classification applies to its own error, never to the class or to another instance."""
        caller_fault = StuffFactoryError("Error combining stuffs for concept Report").as_caller_fault()
        other = StuffFactoryError("A factory refusal that is not the caller's")

        caller_report = caller_fault.to_error_report()
        assert caller_report.error_domain == ErrorDomain.INPUT
        assert caller_report.caller_facing_message is True
        assert caller_report.http_status == 422

        other_report = other.to_error_report()
        assert other_report.error_domain is None
        assert other_report.caller_facing_message is False
        assert StuffFactoryError.error_domain is None

    def test_strict_disclosure_keeps_the_message_and_the_user_action(self) -> None:
        """A caller fault reads its own message and next step under STRICT, instead of the placeholder."""
        user_action = UserAction(kind=UserActionKind.CHANGE_INPUT, detail="Provide the input 'topic'.")
        error = StuffFactoryError("Input 'topic' is missing").as_caller_fault(user_action=user_action)

        payload = error.to_error_report().to_dict(disclosure_mode=DisclosureMode.STRICT)
        assert payload["message"] == "Input 'topic' is missing"
        assert payload["user_action"] == {"kind": "change_input", "detail": "Provide the input 'topic'."}

    def test_wins_over_a_domain_the_category_derives(self) -> None:
        """On a `CogtError`, the raise site's domain wins over the one its category derives."""
        error = ModelNotFoundError(message="Model handle 'x' was not found in the model deck.", model_handle="x").as_caller_fault()

        report = error.to_error_report()
        assert error.error_category is InferenceErrorCategory.CONFIGURATION
        assert report.error_category == "configuration"
        assert report.error_domain == ErrorDomain.INPUT
        assert report.caller_facing_message is True

    def test_a_wrapper_inherits_the_domain_but_never_the_caller_facing_flag(self) -> None:
        """The flag records who wrote the message: a plain wrapper's own message stays redacted."""
        cause = StuffFactoryError("Error combining stuffs for concept Report").as_caller_fault()
        wrapper = PipelexError("An internal sentence about the cause")
        wrapper.__cause__ = cause

        report = wrapper.to_error_report()
        assert report.error_domain == ErrorDomain.INPUT
        assert report.caller_facing_message is False
        assert report.to_dict(disclosure_mode=DisclosureMode.STRICT)["message"] == INTERNAL_ERROR_PLACEHOLDER

    def test_a_located_wrapper_reports_the_caller_fault_it_locates(self) -> None:
        """The pipe router's location takes the root fault's flag, so the located message survives STRICT."""
        cause = StuffFactoryError("Error combining stuffs for concept Report").as_caller_fault()
        located = PipeRouterError.make_located(
            failure=cause,
            run_mode=PipeRunMode.LIVE,
            pipe_code="analyze",
            output_name=None,
            pipe_stack=["flow", "analyze"],
        )
        located.__cause__ = cause

        payload = located.to_error_report().to_problem_document(disclosure_mode=DisclosureMode.STRICT)
        assert payload["status"] == 422
        assert payload["detail"] == "Pipe 'analyze' failed (flow → analyze): Error combining stuffs for concept Report"
