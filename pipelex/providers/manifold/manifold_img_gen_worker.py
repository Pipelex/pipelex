"""Image generation and editing through the Pipelex Manifold service.

**This module is the one place the manifold plugin depends on `portkey_ai`, and the dependency has a
deletion trigger.** The two-gateways design ruled that the manifold plugin must not depend on the
vendor's library — "when Portkey retires as a vendor, the library retires with it" — and the
engineering review of 2026-08-25 lifted that rule *for the beta only*, so the image path could reuse
work that was already proven live rather than being ported first. Reusing `AsyncPortkey` buys one
specific thing: its `images.generate` / `images.edit` methods carry the multipart serialization for
image edits, which is the part that was expensive to get right.

**Delete this dependency when** the manifold image path is ported to the OpenAI SDK — the mapping
can be read out of the Portkey SDK's own source. What changes then is this module's client and its
exception arms; nothing else in the package imports the vendor library. Until that happens, the
design page's claim that the manifold plugin does not depend on `portkey_ai` is false, which is why
the lift is written into the design rather than only into a plan.

**The response shapes this worker parses are only the ones the manifold catalog names.** Every
`manifold_img_gen` entry is an Azure GPT Image model, and the gateway's own configuration serves
them from one integration. The Portkey path's worker also carries a Black Forest Labs Flux 2 Pro
branch and a FAL queue-polling branch; neither has a model on this path, so neither is carried here.
A response that matches nothing is refused with what it actually contained, and restoring a branch
is a `git show` away.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, cast

from portkey_ai import AsyncPortkey

# The vendored openai package is the one AsyncPortkey is built from, so the exceptions it raises are
# the vendored classes (not the real `openai` package's) — there is no public re-export in portkey_ai.
from portkey_ai._vendor import openai as portkey_vendored_openai  # ruff: ignore[import-private-name]
from portkey_ai.api_resources import exceptions as portkey_exceptions
from pydantic import ValidationError
from typing_extensions import override

from pipelex.cogt.exceptions import ImgGenGenerationError, ImgGenParameterError, InferenceErrorCategory, SdkTypeError
from pipelex.cogt.image.generated_image import GeneratedImageRawDetails
from pipelex.cogt.image.image_size import ImageSize
from pipelex.cogt.img_gen.img_gen_args_factory import ImageFileTuple, ImgGenArgsFactory
from pipelex.cogt.img_gen.img_gen_worker_abstract import ImgGenWorkerAbstract
from pipelex.cogt.inference.error_classification import UserAction, UserActionKind, extract_gateway_metadata
from pipelex.cogt.inference.error_classify import classify_inference_error
from pipelex.cogt.inference.error_render import InferenceErrorFamily, render_inference_error
from pipelex.cogt.usage.token_category import NbTokensByCategoryDict, TokenCategory
from pipelex.providers.manifold.manifold_schemas import ManifoldImgGenAzureGptImage
from pipelex.tools.typing.pydantic_utils import format_pydantic_validation_error

if TYPE_CHECKING:
    from pipelex.cogt.img_gen.img_gen_job import ImgGenJob
    from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
    from pipelex.reporting.reporting_protocol import ReportingProtocol


class ManifoldImgGenWorker(ImgGenWorkerAbstract):
    def __init__(
        self,
        sdk_instance: Any,
        inference_model: InferenceModelSpec,
        reporting_delegate: ReportingProtocol | None = None,
    ):
        super().__init__(inference_model=inference_model, reporting_delegate=reporting_delegate)

        if not isinstance(sdk_instance, AsyncPortkey):
            msg = f"Provided ImgGen sdk_instance for {self.__class__.__name__} is not of type portkey_ai.AsyncPortkey: it's a '{type(sdk_instance)}'"
            raise SdkTypeError(msg)

        self.portkey_client: AsyncPortkey = sdk_instance

    @override
    async def _gen_image(
        self,
        img_gen_job: ImgGenJob,
    ) -> GeneratedImageRawDetails:
        one_image_list = await self._gen_image_list(img_gen_job=img_gen_job, nb_images=1)
        return one_image_list[0]

    @override
    async def _gen_image_list(
        self,
        img_gen_job: ImgGenJob,
        *,
        nb_images: int,
    ) -> list[GeneratedImageRawDetails]:
        if self.inference_model.rules is None:
            msg = f"Model '{self.inference_model.name}' does not have rules configured"
            raise ImgGenParameterError(msg)
        args_dict = await ImgGenArgsFactory.make_args_for_model(
            model_rules=self.inference_model.rules,
            img_gen_job=img_gen_job,
            nb_images=nb_images,
            model_id=self.inference_model.model_id,
            model_name=self.inference_model.name,
        )

        image_files: list[ImageFileTuple] | None = args_dict.pop("image", None)
        response_dict = await self._call_images_api(image_files=image_files, args_dict=args_dict)
        self._record_usage(response_dict=response_dict, img_gen_job=img_gen_job)
        return self._make_generated_images(response_dict=response_dict)

    async def _call_images_api(self, *, image_files: list[ImageFileTuple] | None, args_dict: dict[str, Any]) -> dict[str, Any]:
        """One call, one dict back — whichever of the two Images routes the job needs.

        There is no `endpoint_path` here and no config id: the manifold dialect puts the model in the
        body and lets the gateway decide who serves it, so which *route* is called is the SDK
        method's business and which *provider* answers is the gateway's.
        """
        # Declared rather than inferred: the SDK's image methods are typed with `**kwargs: Unknown`,
        # so calling them with a spread argument dict leaves pyright unable to name the result.
        response: Any
        try:
            if image_files is not None:
                # OpenAI's Images API splits generation and editing across two routes, and only
                # /images/edits accepts input images (/images/generations rejects them with a 400
                # "Unknown parameter"). The shape of the multipart body is the SDK's business too: a
                # list under `image` is serialized as `image[]` parts, a single file as the bare
                # `image` field. That distinction is not cosmetic — a server handed repeated bare
                # `image` parts keeps one and silently drops the rest, so an edit of several images
                # would come back as a plausible edit of the first.
                images_arg: Any = image_files[0] if len(image_files) == 1 else list(image_files)
                response = await self.portkey_client.images.edit(image=images_arg, **args_dict)  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
            else:
                response = await self.portkey_client.images.generate(**args_dict)  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
        except (portkey_exceptions.APIError, portkey_vendored_openai.APIError) as exc:
            metadata = extract_gateway_metadata(exc)
            classification = classify_inference_error(metadata)
            raise render_inference_error(
                metadata=metadata,
                classification=classification,
                family=InferenceErrorFamily.IMG_GEN,
                model_desc=self.inference_model.desc,
                model_handle=self.inference_model.name,
            ) from exc
        except json.JSONDecodeError as exc:
            # A 2xx carrying a body that is not JSON — an intermediary's HTML error page is the way
            # this happens — makes the SDK's own decode raise. `JSONDecodeError` is not an `APIError`
            # and so falls through the arm above; left raw it is neither a `PipelexError` nor
            # annotated with the model, which means it escapes the Temporal error bridge and gets
            # retried, billing a second generation for the same job.
            msg = f"The Pipelex Manifold service returned a non-JSON body for model '{self.inference_model.name}'"
            raise ImgGenGenerationError(
                msg,
                error_category=InferenceErrorCategory.UNKNOWN,
                user_action=UserAction(
                    kind=UserActionKind.CONTACT_SUPPORT,
                    detail="The gateway returned a malformed response — retry, and report this if it persists",
                ),
                provider_metadata=None,
            ) from exc

        raw_response = cast("object", response.model_dump(serialize_as_any=True))  # pyright: ignore[reportUnknownMemberType]
        if not isinstance(raw_response, dict):
            msg = f"Response from model '{self.inference_model.name}' did not serialize to an object: it is a '{type(raw_response).__name__}'"
            raise ImgGenGenerationError(
                msg,
                error_category=InferenceErrorCategory.UNKNOWN,
                user_action=UserAction(
                    kind=UserActionKind.CHANGE_MODEL,
                    detail="The gateway returned an unexpected response shape — try a different model",
                ),
                provider_metadata=None,
            )
        return cast("dict[str, Any]", raw_response)

    def _record_usage(self, *, response_dict: dict[str, Any], img_gen_job: ImgGenJob) -> None:
        if (usage_dict := response_dict.get("usage")) and (img_gen_tokens_usage := img_gen_job.job_report.img_gen_tokens_usage):
            nb_tokens: NbTokensByCategoryDict = {}
            if input_tokens := usage_dict.get("prompt_tokens") or usage_dict.get("input_tokens"):
                nb_tokens[TokenCategory.INPUT] = input_tokens
            if output_tokens := usage_dict.get("completion_tokens") or usage_dict.get("output_tokens"):
                nb_tokens[TokenCategory.OUTPUT] = output_tokens
            img_gen_tokens_usage.nb_tokens_by_category = nb_tokens

    def _make_generated_images(self, *, response_dict: dict[str, Any]) -> list[GeneratedImageRawDetails]:
        try:
            azure_gpt_image = ManifoldImgGenAzureGptImage.model_validate(response_dict)
        except ValidationError as exc:
            msg = f"Could not parse the image generation response for model '{self.inference_model.name}': {format_pydantic_validation_error(exc)}"
            raise ImgGenGenerationError(
                msg,
                error_category=InferenceErrorCategory.UNKNOWN,
                user_action=UserAction(
                    kind=UserActionKind.CHANGE_MODEL,
                    detail="The gateway returned an unexpected response shape — try a different model",
                ),
                provider_metadata=None,
            ) from exc

        if not azure_gpt_image.data:
            msg = f"Response from model '{self.inference_model.name}' carries no 'data' images"
            raise ImgGenGenerationError(
                msg,
                error_category=InferenceErrorCategory.UNKNOWN,
                user_action=UserAction(
                    kind=UserActionKind.CHANGE_MODEL,
                    detail="The gateway returned an unexpected response shape — try a different model",
                ),
                provider_metadata=None,
            )

        width, height = self._parse_size(size=azure_gpt_image.size)

        generated_images: list[GeneratedImageRawDetails] = []
        for image in azure_gpt_image.data:
            if not image.b64_json:
                msg = f"No base64 image data received from model '{self.inference_model.name}'"
                raise ImgGenGenerationError(
                    msg,
                    error_category=InferenceErrorCategory.CONTENT,
                    user_action=UserAction(
                        kind=UserActionKind.CHANGE_INPUT,
                        detail="The gateway returned no image data — try rephrasing the prompt or using a different model",
                    ),
                    provider_metadata=None,
                )
            generated_images.append(
                GeneratedImageRawDetails(
                    base64_str=image.b64_json,
                    size=ImageSize(width=width, height=height),
                    image_format=azure_gpt_image.output_format,
                ),
            )
        return generated_images

    def _parse_size(self, *, size: str) -> tuple[int, int]:
        size_split = size.split("x")
        if len(size_split) != 2:
            msg = f"Size from img gen response is not a valid size: '{size}'"
            raise ImgGenGenerationError(
                msg,
                error_category=InferenceErrorCategory.UNKNOWN,
                user_action=UserAction(
                    kind=UserActionKind.CHANGE_MODEL,
                    detail="The gateway returned a malformed image size — try a different model",
                ),
                provider_metadata=None,
            )
        width_str, height_str = size_split
        try:
            return int(width_str), int(height_str)
        except ValueError as exc:
            msg = f"Size from img gen response has non-numeric dimensions: '{size}'"
            raise ImgGenGenerationError(
                msg,
                error_category=InferenceErrorCategory.UNKNOWN,
                user_action=UserAction(
                    kind=UserActionKind.CHANGE_MODEL,
                    detail="The gateway returned a malformed image size — try a different model",
                ),
                provider_metadata=None,
            ) from exc
