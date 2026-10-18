"""Answers a runner gives a refused run, for the agent CLI's tests of a run on a runner."""

import json
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


#: A run stopped by an operator, as a runner answers it to its operator: the operator's next step, which reads the run's
#: record, and the diagnostics only an operator reads. The caller of such a runner reports it instead.
_OPERATOR_VIEW_OF_A_STOPPED_RUN: dict[str, Any] = {
    "type": "https://mthds.ai/errors/run.terminated",
    "title": "The run was stopped by an operator or an erasure",
    "status": 409,
    "detail": "The run was stopped before it ended (ended by: operator).",
    "code": "run.terminated",
    "domain": "operator",
    "retry": "no",
    "next_step": {"kind": "read_run", "detail": "Read the run's record to see when and why it was stopped."},
    "params": {"ended_by": "operator"},
}
_OPERATOR_DIAGNOSTICS: dict[str, Any] = {"error_class": "RunTerminatedError", "message": "terminated from the console"}


class OperatorViewAnswers:
    """A runner's answers in its operator's view, each with one of Pipelex's members in a shape this version does not read."""

    # The diagnostics read, the request id does not.
    UNREADABLE_REQUEST_ID: ClassVar[str] = json.dumps({**_OPERATOR_VIEW_OF_A_STOPPED_RUN, "request_id": 12345, "diagnostics": _OPERATOR_DIAGNOSTICS})
    # The request id reads, the diagnostics do not.
    UNREADABLE_DIAGNOSTICS: ClassVar[str] = json.dumps(
        {**_OPERATOR_VIEW_OF_A_STOPPED_RUN, "request_id": "01M55PREQUEST0000000000000", "diagnostics": 7}
    )
    # The problem the caller reads for either: the caller's next step, and no diagnostics.
    CALLER_VIEW: ClassVar[dict[str, Any]] = {
        **_OPERATOR_VIEW_OF_A_STOPPED_RUN,
        "next_step": {"kind": "report", "detail": "Report this to whoever runs the runtime if the run was still wanted."},
    }
    # A read of a failed run's results in the caller's view, nesting the run's stored record in its operator's view with
    # no diagnostics to tell it by: the nested problem is the run's record, so it reads in the caller's view all the same.
    NESTING_THE_OPERATOR_S_RECORD: ClassVar[str] = json.dumps(
        {
            "type": "https://mthds.ai/errors/run.failed",
            "title": "The run did not succeed",
            "status": 409,
            "detail": "The run 'run_9' ended as 'TERMINATED', without success.",
            "code": "run.failed",
            "domain": "runtime",
            "retry": "no",
            "next_step": {"kind": "read_run", "detail": "Read the run's own problem in run_error to see why it did not succeed."},
            "params": {"pipeline_run_id": "run_9", "run_status": "TERMINATED"},
            "pipeline_run_id": "run_9",
            "run_error": _OPERATOR_VIEW_OF_A_STOPPED_RUN,
        }
    )
    # Pipelex's members in shapes no version reads, the nested run's problem included: none of them may stop the report.
    HOSTILE: ClassVar[tuple[str, ...]] = (
        json.dumps({**_OPERATOR_VIEW_OF_A_STOPPED_RUN, "run_error": "not a problem"}),
        json.dumps({**_OPERATOR_VIEW_OF_A_STOPPED_RUN, "run_error": {"code": 5, "diagnostics": []}}),
        json.dumps({**_OPERATOR_VIEW_OF_A_STOPPED_RUN, "request_id": ["x"], "diagnostics": "x", "run_error": []}),
        json.dumps(
            {
                **_OPERATOR_VIEW_OF_A_STOPPED_RUN,
                "request_id": {"id": 1},
                "run_error": {**_OPERATOR_VIEW_OF_A_STOPPED_RUN, "request_id": 9, "diagnostics": "x", "run_error": {"title": 3}},
            }
        ),
    )


#: A refused run whose problem carries, at every level, members neither the standard nor Pipelex declares: those the
#: runner's API-authored errors write (`error_type`, `error_domain`, `retryable`), RFC 9457's `instance`, and others.
_PROBLEM_WITH_UNDECLARED_MEMBERS: dict[str, Any] = {
    "type": "https://mthds.ai/errors/method.invalid",
    "title": "The method does not validate",
    "status": 422,
    "detail": "The method does not validate.",
    "code": "method.invalid",
    "domain": "method",
    "retry": "no",
    "next_step": {"kind": "change_method", "detail": "Fix each fault the problem's errors list, then validate the method again.", "hint": "x"},
    "errors": [
        {
            "code": "model.unknown",
            "detail": "The method names the llm model 'gpt-5.1', which no catalog knows.",
            "params": {"model": "gpt-5.1", "model_type": "llm"},
            "location": {"pipe": "draft_pitch", "field": "model", "source": "main.mthds"},
            "suggestions": ["gpt-5.5"],
            "suggested_fix": {
                "fix_code": "rename-model",
                "description": "Replace model 'gpt-5.1' of pipe 'draft_pitch' with 'gpt-5.5'",
                "safety": "unsafe",
                "ops": [{"kind": "set_key", "table_path": ["pipe", "draft_pitch"], "key": "model", "value": "gpt-5.5"}],
                "error_code": "unknown_model",
            },
            "error_type": "unknown_model",
            "error_category": "pipe_validation",
        }
    ],
    "location": {"pipe": "draft_pitch", "pipe_stack": ["draft_pitch"]},
    "request_id": "01M55PUNDECLARED0000000000",
    "instance": "urn:pipelex:request:01M55PUNDECLARED0000000000",
    "error_type": "PipeValidationError",
    "error_domain": "input",
    "retryable": False,
    "hint": "Fix the method",
    "http_status": 422,
    "validation_errors": [{"category": "pipe_validation", "message": "unknown model"}],
}


class UndeclaredMembers:
    """A runner's problem carrying members no reader declares, and what the agent CLI reports of it: its declared members alone."""

    SENT: ClassVar[str] = json.dumps(_PROBLEM_WITH_UNDECLARED_MEMBERS)
    REPORTED: ClassVar[dict[str, Any]] = {
        "type": "https://mthds.ai/errors/method.invalid",
        "title": "The method does not validate",
        "status": 422,
        "detail": "The method does not validate.",
        "code": "method.invalid",
        "domain": "method",
        "retry": "no",
        "next_step": {"kind": "change_method", "detail": "Fix each fault the problem's errors list, then validate the method again."},
        "location": {"pipe": "draft_pitch"},
        "errors": [
            {
                "code": "model.unknown",
                "detail": "The method names the llm model 'gpt-5.1', which no catalog knows.",
                "params": {"model": "gpt-5.1", "model_type": "llm"},
                "location": {"pipe": "draft_pitch", "field": "model"},
                "suggestions": ["gpt-5.5"],
                "suggested_fix": {
                    "fix_code": "rename-model",
                    "description": "Replace model 'gpt-5.1' of pipe 'draft_pitch' with 'gpt-5.5'",
                    "safety": "unsafe",
                    "ops": [{"kind": "set_key", "table_path": ["pipe", "draft_pitch"], "key": "model", "value": "gpt-5.5"}],
                },
            }
        ],
        "request_id": "01M55PUNDECLARED0000000000",
    }


class HostedPlaneRefusals:
    """Refusals the hosted plane answers in its own shape, which predates the standard's problem document."""

    UNAUTHORIZED: ClassVar[str] = json.dumps(
        {
            "type": "https://pipelex.com/errors/unauthorized",
            "title": "Unauthorized",
            "status": 401,
            "code": "unauthorized",
            "detail": "The API key is not valid.",
            "instance": "urn:pipelex:request:01M55PLEGACY401000000000000",
            "request_id": "01M55PLEGACY401000000000000",
            "error_domain": "config",
            "retryable": False,
        }
    )
    FORBIDDEN: ClassVar[str] = json.dumps(
        {
            "type": "https://pipelex.com/errors/role_not_permitted",
            "title": "Forbidden",
            "status": 403,
            "code": "role_not_permitted",
            "detail": "Your role in this organization does not allow running methods.",
            "request_id": "01M55PLEGACY403000000000000",
            "error_domain": "input",
            "retryable": False,
        }
    )
    # The platform's generic refusal of an operation to a key it authenticated, which is no matter of role.
    FORBIDDEN_OPERATION: ClassVar[str] = json.dumps(
        {
            "type": "https://pipelex.com/errors/forbidden",
            "title": "Forbidden",
            "status": 403,
            "code": "forbidden",
            "detail": "This route is served to a web session only.",
            "error_domain": "config",
            "retryable": False,
        }
    )
    # A 403 whose code is no refusal of an operation but of the credential, as a key that expired.
    FORBIDDEN_EXPIRED_KEY: ClassVar[str] = json.dumps(
        {
            "type": "https://pipelex.com/errors/api_key_expired",
            "title": "Forbidden",
            "status": 403,
            "code": "api_key_expired",
            "detail": "The API key has expired.",
            "error_domain": "config",
            "retryable": False,
        }
    )
    NOT_FOUND: ClassVar[str] = json.dumps(
        {
            "type": "https://pipelex.com/errors/not_found",
            "title": "Not found",
            "status": 404,
            "code": "not_found",
            "detail": "No route serves POST /v1/execute.",
            "error_domain": "config",
            "retryable": False,
        }
    )
    RATE_LIMITED: ClassVar[str] = json.dumps(
        {
            "type": "https://pipelex.com/errors/rate_limited",
            "title": "Too many requests",
            "status": 429,
            "code": "rate_limited",
            "detail": "Too many runs started in the last minute.",
            "request_id": "01M55PLEGACY429000000000000",
            "error_domain": "runtime",
            "retryable": True,
        }
    )
    # A run the platform knows no run by, which names the run it means by its own code.
    RUN_NOT_FOUND: ClassVar[str] = json.dumps(
        {
            "type": "https://pipelex.com/errors/run_not_found",
            "title": "Not found",
            "status": 404,
            "code": "run_not_found",
            "detail": "No run run_9 is visible to this key.",
            "error_domain": "input",
            "retryable": False,
        }
    )
    # A method version the method never published, which names the method by its own code.
    METHOD_VERSION_NOT_FOUND: ClassVar[str] = json.dumps(
        {
            "type": "https://pipelex.com/errors/method_version_not_found",
            "title": "Not found",
            "status": 404,
            "code": "method_version_not_found",
            "detail": "The method mt_7 has no published version 3.",
            "error_domain": "input",
            "retryable": False,
        }
    )
    # A rate limit whose delay rides the body alone, with no `Retry-After` header.
    RATE_LIMITED_BODY_DELAY: ClassVar[str] = json.dumps(
        {
            "type": "https://pipelex.com/errors/rate_limited",
            "title": "Too many requests",
            "status": 429,
            "code": "rate_limited",
            "detail": "Too many runs started in the last minute.",
            "retry_after_seconds": 12,
            "error_domain": "runtime",
            "retryable": True,
        }
    )


class GatewayAnswers:
    """Answers that are no problem document, which a gateway or a hosted plane in front of the runner may give."""

    # A gateway's error page in front of the runner.
    HTML_PAGE: ClassVar[str] = "<html><head><title>502 Bad Gateway</title></head><body><h1>502 Bad Gateway</h1></body></html>"
    # A server that does not serve the route at all, as a framework answers it.
    NOT_FOUND: ClassVar[str] = '{"detail":"Not Found"}'
    # A gateway's refusal of a request its authorizer did not let through.
    FORBIDDEN: ClassVar[str] = '{"message":"Forbidden"}'


class RunnerOwnRefusals:
    """Refusals a runner authors itself rather than raising a Pipelex error for, in the shape that predates the standard's."""

    # The runner's 422 for a run request carrying a reserved object key, as `raise_validation_error` answers it: a
    # reason, but no code, domain, retry verdict or next step the standard's client reads.
    RESERVED_OBJECT_KEY: ClassVar[str] = json.dumps(
        {
            "type": "https://docs.pipelex.com/latest/errors/reserved-object-key/",
            "title": "Reserved object key",
            "status": 422,
            "detail": (
                "Request body contains the reserved object key '__class__'. A run request is plain JSON: no object in it may "
                "carry a '__class__' or '__module__' key, or a key starting with '__kajson'."
            ),
            "instance": "urn:pipelex:request:01M55PRESERVED00000000000",
            "request_id": "01M55PRESERVED00000000000",
            "error_type": "ReservedObjectKey",
            "error_domain": "input",
            "retryable": False,
        }
    )
    # The reason and the advice of a refusal whose advice names a kind of its own.
    NO_CREDIT_REASON: ClassVar[str] = "The account has no inference credit left."
    NO_CREDIT_ADVICE: ClassVar[str] = "Add credit to the account on app.pipelex.com, then run again"
    # A 402 advising the caller to check its billing: a reason and an advice of the kind `check_billing`, but no code,
    # domain, retry verdict or next step the standard's client reads.
    NO_CREDIT: ClassVar[str] = json.dumps(
        {
            "type": "https://docs.pipelex.com/latest/errors/payment-required/",
            "title": "Payment required",
            "status": 402,
            "detail": NO_CREDIT_REASON,
            "error_domain": "config",
            "retryable": False,
            "user_action": {"kind": "check_billing", "detail": NO_CREDIT_ADVICE},
        }
    )


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
    # A report in the former shape for a run whose method did not validate, with the items and the advice it gives.
    FORMER_SHAPE_WITH_ITEMS: ClassVar[dict[str, Any]] = {
        "error_type": "ValidateBundleError",
        "message": "The method does not validate: pipe 'draft' names an unknown model",
        "title": "Validate bundle error",
        "type_uri": "https://docs.pipelex.com/latest/errors/validate-bundle-error/",
        "error_domain": "input",
        "error_category": "configuration",
        "retryable": False,
        "caller_facing_message": True,
        "user_action": {"kind": "change_model", "detail": "Name a model the catalog knows, such as gpt-5.5, then run again"},
        "validation_errors": [
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
                "pipe_type": "PipeLLM",
            }
        ],
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
    # The same problem with the members the hosted plane's stored report carries beside it, which no reader of the
    # problem declares, its own diagnostics in a shape this version does not read.
    PROBLEM_WITH_REPORT_MEMBERS: ClassVar[dict[str, Any]] = {
        **PROBLEM,
        "diagnostics": "unreadable",
        "message": "the branches do not combine",
        "error_type": "PipeOutputMultiplicityError",
        "error_domain": "input",
        "error_category": "validation",
        "retryable": False,
        "caller_facing_message": "The pipe's output has another multiplicity",
        "provider_metadata": {"region": "eu"},
        "validation_errors": [{"category": "pipe_validation", "message": "multiplicity"}],
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
    # An item of a type this version reads, carrying a field neither this version nor the SDK declares.
    SENT_WITH_AN_UNKNOWN_FIELD: ClassVar[dict[str, Any]] = {**SENT[1], "pipe_type": "PipeLLM"}
    # A missing dependency of a newer runner, whose fix carries a member the SDK reads and this version does not.
    SENT_WITH_AN_UNREADABLE_FIX: ClassVar[dict[str, Any]] = {
        "category": "pipe_validation",
        "message": "In-memory resolve cannot load address-based dependency 'github.com/mthds/scoring-lib/scoring'.",
        "error_type": "unresolved_package_dependency",
        "pipe_code": "score_invoice",
        "source": "bundle.mthds",
        "field_path": "pipe.score_invoice.steps[0].pipe",
        "missing_pipe_code": "github.com/mthds/scoring-lib/scoring->scoring.score",
        "suggested_fix": {
            "fix_code": "ship-dependency",
            "description": "Ship the dependency with the method",
            "safety": "unsafe",
            "ops": [{"kind": "set_key", "table_path": ["pipe", "score_invoice"], "key": "note", "value": "shipped"}],
            "preview": "A member a newer runner adds to its fixes",
        },
    }
    # Its problem item: the missing dependency its type and its locators give, without the fix this version cannot read.
    UNREADABLE_FIX_PROBLEM_ITEM: ClassVar[dict[str, Any]] = {
        "code": "method.dependency_missing",
        "detail": "The method depends on the package 'github.com/mthds/scoring-lib/scoring', which is not available here (reason: not_found).",
        "params": {"kind": "package", "name": "github.com/mthds/scoring-lib/scoring", "reason": "not_found"},
        "location": {"pipe": "score_invoice", "field": "pipe.score_invoice.steps[0].pipe", "file": "bundle.mthds"},
    }
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


class RunnerOwnMethodRefusals:
    """A runner's refusal of a run request whose method does not validate, in the shape that predates the standard's."""

    # The reason and the advice the refusal gives.
    REASON: ClassVar[str] = "The method does not validate: pipe 'draft' names an unknown model"
    ADVICE: ClassVar[str] = "Name a model the catalog knows, such as gpt-5.5, then run again"
    # The 422 a runner answers `POST /v1/start` and `POST /v1/execute` with for a method that does not load, as
    # `ValidateBundleError` answers it in the former shape: its reason, its advice and the validation items locating the
    # faults, but no code, domain, retry verdict or next step the standard's client reads.
    INVALID_METHOD: ClassVar[str] = json.dumps(
        {
            "type": "https://docs.pipelex.com/latest/errors/validate-bundle-error/",
            "title": "Validate bundle error",
            "status": 422,
            "detail": REASON,
            "instance": "urn:pipelex:request:01M55PINVALIDMETHOD000000",
            "request_id": "01M55PINVALIDMETHOD000000",
            "error_type": "ValidateBundleError",
            "error_domain": "input",
            "retryable": False,
            "user_action": {"kind": "change_model", "detail": ADVICE},
            "validation_errors": HostedMethodItems.SENT[:2],
        }
    )
