from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, model_validator
from typing_extensions import override

from pipelex.cogt.doc_gen.doc_gen_format import DocGenFormat
from pipelex.cogt.doc_gen.doc_gen_setting import DocGenModelChoice
from pipelex.cogt.doc_gen.table_fill import CellPolicy, TableFill
from pipelex.cogt.templating.exceptions import TemplateSigilSyntaxError
from pipelex.cogt.templating.template_preprocessor import preprocess_template
from pipelex.core.method_trees.file_references import BundleFileOrigin, bundle_file_origin, file_reference_refusal
from pipelex.core.pipes.exceptions import PipeVariableMultiplicityError
from pipelex.core.pipes.variable_multiplicity import parse_concept_with_multiplicity
from pipelex.pipe_machinery.pipe_blueprint import PipeBlueprint
from pipelex.tools.jinja2.exceptions import Jinja2TemplateSyntaxError
from pipelex.tools.jinja2.jinja2_parsing import check_jinja2_parsing
from pipelex.tools.jinja2.jinja2_required_variables import detect_jinja2_required_variables
from pipelex.tools.jinja2.template_category import TemplateCategory
from pipelex.tools.misc.string_utils import get_root_from_dotted_path


def template_required_roots(*, template_source: str, template_category: TemplateCategory, declared_inputs: set[str], label: str) -> set[str]:
    """Check that a `PipeDocGen` template parses, and return the input names it reads.

    Sigils are rewritten first, exactly as PipeCompose does, so `$invoice` and `@invoice` count as reads of
    `invoice`. Raises `ValueError`, which pydantic turns into a validation error located on the blueprint.
    """
    try:
        preprocessed = preprocess_template(template_source, declared_inputs=declared_inputs)
    except TemplateSigilSyntaxError as exc:
        msg = f"Template sigil error in the PipeDocGen {label}: {exc}"
        raise ValueError(msg) from exc
    try:
        check_jinja2_parsing(template_source=preprocessed, template_category=template_category)
    except Jinja2TemplateSyntaxError as exc:
        msg = f"Could not parse the PipeDocGen {label}: {exc}"
        raise ValueError(msg) from exc
    roots: set[str] = set()
    for path in detect_jinja2_required_variables(template_category=template_category, template_source=preprocessed):
        root = get_root_from_dotted_path(path)
        if not root.startswith("_") and root != "place_holder":
            roots.add(root)
    return roots


class DocGenSheetRangeBlueprint(BaseModel):
    """A range of rows on a worksheet that holds no Excel Table, and the list that fills it: `PipeDocGen`'s `sheet_range`.

    `list` names the list of records that fills the range, by its path in the step's data, its input's name first, as
    `match_row` names a field; that list fills the range and no Table. `sheet` names the worksheet, compared ignoring
    case, the workbook's only worksheet when it is absent, and `header_row` the sheet row holding the header, counted
    from 1, the sheet's first row holding a value when it is absent. A worksheet holding one Excel Table is filled as
    that Table.
    """

    model_config = ConfigDict(extra="forbid")

    list: str
    sheet: str | None = None
    header_row: Annotated[int, Field(ge=1, strict=True)] | None = None


class PipeDocGenBlueprint(PipeBlueprint):
    """Generate a document file from a method's structured result: a PDF, an Excel workbook, a Word document or a PowerPoint deck.

    It calls no AI model: it lays out or fills what its inputs already hold. With no template, the pipe lays its inputs
    out by itself (the auto-layout), for every format but `pptx`. `template` is an inline HTML and Jinja2 template, for
    `pdf` only; `template_file` is a path relative to the bundle's file, inside its bundle and written with forward
    slashes: an `.html` for `pdf`, an `.xlsx` for `xlsx`, a
    `.docx` for `docx` and a `.pptx` for `pptx`, which `pptx` requires. `filename` is a Jinja expression over the
    inputs; the suffix is added, and without it the file is named after the step, or after the template input's file.
    `template_input` names one of the step's inputs, a single `Document` or a concept refining it, whose file is the
    template, as an alternative to `template_file` for `xlsx`, `docx` and `pptx`: the run supplies the template, which
    is checked when the run starts, and the output is a new file, the input's file being left as it was. `table_fill`
    says how the template's Tables are filled: `replace`, the default, writes a list's records over a Table's rows,
    `append`, for `xlsx` only, writes them after its last row, and `update`, for `xlsx` only, writes each record into the
    one row it matches, by the key fields `match_on` names or by the row position the field `match_row` names, exactly
    one of the two. Under `update` a null leaves its cell as it was, and `cells` says which cells may be written:
    `fill_empty`, the default, writes only empty cells, and `overwrite` writes every cell a value matches. `sheet_range`,
    under `append` or `update`, fills a range on a sheet that holds no Excel Table from the list it names, rather than a
    Table from the list of its name. The output must
    be a single `Document`, or a concept refining it. `model` names the document engine that prints it, a model of the
    `doc_gen` family such as `reportlab-pdf` or, with the Pipelex document generation plugin, `pipelex-pdf`; without it,
    the model deck's default for the format and source prints it. Which engines a runtime has depends on its plugins:
    open Pipelex prints a `pdf` without a template on `reportlab-pdf`, and a runtime without the engine a step needs
    refuses the method when it loads.
    """

    type: Literal["PipeDocGen"] = "PipeDocGen"
    pipe_category: Literal["PipeOperator"] = "PipeOperator"

    format: DocGenFormat = Field(strict=False)
    model: DocGenModelChoice | None = None
    template: str | None = None
    template_file: str | None = None
    template_input: str | None = None
    table_fill: TableFill | None = Field(default=None, strict=False)
    match_on: list[str] | None = None
    match_row: str | None = None
    cells: CellPolicy | None = Field(default=None, strict=False)
    sheet_range: DocGenSheetRangeBlueprint | None = None
    filename: str | None = None

    @model_validator(mode="after")
    def validate_template_sources(self, info: ValidationInfo) -> Self:
        # A bundle read into a method tree is held to the form of a file reference, the one check a blueprint can make
        # before its tree is at hand: whether the path names a file, a `..` climbing elsewhere in the tree included, is
        # decided when the bundle loads, in its tree. A bundle loaded from a content string reads only the files
        # submitted with it, so its step is also held to the rule they are keyed by, here, before any file is looked up.
        # The message never repeats the path: a host library's step would put the host's own path in front of a caller.
        if self.template_file is not None:
            file_origin = bundle_file_origin(validation_context=info.context)
            refusal = file_reference_refusal(reference=self.template_file, file_origin=file_origin)
            if refusal is not None:
                match file_origin:
                    case BundleFileOrigin.METHOD_TREE:
                        msg = (
                            f"PipeDocGen's 'template_file' is a path relative to the bundle's file, in its method, and this one cannot be: {refusal}."
                        )
                    case BundleFileOrigin.SUBMITTED_FILES:
                        msg = (
                            "PipeDocGen's 'template_file' names a file submitted with its bundle, by a path relative to the bundle "
                            f"and inside it, and this one cannot be: {refusal}."
                        )
                raise ValueError(msg)
        if self.template is not None and self.template_file is not None:
            msg = "PipeDocGen cannot have both 'template' and 'template_file': use one or the other."
            raise ValueError(msg)
        if self.template is not None and not self.format.is_template_html:
            msg = (
                f"PipeDocGen's inline 'template' is an HTML template, for the 'pdf' format only. "
                f"For '{self.format}', use 'template_file' with a {self.format.template_file_suffix} file"
                f"{', or no template for the auto-layout' if self.format.has_auto_layout else ''}."
            )
            raise ValueError(msg)
        if self.template_file is not None and not self.template_file.lower().endswith(self.format.template_file_suffix):
            msg = (
                f"PipeDocGen's 'template_file' for the '{self.format}' format must be a {self.format.template_file_suffix} file, "
                f"got '{self.template_file}'."
            )
            raise ValueError(msg)
        self._validate_template_input()
        if not self.format.has_auto_layout and self.template_file is None and self.template_input is None:
            msg = (
                f"PipeDocGen's '{self.format}' format has no auto-layout: name the designed {self.format.template_file_suffix} "
                "file it fills with 'template_file', or the input that supplies it with 'template_input'."
            )
            raise ValueError(msg)
        self._validate_table_fill()
        self._validate_table_match()
        self._validate_sheet_range()
        return self

    def _validate_template_input(self) -> None:
        """`template_input` names one declared single input, alone among the template sources, for an office format."""
        template_input = self.template_input
        if template_input is None:
            return
        if self.template is not None or self.template_file is not None:
            msg = "PipeDocGen's 'template_input' names the input that supplies the template: it cannot be used with 'template' or 'template_file'."
            raise ValueError(msg)
        if self.format.is_template_html:
            msg = (
                f"PipeDocGen's 'template_input' is for an office format: a '{self.format}' template is HTML text of the method, "
                "written in 'template' or 'template_file', not a file a run supplies."
            )
            raise ValueError(msg)
        concept_specs = self.inputs_concept_specs or {}
        concept_spec = concept_specs.get(template_input)
        if concept_spec is None:
            declared = ", ".join(f"'{input_name}'" for input_name in concept_specs) or "none"
            msg = f"PipeDocGen's 'template_input' names '{template_input}', which is not one of the step's inputs (declared: {declared})."
            raise ValueError(msg)
        try:
            parsed_spec = parse_concept_with_multiplicity(concept_ref_or_code=concept_spec)
        except PipeVariableMultiplicityError:
            # The input's own validation refuses its spec, naming it.
            return
        if parsed_spec.multiplicity:
            msg = f"PipeDocGen's 'template_input' names '{template_input}', a list ('{concept_spec}'): the template is one file, a single Document."
            raise ValueError(msg)
        if parsed_spec.presence.is_optional:
            msg = f"PipeDocGen's 'template_input' names '{template_input}', an optional input ('{concept_spec}'): the template must be supplied."
            raise ValueError(msg)

    def _validate_table_fill(self) -> None:
        """A fill other than `replace` is for an `xlsx` step's Tables, and any fill needs a template whose Tables it fills."""
        table_fill = self.table_fill
        if table_fill is None:
            return
        if self.template_file is None and self.template_input is None:
            msg = (
                f"PipeDocGen's 'table_fill' fills the Tables of a template file, and this step has none: name it with "
                f"'template_file' or 'template_input', or remove 'table_fill'{' for the auto-layout' if self.format.has_auto_layout else ''}."
            )
            raise ValueError(msg)
        if not table_fill.is_replace and not self.format.has_table_fills:
            msg = f"PipeDocGen's 'table_fill = \"{table_fill}\"' is for the 'xlsx' format only: a '{self.format}' template's tables are replaced."
            raise ValueError(msg)

    def _validate_table_match(self) -> None:
        """An update matches each record to its row by exactly one of `match_on` and `match_row`; no other fill matches rows.

        Whether each field exists on the records is checked once the library resolves their concept
        (`PipeDocGen.validate_inputs_with_library`).
        """
        if self.table_fill is None or not self.table_fill.is_update:
            fill_label = f"'table_fill = \"{self.table_fill}\"'" if self.table_fill is not None else "the default 'table_fill = \"replace\"'"
            for field_name, value in (("match_on", self.match_on), ("match_row", self.match_row), ("cells", self.cells)):
                if value is not None:
                    msg = (
                        f"PipeDocGen's '{field_name}' says how 'table_fill = \"update\"' writes a record into the row it matches, "
                        f"and this step uses {fill_label}: remove '{field_name}', or update the Table's rows."
                    )
                    raise ValueError(msg)
            return
        match_on = self.match_on
        if match_on is None and self.match_row is None:
            msg = (
                "PipeDocGen's 'table_fill = \"update\"' writes each record into the row it matches: name the fields whose "
                "columns are the Table's key with 'match_on', or the field holding each record's row position with 'match_row'."
            )
            raise ValueError(msg)
        if match_on is not None and self.match_row is not None:
            msg = "PipeDocGen's 'table_fill = \"update\"' matches a record to its row one way: by 'match_on' or by 'match_row', not both."
            raise ValueError(msg)
        if match_on is not None:
            if not match_on:
                msg = "PipeDocGen's 'match_on' names the fields whose columns are the Table's key, and it names none."
                raise ValueError(msg)
            repeated = sorted({field_name for field_name in match_on if match_on.count(field_name) > 1})
            if repeated:
                msg = f"PipeDocGen's 'match_on' names each key field once, and it repeats {', '.join(repr(name) for name in repeated)}."
                raise ValueError(msg)

    def _validate_sheet_range(self) -> None:
        """A sheet range is an `xlsx` template's, filled by `append` or `update`, from a list it names.

        Whether the list is one of the step's data is checked once the library resolves its concept
        (`PipeDocGen.validate_inputs_with_library`).
        """
        sheet_range = self.sheet_range
        if sheet_range is None:
            return
        if self.template_file is None and self.template_input is None:
            msg = (
                "PipeDocGen's 'sheet_range' fills a range on a sheet of a template workbook, and this step has none: name it with "
                "'template_file' or 'template_input', or remove 'sheet_range'."
            )
            raise ValueError(msg)
        if not self.format.has_table_fills:
            msg = f"PipeDocGen's 'sheet_range' is for the 'xlsx' format only: a '{self.format}' template has no sheets."
            raise ValueError(msg)
        if self.table_fill is None or self.table_fill.is_replace:
            fill_label = f"'table_fill = \"{self.table_fill}\"'" if self.table_fill is not None else "the default 'table_fill = \"replace\"'"
            msg = (
                f"PipeDocGen's 'sheet_range' is filled by 'table_fill = \"append\"' or 'table_fill = \"update\"', and this step uses "
                f"{fill_label}: a replace shrinks the rows to the list's length, and on a range found by rules rather than declared "
                "by an Excel Table that could clear the user's rows. Append to or update the range, or fill an Excel Table instead."
            )
            raise ValueError(msg)
        if not sheet_range.list:
            msg = "PipeDocGen's 'sheet_range' names the list of records that fills the range in 'list', and it names none."
            raise ValueError(msg)

    @property
    @override
    def named_file_references(self) -> set[str]:
        if self.template_file is None:
            return set()
        return {self.template_file}

    @override
    def validate_inputs(self):
        declared_inputs = set(self.input_names)
        if self.template is not None:
            self._check_roots_are_inputs(
                roots=template_required_roots(
                    template_source=self.template,
                    template_category=TemplateCategory.HTML,
                    declared_inputs=declared_inputs,
                    label="template",
                ),
                label="template",
            )
        if self.filename is not None:
            self._check_roots_are_inputs(
                roots=template_required_roots(
                    template_source=self.filename,
                    template_category=TemplateCategory.BASIC,
                    declared_inputs=declared_inputs,
                    label="filename",
                ),
                label="filename",
            )

    def _check_roots_are_inputs(self, *, roots: set[str], label: str):
        for root in sorted(roots):
            if root not in self.input_names:
                msg = f"Variable '{root}' in the PipeDocGen {label} is not in the inputs of the pipe."
                raise ValueError(msg)

    @override
    def validate_output(self):
        parsed_output = parse_concept_with_multiplicity(concept_ref_or_code=self.output)
        if parsed_output.multiplicity:
            msg = f"PipeDocGen produces one file: its output must be a single Document, or a concept refining Document. Current output: {self.output}"
            raise ValueError(msg)
