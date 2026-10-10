"""The images and documents a prompt template reads, analyzed the same way for every prompt-shaped operator.

PipeLLM, PipeImgGen and PipeJudge each turn a template into the file references the shared assembly
(`pipelex.kernel.prompt_assembly`) fetches when the prompt is built. They call this one analysis so that
what a reference carries cannot differ between them, in particular whether the input it starts from is
declared optional, which decides whether an absent file is skipped or refused. It lives beside the
analyzers rather than beside the assembly because analyzing resolves concepts through the library, which
the kernel may not import.
"""

from pydantic import BaseModel, ConfigDict

from pipelex.core.pipes.variable_multiplicity import parse_concept_with_multiplicity
from pipelex.kernel.prompt_references import DocumentReference, ImageReference
from pipelex.pipe_operators.shared.template_document_analyzer import TemplateDocumentAnalyzer
from pipelex.pipe_operators.shared.template_image_analyzer import TemplateImageAnalyzer
from pipelex.tools.jinja2.template_category import TemplateCategory
from pipelex.tools.misc.string_utils import get_root_from_dotted_path


class TemplateFileReferences(BaseModel):
    """The image and document references one template makes, each in the order the template reads it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    image_references: list[ImageReference]
    document_references: list[DocumentReference]


def analyze_template_file_references(
    *,
    template_source: str,
    input_specs: dict[str, str],
    domain_code: str,
    template_category: TemplateCategory = TemplateCategory.LLM_PROMPT,
) -> TemplateFileReferences:
    """Find the images and documents a template reads, each marked with whether its root input is optional.

    Args:
        template_source: The template, in its authored syntax (`@photo`, `$note`, Jinja2).
        input_specs: Each input's concept spec, presence marker included (`{"photo": "Image?"}`).
        domain_code: The domain the template's concepts resolve in.
        template_category: The template's category, which decides the filters it may use.
    """
    image_references = TemplateImageAnalyzer.analyze_template_for_images(
        template_source=template_source,
        input_specs=input_specs,
        domain_code=domain_code,
        template_category=template_category,
    )
    document_references = TemplateDocumentAnalyzer.analyze_template_for_documents(
        template_source=template_source,
        input_specs=input_specs,
        domain_code=domain_code,
        template_category=template_category,
    )
    return TemplateFileReferences(
        image_references=[
            image_reference.model_copy(
                update={"is_optional": _is_root_input_optional(variable_path=image_reference.variable_path, input_specs=input_specs)}
            )
            for image_reference in image_references
        ],
        document_references=[
            document_reference.model_copy(
                update={"is_optional": _is_root_input_optional(variable_path=document_reference.variable_path, input_specs=input_specs)}
            )
            for document_reference in document_references
        ],
    )


def _is_root_input_optional(*, variable_path: str, input_specs: dict[str, str]) -> bool:
    # The analyzers only return references whose root is a declared input.
    input_spec = input_specs[get_root_from_dotted_path(variable_path)]
    return parse_concept_with_multiplicity(input_spec).presence.is_optional
