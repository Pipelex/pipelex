"""Compose operator semantics: context assembly, template rendering, content construction, write-back.

These are the functions the interpreter's `PipeCompose` calls on its template path, and the ones a
programmatic caller invokes on a `RuntimeBoot`-only process. Nothing here reaches a hub: composing a
text is pure rendering over the memory it is handed.

**Construct mode is deliberately not here**, and that is a placement verdict rather than an oversight.
Its semantics are `StructuredContentComposer` over a `ConstructBlueprint`, and the blueprint is a
language artifact that `.mthds` parses into — moving both into the kernel would relocate the MTHDS
field-composition model and its error family for a caller shape that has no programmatic use (a caller
holding real Python would build the object, not describe it in a blueprint).
"""

from typing import Any

from pipelex.cogt.templating.template_rendering import render_template
from pipelex.core.concepts.concept import Concept
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.stuffs.html_content import HtmlContent
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.kernel.compose_results import ComposeResult
from pipelex.kernel.memory_ops import store_result
from pipelex.tools.jinja2.template_category import TemplateCategory
from pipelex.tools.templating.templating_style import TemplatingStyle


def build_compose_context(
    *,
    memory: WorkingMemory,
    runtime_params: dict[str, Any] | None = None,
    extra_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Layer the three context sources a composed template renders against, least specific first.

    Memory's stuffs, then the per-run params, then the step's own `extra_context` — so a step-authored
    value wins over a run-supplied one, which wins over a stuff of the same name. Single-sourced here
    because the construct path's TEMPLATE fields layer the same three in the same order, and a second
    copy of the order is how the two would drift.
    """
    context: dict[str, Any] = memory.generate_context()
    if runtime_params:
        context.update(**runtime_params)
    if extra_context:
        context.update(**extra_context)
    return context


def build_composed_content(*, output_class: type[StuffContent], rendered_text: str) -> StuffContent:
    """Wrap a rendered text in the step's declared output class.

    An HTML-shaped class takes the text as its inner markup with no wrapper class; anything else takes
    it as plain text. That fork is on the class rather than on the concept, which is why the kernel can
    answer it without a library.

    `model_validate` rather than a keyword construction, for the reason `run_llm_text` states: the class
    arrives typed as `type[StuffContent]`, whose declared fields include neither `text` nor `inner_html`
    — the subclasses a Text- or Html-compatible concept resolves to are what carry them. Validation, and
    the `ValidationError` a mismatch raises, are identical either way.
    """
    if issubclass(output_class, HtmlContent):
        return output_class.model_validate({"inner_html": rendered_text})
    return output_class.model_validate({"text": rendered_text})


async def run_compose_template(
    *,
    memory: WorkingMemory,
    template: str,
    category: TemplateCategory,
    concept: Concept,
    output_class: type[StuffContent],
    templating_style: TemplatingStyle,
    runtime_params: dict[str, Any] | None = None,
    extra_context: dict[str, Any] | None = None,
    result_name: str | None = None,
    result_code: str | None = None,
) -> ComposeResult:
    """A whole compose step over a template: build the context, render, wrap, store, report.

    `templating_style` is required rather than nullable: a composed template can tag its inputs like
    any prompt does, and the filters that do it have no default of their own. The caller resolves what
    the step authored against the runtime default.
    """
    rendered_text = await render_template(
        template=template,
        category=category,
        context=build_compose_context(memory=memory, runtime_params=runtime_params, extra_context=extra_context),
        templating_style=templating_style,
    )
    content = build_composed_content(output_class=output_class, rendered_text=rendered_text)
    return ComposeResult(
        memory=store_result(memory=memory, concept=concept, content=content, result_name=result_name, result_code=result_code),
        content=content,
        rendered_text=rendered_text,
    )
