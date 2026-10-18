"""Test data for the server's problem documents: the failures they are built from and the identities that pick their view."""

from typing import Any, ClassVar

from mthds.protocol.problem.registry import CoreCode
from pipelex.cogt.exceptions import InferenceErrorCategory, LLMCompletionError
from pipelex.cogt.inference.error_classification import ProviderErrorMetadata
from pipelex.cogt.inference.provider_name import ProviderName
from pipelex.errors.error_codes import ErrorCode
from pipelex.errors.registry.pipelex_codes import PipelexErrorCode


class ProblemTestData:
    """A provider's rate limit, the failure whose problem carries the most members, and the synthetic credentials of each identity."""

    RATE_LIMIT_MESSAGE = "OpenAI returned 429 (rate_limit_exceeded)"
    RATE_LIMIT_MODEL = "gpt-4o-mini"
    RATE_LIMIT_BACKEND = "openai"
    RATE_LIMIT_PROVIDER_REQUEST_ID = "req_provider_abc"
    RATE_LIMIT_RETRY_AFTER_SECONDS = 12.0
    RATE_LIMIT_DETAIL = "The provider 'openai' is rate limiting this deployment's calls to the model 'gpt-4o-mini'."

    # Synthetic credentials, valid only against the environment a test patches in.
    SYNTHETIC_API_KEY = "test-api-key-problem-views-only"
    SYNTHETIC_JWT_SECRET = "test-jwt-secret-problem-views-only"
    SYNTHETIC_CALLBACK_SECRET = "test-callback-secret-problem-views-only"
    FORWARDED_USER_ID = "22222222-2222-4222-2222-222222222222"
    JWT_USER_ID = "33333333-3333-4333-3333-333333333333"
    CALLBACK_URL = "https://example.com/done"

    # A problem whose code no registry of this server holds, as a newer worker or a stored record carries it, built in
    # the operator's view: its step and its diagnostics name a file of the host that a caller must never read.
    PRIVATE_HOST_FILE = "/srv/pipelex/private/settings.toml"
    UNKNOWN_OPERATOR_PROBLEM: ClassVar[dict[str, Any]] = {
        "type": "https://docs.pipelex.com/errors/pipelex.config.future_setting_missing",
        "title": "A setting the runtime needs is missing",
        "detail": "A setting the runtime needs is missing.",
        "code": "pipelex.config.future_setting_missing",
        "domain": "operator",
        "retry": "no",
        "next_step": {"kind": "fix_configuration", "detail": "Set the setting in '/srv/pipelex/private/settings.toml', then restart the runtime."},
        "diagnostics": {"error_class": "FutureSettingError", "message": "no setting in /srv/pipelex/private/settings.toml"},
    }

    # Each code with the status its registry entry declares, which the response must carry.
    CODE_STATUSES: ClassVar[list[tuple[ErrorCode, int]]] = [
        (CoreCode.METHOD_SYNTAX, 422),
        (CoreCode.METHOD_NOT_FOUND, 404),
        (CoreCode.RUN_FAILED, 409),
        (PipelexErrorCode.RUN_ALREADY_EXISTS, 409),
        (CoreCode.PROVIDER_RATE_LIMITED, 429),
        (PipelexErrorCode.CONFIG_INVALID, 500),
        (CoreCode.RUNTIME_UNSUPPORTED, 501),
        (CoreCode.PROVIDER_UNAVAILABLE, 502),
        (CoreCode.RUNTIME_UNAVAILABLE, 503),
        (PipelexErrorCode.DEPLOYMENT_PYTHON_STRUCTURES_REFUSED, 422),
    ]

    # A retry delay by case: (code, the delay the error knows, the status, the `Retry-After` header, the body's `retry_after`).
    RETRY_CASES: ClassVar[dict[str, tuple[ErrorCode, float | None, int, str | None, float | None]]] = {
        "finite": (CoreCode.PROVIDER_RATE_LIMITED, 12.4, 429, "13", 12.4),
        "whole": (CoreCode.PROVIDER_RATE_LIMITED, 12.0, 429, "12", 12.0),
        "infinite": (CoreCode.PROVIDER_RATE_LIMITED, float("inf"), 429, None, None),
        "nan": (CoreCode.PROVIDER_RATE_LIMITED, float("nan"), 429, None, None),
        "negative": (CoreCode.PROVIDER_RATE_LIMITED, -5.0, 429, None, None),
        "absent": (CoreCode.PROVIDER_RATE_LIMITED, None, 429, None, None),
        "non_429": (CoreCode.PROVIDER_UNAVAILABLE, 30.0, 502, None, 30.0),
    }


def rate_limited_failure() -> LLMCompletionError:
    """A provider's 429 as the inference layer raises it, attributed to the backend and the model it addressed."""
    failure = LLMCompletionError(
        ProblemTestData.RATE_LIMIT_MESSAGE,
        error_category=InferenceErrorCategory.TRANSIENT,
        provider_metadata=ProviderErrorMetadata(
            provider=ProviderName.OPENAI,
            sdk_exception_type="RateLimitError",
            status_code=429,
            retry_after_seconds=ProblemTestData.RATE_LIMIT_RETRY_AFTER_SECONDS,
            request_id=ProblemTestData.RATE_LIMIT_PROVIDER_REQUEST_ID,
        ),
    ).with_error_code(CoreCode.PROVIDER_RATE_LIMITED)
    failure.fill_model_and_provider(ProblemTestData.RATE_LIMIT_MODEL, backend_name=ProblemTestData.RATE_LIMIT_BACKEND)
    return failure


class RequiredParamsTestData:
    """The methods and trees whose refusals the acceptance of the error contract found without a required parameter."""

    BUNDLE_PATH = "bundle.mthds"

    # A model the vendored inference tree catalogs in `anthropic.toml`, whose backend `backends.toml` disables.
    UNSERVED_MODEL = "claude-4.5-haiku"
    UNSERVED_MODEL_MTHDS = f"""\
domain = "smoke"
main_pipe = "echo"

[pipe.echo]
type = "PipeLLM"
description = "Echo"
inputs = {{ text = "Text" }}
output = "Text"
model = "{UNSERVED_MODEL}"
prompt = "@text"
"""

    # A model reference one letter away from a handle the deck serves, so the refusal has a suggestion to offer.
    NEAR_MODEL = "gpt-4o-mimi"
    NEAR_MODEL_SUGGESTION = "gpt-4o-mini"
    NEAR_MODEL_MTHDS = f"""\
domain = "smoke"
main_pipe = "echo"

[pipe.echo]
type = "PipeLLM"
description = "Echo"
inputs = {{ text = "Text" }}
output = "Text"
model = "{NEAR_MODEL}"
prompt = "@text"
"""

    ECHO_MTHDS = """\
domain = "smoke"
main_pipe = "echo"

[pipe.echo]
type = "PipeLLM"
description = "Echo"
inputs = { text = "Text" }
output = "Text"
prompt = "@text"
"""

    UNKNOWN_CONCEPT_MTHDS = """\
domain = "smoke"
main_pipe = "make_thing"

[concept.Thing]
description = "A thing"

[pipe.make_thing]
type = "PipeLLM"
description = "Make a thing"
inputs = { text = "Text" }
output = "Thingg"
prompt = "@text"
"""

    TEMPLATE_REFUSED_MTHDS = """\
domain = "smoke"
main_pipe = "say"

[pipe.say]
type = "PipeCompose"
description = "Say"
inputs = { text = "Text" }
output = "Text"
template = "Talk about {{ text['_owner'] }}"
"""

    NATIVE_REDECLARATION_MTHDS = """\
domain = "smoke"
main_pipe = "echo"

[concept.Rating]
description = "A rating, declared again"

[pipe.echo]
type = "PipeLLM"
description = "Echo"
inputs = { text = "Text" }
output = "Text"
prompt = "@text"
"""

    DUPLICATE_BUNDLES: ClassVar[dict[str, str]] = {
        "first/declares.mthds": 'domain = "dup"\n\n[concept]\nDoc = "A document, as the first bundle declares it"\n',
        "second/declares.mthds": 'domain = "dup"\n\n[concept]\nDoc = "A document, as the second bundle declares it"\n',
    }
    # The same collision in a method a run can start: the first bundle names its main pipe.
    DUPLICATE_RUNNABLE_BUNDLES: ClassVar[dict[str, str]] = {
        "first/declares.mthds": (
            'domain = "dup"\nmain_pipe = "echo"\n\n[concept]\nDoc = "A document, as the first bundle declares it"\n\n'
            '[pipe.echo]\ntype = "PipeCompose"\ndescription = "Echo"\ninputs = { text = "Text" }\noutput = "Text"\ntemplate = "{{ text }}"\n'
        ),
        "second/declares.mthds": 'domain = "dup"\n\n[concept]\nDoc = "A document, as the second bundle declares it"\n',
    }

    DEPENDENCY_REPOSITORY_ADDRESS = "github.com/invented/probe-lib"
    DEPENDENCY_ADDRESS = f"{DEPENDENCY_REPOSITORY_ADDRESS}/probe"
    DEPENDENCY_TREE: ClassVar[dict[str, str]] = {
        "METHODS.toml": (
            "[package]\n"
            'name = "probe"\n'
            f'address = "{DEPENDENCY_REPOSITORY_ADDRESS}"\n'
            'version = "0.1.0"\n'
            'description = "An invented package a request ships beside its method"\n'
        ),
        "probe.mthds": (
            'domain = "probe_dep"\n\n[pipe.entry]\ntype = "PipeLLM"\ndescription = "Entry"\ninputs = { text = "Text" }\n'
            'output = "Text"\nprompt = "@text"\n'
        ),
    }
    CALLER_MTHDS = f"""\
domain = "caller"
main_pipe = "call_probe"

[pipe.call_probe]
type = "PipeSequence"
description = "Call the probe"
inputs = {{ text = "Text" }}
output = "Text"
steps = [{{ pipe = "{DEPENDENCY_ADDRESS}->probe_dep.entry", result = "out" }}]
"""
