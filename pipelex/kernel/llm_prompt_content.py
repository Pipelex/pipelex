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

**An LLM step renders its prompt in its content-generation leaf.** The operator calls
:func:`prepare_llm_prompt`, which registers the files and gathers the stuffs the templates read into an
:class:`~pipelex.cogt.llm.unrendered_llm_prompt.UnrenderedLLMPrompt`, performing no IO, and the leaf
calls :func:`render_llm_prompt`, which loads every stored value those stuffs hold and renders. On a host
runtime the operator is workflow code and the leaf an activity, so a text kept in storage is read only
by the activity. :func:`assemble_llm_prompt` does both halves in one process, over a context whose
stored values are already loaded.
"""

from collections.abc import Generator, Sequence
from contextlib import contextmanager
from typing import Any, Self

from pydantic import BaseModel, Field, model_validator

from pipelex.cogt.llm.llm_prompt import LLMPrompt
from pipelex.cogt.llm.unrendered_llm_prompt import UnrenderedLLMPrompt
from pipelex.cogt.templating.template_blueprint import TemplateBlueprint
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.stuffs.stored_value_loader import load_stored_values
from pipelex.core.stuffs.stored_value_walker import find_unloaded_stored_values
from pipelex.kernel.prompt_assembly import PromptFiles
from pipelex.kernel.prompt_references import DocumentReference, ImageReference
from pipelex.tools.jinja2.jinja2_rendering import locating_template_refusal
from pipelex.tools.jinja2.template_category import TemplateCategory
from pipelex.tools.jinja2.template_owner import TemplateOwner
from pipelex.tools.misc.context_provider_abstract import ContextProviderAbstract
from pipelex.tools.misc.string_utils import get_root_from_dotted_path
from pipelex.tools.storage.storage_provider_abstract import StorageProviderAbstract
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
    read_paths: frozenset[str] = Field(
        default_factory=frozenset,
        description=(
            "The dotted paths through which the two templates read their inputs (`detect_jinja2_read_paths`). Derived "
            "from the templates when not given; a pipe gives the paths it computed once, so no step parses them again."
        ),
    )

    @model_validator(mode="after")
    def derive_read_paths(self) -> Self:
        if "read_paths" not in self.model_fields_set:
            self.read_paths = templates_read_paths(templates=[self.system_template, self.user_template])
        return self

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


def templates_read_paths(*, templates: Sequence[TemplateBlueprint | None]) -> frozenset[str]:
    """The dotted paths through which any of the given templates reads its inputs, each template parsed once."""
    read_paths: set[str] = set()
    for template in templates:
        if template is not None:
            read_paths.update(template.read_paths())
    return frozenset(read_paths)


def prepare_llm_prompt(
    *,
    prompt_content: LlmPromptContent,
    memory: WorkingMemory,
    output_structure_prompt: str | None = None,
    extra_params: dict[str, Any] | None = None,
    templating_style: TemplatingStyle,
) -> UnrenderedLLMPrompt:
    """The operator's half: register the prompt's files and gather what its templates read, rendering nothing.

    It performs no IO, so workflow code may call it. The numbering is the shared user-prompt assembly's: the system
    prompt's references are registered before the user prompt's. The memory handed on holds only the stuffs the
    templates and the references name, so a step reads no more of a long run's memory than it uses, and its stored
    values stay references until the leaf loads them.

    Raises:
        PromptContentError: when a reference names something the memory does not hold, or holds as the wrong type.
    """
    prompt_files = _register_prompt_files(prompt_content=prompt_content, context_provider=memory)
    return UnrenderedLLMPrompt(
        system_template=prompt_content.system_template,
        user_template=prompt_content.user_template,
        templating_style=templating_style,
        context=_memory_read_by_prompt(prompt_content=prompt_content, memory=memory),
        read_paths=sorted(prompt_content.read_paths),
        extra_params=dict(extra_params) if extra_params else {},
        output_structure_prompt=output_structure_prompt,
        files=prompt_files.to_registrations(),
    )


async def render_llm_prompt(
    *,
    unrendered_prompt: UnrenderedLLMPrompt,
    read_scope: str | None,
    storage_provider: StorageProviderAbstract | None,
) -> LLMPrompt:
    """The leaf's half: load the stored values the templates read, then render both templates.

    Every stored value the templates read is loaded before anything renders, wherever it sits (a stuff's content, a list
    item, a field of a structure), so a template and its filters read the real text. A stored value the templates never
    read, such as a field beside the one a template names, is not read at all (`StoredValueAtPath.is_read_through`).
    Each read is checked against the run's read scope.

    Args:
        unrendered_prompt: The prompt the operator prepared with :func:`prepare_llm_prompt`.
        read_scope: The run's read scope, ``None`` for an unscoped run.
        storage_provider: The storage provider that resolves a storage URI, required when the memory holds one.

    Raises:
        UriReadRefusedError: A stored value's URL is outside the run's read scope.
        StorageNotConfiguredError: A stored value is a storage URI and no storage provider is given.
        Jinja2TemplateInvalidError: A template cannot render as written, located on its prompt field.
    """
    memory = unrendered_prompt.context
    # Keyed by the names the templates read the stuffs by, an alias included, so a read path through an alias matches.
    read_contents: dict[str, Any] = {stuff_name: stuff.content for stuff_name, stuff in memory.root.items()}
    for alias, target in memory.aliases.items():
        if target in memory.root:
            read_contents[alias] = memory.root[target].content
    await load_stored_values(
        stored_values=find_unloaded_stored_values(roots=read_contents, read_paths=unrendered_prompt.read_paths),
        read_scope=read_scope,
        storage_provider=storage_provider,
    )
    return await _render_llm_prompt(
        prompt_files=PromptFiles.make_from_registrations(registrations=unrendered_prompt.files),
        system_template=unrendered_prompt.system_template,
        user_template=unrendered_prompt.user_template,
        context_provider=memory,
        output_structure_prompt=unrendered_prompt.output_structure_prompt,
        extra_params=unrendered_prompt.extra_params,
        templating_style=unrendered_prompt.templating_style,
        system_template_field=unrendered_prompt.system_template_field,
        user_template_field=unrendered_prompt.user_template_field,
        template_owner=unrendered_prompt.template_owner,
    )


async def assemble_llm_prompt(
    *,
    prompt_content: LlmPromptContent,
    context_provider: ContextProviderAbstract,
    output_structure_prompt: str | None = None,
    extra_params: dict[str, Any] | None = None,
    templating_style: TemplatingStyle,
) -> LLMPrompt:
    """Both halves in one process: render both templates against the context and collect the files they reference.

    The context's stored values must already be loaded, since a context provider cannot be walked for them: a step
    renders through :func:`prepare_llm_prompt` and :func:`render_llm_prompt` instead. The numbering is the shared
    user-prompt assembly's (`pipelex.kernel.prompt_assembly`): the system prompt's references are registered before
    the user prompt's, and the system text renders first, so its files take the lower numbers in both texts.
    """
    return await _render_llm_prompt(
        prompt_files=_register_prompt_files(prompt_content=prompt_content, context_provider=context_provider),
        system_template=prompt_content.system_template,
        user_template=prompt_content.user_template,
        context_provider=context_provider,
        output_structure_prompt=output_structure_prompt,
        extra_params=extra_params,
        templating_style=templating_style,
        system_template_field="system_prompt",
        user_template_field="prompt",
        template_owner=TemplateOwner.METHOD,
    )


def _register_prompt_files(*, prompt_content: LlmPromptContent, context_provider: ContextProviderAbstract) -> PromptFiles:
    return PromptFiles.make_from_references(
        context_provider=context_provider,
        image_references=[*(prompt_content.system_image_references or []), *(prompt_content.user_image_references or [])],
        document_references=[*(prompt_content.system_document_references or []), *(prompt_content.user_document_references or [])],
    )


def _memory_read_by_prompt(*, prompt_content: LlmPromptContent, memory: WorkingMemory) -> WorkingMemory:
    """The part of the memory the prompt reads: the stuffs its templates and references name, aliases resolved.

    A name read through an alias keeps the alias and brings its target, so the context the leaf generates binds the
    name to the same stuff the operator's memory does.
    """
    read_names: set[str] = {get_root_from_dotted_path(read_path) for read_path in prompt_content.read_paths}
    for references in (
        prompt_content.system_image_references,
        prompt_content.user_image_references,
        prompt_content.system_document_references,
        prompt_content.user_document_references,
    ):
        read_names.update(get_root_from_dotted_path(reference.variable_path) for reference in references or [])

    read_root = {name: stuff for name, stuff in memory.root.items() if name in read_names}
    read_aliases: dict[str, str] = {}
    for alias, target in memory.aliases.items():
        if alias in read_names and target in memory.root:
            read_aliases[alias] = target
            read_root[target] = memory.root[target]
    return WorkingMemory(root=read_root, aliases=read_aliases)


async def _render_llm_prompt(
    *,
    prompt_files: PromptFiles,
    system_template: TemplateBlueprint | None,
    user_template: TemplateBlueprint | None,
    context_provider: ContextProviderAbstract,
    output_structure_prompt: str | None,
    extra_params: dict[str, Any] | None,
    templating_style: TemplatingStyle,
    system_template_field: str | None,
    user_template_field: str | None,
    template_owner: TemplateOwner,
) -> LLMPrompt:
    template_params = prompt_files.template_params(extra_params=extra_params)

    system_text: str | None = None
    if system_template:
        with _locating_refusal_on(template_field=system_template_field):
            system_text = await prompt_files.render(
                template_blueprint=system_template,
                context_provider=context_provider,
                extra_params=template_params,
                templating_style=templating_style,
                template_owner=template_owner,
            )

    user_text: str | None
    if user_template:
        with _locating_refusal_on(template_field=user_template_field):
            user_text = await prompt_files.render(
                template_blueprint=user_template,
                context_provider=context_provider,
                extra_params=template_params,
                templating_style=templating_style,
                template_owner=template_owner,
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


@contextmanager
def _locating_refusal_on(*, template_field: str | None) -> Generator[None]:
    """Locate a refusal of the template sandbox on the pipe's field the template is written in, when it is written in one.

    A template written in no field of the pipe, such as the structuring prompt, which is Pipelex's own, is located on
    none rather than on a field the pipe does not have.
    """
    if template_field is None:
        yield
        return
    with locating_template_refusal(template_field=template_field):
        yield
