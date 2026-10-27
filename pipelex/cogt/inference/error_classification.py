"""Helpers for classifying SDK errors into InferenceErrorCategory values.

Pure functions that inspect error statuses and codes to discriminate a spent
quota from a rate limit, inspect messages to detect content policy violations,
and recover the underlying SDK exception that ``InstructorRetryException``
wraps when ``instructor`` exhausts its retry loop.
"""

import json
import math
import re
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from enum import StrEnum
from http import HTTPStatus
from typing import Any, TypeAlias, cast

import httpx
from pydantic import BaseModel, Field, ValidationError

from pipelex.cogt.inference.provider_name import ProviderName
from pipelex.tools.typing.pydantic_utils import ValidatedType, describe_exception_without_input

# SDK exception class-name substrings that identify a network/transport failure
# (no HTTP status reached us). Matched case-insensitively against
# ``sdk_exception_type`` — covers httpx transport errors, SDK timeout/connection
# errors, Mistral's ``NoResponseError``, and builtin ``TimeoutError``.
_NETWORK_ERROR_TOKENS: tuple[str, ...] = ("timeout", "connect", "transport", "noresponse")

# ``httpx.TransportError`` subclass names whose class names contain none of the
# ``_NETWORK_ERROR_TOKENS`` and therefore would otherwise fall through to
# UNKNOWN. These can reach a provider's extract_* helper directly (Azure REST
# uses raw httpx; OpenAI / Anthropic / Gateway SDKs may also surface them when
# their connection wrappers are bypassed) without going through the
# ``_resolve_sdk_exception_type`` normalization, so we recognize them by name
# here to keep transport failures classified as TRANSIENT.
_STATUSLESS_TRANSPORT_TYPE_NAMES: frozenset[str] = frozenset(
    {
        "TransportError",
        "ReadError",
        "WriteError",
        "CloseError",
        "RemoteProtocolError",
        "ProxyError",
        "UnsupportedProtocol",
        "NetworkError",
    }
)


class ProviderLimitVerdict(StrEnum):
    """What a provider's refusal says about its limits: a spent quota, a rate limit, or neither.

    A spent quota is cured by a person adding credit or raising a quota; a rate limit by time. ``NEITHER`` leaves the
    refusal to the rest of the classifier.
    """

    QUOTA_EXHAUSTED = "quota_exhausted"
    RATE_LIMITED = "rate_limited"
    NEITHER = "neither"


# The one error code outside any service's own namespace that the runtime classifies itself:
# Portkey's refusal of a model an integration serves but does not allow for this caller, because the
# model is off the integration's allow-list or archived. Portkey's cloud emits it for a caller's own
# workspace behind the ``portkey`` backend, and so does any gateway built on Portkey's middleware. The
# refusal means the same thing and calls for the same move whichever of them raised it, so it is
# classified here rather than contributed by one service's plugin. Both raise sites answer 412, so
# checking the status too would add nothing. It arrives with the code in ``type`` and ``code`` null,
# and every Extract hop recovers it from there: the vendor-facing hops read ``type`` first, and the
# code-first hops fall back to it.
MODEL_NOT_ALLOWED_ERROR_CODE = "model_not_allowed_error"

# The codes the runtime classifies itself, which no plugin may contribute to the service error
# vocabulary (see ``PluginRegistrar.add_service_error_codes``).
RUNTIME_CLASSIFIED_ERROR_CODES: frozenset[str] = frozenset({MODEL_NOT_ALLOWED_ERROR_CODE})


def _resolve_sdk_exception_type(exc: BaseException, *, status_code: int | None) -> str:
    """Return the ``sdk_exception_type`` name, normalizing status-less httpx transport errors.

    Some ``httpx.TransportError`` subclasses (``ReadError``, ``WriteError``,
    ``CloseError``, ``RemoteProtocolError``, ``ProxyError``, ``UnsupportedProtocol``,
    ``NetworkError``) have names that contain none of the recognized
    ``_NETWORK_ERROR_TOKENS``, so without normalization the classifier would treat
    them as ``UNKNOWN`` instead of transient transport failures. We surface them
    as ``"TransportError"`` only when the original name lacks a recognized token —
    ``ConnectError`` / ``ReadTimeout`` / ``ConnectTimeout`` etc. already match
    and stay unchanged so their semantic stays in the metadata.
    """
    raw = type(exc).__name__
    if status_code is None and isinstance(exc, httpx.TransportError):
        if not any(token in raw.lower() for token in _NETWORK_ERROR_TOKENS):
            return "TransportError"
    return raw


class ProviderErrorMetadata(BaseModel):
    """Structured SDK metadata attached to inference errors.

    Carries information downstream consumers (retry, temporal, CLI) need
    without having to scrape it back from the exception chain.
    """

    provider: ProviderName
    sdk_exception_type: str
    # Human-readable error text from the SDK exception (``str(exc)``). Both the
    # Classify step (quota / content-policy discrimination) and the Render step
    # (message composition) read it, so the Extract step must capture it. A
    # pydantic ``ValidationError``, which ends instructor's re-asks, is written by
    # its locations and reasons alone: its own text quotes the model's answer. Any
    # other failure to parse that answer, such as instructor's assertion carrying a
    # model's refusal, is written by its class alone.
    message: str = ""
    status_code: int | None = None
    request_id: str | None = None
    retry_after_seconds: float | None = None
    provider_error_code: str | None = None
    # Raw provider response body — can carry account ids, billing details, or
    # credential fragments, so it is excluded from serialization (CLI JSON,
    # agent output, Temporal error details) while staying available in-process.
    body: Any | None = Field(default=None, exclude=True)

    @property
    def limit_verdict(self) -> ProviderLimitVerdict:
        """Whether the provider refused the call for a spent quota, for a rate limit, or for neither.

        A spent quota and a rate limit both refuse the call, often on the same status, and differ only in what cures
        them: time cures a rate limit, and only a person cures a spent quota. Each provider signals a spent quota in its
        own structure, so the rule dispatches on ``provider`` and reads the provider's status and its error code, type
        or details, never the words of its message, with one exception: Anthropic, whose credit-balance and self-set
        spend limit refusals carry nothing but their sentence on a 400 (see ``_is_quota_exhaustion_anthropic``).

        A throttle a provider documents on another status than 429 is a rate limit first (see
        ``is_throttle_on_another_status``). Then a spent quota, by the provider's rule. Then every other 429, whatever
        its message says: when the structure says nothing either way, a quota read as a rate limit costs some refused
        calls and some waiting, while a rate limit read as a quota fails the run and sends a person to add credit that
        cannot help. The providers whose rule never reports a spent quota reach one through the classifier's status
        ladder alone, which reads every 402 as one, or, for Linkup, through its typed exception. Each verdict is
        computed once here; the classifier reads this property once.
        """
        if self.is_throttle_on_another_status:
            return ProviderLimitVerdict.RATE_LIMITED
        if self._reads_as_spent_quota():
            return ProviderLimitVerdict.QUOTA_EXHAUSTED
        if self.status_code == 429:
            return ProviderLimitVerdict.RATE_LIMITED
        return ProviderLimitVerdict.NEITHER

    @property
    def is_quota_exhaustion(self) -> bool:
        """Whether the provider said, in its status or its structured error, that a quota or a credit is spent."""
        return self.limit_verdict is ProviderLimitVerdict.QUOTA_EXHAUSTED

    @property
    def is_rate_limit(self) -> bool:
        """Whether the provider refused the call for a limit that time cures, which the classifier reads as a rate limit."""
        return self.limit_verdict is ProviderLimitVerdict.RATE_LIMITED

    def _reads_as_spent_quota(self) -> bool:
        """Apply the provider's own spent-quota rule, once ``is_throttle_on_another_status`` has set its throttles aside."""
        status_code = self.status_code or 0
        match self.provider:
            case ProviderName.OPENAI:
                # The Extract step keeps the type before the code, so the rule reads both: the type when there is one,
                # and the body's code when there is one.
                return _is_quota_exhaustion_by_code(
                    status_code=status_code, error_codes=(self.provider_error_code, error_code_from_body_code_first(self.body))
                )
            case ProviderName.GATEWAY:
                # A gateway relays every provider's prose, so its message decides nothing; its Extract step already
                # reads the body's code before its type.
                return _is_quota_exhaustion_by_code(status_code=status_code, error_codes=(self.provider_error_code,))
            case ProviderName.ANTHROPIC:
                return _is_quota_exhaustion_anthropic(status_code=status_code, error_type=self.provider_error_code, body=self.body)
            case ProviderName.GOOGLE:
                return _is_quota_exhaustion_google(status_code=status_code, body=self.body)
            case ProviderName.MISTRAL:
                # Mistral answers a spent balance with a 402 and every rate limit with a 429, a monthly cap that a
                # person may have to raise included, so the status alone decides.
                return status_code == 402
            case (
                ProviderName.BEDROCK
                | ProviderName.AZURE
                | ProviderName.FAL
                | ProviderName.HUGGINGFACE
                | ProviderName.LINKUP
                | ProviderName.TYPESAFE
                | ProviderName.DOCLING
                | ProviderName.PYPDFIUM2
            ):
                # Bedrock is billed to the AWS account, with no balance to spend, and every error AWS calls a quota is a
                # rate quota: `ThrottlingException` on a 429, and `ServiceQuotaExceededException`, which AWS says can
                # be resubmitted later and which `is_throttle_on_another_status` reads.
                return False

    @property
    def is_throttle_on_another_status(self) -> bool:
        """Whether the provider documents this refusal, on a status other than 429, as a throttle that a wait cures.

        OpenRouter, an OpenAI-dialect backend, answers a request its in-flight spending budget cannot hold yet with a
        402 whose ``error.metadata.limit_source`` is ``openrouter_in_flight_budget``, and documents it as a wait for
        its ``Retry-After``: the structure decides, and the header, when it came and was readable, is the wait. Groq,
        another OpenAI-dialect backend, answers a request its flex tier has no capacity for with its own status, 498,
        and documents retrying it with backoff. Bedrock answers ``ServiceQuotaExceededException`` on a 400, and AWS
        documents it as a request over the account's service quota that "you can resubmit later"; Claude on Bedrock,
        called through the Anthropic SDK, carries the same code, read from Bedrock's ``x-amzn-errortype`` header by
        ``extract_anthropic_metadata``.
        """
        match self.provider:
            case ProviderName.OPENAI:
                return self.status_code == _GROQ_FLEX_CAPACITY_STATUS_CODE or _is_in_flight_budget_throttle_openrouter(
                    status_code=self.status_code, body=self.body
                )
            case ProviderName.BEDROCK | ProviderName.ANTHROPIC:
                return self.provider_error_code == _AWS_SERVICE_QUOTA_EXCEEDED_ERROR_CODE
            case (
                ProviderName.GOOGLE
                | ProviderName.MISTRAL
                | ProviderName.GATEWAY
                | ProviderName.AZURE
                | ProviderName.FAL
                | ProviderName.HUGGINGFACE
                | ProviderName.LINKUP
                | ProviderName.TYPESAFE
                | ProviderName.DOCLING
                | ProviderName.PYPDFIUM2
            ):
                return False

    @property
    def is_model_not_allowed(self) -> bool:
        """Whether an integration serves the model but does not allow it for this caller.

        Reads ``provider_error_code`` (see ``MODEL_NOT_ALLOWED_ERROR_CODE``). Without this the
        refusal takes the status ladder's generic 4xx arm, whose domain is right but whose action
        sends the caller to edit their inputs.
        """
        return self.provider_error_code == MODEL_NOT_ALLOWED_ERROR_CODE

    @property
    def is_content_policy_violation(self) -> bool:
        """Whether the error indicates a content policy / safety filter violation.

        Checks the structured ``provider_error_code`` (e.g. FAL surfaces
        ``ContentPolicyViolation`` here without echoing it into the message),
        the rendered ``message``, and the in-process ``body`` payload. ``body``
        is scanned because Azure REST returns the safety phrasing only in the
        response body — never in the ``HTTPStatusError`` message — and ``body``
        is ``exclude=True`` on serialization so the scan stays in-process.
        """
        if self.provider_error_code and "contentpolicy" in self.provider_error_code.lower():
            return True
        if _is_content_policy_violation(self.message):
            return True
        return self.body is not None and _is_content_policy_violation(_stringify_for_scan(self.body))

    @property
    def is_context_window_exceeded(self) -> bool:
        """Whether the provider refused the request because its inputs are over what the model can read.

        For a language model, that is its context window, which holds the prompt and the output the request reserves
        with ``max_tokens`` together, so a refusal the ``max_tokens`` sent caused reads the same. Reads the structured
        error code first, ``provider_error_code`` and the code an error body carries
        (OpenAI puts ``context_length_exceeded`` in ``code`` beside a generic ``type``, which the Extract step
        prefers), then the wording each provider gives such a refusal, in its rendered message or in the in-process
        ``body``, as the content-policy check reads them: a raw ``httpx`` error, such as Azure REST's, renders only
        its status and URL, and keeps the provider's words in the body alone. The classifier reads it on a 400 and on
        any other 4xx, which a gateway may answer such a refusal with, and the Render step words its next step from
        the code the classifier picks, so a phrase in a 5xx, or quoted in a failure that reached no status, says
        nothing.
        """
        if self.provider_error_code in _CONTEXT_WINDOW_ERROR_CODES:
            return True
        if error_code_from_body_code_first(self.body) in _CONTEXT_WINDOW_ERROR_CODES:
            return True
        if _names_the_context_window(text=self.message):
            return True
        return self.body is not None and _names_the_context_window(text=_stringify_for_scan(self.body))

    @property
    def is_network_error(self) -> bool:
        """Whether this is a network/transport failure that never reached an HTTP status."""
        if self.status_code is not None:
            return False
        if self.sdk_exception_type in _STATUSLESS_TRANSPORT_TYPE_NAMES:
            return True
        lowered = self.sdk_exception_type.lower()
        return any(token in lowered for token in _NETWORK_ERROR_TOKENS)


# Readable alias for the Classify / Render pipeline: the metadata model is the
# structured envelope those steps consume.
SDKErrorEnvelope: TypeAlias = ProviderErrorMetadata


class UserActionKind(StrEnum):
    """Discrete categories of advice we surface to the user/agent.

    Lets the CLI render consistent guidance and agent JSON stay typed across
    providers. The free-form ``detail`` string carries provider-specific text.
    """

    WAIT_AND_RETRY = "wait_and_retry"
    CHECK_BILLING = "check_billing"
    CHECK_CREDENTIALS = "check_credentials"
    CHANGE_INPUT = "change_input"
    CHANGE_MODEL = "change_model"
    CONTACT_SUPPORT = "contact_support"
    UNKNOWN = "unknown"


class UserAction(BaseModel):
    """Structured user-facing advice attached to an inference error.

    ``kind`` discriminates the type of action, ``detail`` is the free-form
    provider-specific advice (e.g. a billing URL, a retry hint).
    """

    kind: UserActionKind
    detail: str


_CONTENT_POLICY_PATTERNS: tuple[str, ...] = (
    "content_policy",
    "content_filter",
    "safety system",
    "safety filter",
    "blocked by safety",
)

# The error code a provider gives a refusal of a prompt over the model's context window: OpenAI's, which Azure OpenAI
# and the OpenAI-compatible gateways relay.
_CONTEXT_WINDOW_ERROR_CODES: frozenset[str] = frozenset({"context_length_exceeded"})

# How each provider words that refusal in the message its SDK renders, every one a 400. Each phrase names the
# context window or the prompt's length, so a 400 about a malformed request matches none of them. A language model's
# window also holds the output the request reserves with `max_tokens`, so two of them also match a 400 the
# `max_tokens` sent caused, which the deck's default may be: Anthropic's "exceed context limit" and OpenAI's "maximum
# context length", which counts the completion beside the messages. The Render step's advice for the language-model
# family therefore names both the input and `max_tokens`.
_CONTEXT_WINDOW_PATTERNS: tuple[str, ...] = (
    # OpenAI's code, which its SDK renders into the message with the error body
    "context_length_exceeded",
    # OpenAI's earlier wording, also Mistral's and that of OpenAI-compatible servers such as vLLM, for the messages
    # alone or for the messages and the completion together
    "maximum context length",
    # OpenAI's current wording
    "exceeds the context window",
    # Anthropic's, directly or through Bedrock
    "prompt is too long",
    # Anthropic's when the prompt and the max_tokens requested together pass the window
    "exceed context limit",
    # Bedrock's ValidationException, in full: a 400 about one field's length, such as a tool description's, may say
    # "input is too long" of that field alone
    "input is too long for requested model",
    # Bedrock's ValidationException for the models that word it themselves. Bedrock has no structured signal for an
    # input over the window, only the model's sentence: Amazon Nova's "Input Tokens Exceeded: Number of input tokens
    # exceeds maximum length." and Amazon Titan's "Too many input tokens", each matched the same way by langchain-aws's
    # `_CONTEXT_OVERFLOW_MARKERS` (libs/aws/langchain_aws/chat_models/bedrock_converse.py). The bare "too many tokens" is
    # left out on purpose: it is also Bedrock's throttle, "Too many tokens per day". The models Bedrock serves through its
    # OpenAI-compatible engine word it with numbers inside, so `_PROMPT_TOKENS_OVER_MODEL_MAXIMUM` reads theirs.
    "input tokens exceeded",
    "too many input tokens",
    # Gemini's INVALID_ARGUMENT
    "exceeds the maximum number of tokens allowed",
)

# The models Bedrock serves through its OpenAI-compatible engine, such as Kimi, refuse an input over their window with
# "prompt tokens (N) exceed model maximum (M)", the sentence LiteLLM reads for them
# (litellm/litellm_core_utils/exception_mapping_utils.py, `_BEDROCK_MANTLE_CONTEXT_WINDOW_PATTERN`). It is read whole,
# with its subject: "exceed model maximum" alone is also how a parameter over its bound is refused, as in
# "max_tokens (200000) exceed model maximum (8192)", which is the request's fault, not the input's length.
_PROMPT_TOKENS_OVER_MODEL_MAXIMUM = re.compile(r"prompt tokens \(\d+\) exceed model maximum")

# The error codes that make a 429 a spent quota rather than a rate limit, on the OpenAI dialect and through a gateway
# alike, each one OpenAI's error-code guide documents for a billing refusal
# (https://developers.openai.com/api/docs/guides/error-codes), which Azure OpenAI and the OpenAI-compatible providers
# relay in the same fields. OpenAI names each billing cause in `error.code` and says `error.type` can still be
# `insufficient_quota`, so the rule reads both. Every other 429, the rate limits and OpenAI's `slow_down` included, is a
# rate limit, whatever its message says: "You exceeded your current quota" is also Gemini's wording for its per-minute
# throttle, which an OpenAI-dialect backend pointed at Google relays, and Azure's throttle links to its quota-increase
# page. A code joins this set only when the provider that sends it documents it as a spent quota on a 429, with a
# comment naming that provider and a test case. A 402 needs no entry, since its status decides it, and a gateway's own
# codes are read from the service error vocabulary before this rule runs.
_QUOTA_ERROR_CODES: frozenset[str] = frozenset(
    {
        # the broad code and type, and the long-standing code of a spent quota
        "insufficient_quota",
        # no prepaid credits remaining
        "credit_balance_exhausted",
        # the organization's enforced spend limit
        "organization_spend_limit_exceeded",
        # the project's enforced spend limit
        "project_spend_limit_exceeded",
        # the organization's OpenAI-assigned usage limit
        "organization_usage_limit_exceeded",
    }
)

# Groq's own status for a request its flex tier has no capacity for, sent with the error `capacity_exceeded`, which it
# says to retry with jittered backoff (https://console.groq.com/docs/flex-processing). No other OpenAI-dialect backend
# is known to answer it, and its error's field is not documented, so the status alone decides.
_GROQ_FLEX_CAPACITY_STATUS_CODE = 498

# OpenRouter's `error.metadata.limit_source` for a 402 that its in-flight spending budget, not the account's balance,
# caused: the budget frees itself as the running requests settle
# (https://openrouter.ai/docs/api_reference/limits.md#handling-402-errors).
_OPENROUTER_IN_FLIGHT_BUDGET_LIMIT_SOURCE = "openrouter_in_flight_budget"

# Anthropic's error type for a billing refusal, documented on a 402 (https://platform.claude.com/docs/en/api/errors)
_ANTHROPIC_BILLING_ERROR_TYPE = "billing_error"

# Anthropic's `error.details.error_code` on the 429 its tier's monthly spend cap answers, whose type is
# `rate_limit_error` like a rate limit's and which carries no `retry-after`
# (https://platform.claude.com/docs/en/api/rate-limits#reaching-your-spend-cap)
_ANTHROPIC_SPEND_CAP_ERROR_CODE = "enforced_spend_limit_reached"

# Anthropic's error type for a malformed request, which its credit-balance and self-set spend-limit refusals share
_ANTHROPIC_INVALID_REQUEST_ERROR_TYPE = "invalid_request_error"

# How Anthropic's 400 `invalid_request_error` refusals for a spent credit or spend limit begin, lowercased. Anthropic
# sends no structured signal for them: they share their status and type with every malformed request, so their sentence
# is the only signal, and it is read on that status and type alone, anchored at the message's start.
_ANTHROPIC_QUOTA_MESSAGE_PREFIXES: tuple[str, ...] = (
    # The credit balance, documented nowhere; an SDK maintainer confirmed its status and type
    # (https://github.com/anthropics/anthropic-sdk-typescript/issues/618)
    "your credit balance is too low",
    # The organization's and the workspace's own spend limits
    # (https://platform.claude.com/docs/en/api/rate-limits#setting-your-own-spend-limit)
    "you have reached your specified api usage limits",
    "you have reached your specified workspace api usage limits",
)

# AWS's error code for a request over the account's Bedrock service quota, answered on a 400, which "you can resubmit
# later" (https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_InvokeModel.html): a throttle, not a
# spent quota, since Bedrock is billed to the AWS account with no balance to spend.
_AWS_SERVICE_QUOTA_EXCEEDED_ERROR_CODE = "ServiceQuotaExceededException"

# Google's `google.rpc.ErrorInfo` reason for a request whose project's billing account is disabled, which the Gemini
# API and Vertex AI send as Google Cloud APIs (https://github.com/googleapis/googleapis/blob/master/google/api/error_reason.proto).
# Only a person can enable billing again, so it is a spent quota whatever status it arrives on.
_GOOGLE_BILLING_DISABLED_REASON = "BILLING_DISABLED"

# The `@type` of the Google error details the rules read (https://github.com/googleapis/googleapis/blob/master/google/rpc/error_details.proto)
_GOOGLE_ERROR_INFO_TYPE = "type.googleapis.com/google.rpc.ErrorInfo"
_GOOGLE_QUOTA_FAILURE_TYPE = "type.googleapis.com/google.rpc.QuotaFailure"


def _error_sections(body: Any) -> list[dict[str, Any]]:
    """The places an error body may hold its fields: its nested ``error`` section first, then its top level.

    Most providers nest their error under ``error``, and the OpenAI client pre-unwraps that section onto the body it
    keeps, which leaves the fields at the top level.
    """
    if not isinstance(body, dict):
        return []
    body_dict = cast("dict[str, Any]", body)
    sections: list[dict[str, Any]] = []
    error_section = body_dict.get("error")
    if isinstance(error_section, dict):
        sections.append(cast("dict[str, Any]", error_section))
    sections.append(body_dict)
    return sections


def _is_quota_exhaustion_by_code(*, status_code: int, error_codes: tuple[str | None, ...]) -> bool:
    """Check if an OpenAI-dialect or gateway error is a spent quota, from its status and its error codes alone.

    A 402 is a spent quota whatever its code, as OpenRouter answers insufficient credits, except its in-flight budget's
    throttle, which ``ProviderErrorMetadata.is_throttle_on_another_status`` sets aside first. A 429 is a spent quota only
    when one of ``error_codes`` is in ``_QUOTA_ERROR_CODES``; any other 429, one with no code included, is a rate limit.
    The message is never read.
    """
    if status_code == 402:
        return True
    return status_code == 429 and any(error_code in _QUOTA_ERROR_CODES for error_code in error_codes)


def _is_in_flight_budget_throttle_openrouter(*, status_code: int | None, body: Any) -> bool:
    """Check if an OpenAI-dialect 402 is OpenRouter's in-flight budget throttle, from its ``error.metadata.limit_source``.

    The source is read in every section of the body, the nested ``error`` and the top level the OpenAI client unwraps it
    to. The ``Retry-After`` OpenRouter documents beside it is the wait, not the verdict: a throttle whose header is
    missing or unreadable is still one, waited for by the retry's own backoff.
    """
    if status_code != 402:
        return False
    for section in _error_sections(body):
        error_metadata = section.get("metadata")
        if not isinstance(error_metadata, dict):
            continue
        if cast("dict[str, Any]", error_metadata).get("limit_source") == _OPENROUTER_IN_FLIGHT_BUDGET_LIMIT_SOURCE:
            return True
    return False


def _is_quota_exhaustion_anthropic(*, status_code: int, error_type: str | None, body: Any) -> bool:
    """Check if an Anthropic error is a spent quota or credit, from its status, its error type and its details.

    A 402, or an error of type ``billing_error`` on any status, is a billing refusal. A 429 is a spent quota only when
    its ``error.details.error_code`` is ``enforced_spend_limit_reached``, the tier's monthly spend cap; every other 429
    is a rate limit. A 400 of type ``invalid_request_error`` is a spent quota when its message begins with one of
    ``_ANTHROPIC_QUOTA_MESSAGE_PREFIXES``: Anthropic answers a spent credit balance and a spend limit the organization
    set itself with nothing but that sentence, so it is the one refusal any rule reads from the provider's words.
    The details and the message are read from the error body, since the message the SDK renders prefixes them.
    """
    if status_code == 402 or error_type == _ANTHROPIC_BILLING_ERROR_TYPE:
        return True
    error_sections = _error_sections(body)
    if not error_sections:
        return False
    error_section = error_sections[0]
    if status_code == 429:
        details = error_section.get("details")
        return isinstance(details, dict) and cast("dict[str, Any]", details).get("error_code") == _ANTHROPIC_SPEND_CAP_ERROR_CODE
    if status_code == 400 and error_type == _ANTHROPIC_INVALID_REQUEST_ERROR_TYPE:
        error_message = error_section.get("message")
        return isinstance(error_message, str) and error_message.strip().lower().startswith(_ANTHROPIC_QUOTA_MESSAGE_PREFIXES)
    return False


def _google_detail_entries(body: Any, *, detail_type: str) -> list[dict[str, Any]]:
    """The entries of a Google error's ``details`` whose ``@type`` is ``detail_type``, the nested ``error`` first."""
    entries: list[dict[str, Any]] = []
    for section in _error_sections(body):
        details = section.get("details")
        if not isinstance(details, list):
            continue
        for entry in cast("list[Any]", details):
            if isinstance(entry, dict) and cast("dict[str, Any]", entry).get("@type") == detail_type:
                entries.append(cast("dict[str, Any]", entry))
    return entries


def _google_error_info_metadata(entry: dict[str, Any]) -> dict[str, Any]:
    metadata = entry.get("metadata")
    return cast("dict[str, Any]", metadata) if isinstance(metadata, dict) else {}


def _is_quota_exhaustion_google(*, status_code: int, body: Any) -> bool:
    """Check if a Google error is a spent quota, from its status and its ``google.rpc`` details alone.

    A 402 is a spent balance. An ``ErrorInfo`` whose reason is ``BILLING_DISABLED`` is a project whose billing account is
    disabled, on whatever status it arrives, a 403 in practice. A 429 is a spent quota only when its details say the
    quota it hit has a limit of zero: the model is not included in the project's tier at all, as for a free-tier quota
    on a model the free tier leaves out, so no wait can cure it. Every other 429 is a rate limit, a per-day cap
    included: it resets by itself, and a run that waits for it within its budget may still succeed.
    """
    if status_code == 402:
        return True
    error_infos = _google_detail_entries(body, detail_type=_GOOGLE_ERROR_INFO_TYPE)
    if any(entry.get("reason") == _GOOGLE_BILLING_DISABLED_REASON for entry in error_infos):
        return True
    if status_code != 429:
        return False
    if any(str(_google_error_info_metadata(entry).get("quota_limit_value")) == "0" for entry in error_infos):
        return True
    for quota_failure in _google_detail_entries(body, detail_type=_GOOGLE_QUOTA_FAILURE_TYPE):
        violations = quota_failure.get("violations")
        if not isinstance(violations, list):
            continue
        for violation in cast("list[Any]", violations):
            # `quotaValue` is an int64, which protobuf's JSON form writes as a string
            if isinstance(violation, dict) and str(cast("dict[str, Any]", violation).get("quotaValue")) == "0":
                return True
    return False


def _is_content_policy_violation(error_message: str) -> bool:
    """Check if an error message indicates a content policy or safety filter violation."""
    lower_message = error_message.lower()
    return any(pattern in lower_message for pattern in _CONTENT_POLICY_PATTERNS)


def _names_the_context_window(*, text: str) -> bool:
    """Check if an error's text words a refusal of inputs over the model's context window, as some provider words it."""
    lower_text = text.lower()
    if any(pattern in lower_text for pattern in _CONTEXT_WINDOW_PATTERNS):
        return True
    return _PROMPT_TOKENS_OVER_MODEL_MAXIMUM.search(lower_text) is not None


def _stringify_for_scan(body: Any) -> str:
    """Render a metadata body into a lowercase string for content-policy / quota probing.

    Used only by in-process scanners that need to inspect the response payload; the
    return value is never surfaced to users (``body`` is ``exclude=True``).
    """
    if isinstance(body, str):
        return body
    try:
        return json.dumps(body, default=str)
    except (TypeError, ValueError):
        return str(body)


def extract_underlying_sdk_exception(instructor_exc: Any) -> BaseException | None:
    """Recover the exception that ended instructor's retry loop, from an ``InstructorRetryException``.

    instructor raises ``InstructorRetryException`` ``from`` the last exception its loop saw. With the
    schema-only retrying pipelex passes, that is either the raw SDK exception of a call that failed in
    transport, which is never re-asked, or tenacity's ``RetryError`` once the re-ask budget is spent,
    whose last attempt holds the final parse failure. So ``__cause__`` is read first.
    ``failed_attempts`` records only the attempts whose response failed to parse: after a re-ask, a
    transport failure that follows is not in it, and its last entry would name the wrong exception.
    It remains the fallback for a wrapper that carries no cause.

    Args:
        instructor_exc: The ``InstructorRetryException`` to unwrap. Typed as
            ``Any`` so callers don't need to import ``InstructorRetryException``
            just for the call site, and so malformed inputs are tolerated.

    Returns:
        The underlying exception when one can be recovered, ``None`` when
        neither path yields a ``BaseException``.
    """
    cause: Any = getattr(instructor_exc, "__cause__", None)
    retry_last_attempt: Any = getattr(cause, "last_attempt", None)
    if retry_last_attempt is not None:
        underlying = getattr(retry_last_attempt, "_exception", None)
        if isinstance(underlying, BaseException):
            return underlying
    elif isinstance(cause, BaseException):
        return cause
    failed_attempts: Any = getattr(instructor_exc, "failed_attempts", None)
    if failed_attempts:
        try:
            last_failed_attempt = failed_attempts[-1]
        except (TypeError, KeyError, IndexError):
            last_failed_attempt = None
        if last_failed_attempt is not None:
            last_exc = getattr(last_failed_attempt, "exception", None)
            if isinstance(last_exc, BaseException):
                return last_exc
    return None


def describe_instructor_failure(*, instructor_exc: BaseException) -> str:
    """Why instructor's structured generation failed, when :func:`extract_underlying_sdk_exception` recovered nothing.

    The worker calls it with the result of that extraction already known to be ``None``: the wrapper's cause is then
    either nothing or a retry error whose last attempt holds no exception, such as tenacity's ``RetryError``, whose text
    is a ``Future``'s representation, a memory address included. Neither ``instructor``'s own text, which is the last
    exception's and quotes the model's answer, nor the cause's is used: the failure is named by the class of the cause,
    or of the wrapper itself when there is none.

    Args:
        instructor_exc: The ``InstructorRetryException`` instructor raised.

    Returns:
        The reason, such as ``RetryError``.
    """
    cause = instructor_exc.__cause__
    return type(cause).__name__ if cause is not None else type(instructor_exc).__name__


# The exception classes a provider's SDK raises as its own, as a worker catches them.
SdkErrorTypes: TypeAlias = tuple[type[BaseException], ...]


def _describe_provider_exception(*, exc: BaseException, validated_type: ValidatedType | None, sdk_error_types: SdkErrorTypes | None) -> str:
    """The text a provider's metadata carries for ``exc``, which never quotes the model's answer.

    ``sdk_error_types`` is ``None`` when the worker caught ``exc`` as its SDK's own error: its text is the provider's,
    which the Classify step reads, quota against rate limiting or a content policy, and is kept. A tuple says ``exc``
    was recovered from ``instructor``'s loop, which ends either on the SDK's own error, an instance of one of these
    types, or on a failure to parse the model's answer, whose text can quote that answer: a ``ValidationError`` is
    written by its locations and reasons, located by ``validated_type``, and any other parsing failure by its class
    alone, such as the ``AssertionError`` that ``instructor``'s OpenAI parser raises with the model's refusal in its text.
    """
    if sdk_error_types is not None and not isinstance(exc, (ValidationError, *sdk_error_types)):
        return type(exc).__name__
    return describe_exception_without_input(exc=exc, validated_type=validated_type)


def parse_retry_after_seconds(value: Any) -> float | None:
    """Parse a ``Retry-After`` header value into a delay in seconds.

    The HTTP spec allows two forms: a non-negative number of seconds, or an
    HTTP-date. Numeric values are returned directly; HTTP-date values are
    converted to a delay relative to now, clamped to ``0.0`` when already past.
    A number the spec does not allow — negative, or one ``float`` accepts but no
    delay can be, such as ``inf``, ``nan`` or ``1e999`` — reads as no delay, so
    nothing downstream rounds or waits on it.
    """
    if value is None:
        return None
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        pass
    else:
        if math.isfinite(seconds) and seconds >= 0:
            return seconds
        return None
    if not isinstance(value, str):
        return None
    try:
        retry_date = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if retry_date.tzinfo is None:
        retry_date = retry_date.replace(tzinfo=UTC)
    delta_seconds = (retry_date - datetime.now(UTC)).total_seconds()
    return max(delta_seconds, 0.0)


def retry_after_seconds_from_headers(*, headers: Any) -> float | None:
    """Read the delay a provider asked for from a response's headers, in seconds.

    ``retry-after-ms``, a delay in milliseconds, comes first: it is not standard, but Azure OpenAI sends it beside
    ``retry-after`` on a 429 (https://learn.microsoft.com/en-us/azure/ai-services/openai/how-to/provisioned-get-started),
    it is the more precise of the two, and the OpenAI and Anthropic SDKs read it first for their own retries. As in
    those SDKs, it decides only when it is a finite number above zero; otherwise ``retry-after`` decides, through
    ``parse_retry_after_seconds``.
    """
    if headers is None:
        return None
    retry_after_ms = headers.get("retry-after-ms")
    if retry_after_ms is not None:
        try:
            milliseconds = float(retry_after_ms)
        except (TypeError, ValueError):
            pass
        else:
            if math.isfinite(milliseconds) and milliseconds > 0:
                return milliseconds / 1000
    return parse_retry_after_seconds(headers.get("retry-after"))


# Bedrock's error type header, which its REST-JSON protocol sends on every error answer: Claude on Bedrock, called
# through the Anthropic SDK, keeps it, while its body carries only a message.
_AWS_ERROR_TYPE_HEADER = "x-amzn-errortype"


def _aws_error_code_from_headers(*, headers: Any) -> str | None:
    """Read the AWS error code from Bedrock's ``x-amzn-errortype`` header, normalized as botocore normalizes it.

    The header may carry colon-separated data after the code and may name it as a namespaced shape id, as in
    ``ThrottlingException:http://internal.amazon.com/coral/com.amazon.bedrock/``; botocore's ``RestJSONParser`` keeps
    what precedes the first colon and follows the last ``#``.
    """
    if headers is None:
        return None
    error_type = headers.get(_AWS_ERROR_TYPE_HEADER)
    if not isinstance(error_type, str):
        return None
    code = error_type.split(":", 1)[0].rsplit("#", 1)[-1].strip()
    return code or None


def _provider_error_code_from_body(body: Any) -> str | None:
    if not isinstance(body, dict):
        return None
    error_section = cast("dict[str, Any]", body).get("error")
    if not isinstance(error_section, dict):
        return None
    error_dict = cast("dict[str, Any]", error_section)
    code = error_dict.get("type") or error_dict.get("code")
    if isinstance(code, str):
        return code
    return None


def extract_openai_metadata(
    exc: BaseException, *, validated_type: ValidatedType | None = None, sdk_error_types: SdkErrorTypes | None = None
) -> ProviderErrorMetadata:
    """Distill an OpenAI SDK exception into a ``ProviderErrorMetadata``.

    ``exc`` can also be the exception that ended instructor's re-asks, recovered from its wrapper, for which the worker
    passes its SDK's own error classes as ``sdk_error_types``: an exception of none of them failed to parse the model's
    answer, and its text can quote that answer. The most common, the ``ValidationError`` of the model's last answer, is
    written by its reasons, located by the schema of ``validated_type``, the class the structured generation asked for,
    never by the answer's values, and any other parsing failure by its class alone.

    Tolerates the SDK's two exception shapes:

    - ``APIStatusError`` subclasses (``BadRequestError``, ``RateLimitError``,
      ``AuthenticationError`` …) expose ``status_code``, ``request_id``,
      ``response.headers`` (for ``retry-after-ms`` and ``Retry-After``), and ``body``. The SDK
      pre-unwraps ``body["error"]`` so ``body["type"]`` / ``body["code"]``
      sit at the top level — and are also mirrored to ``exc.type`` /
      ``exc.code`` as instance attributes.
    - ``APIConnectionError`` / ``APITimeoutError`` carry only a ``request``;
      every status-related field comes back as ``None``.
    """
    status_code = getattr(exc, "status_code", None)
    if not isinstance(status_code, int):
        status_code = None
    request_id = getattr(exc, "request_id", None)
    if not isinstance(request_id, str):
        request_id = None
    response = getattr(exc, "response", None)
    retry_after_seconds = retry_after_seconds_from_headers(headers=getattr(response, "headers", None))
    body = getattr(exc, "body", None)
    # OpenAI's _make_status_error pre-unwraps body["error"] onto exc.type / exc.code,
    # so we read those attributes directly rather than re-parsing the body.
    error_type = getattr(exc, "type", None)
    error_code = getattr(exc, "code", None)
    provider_error_code: str | None = None
    if isinstance(error_type, str):
        provider_error_code = error_type
    elif isinstance(error_code, str):
        provider_error_code = error_code
    return ProviderErrorMetadata(
        provider=ProviderName.OPENAI,
        sdk_exception_type=type(exc).__name__,
        message=_describe_provider_exception(exc=exc, validated_type=validated_type, sdk_error_types=sdk_error_types),
        status_code=status_code,
        request_id=request_id,
        retry_after_seconds=retry_after_seconds,
        provider_error_code=provider_error_code,
        body=body,
    )


def extract_anthropic_metadata(
    exc: BaseException, *, validated_type: ValidatedType | None = None, sdk_error_types: SdkErrorTypes | None = None
) -> ProviderErrorMetadata:
    """Distill an Anthropic SDK exception into a ``ProviderErrorMetadata``.

    ``exc`` can also be the exception that ended instructor's re-asks, recovered from its wrapper, for which the worker
    passes its SDK's own error classes as ``sdk_error_types``: an exception of none of them failed to parse the model's
    answer, and its text can quote that answer. The most common, the ``ValidationError`` of the model's last answer, is
    written by its reasons, located by the schema of ``validated_type``, the class the structured generation asked for,
    never by the answer's values, and any other parsing failure by its class alone.

    Tolerates the two exception shapes in the Anthropic SDK:

    - ``APIStatusError`` subclasses expose ``status_code``, ``request_id``,
      ``response.headers`` (for ``retry-after-ms`` and ``Retry-After``, and, for Claude on Bedrock,
      ``x-amzn-errortype``, Bedrock's error code) and ``body``.
    - ``APIConnectionError`` / ``APITimeoutError`` expose neither
      ``status_code`` nor ``response``; every status-related field comes back
      as ``None``.
    """
    status_code = getattr(exc, "status_code", None)
    if not isinstance(status_code, int):
        status_code = None
    request_id = getattr(exc, "request_id", None)
    if not isinstance(request_id, str):
        request_id = None
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    retry_after_seconds = retry_after_seconds_from_headers(headers=headers)
    body = getattr(exc, "body", None)
    # Claude on Bedrock answers with Bedrock's error, whose body holds a message alone and whose code is in a header
    provider_error_code = _provider_error_code_from_body(body) or _aws_error_code_from_headers(headers=headers)
    return ProviderErrorMetadata(
        provider=ProviderName.ANTHROPIC,
        sdk_exception_type=type(exc).__name__,
        message=_describe_provider_exception(exc=exc, validated_type=validated_type, sdk_error_types=sdk_error_types),
        status_code=status_code,
        request_id=request_id,
        retry_after_seconds=retry_after_seconds,
        provider_error_code=provider_error_code,
        body=body,
    )


def _provider_error_code_from_flat_body(body: Any) -> str | None:
    """Read ``type``/``code`` directly off the top-level body dict.

    Mistral returns flat error payloads (``{"message": ..., "type": ..., "code": ...}``)
    on most endpoints, in addition to the nested ``{"error": {...}}`` shape covered
    by ``_provider_error_code_from_body``.
    """
    if not isinstance(body, dict):
        return None
    flat = cast("dict[str, Any]", body)
    code = flat.get("type") or flat.get("code")
    if isinstance(code, str):
        return code
    return None


def error_code_from_body_code_first(body: Any) -> str | None:
    """Read the error code off an error body, preferring ``code`` over ``type``.

    Same traversal as ``_provider_error_code_from_body`` then
    ``_provider_error_code_from_flat_body`` — nested ``{"error": {…}}`` first, then
    the top level, which is where the OpenAI client leaves it after pre-unwrapping —
    **but reading ``code`` before ``type``**, and that inversion is the whole point
    of the function.

    A gateway that renders its refusals in the OpenAI error shape may put its
    *specific* code in ``code`` and a generic OpenAI-shaped bucket in ``type``:
    ``{"error": {"message": …, "type": "invalid_request_error", "code":
    "<specific_code>"}}``. The vendor-facing precedence is right for Anthropic,
    whose error section carries a ``type`` and no ``code`` at all, and wrong there —
    it replaces every specific code with ``invalid_request_error`` and the code
    never reaches the classifier. A body carrying only ``code`` reads identically
    through either precedence.
    """
    for section in _error_sections(body):
        code = section.get("code") or section.get("type")
        if isinstance(code, str):
            return code
    return None


def _parse_response_text_body(response: Any) -> tuple[Any | None, str | None]:
    """Read ``response.text`` and recover ``(body, provider_error_code)`` on a best-effort basis.

    Used by providers that deliver the response body as a *raw string* (Azure REST,
    FAL, HuggingFace, Mistral) — JSON-parse it when possible, fall back to the raw
    string for HTML / non-JSON bodies. The provider-error-code probe tries both the
    nested ``{"error": {...}}`` shape and the flat ``{"type": ..., "code": ...}``
    shape so the same helper works across providers.

    Returns ``(None, None)`` when the response has no text. Returns
    ``(raw_string, None)`` for non-JSON bodies. Returns ``(parsed_dict, code)``
    when the body parses as a JSON dict.
    """
    if response is None:
        return None, None
    try:
        raw_text = getattr(response, "text", None)
    except httpx.StreamError:
        # An httpx.Response whose body was never buffered (e.g. hub 1.x async
        # streaming errors) raises ResponseNotRead/StreamConsumed on ``.text``,
        # and the body cannot be recovered synchronously — treat as "no text".
        return None, None
    if not isinstance(raw_text, str) or not raw_text:
        return None, None
    try:
        parsed: Any = json.loads(raw_text)
    except (json.JSONDecodeError, ValueError):
        return raw_text, None
    if not isinstance(parsed, dict):
        return raw_text, None
    parsed_dict = cast("dict[str, Any]", parsed)
    code = _provider_error_code_from_body(parsed_dict) or _provider_error_code_from_flat_body(parsed_dict)
    return parsed_dict, code


def _google_provider_error_code_from_details(details: Any) -> str | None:
    """Read the symbolic ``status`` (e.g. ``RESOURCE_EXHAUSTED``) from a Google error payload.

    Google API error responses typically look like
    ``{"error": {"code": 429, "message": "...", "status": "RESOURCE_EXHAUSTED"}}``,
    but some endpoints flatten the same field to the top level. Try the nested
    shape first, then the top-level fallback.
    """
    if not isinstance(details, dict):
        return None
    details_dict = cast("dict[str, Any]", details)
    error_section = details_dict.get("error")
    if isinstance(error_section, dict):
        error_dict = cast("dict[str, Any]", error_section)
        nested_status = error_dict.get("status")
        if isinstance(nested_status, str):
            return nested_status
    top_status = details_dict.get("status")
    if isinstance(top_status, str):
        return top_status
    return None


# The type URL of the detail in which a Google error states the wait it asks for
_GOOGLE_RETRY_INFO_TYPE = "type.googleapis.com/google.rpc.RetryInfo"


def _google_retry_delay_seconds(details: Any) -> float | None:
    """Read the wait a Google error asks for from its ``google.rpc.RetryInfo`` detail, in seconds.

    The Gemini API states the wait for a 429 ``RESOURCE_EXHAUSTED`` in its body rather than in a ``Retry-After``
    header: among the error's ``details``, an entry whose ``@type`` is ``google.rpc.RetryInfo`` carries a
    ``retryDelay``, a protobuf ``Duration`` in its JSON form, seconds with an ``s`` suffix and up to nine fractional
    digits (``"33s"``, ``"33.470052706s"``). The nested ``error`` section is read first, then the top level, as for the
    status. A delay that is not a finite, non-negative number of seconds reads as no delay.
    """
    retry_infos = _google_detail_entries(details, detail_type=_GOOGLE_RETRY_INFO_TYPE)
    if not retry_infos:
        return None
    retry_delay = retry_infos[0].get("retryDelay")
    if not isinstance(retry_delay, str) or not retry_delay.endswith("s"):
        return None
    try:
        seconds = float(retry_delay.removesuffix("s"))
    except ValueError:
        return None
    if math.isfinite(seconds) and seconds >= 0:
        return seconds
    return None


def extract_google_metadata(
    exc: BaseException, *, validated_type: ValidatedType | None = None, sdk_error_types: SdkErrorTypes | None = None
) -> ProviderErrorMetadata:
    """Distill a Google GenAI SDK exception into a ``ProviderErrorMetadata``.

    ``exc`` can also be the exception that ended instructor's re-asks, recovered from its wrapper, for which the worker
    passes its SDK's own error classes as ``sdk_error_types``: an exception of none of them failed to parse the model's
    answer, and its text can quote that answer. The most common, the ``ValidationError`` of the model's last answer, is
    written by its reasons, located by the schema of ``validated_type``, the class the structured generation asked for,
    never by the answer's values, and any other parsing failure by its class alone.

    Google's exception shape differs from OpenAI/Anthropic:

    - ``APIError`` (and subclasses ``ClientError`` / ``ServerError``) expose
      ``code: int`` (the HTTP status code — *not* ``status_code``), ``message``,
      ``status`` (the symbolic name like ``RESOURCE_EXHAUSTED``), and
      ``details`` (the raw response JSON dict).
    - ``response`` may be ``None`` or any of ``httpx.Response`` /
      ``requests.Response`` / ``ReplayResponse``. We read ``x-goog-request-id``
      and ``retry-after`` from ``response.headers`` when present.
    - The Gemini API states the wait for a 429 in the body's ``google.rpc.RetryInfo``
      detail rather than in a header, so ``retry_after_seconds`` falls back to its
      ``retryDelay`` when no ``retry-after`` header gave one.
    """
    code = getattr(exc, "code", None)
    status_code = code if isinstance(code, int) else None
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    request_id: str | None = None
    retry_after_seconds: float | None = None
    if headers is not None:
        request_id_value = headers.get("x-goog-request-id") or headers.get("x-request-id")
        if isinstance(request_id_value, str):
            request_id = request_id_value
        retry_after_seconds = parse_retry_after_seconds(headers.get("retry-after"))
    details = getattr(exc, "details", None)
    if retry_after_seconds is None:
        retry_after_seconds = _google_retry_delay_seconds(details)
    return ProviderErrorMetadata(
        provider=ProviderName.GOOGLE,
        sdk_exception_type=_resolve_sdk_exception_type(exc, status_code=status_code),
        message=_describe_provider_exception(exc=exc, validated_type=validated_type, sdk_error_types=sdk_error_types),
        status_code=status_code,
        request_id=request_id,
        retry_after_seconds=retry_after_seconds,
        provider_error_code=_google_provider_error_code_from_details(details),
        body=details,
    )


def extract_azure_metadata(exc: BaseException) -> ProviderErrorMetadata:
    """Distill an Azure REST API error (``httpx`` exception) into a ``ProviderErrorMetadata``.

    Azure REST returns errors as plain ``httpx`` exceptions — there is no SDK
    exception layer like Anthropic/OpenAI. We read fields off ``exc.response``
    when available (status code, headers, body) and JSON-parse the body on a
    best-effort basis. ``httpx.ConnectError`` / ``httpx.TimeoutException`` carry
    only a request; every status-related field comes back as ``None``.
    """
    return _build_azure_metadata(
        response=getattr(exc, "response", None),
        sdk_exception_type=type(exc).__name__,
        message=describe_exception_without_input(exc=exc),
    )


def extract_azure_metadata_from_response(response: Any, *, sdk_exception_type: str, message: str) -> ProviderErrorMetadata:
    """Distill a *successful* Azure REST response into a ``ProviderErrorMetadata``.

    Used when the HTTP status was fine but the body failed to parse (malformed
    JSON): there is no ``httpx`` exception carrying the response, so the caller
    passes the ``httpx.Response`` directly along with the failure's type name
    and message.
    """
    return _build_azure_metadata(response=response, sdk_exception_type=sdk_exception_type, message=message)


def _build_azure_metadata(response: Any, *, sdk_exception_type: str, message: str) -> ProviderErrorMetadata:
    """Read status code, headers, and body off an Azure ``httpx.Response`` on a best-effort basis."""
    status_code = getattr(response, "status_code", None)
    if not isinstance(status_code, int):
        status_code = None
    headers = getattr(response, "headers", None)
    request_id: str | None = None
    retry_after_seconds: float | None = None
    if headers is not None:
        request_id_value = headers.get("x-ms-request-id") or headers.get("apim-request-id") or headers.get("x-request-id")
        if isinstance(request_id_value, str):
            request_id = request_id_value
        retry_after_seconds = retry_after_seconds_from_headers(headers=headers)
    body, provider_error_code = _parse_response_text_body(response)
    return ProviderErrorMetadata(
        provider=ProviderName.AZURE,
        sdk_exception_type=sdk_exception_type,
        message=message,
        status_code=status_code,
        request_id=request_id,
        retry_after_seconds=retry_after_seconds,
        provider_error_code=provider_error_code,
        body=body,
    )


def extract_fal_metadata(exc: BaseException) -> ProviderErrorMetadata:
    """Distill a FAL SDK exception into a ``ProviderErrorMetadata``.

    FAL's ``FalClientHTTPError`` carries ``status_code``, ``response_headers``
    (a plain dict), ``response`` (an httpx.Response), and ``error_type``
    (a SDK-level discriminator like ``ContentPolicyViolation``).
    ``FalClientTimeoutError`` / ``FalClientError`` / ``MissingCredentialsError``
    have no response metadata; every status field comes back as ``None``.
    """
    status_code = getattr(exc, "status_code", None)
    if not isinstance(status_code, int):
        status_code = None
    response_headers = getattr(exc, "response_headers", None)
    request_id: str | None = None
    retry_after_seconds: float | None = None
    if response_headers is not None:
        request_id_value = response_headers.get("x-request-id") or response_headers.get("x-fal-request-id")
        if isinstance(request_id_value, str):
            request_id = request_id_value
        retry_after_seconds = parse_retry_after_seconds(response_headers.get("retry-after"))
    error_type = getattr(exc, "error_type", None)
    base_provider_error_code: str | None = error_type if isinstance(error_type, str) else None
    response = getattr(exc, "response", None)
    body, parsed_provider_error_code = _parse_response_text_body(response)
    # Prefer the SDK's ``error_type`` attribute (FAL's canonical signal) over a
    # code recovered from the body.
    provider_error_code = base_provider_error_code or parsed_provider_error_code
    return ProviderErrorMetadata(
        provider=ProviderName.FAL,
        sdk_exception_type=type(exc).__name__,
        message=describe_exception_without_input(exc=exc),
        status_code=status_code,
        request_id=request_id,
        retry_after_seconds=retry_after_seconds,
        provider_error_code=provider_error_code,
        body=body,
    )


def extract_huggingface_metadata(exc: BaseException) -> ProviderErrorMetadata:
    """Distill a HuggingFace ``HfHubHTTPError`` / ``InferenceTimeoutError`` into a ``ProviderErrorMetadata``.

    HuggingFace (hub 1.x) wraps an ``httpx.Response``; the ``request_id`` is
    mirrored onto ``exc.request_id`` by ``HfHubHTTPError.__init__`` (sourced from
    headers like ``X-Request-Id`` / ``X-Amzn-Trace-Id`` / ``X-Amz-Cf-Id``).
    Network-level failures (``InferenceTimeoutError``, raw ``httpx`` exceptions)
    carry no response metadata; every status field comes back as ``None``.
    """
    response = getattr(exc, "response", None)
    status_code = getattr(response, "status_code", None)
    if not isinstance(status_code, int):
        status_code = None
    request_id = getattr(exc, "request_id", None)
    if not isinstance(request_id, str):
        request_id = None
    headers = getattr(response, "headers", None)
    retry_after_seconds: float | None = None
    if headers is not None:
        retry_after_seconds = parse_retry_after_seconds(headers.get("retry-after"))
    body, provider_error_code = _parse_response_text_body(response)
    return ProviderErrorMetadata(
        provider=ProviderName.HUGGINGFACE,
        sdk_exception_type=type(exc).__name__,
        message=describe_exception_without_input(exc=exc),
        status_code=status_code,
        request_id=request_id,
        retry_after_seconds=retry_after_seconds,
        provider_error_code=provider_error_code,
        body=body,
    )


def extract_gateway_metadata(exc: BaseException) -> ProviderErrorMetadata:
    """Distill a Portkey/Gateway SDK exception into a ``ProviderErrorMetadata``.

    ``APIStatusError`` subclasses expose ``status_code``, ``response`` (httpx) and
    ``body``. ``APIConnectionError`` / ``APITimeoutError`` carry only a request;
    every status field comes back as ``None``.

    **``body`` cannot be trusted to be the payload here**, and that is the whole
    reason for the response fallback below. Portkey's own
    ``_make_status_error_from_response`` sets ``body`` to
    ``json.loads(text)["error"]["message"]`` — the *message string*, not the
    document — so on every refusal the SDK itself raises there is no dict to read a
    code from. Reading ``exc.body`` alone recovered ``provider_error_code = None``
    for every Portkey-substrate error the runtime ever saw. A dict does reach here
    on the paths that bypass Portkey's factory (the vendored OpenAI client the
    image workers fall back to pre-unwraps ``body["error"]``), so the dict probe
    stays first and the response is only re-parsed when it came up empty.
    """
    status_code = getattr(exc, "status_code", None)
    if not isinstance(status_code, int):
        status_code = None
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    request_id: str | None = None
    retry_after_seconds: float | None = None
    if headers is not None:
        request_id_value = headers.get("x-request-id") or headers.get("x-portkey-trace-id")
        if isinstance(request_id_value, str):
            request_id = request_id_value
        retry_after_seconds = retry_after_seconds_from_headers(headers=headers)
    body: Any = getattr(exc, "body", None)
    provider_error_code = error_code_from_body_code_first(body)
    if provider_error_code is None:
        # The response is still buffered — the SDK just read ``.text`` off it to
        # build the message — so the payload it discarded is recoverable here
        # rather than lost. A recovered code means the helper parsed a document, so
        # it also replaces the stringified ``body`` and the in-process
        # content-policy scan gets structure back instead of one rendered sentence.
        recovered_body, _ = _parse_response_text_body(response)
        recovered_code = error_code_from_body_code_first(recovered_body)
        provider_error_code = recovered_code
        if recovered_code is not None:
            body = recovered_body
    return ProviderErrorMetadata(
        provider=ProviderName.GATEWAY,
        sdk_exception_type=type(exc).__name__,
        message=describe_exception_without_input(exc=exc),
        status_code=status_code,
        request_id=request_id,
        retry_after_seconds=retry_after_seconds,
        provider_error_code=provider_error_code,
        body=body,
    )


def extract_mistral_metadata(
    exc: BaseException, *, validated_type: ValidatedType | None = None, sdk_error_types: SdkErrorTypes | None = None
) -> ProviderErrorMetadata:
    """Distill a Mistral SDK exception into a ``ProviderErrorMetadata``.

    ``exc`` can also be the exception that ended instructor's re-asks, recovered from its wrapper, for which the worker
    passes its SDK's own error classes as ``sdk_error_types``: an exception of none of them failed to parse the model's
    answer, and its text can quote that answer. The most common, the ``ValidationError`` of the model's last answer, is
    written by its reasons, located by the schema of ``validated_type``, the class the structured generation asked for,
    never by the answer's values, and any other parsing failure by its class alone.

    Tolerates the two shapes the Mistral SDK raises:

    - ``MistralError`` (and subclasses like ``SDKError``) carry ``status_code``,
      ``headers`` (httpx.Headers), and ``body`` as a *raw response text string*
      — not a pre-parsed dict like OpenAI/Anthropic. We JSON-parse it on a
      best-effort basis to recover ``provider_error_code`` from either the
      top-level ``type``/``code`` or the nested ``error.type``/``error.code``.
    - ``NoResponseError`` is a separate ``Exception`` subclass with no response
      metadata; every status-related field comes back as ``None``.
    """
    status_code = getattr(exc, "status_code", None)
    if not isinstance(status_code, int):
        status_code = None
    headers = getattr(exc, "headers", None)
    request_id: str | None = None
    retry_after_seconds: float | None = None
    if headers is not None:
        request_id_value = headers.get("x-request-id")
        if isinstance(request_id_value, str):
            request_id = request_id_value
        retry_after_seconds = parse_retry_after_seconds(headers.get("retry-after"))
    raw_body = getattr(exc, "body", None)
    body: Any = raw_body
    provider_error_code: str | None = None
    if isinstance(raw_body, str) and raw_body:
        try:
            parsed: Any = json.loads(raw_body)
        except (json.JSONDecodeError, ValueError):
            parsed = None
        if isinstance(parsed, dict):
            parsed_dict = cast("dict[str, Any]", parsed)
            body = parsed_dict
            provider_error_code = _provider_error_code_from_flat_body(parsed_dict) or _provider_error_code_from_body(parsed_dict)
    return ProviderErrorMetadata(
        provider=ProviderName.MISTRAL,
        sdk_exception_type=_resolve_sdk_exception_type(exc, status_code=status_code),
        message=_describe_provider_exception(exc=exc, validated_type=validated_type, sdk_error_types=sdk_error_types),
        status_code=status_code,
        request_id=request_id,
        retry_after_seconds=retry_after_seconds,
        provider_error_code=provider_error_code,
        body=body,
    )


# AWS Bedrock surfaces its canonical error signal as a code string; a
# hand-built ``ClientError`` (and some botocore paths) may carry no HTTP status.
# This maps the documented Bedrock error codes to an HTTP status so the
# provider-blind Classify step can treat Bedrock uniformly. Used only as a
# fallback when ``ResponseMetadata.HTTPStatusCode`` is absent.
_AWS_ERROR_CODE_TO_STATUS: dict[str, int] = {
    "ThrottlingException": 429,
    "ServiceQuotaExceededException": 400,
    "AccessDeniedException": 403,
    "UnauthorizedException": 401,
    "ValidationException": 400,
    "ModelNotReadyException": 429,
    "ServiceUnavailableException": 503,
    "InternalServerException": 500,
    "ResourceNotFoundException": 404,
    "ModelNotFoundException": 404,
}


def extract_bedrock_metadata(exc: BaseException) -> ProviderErrorMetadata:
    """Distill an AWS Bedrock ``botocore.exceptions.ClientError`` into a ``ProviderErrorMetadata``.

    botocore exposes a single ``response`` dict shaped like
    ``{"Error": {"Code": ..., "Message": ...}, "ResponseMetadata":
    {"RequestId": ..., "HTTPStatusCode": ..., "HTTPHeaders": {...}}}``.
    The ``provider_error_code`` we surface is the AWS error code (e.g.
    ``ThrottlingException``); the JSON ``body`` we keep is the full
    ``response`` dict so downstream consumers can recover the original
    error message and any extra fields without scraping ``str(exc)``.
    """
    response = getattr(exc, "response", None)
    response_dict = cast("dict[str, Any]", response) if isinstance(response, dict) else None
    error_section: dict[str, Any] = {}
    response_metadata: dict[str, Any] = {}
    if response_dict is not None:
        raw_error = response_dict.get("Error")
        if isinstance(raw_error, dict):
            error_section = cast("dict[str, Any]", raw_error)
        raw_meta = response_dict.get("ResponseMetadata")
        if isinstance(raw_meta, dict):
            response_metadata = cast("dict[str, Any]", raw_meta)
    status_code_value = response_metadata.get("HTTPStatusCode")
    status_code = status_code_value if isinstance(status_code_value, int) else None
    request_id_value = response_metadata.get("RequestId")
    request_id = request_id_value if isinstance(request_id_value, str) else None
    headers = response_metadata.get("HTTPHeaders")
    retry_after_seconds: float | None = None
    if isinstance(headers, dict):
        # botocore lowercases all HTTPHeaders keys, so ``retry-after`` is the canonical lookup.
        retry_after_seconds = parse_retry_after_seconds(cast("dict[str, Any]", headers).get("retry-after"))
    error_code = error_section.get("Code")
    provider_error_code = error_code if isinstance(error_code, str) else None
    if status_code is None and provider_error_code is not None:
        status_code = _AWS_ERROR_CODE_TO_STATUS.get(provider_error_code)
    return ProviderErrorMetadata(
        provider=ProviderName.BEDROCK,
        sdk_exception_type=type(exc).__name__,
        message=describe_exception_without_input(exc=exc),
        status_code=status_code,
        request_id=request_id,
        retry_after_seconds=retry_after_seconds,
        provider_error_code=provider_error_code,
        body=response_dict,
    )


def extract_linkup_metadata(exc: BaseException) -> ProviderErrorMetadata:
    """Distill a Linkup SDK exception into a ``ProviderErrorMetadata``.

    The Linkup Python SDK raises typed exceptions (``LinkupAuthenticationError``,
    ``LinkupTooManyRequestsError``, ``LinkupInvalidRequestError`` …) that wrap
    a plain message string but do not carry the underlying HTTP ``response``,
    ``status_code``, ``request_id``, or ``retry-after`` header. Every
    status-related field comes back as ``None``; the SDK class name is the
    main discriminator. We expose the exception class name as
    ``provider_error_code`` so downstream consumers can branch on it without
    importing the Linkup SDK at the call site.
    """
    return ProviderErrorMetadata(
        provider=ProviderName.LINKUP,
        sdk_exception_type=type(exc).__name__,
        message=describe_exception_without_input(exc=exc),
        status_code=None,
        request_id=None,
        retry_after_seconds=None,
        provider_error_code=type(exc).__name__,
        body=None,
    )


# The ``error_type`` values TypeSafe puts in an object-shaped ``detail``. Spelled here rather than
# in the provider package because ``provider_error_code`` is this module's field and the classifier
# reads it: a value that never appears here is a value nothing downstream can branch on.
TYPESAFE_AUTHENTICATION_ERROR_TYPE = "authentication_error"
TYPESAFE_MAX_TOKENS_EXCEEDED_ERROR_TYPE = "max_tokens_exceeded"
TYPESAFE_API_USAGE_ERROR_TYPE = "api_usage_error"

# What a bare-string ``detail`` on a ``400`` is reported as. TypeSafe answers 400 with a plain sentence for the
# question-shape refusals — "Noul question must have criteria or instructions: q", "Too many score
# levels. Must have at most 10 levels." — and carries no ``error_type`` at all. The absence is the
# signal, so it is given a code of its own instead of leaving ``provider_error_code`` empty, which
# would make "the body said nothing" indistinguishable from "there was no body".
TYPESAFE_MALFORMED_REQUEST_CODE = "pipelex_typesafe_malformed_request"


def _typesafe_detail(*, body: Any) -> Any | None:
    """The ``detail`` member of a TypeSafe error body, whatever shape it has."""
    if isinstance(body, str):
        try:
            body = json.loads(body)
        except (TypeError, ValueError):
            return None
    if isinstance(body, dict):
        return cast("dict[str, Any]", body).get("detail")
    return None


def extract_typesafe_metadata(exc: BaseException) -> ProviderErrorMetadata:
    """Distill a TypeSafe SDK exception into a ``ProviderErrorMetadata``.

    Two exception shapes reach here and they carry different things. A ``TypeSafeAPIError``
    subclass reached the server and carries ``status``, ``body``, ``endpoint`` and a ``request_id``
    that is declared ``str | None`` and safe to read plainly. A bare ``TypeSafeError`` is the SDK
    refusing before it sent anything — no status, no body, no request id — and the absent status is
    what routes it to the status-less arm of the classifier.

    ``provider_error_code`` is the discriminator the status cannot supply. Every validation failure
    this API produces is a ``400``, covering an illegal question, an oversized state and an unknown
    model alike, so the code is lifted out of the body: the ``error_type`` of an object-shaped
    ``detail``, or ``TYPESAFE_MALFORMED_REQUEST_CODE`` when a ``400``'s ``detail`` is a bare
    sentence. A bare sentence on any other status says nothing the status does not, so a rate limit
    or an outage answered in that shape keeps the status ladder's verdict.
    """
    body = getattr(exc, "body", None)
    status_code = getattr(exc, "status", None)
    detail = _typesafe_detail(body=body)
    provider_error_code: str | None = None
    if isinstance(detail, dict):
        error_type = cast("dict[str, Any]", detail).get("error_type")
        if isinstance(error_type, str):
            provider_error_code = error_type
    elif isinstance(detail, str) and status_code == HTTPStatus.BAD_REQUEST:
        provider_error_code = TYPESAFE_MALFORMED_REQUEST_CODE
    request_id = getattr(exc, "request_id", None)
    headers = getattr(exc, "headers", None)
    retry_after_seconds: float | None = None
    if headers is not None:
        retry_after_seconds = parse_retry_after_seconds(headers.get("retry-after"))
    return ProviderErrorMetadata(
        provider=ProviderName.TYPESAFE,
        sdk_exception_type=type(exc).__name__,
        message=describe_exception_without_input(exc=exc),
        status_code=status_code,
        request_id=request_id if isinstance(request_id, str) else None,
        retry_after_seconds=retry_after_seconds,
        provider_error_code=provider_error_code,
        body=body,
    )


_LOCAL_EXTRACT_TYPE_HIERARCHY: tuple[tuple[type[BaseException], str], ...] = (
    # ``FileNotFoundError`` is itself an ``OSError`` subclass, so it must be probed
    # first; otherwise a missing file would normalize to ``OSError`` → TRANSIENT
    # instead of CONTENT.
    (FileNotFoundError, "FileNotFoundError"),
    (ValueError, "ValueError"),
    (RuntimeError, "RuntimeError"),
    (OSError, "OSError"),
)


def extract_local_extract_metadata(exc: BaseException, *, provider: ProviderName) -> ProviderErrorMetadata:
    """Distill a local (non-HTTP) extraction exception into a ``ProviderErrorMetadata``.

    Local extractors (``docling``, ``pypdfium2`` …) run in-process against the
    file system; there is no HTTP response, no request id, no retry-after.
    The only meaningful signal is the underlying exception class
    (``FileNotFoundError``, ``ValueError``, ``RuntimeError``, ``OSError``),
    which we expose as ``sdk_exception_type``. The classifier matches on exact
    type names, so we normalize ``sdk_exception_type`` to the recognized ancestor
    here — a ``PermissionError`` from docling becomes ``"OSError"`` and routes to
    TRANSIENT instead of falling through to UNKNOWN. The original subclass name
    is preserved in ``provider_error_code`` for traceability.
    """
    raw_type_name = type(exc).__name__
    normalized_type_name = raw_type_name
    for ancestor_cls, ancestor_name in _LOCAL_EXTRACT_TYPE_HIERARCHY:
        if isinstance(exc, ancestor_cls):
            normalized_type_name = ancestor_name
            break
    return ProviderErrorMetadata(
        provider=provider,
        sdk_exception_type=normalized_type_name,
        message=describe_exception_without_input(exc=exc),
        status_code=None,
        request_id=None,
        retry_after_seconds=None,
        provider_error_code=raw_type_name,
        body=None,
    )
