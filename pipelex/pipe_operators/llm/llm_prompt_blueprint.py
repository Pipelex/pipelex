from typing import Any

from pydantic import BaseModel

from pipelex import log
from pipelex.cogt.llm.llm_prompt import LLMPrompt
from pipelex.cogt.templating.template_blueprint import TemplateBlueprint
from pipelex.kernel.llm_prompt_content import LlmPromptContent, assemble_llm_prompt
from pipelex.kernel.prompt_references import DocumentReference, ImageReference
from pipelex.tools.misc.context_provider_abstract import ContextProviderAbstract
from pipelex.tools.misc.string_utils import get_root_from_dotted_path
from pipelex.tools.templating.templating_style import TemplatingStyle


class LLMPromptBlueprint(BaseModel):
    """The parsed form of a PipeLLM's prompt: what `.mthds` declares, before anything is rendered.

    A language artifact — it parses and validates, and it answers which variables a pipe's prompt
    needs, which is what static input checking runs on. Assembling an actual prompt is execution
    semantics and lives in the kernel, so this maps down onto `LlmPromptContent` rather than holding
    a second implementation of it.
    """

    system_prompt_blueprint: TemplateBlueprint | None = None
    prompt_blueprint: TemplateBlueprint | None = None
    user_image_references: list[ImageReference] | None = None
    user_document_references: list[DocumentReference] | None = None
    system_image_references: list[ImageReference] | None = None
    system_document_references: list[DocumentReference] | None = None

    def required_variables(self) -> set[str]:
        required_variables: set[str] = set()
        if self.user_image_references:
            image_ref_root_names = [get_root_from_dotted_path(ref.variable_path) for ref in self.user_image_references]
            required_variables.update(image_ref_root_names)
        if self.user_document_references:
            doc_ref_root_names = [get_root_from_dotted_path(ref.variable_path) for ref in self.user_document_references]
            required_variables.update(doc_ref_root_names)
        if self.system_image_references:
            system_image_ref_root_names = [get_root_from_dotted_path(ref.variable_path) for ref in self.system_image_references]
            required_variables.update(system_image_ref_root_names)
        if self.system_document_references:
            system_doc_ref_root_names = [get_root_from_dotted_path(ref.variable_path) for ref in self.system_document_references]
            required_variables.update(system_doc_ref_root_names)

        if self.prompt_blueprint:
            required_variables.update(get_root_from_dotted_path(path) for path in self.prompt_blueprint.required_variables())
        if self.system_prompt_blueprint:
            required_variables.update(get_root_from_dotted_path(path) for path in self.system_prompt_blueprint.required_variables())
        return {variable_name for variable_name in required_variables if not variable_name.startswith("_") and variable_name != "place_holder"}

    def to_prompt_content(self) -> LlmPromptContent:
        """The kernel-side view of this blueprint — the same content, addressed by what it does at run time."""
        return LlmPromptContent(
            user_template=self.prompt_blueprint,
            system_template=self.system_prompt_blueprint,
            user_image_references=self.user_image_references,
            user_document_references=self.user_document_references,
            system_image_references=self.system_image_references,
            system_document_references=self.system_document_references,
        )

    async def make_llm_prompt(
        self,
        *,
        output_concept_ref: str,
        context_provider: ContextProviderAbstract,
        output_structure_prompt: str | None = None,
        extra_params: dict[str, Any] | None = None,
        templating_style: TemplatingStyle | None = None,
    ) -> LLMPrompt:
        llm_prompt = await assemble_llm_prompt(
            prompt_content=self.to_prompt_content(),
            context_provider=context_provider,
            output_structure_prompt=output_structure_prompt,
            extra_params=extra_params,
            templating_style=templating_style,
        )
        log.verbose(f"User text with {output_concept_ref=}:\n {llm_prompt.user_text}")
        return llm_prompt
