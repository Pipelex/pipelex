"""Assemble an `ImgGenPrompt` — the image counterpart of `llm_prompt_content.assemble_llm_prompt`.

`run_img_gen` takes a *ready* `ImgGenPrompt`, by deliberate analogy with `run_llm_text` taking a ready
`LlmPromptContent`. The analogy is only honest if the kernel also ships the constructor: without this
module a `RuntimeBoot`-only process could call every other operator op and not the image one, because
the sole builder lived in `pipe_operators/` — an interpreter-layer module the kernel may not import.
`kernel/prompt_references.py` already hosts `ImageReference`, under a docstring asserting the kernel
resolves them; this is where that becomes true.

What lives here is the part a caller must not have to re-derive: the image registry, the `[Image N]`
placeholder tokens, and the correspondence between them, through the shared user-prompt assembly
(`pipelex.kernel.prompt_assembly`) that PipeLLM and PipeJudge use too. The registry is the single
source of truth for ordering, because a token/`input_images` order mismatch silently mislabels which
image the prompt is talking about, and nothing downstream can detect it.

What deliberately stays with the caller is `max_prompt_images`. That limit is a property of the model
a caller has chosen, its breach raises an interpreter-layer error, and checking `len(input_images)` is
a line of code — not the kind of subtlety this module exists to centralise.
"""

from typing import Any

from pipelex.cogt.img_gen.img_gen_prompt import ImgGenPrompt
from pipelex.cogt.templating.template_blueprint import TemplateBlueprint
from pipelex.kernel.prompt_assembly import PromptFiles
from pipelex.kernel.prompt_references import ImageReference
from pipelex.tools.misc.context_provider_abstract import ContextProviderAbstract
from pipelex.tools.templating.templating_style import TemplatingStyle


async def assemble_img_gen_prompt(
    *,
    context_provider: ContextProviderAbstract,
    templating_style: TemplatingStyle,
    prompt_blueprint: TemplateBlueprint | None = None,
    negative_prompt_blueprint: TemplateBlueprint | None = None,
    image_references: list[ImageReference] | None = None,
    extra_params: dict[str, Any] | None = None,
) -> ImgGenPrompt:
    """Build an `ImgGenPrompt`: resolve image references, render the templates, collect the images.

    `context_provider` is typically the `WorkingMemory` the step runs against. `templating_style` is
    required for the reason `assemble_llm_prompt` states: an image prompt is a prompt, so it renders
    under a style the caller resolved rather than under whatever a filter would have defaulted to.
    The positive and negative prompts share one numbering, the positive rendering first.

    Raises `PromptContentError` when an image reference names something the context does not hold, or
    holds as the wrong type.
    """
    prompt_files = PromptFiles.make_from_references(
        context_provider=context_provider,
        image_references=image_references or [],
        document_references=[],
    )
    template_params = prompt_files.template_params(extra_params=extra_params)

    positive_text: str = ""
    if prompt_blueprint:
        positive_text = await prompt_files.render(
            template_blueprint=prompt_blueprint,
            context_provider=context_provider,
            extra_params=template_params,
            templating_style=templating_style,
        )

    negative_text: str | None = None
    if negative_prompt_blueprint:
        negative_text = await prompt_files.render(
            template_blueprint=negative_prompt_blueprint,
            context_provider=context_provider,
            extra_params=template_params,
            templating_style=templating_style,
        )

    return ImgGenPrompt(
        positive_text=positive_text,
        negative_text=negative_text,
        input_images=prompt_files.prompt_images() or None,
    )
