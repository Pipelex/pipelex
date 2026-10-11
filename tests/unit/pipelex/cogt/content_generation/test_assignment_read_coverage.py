"""Every URL an assignment carries is declared by its `referenced_uris()`, which its leaf authorizes.

The leaves authorize what `referenced_uris()` declares, so a URL an assignment carries and does not
declare would be read unchecked. This test is the tripwire: it walks every assignment model's fields
for URL-shaped ones (a string field named `uri`, `url` or ending in `_uri` / `_url`), compares them
with the inventory below, and checks that `referenced_uris()` returns a URL placed in each of them. A
new assignment, or a new URL field on a payload, fails here until its `referenced_uris()` declares it
and the inventory names it.
"""

import inspect
import re
import types
import typing
from typing import Annotated, Any, Protocol, Union, get_args, get_origin

from pydantic import BaseModel

from pipelex.cogt.content_generation import assignment_models
from pipelex.cogt.content_generation.assignment_models import (
    ExtractAssignment,
    ImgGenAssignment,
    JudgmentAssignment,
    LLMAssignment,
    ObjectAssignment,
    RenderDocumentAssignment,
    RenderPageViewsAssignment,
    SearchAssignment,
    SearchObjectAssignment,
    TemplatingAssignment,
)
from pipelex.cogt.content_generation.cogt_run_params import CogtRunParams
from pipelex.cogt.doc_gen.doc_gen_format import DocGenFormat, DocGenSource
from pipelex.cogt.doc_gen.doc_gen_setting import DocGenSetting
from pipelex.cogt.doc_gen.document_composition import DocumentComposition
from pipelex.cogt.doc_gen.layout_tree import ImageBlock, LayoutDocument, SectionBlock
from pipelex.cogt.document.prompt_document import PromptDocumentUri
from pipelex.cogt.extract.extract_input import ExtractInput
from pipelex.cogt.extract.extract_job_components import ExtractJobConfig, ExtractJobParams
from pipelex.cogt.image.prompt_image import PromptImageUri
from pipelex.cogt.img_gen.img_gen_job_components import AspectRatio, Background, ImgGenJobConfig, ImgGenJobParams
from pipelex.cogt.img_gen.img_gen_prompt import ImgGenPrompt
from pipelex.cogt.judgment.judgment_models import JudgmentPrompt, YesNoQuestion
from pipelex.cogt.judgment.judgment_setting import JudgmentSetting
from pipelex.cogt.llm.llm_prompt import LLMPrompt
from pipelex.cogt.llm.llm_setting import LLMSetting
from pipelex.system.job_metadata import JobMetadata, RunMetadata
from pipelex.system.pipe_run_mode import PipeRunMode
from pipelex.tools.uri.uri_read_scope import UriReference

URL_FIELD_NAME = re.compile(r"(^|_)(uri|url)$")

# Run metadata and run parameters describe the run, not what it reads.
NON_PAYLOAD_FIELDS = frozenset({"job_metadata", "cogt_run_params"})

# Every URL-shaped field of every assignment, as a dotted path; a list's items are named by the list's field.
URL_FIELD_INVENTORY: dict[type[BaseModel], set[str]] = {
    LLMAssignment: {"llm_prompt.user_images.uri", "llm_prompt.user_documents.uri"},
    ObjectAssignment: {"llm_assignment_for_object.llm_prompt.user_images.uri", "llm_assignment_for_object.llm_prompt.user_documents.uri"},
    ImgGenAssignment: {"img_gen_prompt.input_images.uri"},
    TemplatingAssignment: set(),
    ExtractAssignment: {"extract_input.image_uri", "extract_input.document_uri"},
    RenderPageViewsAssignment: {"document_uri"},
    # A section's blocks hold blocks again: the walk names the images inside one section and stops where a section would enclose itself.
    RenderDocumentAssignment: {"composition.layout.blocks.url", "composition.layout.blocks.blocks.url"},
    SearchAssignment: set(),
    SearchObjectAssignment: set(),
    JudgmentAssignment: {"prompt.images.uri", "prompt.documents.uri"},
}


def _concrete_types(annotation: Any) -> list[Any]:
    """The concrete types an annotation admits, through Annotated, unions and generic containers."""
    origin = get_origin(annotation)
    if origin is Annotated:
        return _concrete_types(get_args(annotation)[0])
    if origin is None:
        return [annotation]
    if origin in {Union, types.UnionType, typing.Literal}:
        found: list[Any] = []
        for arg in get_args(annotation):
            found.extend(_concrete_types(arg))
        return found
    found = []
    for arg in get_args(annotation):
        found.extend(_concrete_types(arg))
    return found


def _url_field_paths(model_class: type[BaseModel], *, prefix: str = "", enclosing: frozenset[type] | None = None) -> set[str]:
    """The dotted paths of the URL-shaped fields under a model, not walking again into a model that encloses itself."""
    paths: set[str] = set()
    enclosing = (enclosing or frozenset()) | {model_class}
    for field_name, field_info in model_class.model_fields.items():
        if field_name in NON_PAYLOAD_FIELDS:
            continue
        for concrete_type in _concrete_types(field_info.annotation):
            if concrete_type is str and URL_FIELD_NAME.search(field_name):
                paths.add(f"{prefix}{field_name}")
            elif inspect.isclass(concrete_type) and issubclass(concrete_type, BaseModel) and concrete_type not in enclosing:
                paths |= _url_field_paths(concrete_type, prefix=f"{prefix}{field_name}.", enclosing=enclosing)
    return paths


def _assignment_classes() -> list[type[BaseModel]]:
    return [
        member
        for _, member in inspect.getmembers(assignment_models, inspect.isclass)
        if issubclass(member, BaseModel) and member.__module__ == assignment_models.__name__
    ]


def _job_metadata() -> JobMetadata:
    return JobMetadata(run_metadata=RunMetadata(user_id="u", pipeline_run_id="run_1", storage_scope="run_1", read_scope=None))


def _llm_assignment() -> LLMAssignment:
    return LLMAssignment(
        job_metadata=_job_metadata(),
        cogt_run_params=CogtRunParams(run_mode=PipeRunMode.DRY),
        llm_setting=LLMSetting(model="gpt-4o", temperature=0.5),
        llm_prompt=LLMPrompt(
            user_text="t",
            user_images=[PromptImageUri(uri="pipelex-storage://s/image_a.png"), PromptImageUri(uri="pipelex-storage://s/image_b.png")],
            user_documents=[PromptDocumentUri(uri="pipelex-storage://s/document_a.pdf")],
        ),
    )


class _Out(BaseModel):
    text: str


class _DeclaresReads(Protocol):
    def referenced_uris(self) -> list[UriReference]: ...


# One instance per URL-bearing assignment, with a distinct URL in every URL-shaped field.
URL_BEARING_SAMPLES: dict[type[BaseModel], tuple[_DeclaresReads, set[str]]] = {
    LLMAssignment: (
        _llm_assignment(),
        {"pipelex-storage://s/image_a.png", "pipelex-storage://s/image_b.png", "pipelex-storage://s/document_a.pdf"},
    ),
    ObjectAssignment: (
        ObjectAssignment.make_for_class(_Out, llm_assignment=_llm_assignment()),
        {"pipelex-storage://s/image_a.png", "pipelex-storage://s/image_b.png", "pipelex-storage://s/document_a.pdf"},
    ),
    ImgGenAssignment: (
        ImgGenAssignment(
            job_metadata=_job_metadata(),
            cogt_run_params=CogtRunParams(run_mode=PipeRunMode.DRY),
            img_gen_handle="h",
            img_gen_prompt=ImgGenPrompt(positive_text="p", input_images=[PromptImageUri(uri="pipelex-storage://s/input.png")]),
            img_gen_job_params=ImgGenJobParams(aspect_ratio=AspectRatio.SQUARE, background=Background.AUTO),
            img_gen_job_config=ImgGenJobConfig(is_sync_mode=True),
            nb_images=1,
        ),
        {"pipelex-storage://s/input.png"},
    ),
    ExtractAssignment: (
        ExtractAssignment(
            job_metadata=_job_metadata(),
            cogt_run_params=CogtRunParams(run_mode=PipeRunMode.DRY),
            extract_handle="h",
            extract_input=ExtractInput(document_uri="pipelex-storage://s/doc.pdf"),
            extract_job_params=ExtractJobParams.make_default_extract_job_params(),
            extract_job_config=ExtractJobConfig(),
        ),
        {"pipelex-storage://s/doc.pdf"},
    ),
    RenderPageViewsAssignment: (
        RenderPageViewsAssignment(
            job_metadata=_job_metadata(),
            cogt_run_params=CogtRunParams(run_mode=PipeRunMode.DRY),
            document_uri="pipelex-storage://s/doc.pdf",
            page_views_dpi=72,
        ),
        {"pipelex-storage://s/doc.pdf"},
    ),
    RenderDocumentAssignment: (
        RenderDocumentAssignment(
            job_metadata=_job_metadata(),
            cogt_run_params=CogtRunParams(run_mode=PipeRunMode.DRY),
            composition=DocumentComposition(
                format=DocGenFormat.PDF,
                source=DocGenSource.LAYOUT,
                filename="report.pdf",
                title="Report",
                layout=LayoutDocument(
                    title="Report",
                    blocks=[
                        ImageBlock(url="pipelex-storage://s/cover.png"),
                        SectionBlock(title="Figures", level=1, blocks=[ImageBlock(url="pipelex-storage://s/figure.png")]),
                    ],
                ),
            ),
            doc_gen_setting=DocGenSetting(model="reportlab-pdf"),
        ),
        {"pipelex-storage://s/cover.png", "pipelex-storage://s/figure.png"},
    ),
    JudgmentAssignment: (
        JudgmentAssignment(
            job_metadata=_job_metadata(),
            cogt_run_params=CogtRunParams(run_mode=PipeRunMode.DRY),
            prompt=JudgmentPrompt(
                text="Before: [Image 1] After: [Image 2] Claim: [Document 1], and the url https://example.com/in-the-text is data, never read",
                images=[PromptImageUri(uri="pipelex-storage://s/before.png"), PromptImageUri(uri="pipelex-storage://s/after.png")],
                documents=[PromptDocumentUri(uri="pipelex-storage://s/claim.pdf")],
            ),
            questions={"is_urgent": YesNoQuestion(instructions="Is it urgent?")},
            judgment_setting=JudgmentSetting(model="h"),
        ),
        {"pipelex-storage://s/before.png", "pipelex-storage://s/after.png", "pipelex-storage://s/claim.pdf"},
    ),
}


class TestAssignmentReadCoverage:
    def test_the_inventory_names_every_assignment(self) -> None:
        assert set(_assignment_classes()) == set(URL_FIELD_INVENTORY)

    def test_every_assignment_declares_what_it_reads(self) -> None:
        for assignment_class in _assignment_classes():
            assert "referenced_uris" in assignment_class.__dict__, f"{assignment_class.__name__} does not declare referenced_uris()"

    def test_the_url_fields_of_every_assignment_are_the_inventoried_ones(self) -> None:
        for assignment_class, inventoried_paths in URL_FIELD_INVENTORY.items():
            assert _url_field_paths(assignment_class) == inventoried_paths, assignment_class.__name__

    def test_every_url_bearing_assignment_has_a_sample(self) -> None:
        url_bearing = {assignment_class for assignment_class, paths in URL_FIELD_INVENTORY.items() if paths}
        assert url_bearing == set(URL_BEARING_SAMPLES)

    def test_referenced_uris_returns_every_url_the_sample_carries(self) -> None:
        for assignment_class, (sample, expected_uris) in URL_BEARING_SAMPLES.items():
            referenced_uris = sample.referenced_uris()
            assert {uri_reference.uri for uri_reference in referenced_uris} == expected_uris, assignment_class.__name__

    def test_the_extract_input_declares_an_image_too(self) -> None:
        referenced_uris = ExtractInput(image_uri="pipelex-storage://s/scan.png").referenced_uris()
        assert [uri_reference.uri for uri_reference in referenced_uris] == ["pipelex-storage://s/scan.png"]
