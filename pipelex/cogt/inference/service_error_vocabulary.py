"""The error codes an inference service emits on its own, contributed by the plugin that speaks to it.

A gateway or a hosted inference service may refuse a request itself, before any provider sees it,
under codes of its own: a request over its size limit, a file reference it cannot resolve, a model it
does not route. Those refusals arrive on statuses the status ladder reads as a provider rejecting the
prompt, so without their codes a caller who has a reference to fix or a deployment to report is told
to revise their inputs.

The codes are the service's wire contract, so the plugin that speaks to the service owns them: it
contributes each code with the category it falls in, the action it calls for and the advice to render,
through `PluginRegistrar.add_service_error_codes`. Boot freezes the contributions into one
`ServiceErrorVocabulary` on the runtime hub, which `classify_inference_error` consults ahead of the
status ladder and whose matched entry `render_inference_error` renders.

**Matched on the code alone, with no check on the provider.** A request reaches a service through
whichever SDK its protocol calls for, so the reporting provider does not identify the service; the
code does, and a service that contributes codes vouches that no vendor emits into them.
"""

from collections.abc import Mapping

from pydantic import BaseModel, ConfigDict, Field

from pipelex.cogt.exceptions import InferenceErrorCategory
from pipelex.cogt.inference.error_classification import UserActionKind


class ServiceErrorCode(BaseModel):
    """One error code a service emits, and what the runtime does about it.

    `detail` is the advice rendered beside the service's own message. It names what the caller, or
    whoever operates the service, should do; the service's message already names the specifics.
    `is_model_not_found` selects the family's `*ModelNotFoundError` class, for a code that means the
    service does not know the model at all.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str
    category: InferenceErrorCategory = Field(strict=False)
    user_action_kind: UserActionKind = Field(strict=False)
    detail: str
    is_model_not_found: bool = False


class ServiceErrorVocabulary:
    """Every service error code the booted plugins contributed, keyed by code.

    Built once at boot from the registrar, which has already refused a code claimed twice, so a code
    resolves to exactly one entry.
    """

    def __init__(self, codes: Mapping[str, ServiceErrorCode]):
        self._codes: dict[str, ServiceErrorCode] = dict(codes)

    def lookup(self, *, code: str | None) -> ServiceErrorCode | None:
        if code is None:
            return None
        return self._codes.get(code)

    @property
    def codes(self) -> frozenset[str]:
        return frozenset(self._codes)
