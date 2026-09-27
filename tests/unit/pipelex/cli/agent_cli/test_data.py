"""Problem documents an API runner answers a refused run with, for the agent CLI's refusal tests."""

from typing import ClassVar, NamedTuple


class RefusedRunBodies:
    """Problem documents a runner answers when it refuses a request, as they came off the wire.

    The first three are the dev plane's `POST /v1/execute` refusals of the execution-errors acceptance
    methods, captured on 2026-09-27 through `MthdsAPIClient` against `https://api-dev.pipelex.com`
    (pipelex-api v0.29.0 on pipelex 0.67.0) and copied byte for byte from mthds-python's
    `tests/unit/test_data.py`: a bundle the runner refused at load with an itemized diagnostic, a run
    that failed at a pipe's combine step, and a run that failed on a model the deck does not serve.
    The rest are other shapes a runner, or a gateway in front of it, may answer.
    """

    UNKNOWN_MODEL_AT_LOAD: ClassVar[str] = (
        '{"type":"https://docs.pipelex.com/latest/errors/validate-bundle-error/","title":"Validate bundle","status":422,'
        "\"detail\":\"Pipe 'draft_pitch' (PipeLLM), field 'model': Model handle 'gpt-5.1' was not found in the model deck\\n\\n"
        'Did you mean: gpt-5.5, gpt-5.4, gpt-5.6-sol, gpt-5.4-pro, gpt-5.6-luna","instance":"/v1/execute",'
        '"request_id":"req_a3dd6900-7909-48d3-b551-0140e73ac7fc","error_category":"configuration","error_domain":"input",'
        '"retryable":false,"error_type":"ValidateBundleError","validation_errors":[{"category":"pipe_validation",'
        "\"message\":\"Pipe 'draft_pitch' (PipeLLM), field 'model': Model handle 'gpt-5.1' was not found in the model deck\\n\\n"
        'Did you mean: gpt-5.5, gpt-5.4, gpt-5.6-sol, gpt-5.4-pro, gpt-5.6-luna","error_type":"unknown_model",'
        '"pipe_code":"draft_pitch","domain_code":"sales_copy","field_path":"pipe.draft_pitch.model","field_name":"model",'
        '"model_reference":"gpt-5.1","model_type":"llm","suggestions":["gpt-5.5","gpt-5.4","gpt-5.6-sol","gpt-5.4-pro","gpt-5.6-luna"]}],'
        '"user_action":{"kind":"change_input","detail":"Edit the bundle as each validation error says: apply its suggested fix '
        'where it has one, after confirming an unsafe one"}}'
    )
    UNKNOWN_MODEL_DETAIL: ClassVar[str] = (
        "Pipe 'draft_pitch' (PipeLLM), field 'model': Model handle 'gpt-5.1' was not found in the model deck\n\n"
        "Did you mean: gpt-5.5, gpt-5.4, gpt-5.6-sol, gpt-5.4-pro, gpt-5.6-luna"
    )
    UNKNOWN_MODEL_NEXT_STEP: ClassVar[str] = (
        "Edit the bundle as each validation error says: apply its suggested fix where it has one, after confirming an unsafe one"
    )

    COMBINE_FAILURE_AT_RUN: ClassVar[str] = (
        '{"type":"https://docs.pipelex.com/latest/errors/stuff-factory-error/","title":"Stuff factory","status":422,'
        "\"detail\":\"Pipe 'analyze_topics' failed (review_topics → analyze_topics): PipeParallel 'analyze_topics' cannot "
        "combine its branch results into its output 'TopicReview'. Branch 'draft_ideas' gives result 'ideas' as a list, "
        "'Idea[]', but field 'ideas' of 'TopicReview' holds a single item. Declare the field as a list in the structure of "
        "'TopicReview', with type 'list', item_type 'concept' and item_concept_ref 'Idea', or make branch 'draft_ideas' output "
        'a single \'Idea\'.","instance":"/v1/execute","request_id":"req_d4212542-63a6-4ddb-87c9-4b968785c8c5",'
        '"error_domain":"input","error_type":"StuffFactoryError","user_action":{"kind":"change_input","detail":"Branch '
        "'draft_ideas' gives result 'ideas' as a list, 'Idea[]', but field 'ideas' of 'TopicReview' holds a single item. "
        "Declare the field as a list in the structure of 'TopicReview', with type 'list', item_type 'concept' and "
        "item_concept_ref 'Idea', or make branch 'draft_ideas' output a single 'Idea'.\"}}"
    )
    COMBINE_FAILURE_NEXT_STEP: ClassVar[str] = (
        "Branch 'draft_ideas' gives result 'ideas' as a list, 'Idea[]', but field 'ideas' of 'TopicReview' holds a single item. "
        "Declare the field as a list in the structure of 'TopicReview', with type 'list', item_type 'concept' and "
        "item_concept_ref 'Idea', or make branch 'draft_ideas' output a single 'Idea'."
    )

    UNSERVED_MODEL_AT_RUN: ClassVar[str] = (
        '{"type":"https://docs.pipelex.com/latest/errors/model-not-found-error/","title":"Model not found","status":422,'
        "\"detail\":\"Pipe 'condense_article' failed (digest_article → condense_article): Model handle 'gpt-5.1' was not "
        'found in the model deck.","instance":"/v1/execute","request_id":"req_b7d2c66f-b2d5-4dc7-bd4f-6cf98abfbdc0",'
        '"error_category":"configuration","error_domain":"input","retryable":false,"error_type":"ModelNotFoundError",'
        '"user_action":{"kind":"change_model","detail":"Change the model \'gpt-5.1\' to an LLM the model deck serves."}}'
    )
    UNSERVED_MODEL_DETAIL: ClassVar[str] = (
        "Pipe 'condense_article' failed (digest_article → condense_article): Model handle 'gpt-5.1' was not found in the model deck."
    )
    UNSERVED_MODEL_NEXT_STEP: ClassVar[str] = "Change the model 'gpt-5.1' to an LLM the model deck serves."

    # The hosted plane's own refusals, authored in front of the runner with no `user_action`, `error_domain` or
    # `retryable`: the platform's rate limiter (sent with a `Retry-After` header), the API gateway's refusal of a
    # key (a bare `message`, no problem members at all), and the platform failing to reach the runner.
    PLATFORM_RATE_LIMITED: ClassVar[str] = (
        '{"type":"https://pipelex.com/errors/rate_limited","title":"Too Many Requests","status":429,"code":"rate_limited",'
        '"detail":"Rate limit of 600 requests/minute exceeded for this organization. Retry in 12s.",'
        '"instance":"urn:request:req_rate","request_id":"req_rate","errors":[]}'
    )
    GATEWAY_FORBIDDEN: ClassVar[str] = '{"message":"Forbidden"}'
    PLATFORM_RUNNER_UNREACHABLE: ClassVar[str] = (
        '{"type":"https://pipelex.com/errors/service_unavailable","title":"Service Unavailable","status":503,'
        '"code":"service_unavailable","detail":"The runner is unreachable (/execute). Retry shortly.","request_id":"req_down","errors":[]}'
    )
    # Not a problem document: a gateway's error page in front of the runner.
    GATEWAY_HTML: ClassVar[str] = "<html><head><title>502 Bad Gateway</title></head><body><h1>502 Bad Gateway</h1></body></html>"
    # A refusal carrying the failing pipe and its path as members, and an item of a kind this pipelex does not know.
    LOCATED_WITH_UNKNOWN_ITEM: ClassVar[str] = (
        '{"type":"https://docs.pipelex.com/latest/errors/stuff-factory-error/","title":"Stuff factory","status":422,'
        '"detail":"Pipe \'analyze_topics\' failed (review_topics → analyze_topics): the branches do not combine.",'
        '"request_id":"req_future","error_domain":"input","retryable":true,"error_type":"StuffFactoryError",'
        '"pipe_code":"analyze_topics","pipe_stack":["review_topics","analyze_topics"],'
        '"validation_errors":[{"category":"pipe_validation","message":"A kind of fault from a newer runner",'
        '"error_type":"some_future_fault","pipe_code":"analyze_topics"}]}'
    )


class RefusalCase(NamedTuple):
    """One of the dev plane's refused runs, and what the agent must read in its envelope."""

    topic: str
    body: str
    error_type: str
    reason: str
    next_step: str
    failing_pipe: str


class RefusalCases:
    """The dev plane's three refused runs of the execution-errors acceptance, as the agent CLI must report them."""

    DEV_PLANE: ClassVar[list[RefusalCase]] = [
        RefusalCase(
            topic="unknown_model_at_load",
            body=RefusedRunBodies.UNKNOWN_MODEL_AT_LOAD,
            error_type="ValidateBundleError",
            reason=RefusedRunBodies.UNKNOWN_MODEL_DETAIL,
            next_step=RefusedRunBodies.UNKNOWN_MODEL_NEXT_STEP,
            failing_pipe="draft_pitch",
        ),
        RefusalCase(
            topic="combine_failure_at_run",
            body=RefusedRunBodies.COMBINE_FAILURE_AT_RUN,
            error_type="StuffFactoryError",
            reason=(
                "Pipe 'analyze_topics' failed (review_topics → analyze_topics): PipeParallel 'analyze_topics' cannot combine its branch "
                f"results into its output 'TopicReview'. {RefusedRunBodies.COMBINE_FAILURE_NEXT_STEP}"
            ),
            next_step=RefusedRunBodies.COMBINE_FAILURE_NEXT_STEP,
            failing_pipe="analyze_topics",
        ),
        RefusalCase(
            topic="unserved_model_at_run",
            body=RefusedRunBodies.UNSERVED_MODEL_AT_RUN,
            error_type="ModelNotFoundError",
            reason=RefusedRunBodies.UNSERVED_MODEL_DETAIL,
            next_step=RefusedRunBodies.UNSERVED_MODEL_NEXT_STEP,
            failing_pipe="condense_article",
        ),
    ]
