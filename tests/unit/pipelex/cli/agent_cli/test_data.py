"""Answers a runner gives a refused run, for the agent CLI's tests of a run on a runner."""

from typing import Any, ClassVar


class RunnerProblems:
    """Problem documents a runner answers when it refuses a run, as they came off the wire.

    The first three are the answers of pipelex's runner to `POST /v1/execute` in the error contract's acceptance on
    2026-10-17, as both standard clients received them: a run missing a required input, a pipe whose output has another
    multiplicity than the one declared, and a method naming a model the runner serves no backend for, refused before
    any pipe ran with the fault as its one item. The last is a problem whose items carry suggestions and a suggested fix.
    """

    INPUT_MISSING: ClassVar[str] = (
        '{"type": "https://mthds.ai/errors/input.missing", "title": "A required input is missing", "status": 422, '
        '"detail": "The request does not give the input \'topic\', which the method requires.", "code": "input.missing", '
        '"domain": "input", "retry": "no", "next_step": {"kind": "change_input", "detail": "Add the input \'topic\' to the '
        'request, then send it again."}, "params": {"input": "topic"}, "location": {"pipe": "write_slogan", "path": '
        '["write_slogan"]}, "request_id": "01M55P3J09ADGMD2MW5FSN6S1P"}'
    )
    OUTPUT_MULTIPLICITY: ClassVar[str] = (
        '{"type": "https://mthds.ai/errors/pipe.output_multiplicity", "title": "A pipe\'s output does not have the declared '
        'multiplicity", "status": 422, "detail": "Pipe \'review_topic\' produced an output of the multiplicity \'list\', but '
        'its output \'ideas\' is declared \'single\'.", "code": "pipe.output_multiplicity", "domain": "method", "retry": "no", '
        '"next_step": {"kind": "change_method", "detail": "Declare the output \'ideas\' as \'list\', or make pipe '
        '\'review_topic\' produce \'single\'."}, "params": {"output": "ideas", "declared": "single", "produced": "list", '
        '"pipe": "review_topic"}, "location": {"pipe": "review_topic", "path": ["review_topic"]}, '
        '"request_id": "01M55P71KM9SGEV908K0PNXJ44"}'
    )
    UNKNOWN_MODEL_AT_LOAD: ClassVar[str] = (
        '{"type": "https://mthds.ai/errors/method.invalid", "title": "The method does not validate", "status": 422, '
        '"detail": "The method does not validate.", "code": "method.invalid", "domain": "method", "retry": "no", '
        '"next_step": {"kind": "change_method", "detail": "Fix each fault the problem\'s errors list, then validate the '
        'method again."}, "errors": [{"code": "model.unknown", "detail": "The method names the llm model '
        '\'claude-4.5-haiku\', which no catalog knows.", "params": {"model": "claude-4.5-haiku", "model_type": "llm"}, '
        '"location": {"pipe": "write_slogan", "field": "model"}}], "request_id": "01M55P9XMCX78NQJ1R8QBV9B4F"}'
    )
    ITEMS_WITH_SUGGESTIONS: ClassVar[str] = (
        '{"type": "https://mthds.ai/errors/method.invalid", "title": "The method does not validate", "status": 422, '
        '"detail": "The method does not validate.", "code": "method.invalid", "domain": "method", "retry": "no", '
        '"next_step": {"kind": "change_method", "detail": "Fix each fault the problem\'s errors list, then validate the '
        'method again."}, "errors": [{"code": "model.unknown", "detail": "The method names the llm model \'gpt-5.1\', '
        'which no catalog knows.", "params": {"model": "gpt-5.1", "model_type": "llm", "suggestions": ["gpt-5.5", '
        '"gpt-5.4"]}, "location": {"pipe": "draft_pitch", "field": "model"}, "suggestions": ["gpt-5.5", "gpt-5.4"], '
        '"suggested_fix": {"fix_code": "rename-model", "description": "Replace model \'gpt-5.1\' of pipe \'draft_pitch\' '
        'with \'gpt-5.5\'", "safety": "unsafe", "ops": [{"kind": "set_key", "table_path": ["pipe", "draft_pitch"], '
        '"key": "model", "value": "gpt-5.5"}]}}], "request_id": "01M55PSUGGESTIONS00000000000"}'
    )


class GatewayAnswers:
    """Answers that are no problem document, which a gateway or a hosted plane in front of the runner may give."""

    # A gateway's error page in front of the runner.
    HTML_PAGE: ClassVar[str] = "<html><head><title>502 Bad Gateway</title></head><body><h1>502 Bad Gateway</h1></body></html>"
    # A server that does not serve the route at all, as a framework answers it.
    NOT_FOUND: ClassVar[str] = '{"detail":"Not Found"}'


class RetiredEnvelope:
    """The members of the error envelope this CLI wrote before it reported problems, none of which a problem carries."""

    MEMBERS: ClassVar[tuple[str, ...]] = (
        "error",
        "error_type",
        "error_source",
        "error_domain",
        "error_category",
        "error_code",
        "hint",
        "retryable",
        "http_status",
        "validation_errors",
        "pipe_code",
        "pipe_stack",
        "retry_after_seconds",
        "run_status",
    )


class StoredRunReports:
    """Reports the hosted API may store for a failed run, as `RunFailedError.error` hands them back."""

    # The report in the shape the hosted plane wrote before it stored problem documents.
    FORMER_SHAPE: ClassVar[dict[str, Any]] = {
        "error_type": "LLMCompletionError",
        "message": "The provider refused the prompt",
        "error_domain": "runtime",
        "error_category": "transient",
        "retryable": True,
        "model": "claude-5.5-sonnet",
        "user_action": {"kind": "wait_and_retry", "detail": "Run it again in a minute"},
    }
    # The run's own problem, as a runner that speaks the problem document stores it, in the operator's view.
    PROBLEM: ClassVar[dict[str, Any]] = {
        "type": "https://mthds.ai/errors/pipe.output_multiplicity",
        "title": "A pipe's output does not have the declared multiplicity",
        "detail": "Pipe 'review_topic' produced an output of the multiplicity 'list', but its output 'ideas' is declared 'single'.",
        "code": "pipe.output_multiplicity",
        "domain": "method",
        "retry": "no",
        "next_step": {"kind": "change_method", "detail": "Declare the output 'ideas' as 'list', or make pipe 'review_topic' produce 'single'."},
        "params": {"output": "ideas", "declared": "single", "produced": "list", "pipe": "review_topic"},
        "location": {"pipe": "review_topic", "path": ["review_topic"]},
        "diagnostics": {"error_class": "PipeOutputMultiplicityError", "message": "the branches do not combine"},
    }


class HostedMethodItems:
    """The items of `POST /v1/pipe-io`'s verdict that a method does not load, and the problem items the agent CLI reports."""

    SENT: ClassVar[list[dict[str, Any]]] = [
        # An item no stage classified: its message is the finding of `method.schema_violation`.
        {"category": "blueprint_validation", "message": "unknown concept Foo", "source": "lib/b.mthds", "pipe_code": "step2"},
        # An item of a type this version reads, with the locators the model check gives it.
        {
            "category": "pipe_validation",
            "message": "Pipe 'draft' (PipeLLM), field 'model': Model handle 'gpt-5.1' was not found in the model deck",
            "error_type": "unknown_model",
            "pipe_code": "draft",
            "field_name": "model",
            "model_reference": "gpt-5.1",
            "model_type": "llm",
            "suggestions": ["gpt-5.5"],
            "source": "main.mthds",
        },
        # An item of a newer runner, whose type this version does not read.
        {"category": "pipe_validation", "message": "A kind of fault from a newer runner", "error_type": "some_future_fault", "pipe_code": "step3"},
    ]
    PROBLEM_ITEMS: ClassVar[list[dict[str, Any]]] = [
        {
            "code": "method.schema_violation",
            "detail": "The declaration at 'pipe.step2' breaks a rule of the language (unknown concept Foo).",
            "params": {"field_path": "pipe.step2", "finding": "unknown concept Foo"},
            "location": {"pipe": "step2", "file": "lib/b.mthds"},
        },
        {
            "code": "model.unknown",
            "detail": "The method names the llm model 'gpt-5.1', which no catalog knows.",
            "params": {"model": "gpt-5.1", "model_type": "llm", "suggestions": ["gpt-5.5"]},
            "location": {"pipe": "draft", "field": "model", "file": "main.mthds"},
            "suggestions": ["gpt-5.5"],
        },
        {
            "code": "method.schema_violation",
            "detail": "The declaration at 'pipe.step3' breaks a rule of the language (A kind of fault from a newer runner).",
            "params": {"field_path": "pipe.step3", "finding": "A kind of fault from a newer runner"},
            "location": {"pipe": "step3"},
        },
    ]
