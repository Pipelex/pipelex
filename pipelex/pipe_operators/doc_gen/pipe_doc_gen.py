import asyncio
import re
from pathlib import Path
from typing import Any, Literal

from jinja2.exceptions import UndefinedError
from pydantic import Field
from typing_extensions import override

from pipelex import log
from pipelex.cogt.doc_gen.doc_gen_engine import require_doc_gen_engine_declared, resolve_doc_gen_setting
from pipelex.cogt.doc_gen.doc_gen_format import DocGenFormat, DocGenSource
from pipelex.cogt.doc_gen.doc_gen_setting import DocGenModelChoice, DocGenSetting
from pipelex.cogt.doc_gen.doc_gen_worker_factory import DocGenWorkerFactory
from pipelex.cogt.doc_gen.document_composition import DocumentComposition
from pipelex.cogt.doc_gen.input_shape import InputShape, shape_of_input
from pipelex.cogt.doc_gen.layout_builder import build_layout_document, humanize
from pipelex.cogt.doc_gen.plain_data import plain_data
from pipelex.cogt.doc_gen.template_check import TemplateCheckRequest
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.cogt.models.model_deck_check import check_doc_gen_choice_with_deck
from pipelex.cogt.templating.template_preprocessor import rewrite_template_sigils
from pipelex.cogt.templating.template_rendering import render_template
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.pipes.inputs.input_stuff_specs import InputStuffSpecs
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.core.stuffs.document_content import DocumentContent
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.kernel.compose_ops import build_compose_context
from pipelex.kernel.memory_ops import store_result
from pipelex.kernel.templating_style_ops import resolve_templating_style
from pipelex.pipe_machinery.template_guard_lint import lint_authored_template
from pipelex.pipe_operators.doc_gen.exceptions import PipeDocGenRunError, PipeDocGenTemplateCheckError, PipeDocGenUndefinedValueError
from pipelex.pipe_operators.doc_gen.template_field_check import check_template_field_paths
from pipelex.pipe_operators.pipe_operator import PipeOperator
from pipelex.pipe_run.pipe_run_params import PipeRunParams
from pipelex.runtime_hub import get_class_registry, get_content_generator, get_model_deck, get_report_delegate
from pipelex.system.job_metadata import JobMetadata
from pipelex.tools.jinja2.exceptions import Jinja2TemplateRenderError
from pipelex.tools.jinja2.jinja2_required_variables import detect_jinja2_required_variables
from pipelex.tools.jinja2.template_category import TemplateCategory
from pipelex.tools.misc.string_utils import get_root_from_dotted_path
from pipelex.tools.templating.templating_style import TemplatingStyle

_UNSAFE_FILENAME_CHARACTERS = re.compile(r"[^\w.\-]+")
_MAX_FILENAME_STEM_LENGTH = 120


def safe_filename(*, rendered: str, fallback: str, suffix: str) -> str:
    """One storage-safe path segment ending in the format's suffix, from whatever the filename template rendered."""
    stem = _UNSAFE_FILENAME_CHARACTERS.sub("-", rendered.strip()).strip(".-_")
    if stem.lower().endswith(f".{suffix}"):
        stem = stem[: -(len(suffix) + 1)]
    stem = stem[:_MAX_FILENAME_STEM_LENGTH].strip(".-_") or fallback
    return f"{stem}.{suffix}"


class PipeDocGenOutput(PipeOutput):
    pass


class PipeDocGen(PipeOperator[PipeDocGenOutput]):
    """Turn the step's inputs into a stored document file, in two stages. It calls no AI model.

    The **compose stage** is pure: it builds the layout tree of the inputs, or renders the HTML template, or
    gathers the inputs as plain data for a template file, and it renders the filename, every template with a
    strict undefined so a missing field fails rather than printing as empty text. The **print stage** is the
    content generator's `make_rendered_document`: the step's engine prints the composition, and the bytes are
    stored through the run's storage provider as a `DocumentContent`. The engine is a `doc_gen` model, the one the
    step names or the model deck's default for its format and source, checked when the method loads. A dry run
    composes for real, which checks the templates against mock inputs, runs the engine's template checker on a
    template file, and prints and stores nothing.
    """

    type: Literal["PipeDocGen"] = "PipeDocGen"
    doc_gen_format: DocGenFormat = Field(strict=False)
    doc_gen_choice: DocGenModelChoice | None = Field(default=None, description="The engine the step names, or None for the deck's default")
    template: str | None = Field(default=None, description="The HTML template of a pdf step, inline or read from its template file")
    template_file: str | None = Field(default=None, description="The template file as the method names it")
    template_path: str | None = Field(default=None, description="The resolved path of an office template file, which its engine fills")
    filename: str | None = None

    @property
    def source(self) -> DocGenSource:
        return DocGenSource.for_step(doc_gen_format=self.doc_gen_format, has_template=self.template is not None or self.template_path is not None)

    @override
    def needed_inputs(self, *, visited_pipes: set[str] | None = None) -> InputStuffSpecs:
        return self.inputs

    @override
    def required_variables(self) -> set[str]:
        roots: set[str] = set()
        for template_source, category in ((self.template, TemplateCategory.HTML), (self.filename, TemplateCategory.BASIC)):
            if template_source is None:
                continue
            for path in detect_jinja2_required_variables(template_category=category, template_source=rewrite_template_sigils(template_source)):
                root = get_root_from_dotted_path(path)
                if not root.startswith("_") and root != "place_holder":
                    roots.add(root)
        return roots

    def resolve_engine(self) -> DocGenSetting:
        """The engine this step prints on, resolved in the model deck and checked to print its format from its source here."""
        return resolve_doc_gen_setting(
            doc_gen_choice=self.doc_gen_choice, doc_gen_format=self.doc_gen_format, source=self.source, pipe_code=self.code
        )

    @override
    def validate_inputs_static(self):
        # The engine is resolved when the method loads, so a step no engine here prints is refused before a run spends anything.
        if self.doc_gen_choice is not None:
            with self.locating_model_choice(field_name="model"):
                # The built-in engine or one of the plugin's, named where this installation does not declare it, is refused
                # naming its remedy before the deck check would call it an unknown model.
                require_doc_gen_engine_declared(
                    doc_gen_choice=self.doc_gen_choice, doc_gen_format=self.doc_gen_format, source=self.source, pipe_code=self.code
                )
                check_doc_gen_choice_with_deck(doc_gen_choice=self.doc_gen_choice)
        self.resolve_engine()

        # The same template lints as PipeCompose: no private names, and every reference to a declared-optional input
        # guarded. The filename gets both too, since it renders as strictly as the template does.
        if self.template is not None:
            lint_authored_template(
                pipe_code=self.code,
                domain_code=self.domain_code,
                inputs=self.inputs,
                template_source=self.template,
                template_category=TemplateCategory.HTML,
                template_label=f"template file '{self.template_file}'" if self.template_file is not None else "template",
            )
        if self.filename is not None:
            lint_authored_template(
                pipe_code=self.code,
                domain_code=self.domain_code,
                inputs=self.inputs,
                template_source=self.filename,
                template_category=TemplateCategory.BASIC,
                template_label="filename",
            )

    @override
    def validate_inputs_with_library(self):
        # Every field a template reads exists on its input's concept, which is known once the library is loaded.
        if self.template is not None:
            check_template_field_paths(
                pipe_code=self.code,
                template_source=self.template,
                template_category=TemplateCategory.HTML,
                label=f"template file '{self.template_file}'" if self.template_file is not None else "template",
                inputs=self.inputs,
            )
        if self.filename is not None:
            check_template_field_paths(
                pipe_code=self.code,
                template_source=self.filename,
                template_category=TemplateCategory.BASIC,
                label="filename",
                inputs=self.inputs,
            )

    @override
    def validate_output_static(self):
        pass

    @override
    def validate_output_with_library(self):
        pass

    ####################################################################################################################
    # Compose stage
    ####################################################################################################################

    def _named_contents(self, working_memory: WorkingMemory) -> list[tuple[str, StuffContent]]:
        """The declared inputs present in memory, in declared order; an absent optional input is skipped."""
        named_contents: list[tuple[str, StuffContent]] = []
        for input_name in self.inputs.variables:
            stuff = working_memory.get_optional_stuff(input_name)
            if stuff is not None:
                named_contents.append((input_name, stuff.content))
        return named_contents

    def _title(self, named_contents: list[tuple[str, StuffContent]]) -> str:
        """The document's title: its one input's name, or the step's code when it has several."""
        if len(named_contents) == 1:
            return humanize(named_contents[0][0])
        return humanize(self.code)

    async def _render(
        self, *, template: str, category: TemplateCategory, context: dict[str, Any], label: str, templating_style: TemplatingStyle | None = None
    ) -> str:
        try:
            return await render_template(
                template=template,
                category=category,
                context=context,
                templating_style=templating_style,
                is_undefined_strict=True,
            )
        except Jinja2TemplateRenderError as exc:
            undefined_error = exc.__cause__
            if isinstance(undefined_error, UndefinedError):
                # Raised from Jinja's own error rather than from the tools-layer wrapper, whose message quotes the
                # template and is not caller-facing, so that this is the root fault a verdict or a run report names.
                msg = (
                    f"PipeDocGen '{self.code}' could not render its {label}: {undefined_error.message}. "
                    "Every value a document's template reads must exist: check the name against the input's concept, "
                    "or test an optional value first with {% if ... %}."
                )
                raise PipeDocGenUndefinedValueError(msg) from undefined_error
            msg = f"PipeDocGen '{self.code}' could not render its {label}: {exc}"
            raise PipeDocGenRunError(msg) from exc

    async def compose(self, *, working_memory: WorkingMemory, pipe_run_params: PipeRunParams) -> DocumentComposition:
        """The pure half of the step: everything the print stage needs, and nothing printed yet."""
        context = build_compose_context(memory=working_memory, runtime_params=pipe_run_params.params)
        rendered_filename = self.code
        if self.filename is not None:
            # A `$name` sigil in the filename expands to the `format` filter, which prints under the render's templating style.
            rendered_filename = await self._render(
                template=self.filename,
                category=TemplateCategory.BASIC,
                context=context,
                label="filename",
                templating_style=resolve_templating_style(authored=None),
            )
        filename = safe_filename(rendered=rendered_filename, fallback=self.code, suffix=self.doc_gen_format.suffix)
        named_contents = self._named_contents(working_memory)
        title = self._title(named_contents)
        source = self.source
        match source:
            case DocGenSource.LAYOUT:
                return DocumentComposition(
                    format=self.doc_gen_format,
                    source=source,
                    filename=filename,
                    title=title,
                    layout=build_layout_document(title=title, named_contents=named_contents),
                )
            case DocGenSource.HTML:
                if self.template is None:
                    msg = f"PipeDocGen '{self.code}' composes from HTML but has no HTML template."
                    raise PipeDocGenRunError(msg)
                html = await self._render(
                    template=self.template,
                    category=TemplateCategory.HTML,
                    context=context,
                    label="template",
                    templating_style=resolve_templating_style(authored=None),
                )
                return DocumentComposition(format=self.doc_gen_format, source=source, filename=filename, title=title, html=html)
            case DocGenSource.TEMPLATE_FILE:
                return DocumentComposition(
                    format=self.doc_gen_format,
                    source=source,
                    filename=filename,
                    title=title,
                    template_path=self.template_path,
                    template_name=self.template_file,
                    data={name: plain_data(content) for name, content in named_contents},
                )

    ####################################################################################################################
    # Template file check, at the dry run
    ####################################################################################################################

    def _input_shapes(self) -> dict[str, InputShape]:
        shapes: dict[str, InputShape] = {}
        for input_name, stuff_spec in self.inputs.root.items():
            content_class: type[StuffContent] | None = None
            if stuff_spec.concept.declares_a_structure_class:
                content_class = get_class_registry().get_required_subclass(name=stuff_spec.concept.structure_class_name, base_class=StuffContent)
            shapes[input_name] = shape_of_input(content_class=content_class, is_list=stuff_spec.is_multiple())
        return shapes

    async def check_template_file(self, *, working_memory: WorkingMemory) -> None:
        """Run the engine's template checker on the step's template file, when its engine has one.

        The inputs in memory are the dry run's mocks, so the checker can fill the template in memory with them.

        Raises:
            PipeDocGenTemplateCheckError: the checker reported errors.
        """
        if self.template_path is None or self.template_file is None:
            return
        doc_gen_setting = self.resolve_engine()
        inference_model = get_model_deck().get_required_inference_model(model_handle=doc_gen_setting.model, model_type=ModelType.DOC_GEN)
        worker = DocGenWorkerFactory.make_doc_gen_worker(inference_model=inference_model, reporting_delegate=get_report_delegate())
        request = TemplateCheckRequest(
            format=self.doc_gen_format,
            template=Path(self.template_path).read_bytes(),
            template_name=self.template_file,
            inputs=self._input_shapes(),
            data={name: plain_data(content) for name, content in self._named_contents(working_memory)},
        )
        findings = await asyncio.to_thread(worker.check_template, request=request)
        errors = [finding for finding in findings if finding.severity.is_error]
        for finding in findings:
            if not finding.severity.is_error:
                finding_fields: dict[str, str] = {"pipe_code": self.code, "template_file": self.template_file, "finding_message": finding.message}
                if finding.location:
                    finding_fields["finding_location"] = finding.location
                log.warning("The template check of a PipeDocGen found a warning in its template file", fields=finding_fields)
        if errors:
            listed = "\n".join(f"- {finding.message}" + (f" ({finding.location})" if finding.location else "") for finding in errors)
            msg = f"PipeDocGen '{self.code}': the template file '{self.template_file}' does not fit the step's inputs:\n{listed}"
            raise PipeDocGenTemplateCheckError(msg)

    ####################################################################################################################
    # Runs
    ####################################################################################################################

    def _store_document(
        self,
        *,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        document: DocumentContent,
        doc_gen_setting: DocGenSetting,
        output_name: str | None,
    ) -> PipeDocGenOutput:
        # The output concept refines Document, so its class is DocumentContent or a subclass of it.
        output_class = get_class_registry().get_required_subclass(name=self.output.concept.structure_class_name, base_class=DocumentContent)
        content = output_class.model_validate(document.model_dump())
        working_memory = store_result(memory=working_memory, concept=self.output.concept, content=content, result_name=output_name)
        self._register_execution_data(
            job_metadata=job_metadata,
            execution_data={
                "format": self.doc_gen_format,
                "source": self.source,
                "resolved_model": doc_gen_setting.model,
                "filename": document.filename,
                "url": document.url,
            },
        )
        return PipeDocGenOutput(working_memory=working_memory, pipeline_run_id=job_metadata.run_metadata.pipeline_run_id)

    @override
    async def _live_run_operator_pipe(
        self,
        *,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
        output_name: str | None = None,
    ) -> PipeDocGenOutput:
        composition = await self.compose(working_memory=working_memory, pipe_run_params=pipe_run_params)
        doc_gen_setting = self.resolve_engine()
        document = await get_content_generator().make_rendered_document(
            job_metadata=job_metadata,
            cogt_run_params=pipe_run_params.cogt_run_params,
            composition=composition,
            doc_gen_setting=doc_gen_setting,
        )
        log.verbose(f"PipeDocGen '{self.code}' stored {document.filename} at {document.url}")
        return self._store_document(
            job_metadata=job_metadata,
            working_memory=working_memory,
            document=document,
            doc_gen_setting=doc_gen_setting,
            output_name=output_name,
        )

    @override
    async def _dry_run_operator_pipe(
        self,
        *,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
        output_name: str | None = None,
    ) -> PipeDocGenOutput:
        # The live path with the dry mode riding into the leaf: the compose stage runs for real against the mock
        # inputs, which checks the templates, and the leaf prints and stores nothing. The template file's checker
        # runs first, since only a dry run has inputs to fill it with and nothing to spend.
        await self.check_template_file(working_memory=working_memory)
        return await self._live_run_operator_pipe(
            job_metadata=job_metadata,
            working_memory=working_memory,
            pipe_run_params=pipe_run_params,
            output_name=output_name,
        )

    @override
    async def _validate_before_run(
        self, *, job_metadata: JobMetadata, working_memory: WorkingMemory, pipe_run_params: PipeRunParams, output_name: str | None = None
    ):
        pass

    @override
    async def _validate_after_run(
        self, *, job_metadata: JobMetadata, working_memory: WorkingMemory, pipe_run_params: PipeRunParams, output_name: str | None = None
    ):
        pass
