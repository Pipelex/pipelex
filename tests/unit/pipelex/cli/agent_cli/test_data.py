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


class GatewayAnswers:
    """Answers that are no problem document, which a gateway or a hosted plane in front of the runner may give."""

    # A gateway's error page in front of the runner.
    HTML_PAGE: ClassVar[str] = "<html><head><title>502 Bad Gateway</title></head><body><h1>502 Bad Gateway</h1></body></html>"
    # A server that does not serve the route at all, as a framework answers it.
    NOT_FOUND: ClassVar[str] = '{"detail":"Not Found"}'
    # A gateway's refusal of a request its authorizer did not let through.
    FORBIDDEN: ClassVar[str] = '{"message":"Forbidden"}'
    # A gateway's refusal of a request that carried no credential it reads.
    UNAUTHORIZED: ClassVar[str] = '{"message":"Unauthorized"}'
    # A gateway's throttle.
    TOO_MANY_REQUESTS: ClassVar[str] = '{"message":"Too Many Requests"}'


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
    """The run's own problem the hosted API may store for a failed run, which `run.failed` nests as its `run_error`."""

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
    # A run refused at load, its stored problem listing the method's faults as its items, in the operator's view.
    PROBLEM_WITH_ITEMS: ClassVar[dict[str, Any]] = {
        "type": "https://mthds.ai/errors/method.invalid",
        "title": "The method does not validate",
        "detail": "The method does not validate.",
        "code": "method.invalid",
        "domain": "method",
        "retry": "no",
        "next_step": {"kind": "change_method", "detail": "Fix each fault the problem's errors list, then validate the method again."},
        "errors": [
            {
                "code": "model.unknown",
                "detail": "The method names the llm model 'claude-5.5-sonnet', which no catalog knows.",
                "params": {"model": "claude-5.5-sonnet", "model_type": "llm"},
                "location": {"pipe": "draft", "field": "model", "file": "main.mthds"},
            }
        ],
        "diagnostics": {"error_class": "ValidateBundleError", "message": "the bundle does not load"},
    }


class PipeIoItems:
    """The items of a pipe-io verdict for a method that does not load, as sent and as both CLIs report them.

    pipelex-sdk reads each item member by member: a declared member that does not read is left out of its item alone,
    so the item keeps its code, its locators and its other facts, and a member the standard does not declare is kept
    as received, which the CLIs leave out, reporting each item by its declared members.
    """

    SENT: ClassVar[list[dict[str, Any]]] = [
        {
            "code": "model.unknown",
            "detail": "The method names the llm model 'gpt-5.1', which no catalog knows.",
            "params": {"model": "gpt-5.1", "model_type": "llm"},
            "location": {"pipe": "draft", "field": "model", "file": "main.mthds"},
            "suggestions": ["gpt-5.5"],
        },
        {
            "code": "method.concept_unresolved",
            "detail": "Pipe 'summarize' names the concept 'Summary', which no domain defines.",
            "location": {"pipe": "summarize", "field": "output", "file": "lib/summarize.mthds"},
            "suggested_fix": "define the concept",
            "rank": 2,
        },
    ]
    REPORTED: ClassVar[list[dict[str, Any]]] = [
        SENT[0],
        {
            "code": "method.concept_unresolved",
            "detail": "Pipe 'summarize' names the concept 'Summary', which no domain defines.",
            "location": {"pipe": "summarize", "field": "output", "file": "lib/summarize.mthds"},
        },
    ]


class RefusedBundles:
    """Bundles `run bundle` refuses while it reads them, before a run on a runner sends them.

    Each case is its bundle, the codes of the verdict's items in order, and where each item places its fault beside
    the file it names.
    """

    # A table header TOML cannot parse: the verdict's `method.syntax` item, at its line and column.
    PARSE_FAILURE: ClassVar[str] = 'domain = "broken_syntax"\nmain_pipe = "say"\n\n[pipe.say\ntype = "PipeCompose"\n'
    # A native concept redeclared, an input read but not declared, and an input declared but never read.
    VALIDATION_FAILURE: ClassVar[str] = (
        'domain = "probe_invalid"\n'
        'description = "A method with several faults"\n'
        'main_pipe = "summarize"\n'
        "\n"
        "[concept.Rating]\n"
        'description = "A rating of a summary"\n'
        "\n"
        "[pipe.summarize]\n"
        'type = "PipeLLM"\n'
        'description = "Summarize the text"\n'
        'inputs = { text = "Text" }\n'
        'output = "Text"\n'
        'prompt = "Summarize $text in the style of $author."\n'
        "\n"
        "[pipe.rate]\n"
        'type = "PipeLLM"\n'
        'description = "Rate the summary"\n'
        'inputs = { summary = "Text", audience = "Text" }\n'
        'output = "Text"\n'
        'prompt = "Rate this summary from 1 to 10: $summary"\n'
    )
    # A template Jinja2 cannot parse, which the bundle's own validation refuses, so no run ever renders it.
    TEMPLATE_REFUSAL: ClassVar[str] = (
        'domain = "broken_template"\n'
        'description = "A template that does not parse"\n'
        'main_pipe = "say"\n'
        "\n"
        "[pipe.say]\n"
        'type = "PipeCompose"\n'
        'description = "Say something"\n'
        'inputs = { topic = "Text" }\n'
        'output = "Text"\n'
        'template = "Talk about {{ topic[ }}"\n'
    )
    # A bundle that declares no main pipe: named alone, or as a folder's one bundle, it has no pipe to start at, and its
    # one pipe, `say`, is what it could start at.
    NO_MAIN_PIPE: ClassVar[str] = (
        'domain = "probe"\n'
        "\n"
        "[pipe.say]\n"
        'type = "PipeCompose"\n'
        'description = "Say"\n'
        'inputs = { topic = "Text" }\n'
        'output = "Text"\n'
        'template = "About $topic"\n'
    )
    CASES: ClassVar[list[tuple[str, str, list[str], list[dict[str, Any]]]]] = [
        ("parse_failure", PARSE_FAILURE, ["method.syntax"], [{"line": 4, "column": 10}]),
        (
            "validation_failure",
            VALIDATION_FAILURE,
            ["method.name_conflict", "method.input_undeclared", "method.input_unused"],
            [{"field": "concept.Rating"}, {"pipe": "summarize"}, {"pipe": "rate"}],
        ),
        ("template_refusal", TEMPLATE_REFUSAL, ["method.schema_violation"], [{"pipe": "say", "field": "pipe.say"}]),
    ]
    # What only the operator's view of these refusals holds, none of which a caller may read: the diagnostics' members,
    # the classes along the refusal's chain, and the command's sentence quoting the raise site's message.
    OPERATOR_ONLY: ClassVar[tuple[str, ...]] = (
        "diagnostics",
        "error_class",
        "runtime_version",
        "ValidateBundleError",
        "MthdsParserError",
        "MethodEntryError",
        "ValidationError",
        "TomlError",
        "TOMLDecodeError",
        "Jinja2TemplateSyntaxError",
        "Failed to parse bundle",
    )
