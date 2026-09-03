"""How every manifold client is built: the endpoint rule, the token, and the per-request extras.

**The endpoint rule is normative and it is why this class exists at all.** The backend declares the
Pipelex Manifold service's *origin* — scheme, host and port, with no version segment — and each
client appends what its own SDK expects beneath it. See `manifold_constants` for the probe that
established which SDK appends what.

**There is no fallback endpoint, deliberately.** The Portkey-path sibling reads
``backend.endpoint or PORTKEY_GATEWAY_URL``, which is right there: an unset endpoint means "use the
vendor's cloud". Copied here it would mean that an empty-resolving ``PIPELEX_MANIFOLD_ENDPOINT``
silently builds a client aimed at ``api.portkey.ai`` carrying the *manifold* service token — a live
billable request to the wrong vendor, with nothing anywhere reporting it. So an absent endpoint is a
refusal, and the backend loader's own missing-variable path disables the backend with a named
warning long before this is reached.
"""

from __future__ import annotations

import random
from typing import TYPE_CHECKING, Any

from pipelex.cogt.img_gen.img_gen_gemini_mapping import ImgGenGeminiMapping
from pipelex.cogt.img_gen.img_gen_job import ImgGenJob
from pipelex.cogt.llm.llm_job import LLMJob
from pipelex.providers.manifold.manifold_constants import MANIFOLD_API_VERSION_SEGMENT, MANIFOLD_AUTH_HEADER
from pipelex.providers.manifold.manifold_exceptions import ManifoldCredentialsError, ManifoldEndpointError

if TYPE_CHECKING:
    from portkey_ai import AsyncPortkey

    from pipelex.cogt.img_gen.img_gen_job_components import ImgGenJobParams
    from pipelex.cogt.inference.inference_job_abstract import InferenceJobAbstract
    from pipelex.cogt.model_backends.backend import InferenceBackend
    from pipelex.cogt.model_backends.model_spec import InferenceModelSpec


class ManifoldFactory:
    @classmethod
    def get_origin(cls, backend: InferenceBackend) -> str:
        """The service origin the backend declares, with any trailing slash removed.

        A trailing slash is stripped rather than refused because it is the one shape of a correct
        answer a human types by accident, and it would otherwise produce a doubled separator in
        every path this class builds.
        """
        endpoint = (backend.endpoint or "").strip().rstrip("/")
        if not endpoint:
            msg = (
                f"Backend '{backend.name}' declares no endpoint for the Pipelex Manifold service. "
                f"Set PIPELEX_MANIFOLD_ENDPOINT to the service origin (scheme, host and port, with no '/v1'). "
                f"There is no default: a request built without one would reach a vendor this token is not for."
            )
            raise ManifoldEndpointError(msg)
        return endpoint

    @classmethod
    def get_base_url(cls, backend: InferenceBackend) -> str:
        """The origin plus the version segment, for the SDKs that expect one in their `base_url`."""
        return f"{cls.get_origin(backend=backend)}{MANIFOLD_API_VERSION_SEGMENT}"

    @classmethod
    def get_api_key(cls, backend: InferenceBackend) -> str:
        if not backend.api_key:
            msg = f"Backend '{backend.name}' carries no api_key for the Pipelex Manifold service; set PIPELEX_MANIFOLD_API_KEY"
            raise ManifoldCredentialsError(msg)
        return backend.api_key

    @classmethod
    def make_auth_headers(cls, backend: InferenceBackend) -> dict[str, str]:
        """The whole of what the manifold dialect puts on the wire about itself: one token header.

        No config id, no provider name, no routing of any kind — the service decides which provider
        serves a model from the model id in the request body, and refuses a client that tries to say
        otherwise. Building this dict by hand rather than through the vendor's header helper is what
        makes that property readable here instead of dependent on a library's constructor defaults.
        """
        return {MANIFOLD_AUTH_HEADER: cls.get_api_key(backend=backend)}

    @classmethod
    def make_portkey_client(cls, backend: InferenceBackend) -> AsyncPortkey:
        """The image path's client.

        `portkey_ai` is a beta-only dependency of this package: the image worker reuses the vendor
        SDK's `images.generate` / `images.edit` methods for their multipart serialization, which is
        the part that was expensive to get right. Everything else in this package is built on the
        OpenAI SDK or on plain HTTP. See the deletion trigger in `manifold_img_gen_worker`.
        """
        from portkey_ai import AsyncPortkey  # ruff: ignore[import-outside-top-level]

        return AsyncPortkey(
            base_url=cls.get_base_url(backend=backend),
            api_key=cls.get_api_key(backend=backend),
            debug=cls.is_debug_enabled(backend=backend),
        )

    @classmethod
    def is_debug_enabled(cls, backend: InferenceBackend) -> bool:
        """Read from the backend's own configuration and from nothing else.

        The Portkey-path sibling routes this through the telemetry manager's
        `pipelex_gateway.portkey` knobs. Reusing those here would put one configuration block in
        charge of two services, which is the seam the two-gateways design exists to avoid.
        """
        return bool(backend.extra_config.get("debug", False))

    @classmethod
    def _make_gemini_image_config(cls, inference_model: InferenceModelSpec, *, job_params: ImgGenJobParams) -> dict[str, str]:
        """The gemini `image_config` block, honouring the portable size.

        Same resolution as the native Google worker: a requested size (tier or exact) goes through
        the model's taxonomy rules, an unset size omits `image_size` so the provider applies its own
        default, and a model with no usable taxonomy falls back to the ratio alone rather than
        guessing.
        """
        if job_params.size is None:
            taxonomy = ImgGenGeminiMapping.optional_img_gen_taxonomy(inference_model)
            if taxonomy is None:
                return {"aspect_ratio": ImgGenGeminiMapping.aspect_ratio_literal(job_params.aspect_ratio)}
        else:
            taxonomy = ImgGenGeminiMapping.img_gen_taxonomy(inference_model)
        resolved = ImgGenGeminiMapping.resolve_image_config(
            taxonomy,
            aspect_ratio=job_params.aspect_ratio,
            size=job_params.size,
            model_name=inference_model.name,
        )
        image_config: dict[str, str] = {"aspect_ratio": resolved.aspect_ratio}
        if resolved.image_size is not None:
            image_config["image_size"] = resolved.image_size
        return image_config

    @classmethod
    def make_extras(
        cls, inference_model: InferenceModelSpec, *, inference_job: InferenceJobAbstract, output_desc: str
    ) -> tuple[dict[str, str], dict[str, Any]]:
        """The per-request headers and body additions.

        `output_desc` is part of the shared factory signature and is unused on this path: it exists
        for the Portkey-path tracing header that names the job, and the manifold dialect sends no
        tracing headers in the beta.
        """
        del output_desc
        extra_headers: dict[str, str] = {}
        extra_body: dict[str, Any] = {}
        if inference_model.extra_headers:
            # Per-model outbound headers the catalog sets — `anthropic-beta` is the live example.
            # None of these is routing: the service refuses any client header that tries to choose a
            # provider, and passes the rest through to whichever one it picked.
            extra_headers.update(inference_model.extra_headers)

        if isinstance(inference_job, LLMJob) and inference_model.model_id.lower().startswith("mistral-") and inference_job.job_params.seed is None:
            # Mistral models really want a non-null seed.
            extra_body["seed"] = random.randint(0, 1000000)
        elif isinstance(inference_job, ImgGenJob) and inference_model.model_id.startswith("gemini"):
            extra_body["image_config"] = cls._make_gemini_image_config(inference_model, job_params=inference_job.job_params)

        return extra_headers, extra_body
