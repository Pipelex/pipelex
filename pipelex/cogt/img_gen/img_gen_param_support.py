"""Capability checks for img-gen parameter values against a model's rules.

These helpers tell you whether a value would be accepted by a given model's
rules, without actually building API arguments. They reuse `ImgGenArgsFactory`
as the single source of truth: each check internally calls the corresponding
`make_args_from_*` and captures `ImgGenParameterError`.

Used by:
- Tests, to gracefully `pytest.skip` when a model can't honor a parametrized value.
- `PipeImgGen` blueprint validation, to surface config errors at load time.

Unknown-taxonomy policy: if a rule value cannot be parsed into the expected
taxonomy enum, the check abstains (returns supported=True). Some backends
(e.g. the Pipelex gateway) carry rules whose taxonomy strings predate this
factory, and those rules are consumed by a different worker — abstaining
prevents false negatives in those cases.
"""

from typing import NamedTuple

from pipelex import log
from pipelex.cogt.exceptions import ImgGenParameterError
from pipelex.cogt.image.image_size import ImageSize
from pipelex.cogt.img_gen.img_gen_args_factory import ImgGenArgsFactory
from pipelex.cogt.img_gen.img_gen_job_components import AspectRatio, Background, ImgGenJobParams, InputFidelity, SizeTier
from pipelex.cogt.img_gen.img_gen_model_rules import (
    AspectRatioTaxonomy,
    BackgroundTaxonomy,
    ImgGenArgTopic,
    ImgGenModelRules,
    InputFidelityTaxonomy,
    OutputFormatTaxonomy,
)
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.tools.misc.image_utils import ImageFormat


class SupportCheck(NamedTuple):
    """Result of a single parameter-support check.

    `reason` is populated only when `is_supported` is False.
    """

    is_supported: bool
    reason: str | None


_SUPPORTED = SupportCheck(is_supported=True, reason=None)


class ImgGenParamSupport:
    """Yes/no support checks against ImgGenModelRules for each topic.

    Each check returns a SupportCheck rather than raising. The aggregate methods
    (check_job_params, check_blueprint_params) return a list of unsupported
    reasons (empty if all good).
    """

    @classmethod
    def check_aspect_ratio(
        cls,
        *,
        rules: ImgGenModelRules,
        aspect_ratio: AspectRatio,
        size: SizeTier | ImageSize | None,
        model_name: str,
    ) -> SupportCheck:
        taxonomy_value = rules.get(ImgGenArgTopic.ASPECT_RATIO)
        if taxonomy_value is None:
            return _SUPPORTED
        try:
            taxonomy = AspectRatioTaxonomy(taxonomy_value)
        except ValueError:
            log.debug(f"Abstaining: unknown AspectRatioTaxonomy '{taxonomy_value}' for model '{model_name}'")
            return _SUPPORTED
        try:
            ImgGenArgsFactory.make_args_from_aspect_ratio(
                aspect_ratio_taxonomy=taxonomy,
                aspect_ratio=aspect_ratio,
                size=size,
                model_name=model_name,
            )
        except ImgGenParameterError as exc:
            return SupportCheck(is_supported=False, reason=str(exc))
        return _SUPPORTED

    @classmethod
    def check_background(
        cls,
        *,
        rules: ImgGenModelRules,
        background: Background,
        model_name: str,
    ) -> SupportCheck:
        taxonomy_value = rules.get(ImgGenArgTopic.BACKGROUND)
        if taxonomy_value is None:
            return _SUPPORTED
        try:
            taxonomy = BackgroundTaxonomy(taxonomy_value)
        except ValueError:
            log.debug(f"Abstaining: unknown BackgroundTaxonomy '{taxonomy_value}' for model '{model_name}'")
            return _SUPPORTED
        try:
            ImgGenArgsFactory.make_args_from_background(
                background_taxonomy=taxonomy,
                background=background,
                model_name=model_name,
            )
        except ImgGenParameterError as exc:
            return SupportCheck(is_supported=False, reason=str(exc))
        return _SUPPORTED

    @classmethod
    def check_output_format(
        cls,
        *,
        rules: ImgGenModelRules,
        output_format: ImageFormat | None,
    ) -> SupportCheck:
        taxonomy_value = rules.get(ImgGenArgTopic.OUTPUT_FORMAT)
        if taxonomy_value is None:
            return _SUPPORTED
        try:
            taxonomy = OutputFormatTaxonomy(taxonomy_value)
        except ValueError:
            log.debug(f"Abstaining: unknown OutputFormatTaxonomy '{taxonomy_value}'")
            return _SUPPORTED
        try:
            ImgGenArgsFactory.make_args_from_output_format(
                output_format_taxonomy=taxonomy,
                output_format=output_format,
            )
        except ImgGenParameterError as exc:
            return SupportCheck(is_supported=False, reason=str(exc))
        return _SUPPORTED

    @classmethod
    def check_input_fidelity(
        cls,
        *,
        rules: ImgGenModelRules,
        input_fidelity: InputFidelity | None,
        model_name: str,
    ) -> SupportCheck:
        taxonomy_value = rules.get(ImgGenArgTopic.INPUT_FIDELITY)
        if taxonomy_value is None:
            if input_fidelity is None:
                return _SUPPORTED
            reason = f"Model '{model_name}' does not support input_fidelity"
            return SupportCheck(is_supported=False, reason=reason)
        try:
            taxonomy = InputFidelityTaxonomy(taxonomy_value)
        except ValueError:
            log.debug(f"Abstaining: unknown InputFidelityTaxonomy '{taxonomy_value}' for model '{model_name}'")
            return _SUPPORTED
        try:
            ImgGenArgsFactory.make_args_from_input_fidelity(
                input_fidelity_taxonomy=taxonomy,
                input_fidelity=input_fidelity,
                model_name=model_name,
            )
        except ImgGenParameterError as exc:
            return SupportCheck(is_supported=False, reason=str(exc))
        return _SUPPORTED

    @classmethod
    def check_input_images(
        cls,
        *,
        inference_model: InferenceModelSpec,
        has_input_images: bool,
    ) -> SupportCheck:
        """Check img2img capability against the model's declared `inputs`, not its rules.

        The `input_images` rule is an args-factory formatting concern that only exists for
        providers whose request is built by `ImgGenArgsFactory` (e.g. GPT Image, BFL Flux 2).
        Workers that build the provider request directly (Google Gemini native, chat-completions
        image models) carry no such rule; for them — and in truth for every model — the
        capability declaration is `inputs` containing "images".
        """
        if not has_input_images:
            return _SUPPORTED
        if inference_model.is_img2img_supported:
            return _SUPPORTED
        reason = f"Model '{inference_model.name}' does not accept image inputs, so image-to-image generation is not supported."
        return SupportCheck(is_supported=False, reason=reason)

    @classmethod
    def check_job_params(
        cls,
        *,
        inference_model: InferenceModelSpec,
        params: ImgGenJobParams,
        has_input_images: bool = False,
    ) -> list[str]:
        """Run all relevant checks; return list of unsupported reasons (empty if all good)."""
        rules: ImgGenModelRules = inference_model.rules or {}
        model_name = inference_model.name
        checks: list[SupportCheck] = [
            cls.check_aspect_ratio(rules=rules, aspect_ratio=params.aspect_ratio, size=params.size, model_name=model_name),
            cls.check_background(rules=rules, background=params.background, model_name=model_name),
            cls.check_output_format(rules=rules, output_format=params.output_format),
            cls.check_input_fidelity(rules=rules, input_fidelity=params.input_fidelity, model_name=model_name),
            cls.check_input_images(inference_model=inference_model, has_input_images=has_input_images),
        ]
        return [check.reason for check in checks if not check.is_supported and check.reason is not None]

    @classmethod
    def check_blueprint_params(
        cls,
        *,
        rules: ImgGenModelRules,
        aspect_ratio: AspectRatio | None,
        size: SizeTier | ImageSize | None,
        background: Background | None,
        output_format: ImageFormat | None,
        model_name: str,
    ) -> list[str]:
        """Check blueprint fields that are explicitly set.

        None means "deck default applies later" — those are NOT checked, since the
        actual value is unknown at blueprint load time.
        """
        reasons: list[str] = []
        if aspect_ratio is not None or size is not None:
            # When only `size` is set, the ratio context does not change the verdict:
            # exact sizes ignore the ratio on every taxonomy, and tier satisfiability is
            # uniform across each model's supported ratios — SQUARE is a neutral stand-in.
            # The deferred deck-default ratio itself is still checked at runtime.
            check = cls.check_aspect_ratio(
                rules=rules,
                aspect_ratio=aspect_ratio or AspectRatio.SQUARE,
                size=size,
                model_name=model_name,
            )
            if not check.is_supported and check.reason is not None:
                reasons.append(check.reason)
        if background is not None:
            check = cls.check_background(rules=rules, background=background, model_name=model_name)
            if not check.is_supported and check.reason is not None:
                reasons.append(check.reason)
        if output_format is not None:
            check = cls.check_output_format(rules=rules, output_format=output_format)
            if not check.is_supported and check.reason is not None:
                reasons.append(check.reason)
        return reasons
