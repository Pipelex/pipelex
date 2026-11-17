from typing import Any, Final, Literal, NoReturn, TypeAlias

from mthds.protocol.problem.registry import CoreCode, MethodOutputMultiplicityMismatchExpected
from typing_extensions import override

from pipelex import log
from pipelex.cogt.content_generation.dry_mock import build_mock_object
from pipelex.cogt.doc_gen.sheet_range import SheetRange
from pipelex.cogt.exceptions import LLMCompletionError, ModelChoiceNotFoundError
from pipelex.cogt.llm.llm_setting import LLMModelChoice, LLMSetting
from pipelex.cogt.llm.unrendered_llm_prompt import UnrenderedLLMPrompt
from pipelex.cogt.models.model_deck_check import check_llm_choice_with_deck
from pipelex.cogt.templating.template_blueprint import TemplateBlueprint
from pipelex.config import get_config
from pipelex.core.concepts.exceptions import ConceptStructureClassNotFoundError
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.pipes.exceptions import PipeRunError, PipeValidationError
from pipelex.core.pipes.inputs.input_stuff_specs import InputStuffSpecs
from pipelex.core.pipes.inputs.input_stuff_specs_factory import InputStuffSpecsFactory
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.core.pipes.variable_multiplicity import VariableMultiplicity, multiplicity_kind
from pipelex.core.stuffs.document_content import DocumentContent
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.interpreter_hub import get_concept_library, get_native_concept
from pipelex.kernel.llm_ops import concrete_llm_model_handle, derive_structure_prompt, generate_object_content, resolve_llm_setting_for_object
from pipelex.kernel.memory_ops import store_result
from pipelex.kernel.templating_style_ops import resolve_templating_style
from pipelex.pipe_operators.pipe_operator import PipeOperator
from pipelex.pipe_operators.shared.llm_setting_check import refuse_llm_setting_its_model_refuses
from pipelex.pipe_run.pipe_run_params import PipeRunParams, output_multiplicity_to_apply
from pipelex.runtime_hub import get_class_registry, get_content_generator, get_memory_transport
from pipelex.system.job_metadata import JobMetadata
from pipelex.tools.jinja2.template_category import TemplateCategory
from pipelex.tools.jinja2.template_owner import TemplateOwner
from pipelex.tools.tabular.csv_codec import flat_field_names
from pipelex.tools.tabular.exceptions import CsvError, CsvFlatnessError
from pipelex.tools.tabular.table_reader import locate_table_error, table_subject
from pipelex.tools.tabular.table_records import TableBinding, admits_integer, list_content_from_table_records
from pipelex.tools.tabular.table_selector import TableSelector
from pipelex.validation_error_types import PipeValidationErrorType

# The structure class each row of a spreadsheet is bound to, named outside the class, whose `type` field shadows the builtin.
RowModel: TypeAlias = type[StuffContent]

# How the node's execution data names the spreadsheet path, beside the Text path's `structure`.
SPREADSHEET_STRUCTURING_PATH: Final[str] = "table_read"
# The name the structuring prompt template (`structuring_prompt` in the LLM config) reads the source text by.
STRUCTURING_PROMPT_SOURCE_NAME: Final[str] = "text"


class PipeStructureOutput(PipeOutput):
    pass


class PipeStructure(PipeOperator[PipeStructureOutput]):
    """Turns its single input into structured data, by one of two paths the input's concept decides.

    - **The Text path**, when the input is `Text` or refines it: a model structures the text into the output concept.
    - **The spreadsheet path**, when the input is `Document` or refines it: the runtime reads one table of the file, an
      Excel workbook or a CSV file, into the output list, one item per data row, calling no model. The read is a leaf of
      the content generator (`ContentGeneratorProtocol.read_table`), since it reads storage, and its records are bound
      to the output concept here (`pipelex.tools.tabular.table_records`). `table_name` names the Excel Table or the named
      range, `sheet_range` a range on a sheet, at most one of the two, and `row_field` the output field that receives
      each row's position. The output must be a variable list of a flat
      concept, and `model` is refused. A dry run reads nothing and mocks the records.
    """

    type: Literal["PipeStructure"] = "PipeStructure"
    llm_choice: LLMModelChoice | None = None
    source_input_name: str
    table_name: str | None = None
    sheet_range: SheetRange | None = None
    row_field: str | None = None
    output_multiplicity: VariableMultiplicity | None = None

    @override
    def needed_inputs(self, *, visited_pipes: set[str] | None = None) -> InputStuffSpecs:
        needed_inputs = InputStuffSpecsFactory.make_empty()
        for input_name, stuff_spec in self.inputs.items:
            needed_inputs.add_stuff_spec(
                variable_name=input_name, concept=stuff_spec.concept, multiplicity=stuff_spec.multiplicity, presence=stuff_spec.presence
            )
        return needed_inputs

    @override
    def required_variables(self) -> set[str]:
        return {self.source_input_name}

    @override
    def validate_inputs_static(self):
        if self.llm_choice is not None and not isinstance(self.llm_choice, LLMSetting):
            with self.locating_model_choice(field_name="model"):
                check_llm_choice_with_deck(llm_choice=self.llm_choice)

    @override
    def validate_inputs_with_library(self):
        the_single_input = self.inputs.get_single_stuff_spec()
        text_concept = get_native_concept(native_concept=NativeConceptCode.TEXT)
        document_concept = get_native_concept(native_concept=NativeConceptCode.DOCUMENT)
        if self.reads_document():
            if self.llm_choice is not None:
                self._refuse_field(
                    field_name="model",
                    finding="a PipeStructure reading a spreadsheet calls no model, so it takes no model",
                )
            return
        if get_concept_library().is_compatible(tested_concept=the_single_input.concept, wanted_concept=text_concept, strict=False):
            for field_name, field_value in (("table", self.table_name), ("sheet_range", self.sheet_range), ("row_field", self.row_field)):
                if field_value is not None:
                    self._refuse_field(
                        field_name=field_name,
                        finding=f"'{field_name}' applies only to a PipeStructure reading a spreadsheet, whose input is a Document",
                    )
            return
        msg = (
            f"PipeStructure input must be Text-compatible (a concept that refines Text) or Document-compatible "
            f"(a concept that refines Document), but got '{the_single_input.concept.concept_ref}'."
        )
        raise PipeValidationError(
            message=msg,
            error_type=PipeValidationErrorType.INPUT_STUFF_SPEC_MISMATCH,
            domain_code=self.domain_code,
            pipe_code=self.code,
            provided_concept_code=the_single_input.concept.concept_ref,
        ).with_params(
            input=next(iter(self.inputs.root)),
            declared=the_single_input.concept.concept_ref,
            expected=[text_concept.concept_ref, document_concept.concept_ref],
        )

    def reads_document(self) -> bool:
        """Whether this step reads a spreadsheet: its single input is not Text-compatible and is a `Document` or refines it.

        Being a `Document` is decided by lineage, never by shape: the input's structure class must be `DocumentContent` or
        a class refining it, as the class of a concept refining `Document` is at any depth. The library's loose
        compatibility would also take a concept that merely holds a `Document` in one of its fields, which no spreadsheet
        is read from.

        Needs the library, which resolves the input's concept.
        """
        input_concept = self.inputs.get_single_stuff_spec().concept
        concept_library = get_concept_library()
        text_concept = get_native_concept(native_concept=NativeConceptCode.TEXT)
        if concept_library.is_compatible(tested_concept=input_concept, wanted_concept=text_concept, strict=False):
            return False
        if not input_concept.declares_a_structure_class:
            return False
        return issubclass(concept_library.get_structure_class(concept=input_concept), DocumentContent)

    def _refuse_field(self, *, field_name: str, finding: str) -> NoReturn:
        """Refuse a field of this step that breaks a rule of the language, located at the field's key path."""
        msg = f"PipeStructure '{self.code}': {finding}."
        raise PipeValidationError(
            message=msg,
            domain_code=self.domain_code,
            pipe_code=self.code,
            field_name=field_name,
        ).with_params(field_path=f"pipe.{self.code}.{field_name}", finding=finding)

    @property
    def table_selector(self) -> TableSelector:
        """The step's choice of the rows of a workbook it reads, as the content generator's leaf carries it."""
        return TableSelector(table=self.table_name, sheet_range=self.sheet_range)

    @property
    def _sheet_range_data(self) -> dict[str, Any] | None:
        """The sheet range as the node's execution data records it."""
        return self.sheet_range.model_dump() if self.sheet_range is not None else None

    def row_model(self) -> RowModel:
        """The structure class of the output concept, which each row of a spreadsheet is bound to."""
        return get_class_registry().get_required_subclass(
            name=self.output.concept.structure_class_name,
            base_class=StuffContent,
        )

    @override
    def validate_output_static(self):
        pass

    @override
    def validate_output_with_library(self):
        text_concept = get_native_concept(native_concept=NativeConceptCode.TEXT)
        if get_concept_library().is_compatible(
            tested_concept=self.output.concept,
            wanted_concept=text_concept,
            strict=False,
        ):
            msg = f"PipeStructure output must be a structured concept, not Text-compatible. Got '{self.output.concept.concept_ref}'."
            raise PipeValidationError(
                message=msg,
                error_type=PipeValidationErrorType.INADEQUATE_OUTPUT_CONCEPT,
                domain_code=self.domain_code,
                pipe_code=self.code,
                provided_concept_code=self.output.concept.concept_ref,
            ).with_params(declared=self.output.concept.concept_ref, pipe_type=self.type)

        if self.reads_document():
            self._validate_spreadsheet_output()
            return

        # A reference the deck does not define is refused when the pipe is built, so it is not looked up again here
        try:
            llm_setting_for_object = resolve_llm_setting_for_object(llm_choice=self.llm_choice)
        except ModelChoiceNotFoundError:
            return
        refuse_llm_setting_its_model_refuses(
            pipe_type=self.class_name,
            pipe_code=self.code,
            domain_code=self.domain_code,
            llm_setting=llm_setting_for_object,
            llm_choice=self.llm_choice,
            field_name="model" if self.llm_choice is not None else None,
            is_structured=True,
        )

    def _validate_spreadsheet_output(self) -> None:
        """The output rules of the spreadsheet path: a variable list of a flat structured concept, and a row field that holds a number.

        Raises:
            PipeValidationError: The output is not a variable list, its concept declares no structure or a field no
                cell converts to, or `row_field` names no integer or number field of it.
        """
        declared_multiplicity = multiplicity_kind(multiplicity=self.output.multiplicity)
        is_variable_list: bool
        match declared_multiplicity:
            case MethodOutputMultiplicityMismatchExpected.LIST:
                is_variable_list = True
            case MethodOutputMultiplicityMismatchExpected.SINGLE | MethodOutputMultiplicityMismatchExpected.FIXED:
                is_variable_list = False
        if not is_variable_list:
            msg = (
                f"PipeStructure '{self.code}' reads a spreadsheet into a list whose length is the table's, "
                f"so its output must be a variable list ('{self.output.concept.code}[]'), got '{declared_multiplicity}'."
            )
            raise PipeValidationError(
                message=msg,
                error_type=PipeValidationErrorType.INADEQUATE_OUTPUT_MULTIPLICITY,
                domain_code=self.domain_code,
                pipe_code=self.code,
            ).with_params(declared=declared_multiplicity, expected=MethodOutputMultiplicityMismatchExpected.LIST)

        structure_finding = "the output concept declares no structure, so a row has no fields to read into"
        output_concept = self.output.concept
        if not output_concept.declares_a_structure_class:
            self._refuse_field(field_name="output", finding=structure_finding)
        try:
            row_model = get_concept_library().get_structure_class(concept=output_concept)
        except ConceptStructureClassNotFoundError:
            self._refuse_field(field_name="output", finding=structure_finding)
        if not issubclass(row_model, StructuredContent):
            self._refuse_field(field_name="output", finding=structure_finding)
        try:
            field_names = flat_field_names(row_model)
        except CsvFlatnessError:
            self._refuse_field(
                field_name="output",
                finding=(
                    "a row's fields must each be text, integer, number, boolean, date, datetime or choices, "
                    f"and concept '{output_concept.concept_ref}' declares another kind of field"
                ),
            )

        if self.row_field is None:
            return
        if self.row_field not in field_names:
            self._refuse_field(
                field_name="row_field",
                finding=f"'{self.row_field}' is not a field of the output concept '{output_concept.concept_ref}'",
            )
        if not admits_integer(annotation=row_model.model_fields[self.row_field].annotation):
            self._refuse_field(
                field_name="row_field",
                finding=f"the row field '{self.row_field}' receives each row's position, so it must be an integer or a number field",
            )

    @override
    async def _dry_run_operator_pipe(
        self,
        *,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
        output_name: str | None = None,
    ) -> PipeStructureOutput:
        """The Text path's dry run reuses the live path, whose leaf mocks; the spreadsheet path reads nothing and mocks the records."""
        if not self.reads_document():
            return await super()._dry_run_operator_pipe(
                job_metadata=job_metadata, working_memory=working_memory, pipe_run_params=pipe_run_params, output_name=output_name
            )
        self._refuse_output_multiplicity_override(pipe_run_params=pipe_run_params)
        row_model = self.row_model()
        nb_records = get_config().inference.dry_run.nb_list_items
        mock_records: list[StuffContent] = []
        for position in range(1, nb_records + 1):
            pinned_values: dict[str, Any] = {self.row_field: position} if self.row_field is not None else {}
            mock_records.append(build_mock_object(row_model, **pinned_values))
        working_memory = store_result(
            memory=working_memory,
            concept=self.output.concept,
            content=ListContent(items=mock_records),
            result_name=output_name,
            result_code=pipe_run_params.final_stuff_code,
        )
        self._register_execution_data(
            job_metadata=job_metadata,
            execution_data={
                "is_multiple_output": True,
                "structuring_path": SPREADSHEET_STRUCTURING_PATH,
                "table": self.table_name,
                "sheet_range": self._sheet_range_data,
            },
        )
        return PipeStructureOutput(
            working_memory=working_memory,
            pipeline_run_id=job_metadata.run_metadata.pipeline_run_id,
        )

    def _refuse_output_multiplicity_override(self, *, pipe_run_params: PipeRunParams) -> None:
        """Refuse a run asking this spreadsheet step for anything but its variable list, as a step's `nb_output` or `multiple_output` can.

        The table decides how many records the step outputs, so neither a single output nor a fixed count can be honoured.

        Raises:
            PipeRunError: The resolved multiplicity is a single output or a fixed count.
        """
        multiplicity_resolution = output_multiplicity_to_apply(
            base_multiplicity=self.output_multiplicity,
            override_multiplicity=pipe_run_params.output_multiplicity,
        )
        if not multiplicity_resolution.is_multiple_outputs_enabled:
            requested = MethodOutputMultiplicityMismatchExpected.SINGLE
            requested_label = "a single output"
        elif multiplicity_resolution.specific_output_count is not None:
            requested = MethodOutputMultiplicityMismatchExpected.FIXED
            requested_label = f"{multiplicity_resolution.specific_output_count} outputs"
        else:
            return
        location = self._format_error_location(pipe_run_params=pipe_run_params)
        msg = (
            f"PipeStructure {location} reads a spreadsheet into a list whose length is the table's, and the run asks it for "
            f"{requested_label}: remove the step's `nb_output` or `multiple_output`."
        )
        raise (
            PipeRunError(message=msg, run_mode=pipe_run_params.run_mode, pipe_code=self.code)
            .with_error_code(CoreCode.METHOD_OUTPUT_MULTIPLICITY_MISMATCH)
            .with_params(declared=MethodOutputMultiplicityMismatchExpected.LIST, expected=requested)
        )

    async def _read_spreadsheet(
        self,
        *,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
        output_name: str | None,
    ) -> PipeStructureOutput:
        """Read the table the step names from its spreadsheet input into the output list, through the content generator's leaf.

        No model is called, so the node records none and the step costs no inference.

        Raises:
            PipeRunError: The run asks the step for a single output or a fixed count.
            CsvError: The file, its table or a row cannot be read into the output concept, naming the input.
            TableFileTypeUnsupportedError: The document is neither an Excel workbook nor a CSV file.
        """
        self._refuse_output_multiplicity_override(pipe_run_params=pipe_run_params)
        document = working_memory.get_stuff_as_document(name=self.source_input_name)
        row_model = self.row_model()
        field_names = flat_field_names(row_model)
        with job_metadata.log_context():
            table_records = await get_content_generator().read_table(
                job_metadata=job_metadata,
                cogt_run_params=pipe_run_params.cogt_run_params,
                source_uri=document.url,
                mime_type=document.mime_type,
                file_name=document.filename,
                input_name=self.source_input_name,
                field_names=field_names,
                row_field=self.row_field,
                table_selector=self.table_selector,
            )
            if table_records.uncached_formula_fields:
                log.warning(
                    "Formula cells with no stored value read as empty",
                    fields={"pipe_code": self.code, "input_path": self.source_input_name, "row_fields": table_records.uncached_formula_fields},
                )
        try:
            list_content: ListContent[StuffContent] = list_content_from_table_records(
                table_records=table_records,
                row_model=row_model,
                row_field=self.row_field,
                binding=TableBinding.STEP,
                subject=table_subject(table_format=table_records.table_format, input_name=self.source_input_name),
            )
        except CsvError as exc:
            locate_table_error(table_error=exc, input_name=self.source_input_name)
            raise

        working_memory = store_result(
            memory=working_memory,
            concept=self.output.concept,
            content=list_content,
            result_name=output_name,
            result_code=pipe_run_params.final_stuff_code,
        )
        self._register_execution_data(
            job_metadata=job_metadata,
            execution_data={
                "is_multiple_output": True,
                "structuring_path": SPREADSHEET_STRUCTURING_PATH,
                "table": self.table_name,
                "sheet_range": self._sheet_range_data,
                "table_format": table_records.table_format,
                "nb_records": len(list_content.items),
                "uncached_formula_fields": table_records.uncached_formula_fields,
            },
        )
        return PipeStructureOutput(
            working_memory=working_memory,
            pipeline_run_id=job_metadata.run_metadata.pipeline_run_id,
        )

    @override
    async def _live_run_operator_pipe(
        self,
        *,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
        output_name: str | None = None,
    ) -> PipeStructureOutput:
        if self.reads_document():
            return await self._read_spreadsheet(
                job_metadata=job_metadata, working_memory=working_memory, pipe_run_params=pipe_run_params, output_name=output_name
            )
        source_stuff = working_memory.get_stuff(name=self.source_input_name)
        # The source as a text, refused here when it is none. Its value is not read here: it may be stored, and the
        # leaf that renders the structuring prompt loads it. It is a native `Text` stuff whatever the source's concept, so
        # the leaf types it again with no library, the content and its concept agreeing.
        source_text_stuff = source_stuff.model_copy(
            update={"concept": get_native_concept(native_concept=NativeConceptCode.TEXT), "content": source_stuff.as_text}
        )

        # Resolve list-vs-single from base + override.
        multiplicity_resolution = output_multiplicity_to_apply(
            base_multiplicity=self.output_multiplicity,
            override_multiplicity=pipe_run_params.output_multiplicity,
        )
        is_multiple_output = multiplicity_resolution.is_multiple_outputs_enabled
        fixed_nb_output = multiplicity_resolution.specific_output_count

        # LLM choice: explicit on the pipe → for_object override → for_object default. This pipe has
        # no text choice of its own, so the kernel's object chain reduces to exactly those three rungs.
        llm_setting_for_object: LLMSetting = resolve_llm_setting_for_object(llm_choice=self.llm_choice)

        # The structuring prompt renders in the leaf, as PipeLLM's does, so a stored source text is read only there.
        # Prompt *assembly* is not shared with PipeLLM: this pipe has no template of its own and no memory-borne
        # references — one configured template reads one input text, under the name `text`.
        # No authored style on this operator: the structuring prompt takes the runtime default, the
        # same one an LLM pipe that declares nothing gets.
        templating_style = resolve_templating_style(authored=None)
        llm_config = get_config().inference.llm
        structuring_template = llm_config.get_template(template_name="structuring_prompt")

        content_class: type[StuffContent] = get_class_registry().get_required_subclass(
            name=self.output.concept.structure_class_name,
            base_class=StuffContent,
        )

        # The schema description is appended to the user text, from the same kernel derivation PipeLLM's object path uses.
        output_structure_prompt = await derive_structure_prompt(output_class=content_class, templating_style=templating_style)

        unrendered_prompt = UnrenderedLLMPrompt(
            user_template=TemplateBlueprint(template=structuring_template, category=TemplateCategory.LLM_PROMPT),
            templating_style=templating_style,
            context=get_memory_transport().pack(working_memory=WorkingMemory(root={STRUCTURING_PROMPT_SOURCE_NAME: source_text_stuff})),
            output_structure_prompt=output_structure_prompt,
            # Pipelex's own template, written in no field of the pipe: its failure is ours, and is located on no field.
            system_template_field=None,
            user_template_field=None,
            template_owner=TemplateOwner.PIPELEX,
        )

        try:
            generated = await generate_object_content(
                job_metadata=job_metadata,
                cogt_run_params=pipe_run_params.cogt_run_params,
                unrendered_prompt=unrendered_prompt,
                llm_setting=llm_setting_for_object,
                output_class=content_class,
                is_multiple_output=is_multiple_output,
                fixed_nb_output=fixed_nb_output,
            )
        except LLMCompletionError as exc:
            location = self._format_error_location(pipe_run_params=pipe_run_params)
            what_failed = "object list" if is_multiple_output else "single object"
            msg = f"Error generating {what_failed} in PipeStructure {location}: {exc}"
            raise PipeRunError(message=msg, run_mode=pipe_run_params.run_mode, pipe_code=self.code) from exc

        working_memory = store_result(
            memory=working_memory,
            concept=self.output.concept,
            content=generated.content,
            result_name=output_name,
            result_code=pipe_run_params.final_stuff_code,
        )

        execution_data_dict: dict[str, Any] = {
            "resolved_model": concrete_llm_model_handle(llm_setting_for_object.model),
            "is_multiple_output": is_multiple_output,
            # Rendered by the leaf, which returned it with the object, a text past the trace's bound as its preview.
            "rendered_user_prompt": generated.rendered_prompt.traced_user_text,
            "structuring_path": "structure",
        }
        self._register_execution_data(job_metadata=job_metadata, execution_data=execution_data_dict)

        return PipeStructureOutput(
            working_memory=working_memory,
            pipeline_run_id=job_metadata.run_metadata.pipeline_run_id,
        )

    def _format_error_location(self, pipe_run_params: PipeRunParams) -> str:
        return f"in pipe '{pipe_run_params.pipe_stack_str}'"

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
