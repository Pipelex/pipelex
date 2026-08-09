"""LLM operator semantics: deck resolution, style derivation, generation, memory write-back.

These are the functions the interpreter's `PipeLLM` and `PipeStructure` call, and the ones a
programmatic caller invokes on a `RuntimeBoot`-only process. They read the runtime hub for the
services a runtime boot stands up (the model deck, the content generator) — sanctioned kernel
internals — and take everything else as an explicit argument.

Two seams are deliberately *not* here, because they are the caller's job by construction:

- **Text-vs-object dispatch.** The two entry points below are that fork made explicit. Deciding
  which one a step wants is a question about the declared output concept, and answering it is what
  a loaded library is for.
- **Error context.** These functions raise the same cogt-level errors the code they were extracted
  from raised — `LLMCompletionError` from a generation call, `ValidationError` from constructing the
  output class. The interpreter re-wraps them into `PipeRunError` with the pipe stack, exactly as it
  always has; the kernel has no pipe to name.
"""

from typing import Any

from pipelex import log
from pipelex.cogt.content_generation.cogt_run_params import CogtRunParams
from pipelex.cogt.llm.llm_prompt import LLMPrompt
from pipelex.cogt.llm.llm_setting import LLMModelChoice, LLMSetting
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.cogt.templating.template_rendering import render_template
from pipelex.config import get_config
from pipelex.core.concepts.concept import Concept
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.kernel.llm_prompt_content import LlmPromptContent, assemble_llm_prompt
from pipelex.kernel.llm_results import LlmObjectResult, LlmTextResult, StructuringPath
from pipelex.kernel.memory_ops import store_result
from pipelex.runtime_hub import get_content_generator, get_model_deck
from pipelex.system.job_metadata import JobMetadata
from pipelex.tools.jinja2.template_category import TemplateCategory
from pipelex.tools.templating.templating_style import TemplatingStyle
from pipelex.tools.typing.structure_printer import StructurePrinter


def resolve_llm_setting_for_text(*, llm_choice: LLMModelChoice | None = None) -> LLMSetting:
    """The deck chain for a text output: the step's own choice, then the deck's override, then its default."""
    model_deck = get_model_deck()
    resolved_choice = llm_choice or model_deck.llm_choice_overrides.for_text or model_deck.llm_choice_defaults.for_text
    return model_deck.get_llm_setting(llm_choice=resolved_choice)


def resolve_llm_setting_for_object(*, llm_choice: LLMModelChoice | None = None, llm_choice_for_text: LLMModelChoice | None = None) -> LLMSetting:
    """The deck chain for a structured output.

    One rung longer than the text chain, and the extra rung is the point: a step that names a model
    for text only still generates its objects with that model, so `llm_choice_for_text` is consulted
    before the deck's own object override. A caller with no text choice (a step that only ever
    produces objects) leaves it unset and gets the plain override-then-default chain.
    """
    model_deck = get_model_deck()
    resolved_choice = llm_choice or llm_choice_for_text or model_deck.llm_choice_overrides.for_object or model_deck.llm_choice_defaults.for_object
    return model_deck.get_llm_setting(llm_choice=resolved_choice)


def derive_templating_style(*, llm_setting: LLMSetting) -> TemplatingStyle | None:
    """The configured prompting style for a resolved setting, via its prompting target.

    Derived per call and never cached: the deck and the config can both change under a live process,
    and a cached style would shadow that with whatever the first call saw.

    Returns `None` when the deck has no inference model for the handle, which is what an external
    LLM plugin looks like from here — the model is real, it is just not in the deck.
    """
    inference_model = get_model_deck().get_optional_inference_model(model_handle=llm_setting.model, model_type=ModelType.LLM)
    if inference_model is None:
        return None
    prompting_target = llm_setting.prompting_target or inference_model.prompting_target
    return get_config().pipelex.prompting_config.get_prompting_style(prompting_target=prompting_target)


async def derive_structure_prompt(*, output_class: type[StuffContent]) -> str | None:
    """Render the structure-description prompt for an output class.

    Derived from the class in hand — no concept-to-class registry hop, because the caller already
    holds the class. Returns `None` when structure prompts are disabled in config, or when the class
    has no printable structure (a bare text content has none).
    """
    llm_config = get_config().cogt.llm_config
    if not llm_config.is_structure_prompt_enabled:
        return None
    class_structure = StructurePrinter().get_type_structure(tp=output_class, base_class=StuffContent)
    if not class_structure:
        return None
    return await render_template(
        template=llm_config.get_template(template_name="output_structure_prompt"),
        category=TemplateCategory.LLM_PROMPT,
        context={"class_structure_str": "\n".join(class_structure)},
    )


async def generate_object_content(
    *,
    job_metadata: JobMetadata,
    cogt_run_params: CogtRunParams,
    llm_prompt: LLMPrompt,
    llm_setting: LLMSetting,
    output_class: type[StuffContent],
    is_multiple_output: bool = False,
    fixed_nb_output: int | None = None,
) -> StuffContent:
    """Generate one object, or a `ListContent` of them when several were asked for.

    Takes the concrete class rather than a name: it is threaded straight through to the content
    generator, so nothing rebuilds a class from a schema when the class already exists. The schema
    round-trip further down still serves the distributed-activity boundary and is untouched.
    """
    content_generator = get_content_generator()
    if is_multiple_output:
        count_desc = f"{fixed_nb_output}x" if fixed_nb_output else "list of "
        log.verbose(f"Kernel generating {count_desc}{output_class.__name__} by object_direct")
        generated_objects = await content_generator.make_object_list(
            job_metadata=job_metadata,
            cogt_run_params=cogt_run_params,
            object_class=output_class,
            llm_prompt_for_object_list=llm_prompt,
            llm_setting_for_object_list=llm_setting,
            nb_items=fixed_nb_output,
        )
        return ListContent(items=generated_objects)

    log.verbose(f"Kernel generating a single {output_class.__name__} by object_direct")
    return await content_generator.make_object(
        job_metadata=job_metadata,
        cogt_run_params=cogt_run_params,
        object_class=output_class,
        llm_prompt_for_object=llm_prompt,
        llm_setting_for_object=llm_setting,
    )


async def run_llm_text(
    *,
    memory: WorkingMemory,
    prompt_content: LlmPromptContent,
    llm_setting: LLMSetting,
    concept: Concept,
    output_class: type[StuffContent],
    job_metadata: JobMetadata,
    cogt_run_params: CogtRunParams,
    templating_style: TemplatingStyle | None = None,
    extra_params: dict[str, Any] | None = None,
    result_name: str | None = None,
    result_code: str | None = None,
) -> LlmTextResult:
    """A whole LLM step with a text output: assemble, generate, store, report.

    `templating_style` is an argument rather than derived here because a caller may hold more than
    one resolved setting for a step and has to say which one governs rendering — `PipeLLM` derives
    it from its text setting even on its object path.
    """
    llm_prompt = await assemble_llm_prompt(
        prompt_content=prompt_content,
        context_provider=memory,
        output_structure_prompt=None,
        extra_params=extra_params,
        templating_style=templating_style,
    )
    generated_text = await get_content_generator().make_llm_text(
        job_metadata=job_metadata,
        cogt_run_params=cogt_run_params,
        llm_prompt_for_text=llm_prompt,
        llm_setting_main=llm_setting,
    )
    # `model_validate` rather than `output_class(text=...)`: the class arrives typed as
    # `type[StuffContent]`, whose declared fields do not include `text` — the subclasses that a
    # Text-compatible concept resolves to are what carry it. Validation, and the `ValidationError`
    # a mismatch raises, are identical either way.
    content = output_class.model_validate({"text": generated_text})
    return LlmTextResult(
        memory=store_result(memory=memory, concept=concept, content=content, result_name=result_name, result_code=result_code),
        text=generated_text,
        rendered_prompt=llm_prompt,
        llm_setting=llm_setting,
        structuring_path=StructuringPath.TEXT,
    )


async def run_llm_object(
    *,
    memory: WorkingMemory,
    prompt_content: LlmPromptContent,
    llm_setting: LLMSetting,
    concept: Concept,
    output_class: type[StuffContent],
    job_metadata: JobMetadata,
    cogt_run_params: CogtRunParams,
    structure_prompt: str | None = None,
    is_multiple_output: bool = False,
    fixed_nb_output: int | None = None,
    templating_style: TemplatingStyle | None = None,
    extra_params: dict[str, Any] | None = None,
    result_name: str | None = None,
    result_code: str | None = None,
) -> LlmObjectResult:
    """A whole LLM step with a structured output: assemble, generate, store, report.

    `structure_prompt` overrides the description the kernel would otherwise derive from
    `output_class`. Leaving it unset is the normal path and is what keeps both callers producing the
    same prompt by default — a prompt supplied only from outside would have left the derivation at
    each caller and let the two defaults fork.
    """
    output_structure_prompt = structure_prompt if structure_prompt is not None else await derive_structure_prompt(output_class=output_class)
    llm_prompt = await assemble_llm_prompt(
        prompt_content=prompt_content,
        context_provider=memory,
        output_structure_prompt=output_structure_prompt,
        extra_params=extra_params,
        templating_style=templating_style,
    )
    content = await generate_object_content(
        job_metadata=job_metadata,
        cogt_run_params=cogt_run_params,
        llm_prompt=llm_prompt,
        llm_setting=llm_setting,
        output_class=output_class,
        is_multiple_output=is_multiple_output,
        fixed_nb_output=fixed_nb_output,
    )
    return LlmObjectResult(
        memory=store_result(memory=memory, concept=concept, content=content, result_name=result_name, result_code=result_code),
        content=content,
        rendered_prompt=llm_prompt,
        llm_setting=llm_setting,
        structuring_path=StructuringPath.OBJECT_LIST if is_multiple_output else StructuringPath.OBJECT_DIRECT,
    )
