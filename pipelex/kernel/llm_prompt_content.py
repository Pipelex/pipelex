"""Prompt assembly: templates plus memory-borne images and documents, into one `LLMPrompt`.

This is the kernel-layer home of what `LLMPromptBlueprint.make_llm_prompt` used to do inline.
`LLMPromptBlueprint` stays where it is — it is a language artifact, what `.mthds` parses into, and it
keeps its parse-and-validate role — but it now maps down onto :func:`assemble_llm_prompt` rather than
holding the semantics, so the interpreter and a programmatic caller assemble prompts through the
same code.

The numbering of the images and documents a prompt references is the shared user-prompt assembly's
(`pipelex.kernel.prompt_assembly`), which PipeImgGen and PipeJudge use too. The ordering is
load-bearing: system-prompt references are registered before user-prompt ones, and the system text
renders before the user text, so the `[Image N]` tokens a template interpolates match the positions
of the images handed to the model.
"""

from typing import Any, Self

from pydantic import BaseModel

from pipelex.cogt.llm.llm_prompt import LLMPrompt
from pipelex.cogt.templating.template_blueprint import TemplateBlueprint
from pipelex.kernel.prompt_assembly import PromptFiles
from pipelex.kernel.prompt_references import DocumentReference, ImageReference
from pipelex.tools.jinja2.template_category import TemplateCategory
from pipelex.tools.misc.context_provider_abstract import ContextProviderAbstract
from pipelex.tools.templating.templating_style import TemplatingStyle


class LlmPromptContent(BaseModel):
    """What a prompt is made of, before anything is rendered: two templates and their references.

    The reference lists are how images and documents enter a prompt — the templates interpolate
    `[Image N]` / `[Document N]` tokens, and the referenced content is fetched out of the context
    provider (working memory) at assembly time.
    """

    user_template: TemplateBlueprint | None = None
    system_template: TemplateBlueprint | None = None
    user_image_references: list[ImageReference] | None = None
    user_document_references: list[DocumentReference] | None = None
    system_image_references: list[ImageReference] | None = None
    system_document_references: list[DocumentReference] | None = None

    @classmethod
    def make_from_text(cls, *, user: str, system: str | None = None) -> Self:
        """Text-only prompt content from two template strings, rendered against the caller's memory.

        No image or document references: a caller that needs those builds the model directly, which
        is what the interpreter's blueprint mapping does.
        """
        return cls(
            user_template=TemplateBlueprint(template=user, category=TemplateCategory.LLM_PROMPT),
            system_template=TemplateBlueprint(template=system, category=TemplateCategory.LLM_PROMPT) if system is not None else None,
        )


async def assemble_llm_prompt(
    *,
    prompt_content: LlmPromptContent,
    context_provider: ContextProviderAbstract,
    output_structure_prompt: str | None = None,
    extra_params: dict[str, Any] | None = None,
    templating_style: TemplatingStyle,
) -> LLMPrompt:
    """Render both templates against the context and collect the images and documents they reference.

    The numbering is the shared user-prompt assembly's (`pipelex.kernel.prompt_assembly`): the system
    prompt's references are registered before the user prompt's, and the system text renders first, so
    its files take the lower numbers in both texts.
    """
    prompt_files = PromptFiles.make_from_references(
        context_provider=context_provider,
        image_references=[*(prompt_content.system_image_references or []), *(prompt_content.user_image_references or [])],
        document_references=[*(prompt_content.system_document_references or []), *(prompt_content.user_document_references or [])],
    )
    template_params = prompt_files.template_params(extra_params=extra_params)

    system_text: str | None = None
    if prompt_content.system_template:
        system_text = await prompt_files.render(
            template_blueprint=prompt_content.system_template,
            context_provider=context_provider,
            extra_params=template_params,
            templating_style=templating_style,
        )

    user_text: str | None
    if prompt_content.user_template:
        user_text = await prompt_files.render(
            template_blueprint=prompt_content.user_template,
            context_provider=context_provider,
            extra_params=template_params,
            templating_style=templating_style,
        )
        if output_structure_prompt:
            user_text += output_structure_prompt
    else:
        # Can be None: a prompt with no user template and no structure to describe has no user text.
        user_text = output_structure_prompt

    return LLMPrompt(
        system_text=system_text,
        user_text=user_text,
        user_images=prompt_files.prompt_images(),
        user_documents=prompt_files.prompt_documents(),
    )
