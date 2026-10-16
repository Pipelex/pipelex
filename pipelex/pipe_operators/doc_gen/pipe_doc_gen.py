from typing import TYPE_CHECKING, Any, Literal

from pydantic import Field, PrivateAttr
from typing_extensions import override

from pipelex import log
from pipelex.cogt.doc_gen.doc_gen_engine import require_doc_gen_engine_declared, resolve_doc_gen_setting
from pipelex.cogt.doc_gen.doc_gen_format import DocGenFormat, DocGenSource
from pipelex.cogt.doc_gen.doc_gen_setting import DocGenModelChoice, DocGenSetting
from pipelex.cogt.doc_gen.document_composition import ComposedTemplateFile, DocumentComposition, TemplateRenderContext
from pipelex.cogt.doc_gen.input_shape import InputShape, shape_of_input
from pipelex.cogt.doc_gen.layout_builder import build_layout_document, humanize
from pipelex.cogt.doc_gen.plain_data import plain_data
from pipelex.cogt.models.model_deck_check import check_doc_gen_choice_with_deck
from pipelex.cogt.templating.template_preprocessor import rewrite_template_sigils
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.method_trees.tree_bundle import MethodFileRef
from pipelex.core.pipes.inputs.input_stuff_specs import InputStuffSpecs
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.core.stuffs.document_content import DocumentContent
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.interpreter_hub import get_current_library, get_library_manager
from pipelex.kernel.compose_ops import build_compose_context
from pipelex.kernel.memory_ops import store_result
from pipelex.kernel.templating_style_ops import resolve_templating_style
from pipelex.pipe_machinery.template_guard_lint import lint_authored_template
from pipelex.pipe_operators.doc_gen.doc_gen_rendering import render_doc_gen_template
from pipelex.pipe_operators.doc_gen.exceptions import PipeDocGenRunError, PipeDocGenTemplateFileUncheckedError
from pipelex.pipe_operators.doc_gen.template_field_check import check_template_field_paths
from pipelex.pipe_operators.pipe_operator import PipeOperator
from pipelex.pipe_run.pipe_run_params import PipeRunParams
from pipelex.runtime_hub import get_class_registry, get_content_generator
from pipelex.system.job_metadata import JobMetadata
from pipelex.tools.jinja2.jinja2_required_variables import detect_jinja2_required_variables
from pipelex.tools.jinja2.template_category import TemplateCategory
from pipelex.tools.misc.string_utils import get_root_from_dotted_path
from pipelex.tools.storage.storage_file_name import path_safe_file_name
from pipelex.tools.templating.templating_style import TemplatingStyle

if TYPE_CHECKING:
    from pipelex.core.stuffs.stuff import Stuff


class PipeDocGenOutput(PipeOutput):
    pass


class PipeDocGen(PipeOperator[PipeDocGenOutput]):
    """Turn the step's inputs into a stored document file, in two stages. It calls no AI model.

    The **compose stage** is pure, and reads no file: it builds the layout tree of the inputs, or renders the inline
    HTML template, or names the template file, a file of the step's method tree, with what the print stage needs to
    use it, and it renders the filename, every template with a strict undefined so a missing field fails rather than
    printing as empty text. The **print stage** is the content generator's `make_rendered_document`, an activity on a
    hosted plane: it reads the template file through the method file store, renders an HTML one with the step's data,
    the step's engine prints the composition, and the bytes are stored through the run's storage provider as a
    `DocumentContent`. The engine is a `doc_gen` model, the one the step names or the model deck's default for its
    format and source, checked when the method loads. A dry run composes for real, which checks the templates against
    mock inputs; its print reads and renders the template file and runs the engine's template checker on an office
    one, and prints and stores nothing.
    """

    type: Literal["PipeDocGen"] = "PipeDocGen"
    doc_gen_format: DocGenFormat = Field(strict=False)
    doc_gen_choice: DocGenModelChoice | None = Field(default=None, description="The engine the step names, or None for the deck's default")
    template: str | None = Field(default=None, description="The inline HTML template of a pdf step")
    template_file: str | None = Field(default=None, description="The template file as the method names it")
    template_file_ref: MethodFileRef | None = Field(
        default=None, description="The template file as a file of the step's method tree, which the print stage reads"
    )
    filename: str | None = None

    # The text of an HTML template file, read when the step was built in a method tree this process holds, for the checks
    # of the method's load: a bundle's, or a crate's whose load validates it where a library holds its tree. None for a
    # step built from a crate by digest alone, which reads no file, and which a validation refuses rather than pass
    # unchecked (`validate_inputs_with_library`).
    _template_file_text: str | None = PrivateAttr(default=None)

    def hold_template_file_text(self, *, template_file_text: str) -> None:
        """Keep the text of the step's HTML template file, read at load, for the load's checks."""
        self._template_file_text = template_file_text

    @property
    def template_file_text(self) -> str | None:
        """The text of the step's HTML template file as the load read and checked it, or None when the load read none."""
        return self._template_file_text

    @property
    def _checked_html_template(self) -> tuple[str, str] | None:
        """The HTML template the load checks, with how a message names it: the inline one, or the file's text when read."""
        if self.template is not None:
            return self.template, "template"
        if self._template_file_text is not None:
            return self._template_file_text, f"template file '{self.template_file}'"
        return None

    @property
    def source(self) -> DocGenSource:
        return DocGenSource.for_step(doc_gen_format=self.doc_gen_format, has_template=self.template is not None or self.template_file is not None)

    @override
    def needed_inputs(self, *, visited_pipes: set[str] | None = None) -> InputStuffSpecs:
        return self.inputs

    @override
    def required_variables(self) -> set[str]:
        roots: set[str] = set()
        checked_html_template = self._checked_html_template
        html_template = checked_html_template[0] if checked_html_template is not None else None
        for template_source, category in ((html_template, TemplateCategory.HTML), (self.filename, TemplateCategory.BASIC)):
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
        checked_html_template = self._checked_html_template
        if checked_html_template is not None:
            html_template, html_template_label = checked_html_template
            lint_authored_template(
                pipe_code=self.code,
                domain_code=self.domain_code,
                inputs=self.inputs,
                template_source=html_template,
                template_category=TemplateCategory.HTML,
                template_label=html_template_label,
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
        # A step built from a crate by digest alone holds no text of its HTML template file, so no check of it ran: the
        # validation refuses rather than reach a verdict the template could contradict. A load that skips validation,
        # such as a worker's load of the crate a validated library made, never gets here.
        if self.template_file is not None and self.doc_gen_format.is_template_html and self._template_file_text is None:
            msg = (
                f"PipeDocGen '{self.code}' prints from the HTML template file '{self.template_file}', which this validation "
                "cannot check: the step was built from a library crate, which names its method tree by digest and carries "
                "none of its files, and no library of this process holds that tree. Validate the method where its files are."
            )
            raise PipeDocGenTemplateFileUncheckedError(msg)
        # Every field a template reads exists on its input's concept, which is known once the library is loaded.
        checked_html_template = self._checked_html_template
        if checked_html_template is not None:
            html_template, html_template_label = checked_html_template
            check_template_field_paths(
                pipe_code=self.code,
                template_source=html_template,
                template_category=TemplateCategory.HTML,
                label=html_template_label,
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
        return await render_doc_gen_template(
            pipe_code=self.code, template=template, category=category, context=context, label=label, templating_style=templating_style
        )

    async def compose(self, *, working_memory: WorkingMemory, pipe_run_params: PipeRunParams) -> DocumentComposition:
        """The pure half of the step: everything the print stage needs, and nothing printed yet.

        It reads no file, so it runs where the step runs, in a workflow on a hosted plane. An inline HTML template is
        rendered here, its text being the bundle's own; a template file is named by its tree's digest and its tree path,
        for the print stage to read it: an HTML one with the step's data and the run's crate, which the print stage
        renders it with, an office one with the step's data as plain data and the shapes of its inputs.
        """
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
        # Stored under a name every `pipelex-storage://` reader serves, the hosted platform's included.
        filename = path_safe_file_name(name=rendered_filename, fallback=self.code, extension=self.doc_gen_format.suffix)
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
                if self.template is not None:
                    html = await self._render(
                        template=self.template,
                        category=TemplateCategory.HTML,
                        context=context,
                        label="template",
                        templating_style=resolve_templating_style(authored=None),
                    )
                    return DocumentComposition(format=self.doc_gen_format, source=source, filename=filename, title=title, html=html)
                return DocumentComposition(
                    format=self.doc_gen_format,
                    source=source,
                    filename=filename,
                    title=title,
                    template_file=self._composed_template_file(
                        render_context=self._render_context(working_memory=working_memory, pipe_run_params=pipe_run_params)
                    ),
                )
            case DocGenSource.TEMPLATE_FILE:
                return DocumentComposition(
                    format=self.doc_gen_format,
                    source=source,
                    filename=filename,
                    title=title,
                    template_file=self._composed_template_file(input_shapes=self._input_shapes()),
                    data={name: plain_data(content) for name, content in named_contents},
                )

    def _composed_template_file(
        self, *, render_context: TemplateRenderContext | None = None, input_shapes: dict[str, InputShape] | None = None
    ) -> ComposedTemplateFile:
        """The step's template file as its print stage reads it.

        Raises:
            PipeDocGenRunError: The step names no template file in its method tree.
        """
        if self.template_file is None or self.template_file_ref is None:
            msg = f"PipeDocGen '{self.code}' prints from a template file but names none in its method tree."
            raise PipeDocGenRunError(msg)
        return ComposedTemplateFile(
            file=self.template_file_ref,
            name=self.template_file,
            pipe_ref=self.pipe_ref,
            render_context=render_context,
            input_shapes=input_shapes or {},
        )

    def _render_context(self, *, working_memory: WorkingMemory, pipe_run_params: PipeRunParams) -> TemplateRenderContext:
        """What the print stage renders the step's HTML template file with, wherever it runs.

        Only the stuffs the step's inputs name travel, under those names: the load checked that the template reads no other
        variable but the run's params. The run's crate travels as its concepts and domains alone, which type them.

        Raises:
            PipeDocGenRunError: The library the step runs in has no crate.
        """
        library_id = get_current_library()
        crate = get_library_manager().get_crate(library_id=library_id)
        if crate is None:
            msg = f"PipeDocGen '{self.code}' cannot name its template file's data: the library it runs in has no crate."
            raise PipeDocGenRunError(msg)
        input_stuffs: dict[str, Stuff] = {}
        for input_name in self.inputs.variables:
            stuff = working_memory.get_optional_stuff(input_name)
            if stuff is not None:
                input_stuffs[input_name] = stuff
        return TemplateRenderContext(
            crate_fingerprint=crate.fingerprint,
            concepts_crate=crate.concepts_only().model_dump(mode="json"),
            working_memory_raw=WorkingMemory(root=input_stuffs).dump_for_transport(),
            runtime_params=dict(pipe_run_params.params),
        )

    def _input_shapes(self) -> dict[str, InputShape]:
        shapes: dict[str, InputShape] = {}
        for input_name, stuff_spec in self.inputs.root.items():
            content_class: type[StuffContent] | None = None
            if stuff_spec.concept.declares_a_structure_class:
                content_class = get_class_registry().get_required_subclass(name=stuff_spec.concept.structure_class_name, base_class=StuffContent)
            shapes[input_name] = shape_of_input(content_class=content_class, is_list=stuff_spec.is_multiple())
        return shapes

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
        # inputs, which checks the inline templates, and the leaf reads and checks the template file, rendering an HTML
        # one and handing an office one to its engine's checker, and prints and stores nothing.
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
