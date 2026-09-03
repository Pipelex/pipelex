"""The manifold dialect's names: its sdk set, its one wire header, and its route paths.

Everything the manifold plugin needs to name is named here rather than imported from
``providers/portkey/`` or ``providers/gateway/``. The duplication is deliberate — it is the
no-intertwining rule from the two-gateways design, and it is what keeps the eventual retirement of
the Portkey path a module deletion rather than an untangling.
"""

from enum import StrEnum

# The header the Pipelex Manifold service reads the caller's token from.
#
# The gateway is a continuation of the Portkey AI Gateway, and the name its inherited auth layer
# answers to is `x-portkey-api-key`. Until 2026-09-03 that was the single word of the vendor's
# vocabulary still on the manifold wire; the gateway now translates this spelling to that one before
# its auth runs (`src/pig/serviceTokenHeader.ts` there), which is what let the rename happen — it
# had no runtime-only half. This is the one header the dialect sends about itself, on every
# protocol: the OpenAI-substrate factories and the native client put it there directly, and the
# shared Anthropic driver reads it from the backend's `auth_header` field, so the value in
# `backends.toml` must spell it exactly as this constant does.
MANIFOLD_AUTH_HEADER = "x-pipelex-api-key"

# The OpenAI and Portkey SDKs both expect their `base_url` to already carry the API version segment
# (`AsyncOpenAI`'s default is `https://api.openai.com/v1`, `AsyncPortkey`'s is
# `https://api.portkey.ai/v1`), and both then append their own route beneath it. The Anthropic SDK
# is the opposite: its default is `https://api.anthropic.com` and it appends `/v1/messages` itself.
#
# So the backend declares the **origin**, with no version segment, and each client appends what it
# needs. Verified against the installed SDKs rather than assumed — spike 5 lost a day to a
# `/v1`-suffixed endpoint under the Anthropic SDK producing `POST /v1/v1/messages`, which the proxy
# forwarded and answered 200-shaped.
MANIFOLD_API_VERSION_SEGMENT = "/v1"

# pig's own routes, beneath the version segment. They serve extraction and web search as themselves
# rather than dressed as chat completions; their wire contract is frozen gateway-side in
# `src/pig/pipelex/schemas.ts`.
MANIFOLD_EXTRACT_ROUTE = "/pipelex/extract"
MANIFOLD_SEARCH_ROUTE = "/pipelex/search"


class ManifoldSdk(StrEnum):
    """The sdk values the manifold catalog section may name.

    `anthropic` is deliberately absent: Claude reaches the manifold service over the *shared*
    Anthropic SDK driver, which is not part of this package and outlives the Portkey retirement.
    """

    COMPLETIONS = "manifold_completions"
    RESPONSES = "manifold_responses"
    IMG_GEN = "manifold_img_gen"
    EXTRACT = "manifold_extract"
    SEARCH = "manifold_search"


class ManifoldOpenAISdkVariant(StrEnum):
    """The two OpenAI-substrate sdks, and which of the two shapes each factory serves.

    A factory checks its own variant so that a catalog entry naming `manifold_responses` cannot be
    served by the completions factory (or the reverse) through a mis-registration — the failure
    would otherwise be a wrong request shape at the provider rather than a refusal at build time.
    """

    MANIFOLD_COMPLETIONS = "manifold_completions"
    MANIFOLD_RESPONSES = "manifold_responses"

    @classmethod
    def is_completions(cls, sdk: str) -> bool:
        try:
            variant = cls(sdk)
        except ValueError:
            return False
        match variant:
            case cls.MANIFOLD_COMPLETIONS:
                return True
            case cls.MANIFOLD_RESPONSES:
                return False

    @classmethod
    def is_responses(cls, sdk: str) -> bool:
        try:
            variant = cls(sdk)
        except ValueError:
            return False
        match variant:
            case cls.MANIFOLD_COMPLETIONS:
                return False
            case cls.MANIFOLD_RESPONSES:
                return True
