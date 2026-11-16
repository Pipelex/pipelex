"""The prompt an LLM step hands its content-generation leaf: templates and what they read, not yet rendered.

A prompt is rendered in its leaf, never in the operator. A text past the inline threshold lives in the run's storage and
travels as a reference (`pipelex.core.stuffs.stored_value_content`), and on a host runtime the operator runs in workflow
code, which may not read storage. So the operator registers the prompt's images and documents, which needs only their
URLs, and hands the leaf this: the templates, the working memory they read with its stored values still references, the
parameters, and the registrations. The leaf loads every stored value the memory holds, renders the templates through
the shared prompt assembly (`pipelex.kernel.llm_prompt_content.render_llm_prompt`), and returns the rendered prompt
with what it generated, which is what the trace records.

What crosses the boundary into the leaf is therefore small: the stored values cross as their references, and the memory
carries only the stuffs the templates read. What crosses back is kept small too: the rendered prompt holds the loaded
texts in full, so the leaf hands it back as an `LLMPromptTrace` (`pipelex.cogt.llm.llm_prompt_trace`), each text past
its bound cut to a preview with its size and hash. A Jinja2 filter applied to a stored text (`truncate`, `upper`) acts
on the real text, since the text is loaded before anything renders.
"""

from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field

from pipelex.cogt.templating.prompt_file_registrations import PromptFileRegistrations
from pipelex.cogt.templating.template_blueprint import TemplateBlueprint
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.tools.jinja2.template_category import TemplateCategory
from pipelex.tools.jinja2.template_owner import TemplateOwner
from pipelex.tools.templating.templating_style import TemplatingStyle


class UnrenderedLLMPrompt(BaseModel):
    """An LLM prompt as its operator hands it to the leaf that renders it and generates from it.

    Attributes:
        system_template: The system prompt's template, if any. It renders before the user prompt's.
        user_template: The user prompt's template, if any.
        templating_style: The style the templates render under, unless a template declares its own.
        context: The working memory the templates read, holding only the stuffs they name, its stored values unloaded.
        read_paths: The dotted paths through which the templates read the context, so the leaf loads only the stored
            values they read. ``None`` loads every stored value the context holds.
        extra_params: The run's parameters the templates may read beside the memory (`_nb_output`, ...).
        output_structure_prompt: The description of the output structure appended to the user text, already rendered:
            it is Pipelex's own text about the output class and reads no run data.
        files: The images and documents the operator registered, which the rendered text numbers.
        system_template_field: The field of the pipe the system template is written in, which a refusal of the template
            sandbox is located on, ``None`` when the pipe has no such field.
        user_template_field: The same for the user template: ``prompt`` for a `PipeLLM`, ``None`` for the structuring
            prompt a `PipeStructure` renders, which is Pipelex's own and written in no field of the pipe.
        template_owner: Who wrote the templates, which decides whose fault their failure is: the method's for a
            `PipeLLM`'s prompts, Pipelex's for the structuring prompt.
    """

    model_config = ConfigDict(frozen=True)

    system_template: TemplateBlueprint | None = None
    user_template: TemplateBlueprint | None = None
    templating_style: TemplatingStyle = Field(strict=False)
    context: WorkingMemory = Field(default_factory=WorkingMemory)
    read_paths: list[str] | None = None
    extra_params: dict[str, Any] = Field(default_factory=dict)
    output_structure_prompt: str | None = None
    files: PromptFileRegistrations = Field(default_factory=PromptFileRegistrations)
    system_template_field: str | None = "system_prompt"
    user_template_field: str | None = "prompt"
    template_owner: TemplateOwner = Field(default=TemplateOwner.METHOD, strict=False)

    @classmethod
    def make_from_texts(cls, *, user_text: str, system_text: str | None = None, templating_style: TemplatingStyle) -> Self:
        """A prompt from two texts that read no run data: what a caller generating from a fixed prompt hands the leaf.

        Each text is a template like any other, so it renders as itself unless it holds Jinja2 syntax.
        """
        return cls(
            user_template=TemplateBlueprint(template=user_text, category=TemplateCategory.LLM_PROMPT),
            system_template=TemplateBlueprint(template=system_text, category=TemplateCategory.LLM_PROMPT) if system_text is not None else None,
            templating_style=templating_style,
        )
