import re
from typing import Any

from pydantic import ConfigDict, Field, field_validator
from rich.console import Group
from rich.table import Table
from rich.text import Text
from typing_extensions import override

from pipelex import log
from pipelex.cogt.content_generation.dry_run_factory import MockFormat
from pipelex.core.concepts.exceptions import ConceptStringError
from pipelex.core.concepts.validation import validate_concept_ref_or_code
from pipelex.core.pipes.pipe_blueprint import PipeBlueprint, PipeCategory, PipeType, valid_pipe_type_tags
from pipelex.core.pipes.variable_multiplicity import MULTIPLICITY_PATTERN, PresenceMarker, parse_concept_with_multiplicity
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.tools.misc.pretty import PrettyPrintable
from pipelex.tools.misc.string_utils import is_snake_case, normalize_to_ascii


class PipeSpec(StructuredContent):
    """Spec defining a pipe: an executable component with a clear contract defined by its inputs and output.

    Pipes are the building blocks of a Pipelex pipeline. There are two categories:
    - Controllers: Manage execution flow (PipeSequence, PipeParallel, PipeCondition, PipeBatch)
    - Operators: Perform specific tasks (PipeLLM, PipeImgGen, PipeExtract, PipeFunc, PipeCompose)

    Multiplicity Notation:
        Both inputs and outputs use bracket notation to specify item counts:
        - No brackets: single item (default)
        - []: variable-length list (e.g., "Text[]")
        - [N]: exactly N items (e.g., "Image[3]" for 3 images)

    Presence Notation:
        Singular inputs and outputs may carry a presence marker after the concept name:
        - ?: optional (e.g., "PenaltyClause?" — the slot may legitimately hold no value)
        - !: force (inputs only, e.g., "PenaltyClause!" — assert the value is present, error if absent)
        Presence markers never combine with multiplicity brackets: an absent plural is the empty list.

    Examples:
        inputs = {"document": "Document", "queries": "Text[]"}  # single document, multiple texts
        output = "Article[]"  # produces a list of articles
        output = "Image[5]"  # produces exactly 5 images
        output = "PenaltyClause?"  # may produce no value
    """

    model_config = ConfigDict(extra="forbid")

    pipe_code: str = Field(description="Unique pipe identifier. Must be snake_case.", json_schema_extra={"mock_format": MockFormat.SNAKE_CASE})
    type: Any = Field(
        description=(
            f"Pipe type. Validated at runtime, must be one of: {PipeType}. Examples: PipeLLM, PipeImgGen, PipeExtract, PipeSequence, PipeParallel."
        ),
        # Do NOT set examples here - subclasses have Literal types with defaults
        # Setting examples would cause mocking issues where the base class type doesn't match subclass fields
    )
    # TODO: Change examples to list(PipeCategory) for randomness in mocks
    pipe_category: Any = Field(
        description=(f"Pipe category. Validated at runtime, must be one of: {PipeCategory}. Either 'PipeController' or 'PipeOperator'."),
        examples=["PipeOperator"],
    )
    description: str = Field(description="Natural language description of the pipe's purpose and functionality.")
    inputs: dict[str, str] = Field(
        description=(
            "Input specifications mapping variable names to concept codes with optional multiplicity or presence marker. "
            "Keys: input names in snake_case. "
            "Values: ConceptCodes in PascalCase with optional brackets, or a presence marker on singular forms. "
            "Examples: 'Text' (single), 'Text[]' (variable list), 'Image[2]' (exactly 2 images), "
            "'domain.Concept[]' (domain-qualified list), 'Clause?' (optional input), 'Clause!' (force: error if absent)."
        ),
        json_schema_extra={"mock_format": MockFormat.DICT_SNAKE_KEY_PASCAL_VALUE},
    )
    output: str = Field(
        description=(
            "Output concept code in PascalCase with optional multiplicity brackets, or '?' on singular forms "
            "to declare the pipe may produce no value ('!' is not allowed on outputs). "
            "Examples: 'Text' (single text), 'Article[]' (list of articles), 'Image[3]' (exactly 3 images), "
            "'PenaltyClause?' (may produce no value). "
            "IMPORTANT: Always use PascalCase for the concept name."
        ),
        json_schema_extra={"mock_format": MockFormat.PASCAL_CASE},
    )

    @field_validator("pipe_code", mode="before")
    @classmethod
    def validate_pipe_code(cls, value: str) -> str:
        return cls.validate_pipe_code_syntax(value)

    @field_validator("type", mode="after")
    @classmethod
    def validate_pipe_type(cls, value: Any) -> Any:
        allowed = valid_pipe_type_tags()
        if value not in allowed:
            msg = f"Invalid pipe type '{value}'. Must be one of: {allowed}"
            raise ValueError(msg)
        return value

    @field_validator("output", mode="after")
    @classmethod
    def validate_output(cls, output: str) -> str:
        # Extract concept without multiplicity/presence markers for validation
        parse_result = parse_concept_with_multiplicity(output)
        # Mirror the blueprint grammar rules (D1, D4): `!` never on outputs, `?` never with multiplicity
        if parse_result.presence.is_force:
            msg = (
                f"Invalid output: '{output}'. The force marker '!' is not allowed on outputs — "
                f"it is a use-site assertion for inputs. To declare that this pipe may produce no value, use '?'."
            )
            raise ValueError(msg)
        if parse_result.presence.is_optional and parse_result.multiplicity is not None:
            msg = (
                f"Invalid output: '{output}'. The optional marker '?' cannot be combined with multiplicity: "
                f"a plural slot is never absent — when nothing is found, it is the empty list."
            )
            raise ValueError(msg)
        try:
            validate_concept_ref_or_code(concept_ref_or_code=parse_result.concept_ref_or_code)
        except ConceptStringError as exc:
            # Wrap so pydantic converts it into a ValidationError; otherwise it escapes the
            # field_validator unwrapped (pydantic v2 only auto-wraps ValueError/TypeError/AssertionError).
            raise ValueError(str(exc)) from exc
        return output

    @field_validator("inputs", mode="after")
    @classmethod
    def validate_inputs(cls, inputs: dict[str, str] | None) -> dict[str, str] | None:
        if inputs is None:
            return None

        for input_name, concept_spec in inputs.items():
            if not is_snake_case(input_name):
                msg = f"Invalid input name syntax '{input_name}'. Must be in snake_case."
                raise ValueError(msg)

            # Validate the concept spec format: optional multiplicity brackets then optional
            # presence marker. Pattern allows: ConceptName, domain.ConceptName, ConceptName[],
            # ConceptName[N], ConceptName?, ConceptName!
            match = re.match(MULTIPLICITY_PATTERN, concept_spec)
            if not match:
                msg = (
                    f"Invalid input syntax for '{input_name}': '{concept_spec}'. "
                    f"Expected format: 'ConceptName', 'ConceptName[]', 'ConceptName[N]' where N is an integer, "
                    f"with an optional presence marker '?' or '!' on singular forms (e.g. 'ConceptName?')."
                )
                raise ValueError(msg)

            # Mirror the blueprint grammar rule (D1, D4): presence markers never combine with multiplicity
            bracket_content = match.group(2)
            presence = PresenceMarker.from_symbol(match.group(3))
            if not presence.is_plain and bracket_content is not None:
                msg = (
                    f"Invalid input '{input_name}': '{concept_spec}'. "
                    f"The presence marker '{presence.symbol}' cannot be combined with multiplicity: "
                    f"a plural slot is never absent — when nothing is found, it is the empty list."
                )
                raise ValueError(msg)

            # Extract the concept part (without markers) and validate it
            concept_ref_or_code = match.group(1)
            try:
                validate_concept_ref_or_code(concept_ref_or_code=concept_ref_or_code)
            except ConceptStringError as exc:
                raise ValueError(str(exc)) from exc

        return inputs

    @classmethod
    def validate_pipe_code_syntax(cls, pipe_code: str) -> str:
        # Strip namespace prefix if present (e.g., "domain.my_pipe" → "my_pipe").
        # The builder LLM sometimes generates dotted pipe codes; the namespace
        # comes from the bundle's domain field, not from the pipe code itself.
        # This must happen BEFORE ASCII normalization, because normalize_to_ascii()
        # strips dots (keeping only alphanumeric + underscore).
        if "." in pipe_code:
            bare_pipe_code = pipe_code.rsplit(".", maxsplit=1)[1]
            log.warning(f"Pipe code '{pipe_code}' contains a namespace prefix, stripped to '{bare_pipe_code}'")
            pipe_code = bare_pipe_code

        # Normalize Unicode to ASCII to prevent homograph attacks
        normalized_pipe_code = normalize_to_ascii(pipe_code)

        if normalized_pipe_code != pipe_code:
            log.warning(f"Pipe code '{pipe_code}' contained non-ASCII characters, normalized to '{normalized_pipe_code}'")

        if not is_snake_case(normalized_pipe_code):
            msg = f"Invalid pipe code syntax '{normalized_pipe_code}'. Must be in snake_case."
            raise ValueError(msg)
        return normalized_pipe_code

    def to_blueprint(self) -> PipeBlueprint:
        return PipeBlueprint(
            description=self.description,
            inputs=self.inputs or None,
            output=self.output,
            type=self.type,
            pipe_category=self.pipe_category,
        )

    @override
    def rendered_pretty(self, *, title: str | None = None, depth: int = 0) -> PrettyPrintable:
        pipe_group = Group()
        if title:
            pipe_group.renderables.append(Text(title, style="bold"))
        pipe_group.renderables.append(Text.from_markup(f"Pipe: [bold red]{self.pipe_code}[/bold red]\n"))
        pipe_group.renderables.append(Text.from_markup(f"Type: [bold magenta]{self.type}[/bold magenta] ({self.pipe_category})\n"))
        if self.description:
            pipe_group.renderables.append(Text.from_markup(f"Description: [yellow italic]{self.description}[/yellow italic]\n"))

        # Create inputs section
        if not self.inputs:
            pipe_group.renderables.append(Text.from_markup("\nNo inputs"))
        elif len(self.inputs) == 1:
            # Single input: display as a simple line of text
            input_name, concept_spec = next(iter(self.inputs.items()))
            pipe_group.renderables.append(Text.from_markup(f"\nInput: [cyan]{input_name}[/cyan] ([bold green]{concept_spec}[/bold green])"))
        else:
            # Multiple inputs: display as a table
            inputs_table = Table(
                title="Inputs:",
                title_justify="left",
                title_style="not italic",
                show_header=False,
                show_edge=True,
                show_lines=True,
                border_style="dim",
            )
            inputs_table.add_column("Variable Name", style="cyan")
            inputs_table.add_column("Concept", style="bold green")
            for input_name, concept_spec in self.inputs.items():
                inputs_table.add_row(input_name, concept_spec)
            pipe_group.renderables.append(inputs_table)

        # Show output
        pipe_group.renderables.append(Text.from_markup(f"\nOutput: [bold green]{self.output}[/bold green]"))

        return pipe_group
