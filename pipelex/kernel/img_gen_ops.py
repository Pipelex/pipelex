"""Image-generation operator semantics: deck resolution, job-params assembly, generation, write-back.

These are the functions the interpreter's `PipeImgGen` calls, and the ones a programmatic caller
invokes on a `RuntimeBoot`-only process. They read the runtime hub and the config for what a runtime
boot stands up (the model deck, the content generator, the image-generation defaults) and take
everything else as an explicit argument.

Two seams are deliberately *not* here, both for the reason `llm_ops` states about text-vs-object
dispatch — answering them needs something the kernel does not have:

- **How many images to generate.** Multiplicity resolution reads the step's declared output against a
  per-run override, which is run-params machinery the interpreter owns; the kernel takes `nb_images`.
- **Prompt assembly.** An image prompt is built from a language-side blueprint over memory-borne image
  references, so the caller hands over a ready `ImgGenPrompt` — the same division `run_llm_text` draws
  when it takes an already-mapped `LlmPromptContent`.
"""

from typing import TYPE_CHECKING, Literal

from pipelex.cogt.content_generation.cogt_run_params import CogtRunParams
from pipelex.cogt.image.image_size import ImageSize
from pipelex.cogt.img_gen.img_gen_job_components import AspectRatio, Background, ImgGenJobParams, ImgGenSize
from pipelex.cogt.img_gen.img_gen_prompt import ImgGenPrompt
from pipelex.cogt.img_gen.img_gen_setting import ImgGenModelChoice, ImgGenSetting
from pipelex.config import get_config
from pipelex.core.concepts.concept import Concept
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.stuffs.image_content import ImageContent
from pipelex.core.stuffs.list_content import ListContent
from pipelex.kernel.img_gen_results import ImgGenResult
from pipelex.kernel.memory_ops import store_result
from pipelex.runtime_hub import get_content_generator, get_model_deck
from pipelex.system.job_metadata import JobMetadata
from pipelex.tools.misc.image_utils import ImageFormat

if TYPE_CHECKING:
    from pipelex.core.stuffs.stuff_content import StuffContent


def resolve_img_gen_setting(*, img_gen_choice: ImgGenModelChoice | None = None) -> ImgGenSetting:
    """The deck chain for an image generation: the step's own choice, then the deck's default."""
    model_deck = get_model_deck()
    if img_gen_choice is not None:
        return model_deck.get_img_gen_setting(img_gen_choice)
    return model_deck.get_img_gen_setting(model_deck.img_gen_choice_default)


def resolve_default_size(*, explicit_aspect_ratio: AspectRatio | None, default_size: ImgGenSize | None) -> ImgGenSize | None:
    """Resolve the config-level size default applicable to a step, honoring exact-size/aspect-ratio exclusivity.

    An exact size implies its own aspect ratio (the blueprint forbids setting both on a pipe), so an
    exact-size deck default does not apply to a step that explicitly sets `aspect_ratio` — the more
    specific step-level field wins. A tier default composes with any ratio and always applies.
    """
    if explicit_aspect_ratio is not None and isinstance(default_size, ImageSize):
        return None
    return default_size


def build_img_gen_job_params(
    *,
    img_gen_setting: ImgGenSetting,
    aspect_ratio: AspectRatio | None = None,
    size: ImgGenSize | None = None,
    is_raw: bool | None = None,
    seed: int | Literal["auto"] | None = None,
    background: Background | None = None,
    output_format: ImageFormat | None = None,
) -> ImgGenJobParams:
    """Compose the per-job parameters from the resolved setting, the step's one-time values and config defaults.

    Three provenances meet here and the precedence between them is the semantics worth single-sourcing:
    quality, step count, guidance, moderation and safety come from the resolved *setting*; aspect ratio,
    size, background, rawness and seed come from the step when it names them and from the configured
    `img_gen_param_defaults` when it does not; and `output_format` is step-only — it has no configured
    default, so leaving it unset means "let the backend decide".

    `seed` accepts the literal `"auto"` that the config and the language both allow, and turns it into
    `None` — the backend reads an absent seed as "pick one". `0` is a legal seed (`ImgGenJobParams`
    constrains it with `ge=0`), so it is read as a value rather than as an absence.
    """
    img_gen_param_defaults = get_config().cogt.img_gen_config.img_gen_param_defaults
    seed_setting = seed if seed is not None else img_gen_param_defaults.seed
    resolved_seed: int | None
    if isinstance(seed_setting, str):
        resolved_seed = None
    else:
        resolved_seed = seed_setting
    return ImgGenJobParams(
        aspect_ratio=aspect_ratio or img_gen_param_defaults.aspect_ratio,
        size=size or resolve_default_size(explicit_aspect_ratio=aspect_ratio, default_size=img_gen_param_defaults.size),
        background=background or img_gen_param_defaults.background,
        quality=img_gen_setting.quality,
        nb_steps=img_gen_setting.nb_steps,
        guidance_scale=img_gen_setting.guidance_scale,
        is_moderated=img_gen_setting.is_moderated,
        safety_tolerance=img_gen_setting.safety_tolerance,
        is_raw=is_raw if is_raw is not None else img_gen_param_defaults.is_raw,
        output_format=output_format,
        seed=resolved_seed,
    )


async def run_img_gen(
    *,
    memory: WorkingMemory,
    img_gen_prompt: ImgGenPrompt,
    img_gen_setting: ImgGenSetting,
    img_gen_job_params: ImgGenJobParams,
    concept: Concept,
    output_class: type[ImageContent],
    job_metadata: JobMetadata,
    cogt_run_params: CogtRunParams,
    nb_images: int = 1,
    result_name: str | None = None,
    result_code: str | None = None,
) -> ImgGenResult:
    """A whole image-generation step: generate, re-validate onto the output class, store, report.

    Takes the concrete `ImageContent` subclass rather than a name, for the reason `run_llm_object`
    takes `output_class`: turning a concept into a class is a library's business. Every generated
    image is re-validated onto it, because the content generator returns a plain `ImageContent` and
    the declared output concept may refine it.
    """
    img_gen_job_config = get_config().cogt.img_gen_config.img_gen_job_config
    content_generator = get_content_generator()
    content: StuffContent
    if nb_images > 1:
        image_contents = await content_generator.make_image_list(
            job_metadata=job_metadata,
            cogt_run_params=cogt_run_params,
            img_gen_handle=img_gen_setting.model,
            img_gen_prompt=img_gen_prompt,
            nb_images=nb_images,
            img_gen_job_params=img_gen_job_params,
            img_gen_job_config=img_gen_job_config,
        )
        content = ListContent(items=[output_class.model_validate(image_content.smart_dump()) for image_content in image_contents])
    else:
        image_content = await content_generator.make_single_image(
            job_metadata=job_metadata,
            cogt_run_params=cogt_run_params,
            img_gen_handle=img_gen_setting.model,
            img_gen_prompt=img_gen_prompt,
            img_gen_job_params=img_gen_job_params,
            img_gen_job_config=img_gen_job_config,
        )
        content = output_class.model_validate(image_content.smart_dump())
    return ImgGenResult(
        memory=store_result(memory=memory, concept=concept, content=content, result_name=result_name, result_code=result_code),
        content=content,
    )
