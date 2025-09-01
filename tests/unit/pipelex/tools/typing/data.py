from __future__ import annotations

import dataclasses
import enum
import typing
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from pipelex.core.bundles.pipelex_bundle_blueprint import (
    PipelexBundleBlueprint as PipelexBundleBlueprintBaseModel,
)
from pipelex.core.concepts.concept_blueprint import (
    ConceptBlueprint as ConceptBlueprintBaseModel,
)
from pipelex.core.stuffs.stuff_content import ListContent, StructuredContent, TextContent
from pipelex.types import StrEnum


class PipelexBundleBlueprint(PipelexBundleBlueprintBaseModel, StructuredContent):
    """A class that inherits from both custom base model and StructuredContent"""

    pass


# ---------- Helper types shared by cases ----------


class IndexScale(StrEnum):
    A = "A"
    B = "B"
    C = "C"
    D = "D"
    E = "E"
    F = "F"
    G = "G"


class MusicGenre(StrEnum):
    """Available music genres."""

    CLASSICAL = "classical"
    JAZZ = "jazz"
    ROCK = "rock"
    ELECTRONIC = "electronic"
    WORLD = "world"


class SimpleTextContent(TextContent):
    """A simple text content class"""

    pass


class MusicCategoryContent(StructuredContent):
    """A content class with a Literal field for music genres."""

    category: typing.Literal[
        MusicGenre.CLASSICAL,
        MusicGenre.JAZZ,
        MusicGenre.ROCK,
        MusicGenre.ELECTRONIC,
        MusicGenre.WORLD,
    ] = Field(description="The genre of music")


class SimpleStructuredContent(StructuredContent):
    """A simple structured content with primitive types"""

    name: str
    age: int
    active: bool


class DocumentType(StrEnum):
    INVOICE = "INVOICE"
    RECEIPT = "RECEIPT"


class DocumentTypeContent(StructuredContent):
    """Content with enum type"""

    document_type: DocumentType


class AddressContent(StructuredContent):
    """Nested address content"""

    street: str
    city: str
    country: str


class PersonContent(StructuredContent):
    """Complex nested content with various types"""

    name: str
    age: int
    address: AddressContent = Field(description="Address of the person")
    documents: typing.List["DocumentTypeContent"]
    priority: typing.Optional["Priority"] = None


class Priority(StrEnum):
    HIGH = "HIGH"
    LOW = "LOW"


class ComplexListContent(ListContent["PersonContent"]):
    """List content with complex items"""

    items: typing.List["PersonContent"]


class GanttTaskDetails(StructuredContent):
    """Do not include timezone in the dates."""

    name: str
    start_date: typing.Optional[datetime] = None
    end_date: typing.Optional[datetime] = None

    @field_validator("start_date", "end_date")
    @classmethod
    def remove_tzinfo(cls, v: typing.Optional[datetime]) -> typing.Optional[datetime]:
        if v is not None:
            return v.replace(tzinfo=None)
        return v


class Milestone(StructuredContent):
    name: str
    date: typing.Optional[datetime]

    @field_validator("date")
    @classmethod
    def remove_tzinfo(cls, v: typing.Optional[datetime]) -> typing.Optional[datetime]:
        if v is not None:
            return v.replace(tzinfo=None)
        return v


class GanttChart(StructuredContent):
    tasks: typing.Optional[typing.List["GanttTaskDetails"]] = None
    milestones: typing.Optional[typing.List["Milestone"]] = None


# Dataclass dependency case
@dataclasses.dataclass
class DC:
    a: int
    b: str


class UsesDC(StructuredContent):
    dc: DC


# Literal-of-enum-members case
class Genre(StrEnum):
    BLUES = "blues"
    FOLK = "folk"


# --- Multiple inheritance helper (left-of-StructuredContent) ---


class BaseLeft(BaseModel):
    z: int


class Mixed(BaseLeft, StructuredContent):
    """Mixed inheritance"""

    pass


class Song(StructuredContent):
    tag: typing.Literal[Genre.BLUES, Genre.FOLK] = Field(description="Tag")


# Employee/Person (field description on child)
class Person(BaseModel):
    name: str
    age: int


class Employee(Person):
    job: str = Field(description="Job title, must be lowercase")


# TaskContent with docstring + descriptions
class TaskContent(StructuredContent):
    """A task content model that represents a single task.

    This model is used to store task information including its title,
    description, and status.
    """

    title: str = Field(description="The title of the task")
    description: str = Field(description="Detailed description of what needs to be done")
    is_completed: bool = Field(False, description="Whether the task is completed")


# ---------- CASES: pretty_type ----------

PRETTY_TYPE_CASES: list[tuple[typing.Any, str]] = [
    (int, "int"),
    (str, "str"),
    (typing.List[int], "List[int]"),
    (typing.Dict[str, int], "Dict[str, int]"),
    (typing.Tuple[int, str], "Tuple[int, str]"),
    (typing.Optional[int], "Optional[int]"),
    (typing.Union[int, str], "Union[int, str]"),
    (int | str, "Union[int, str]"),
    (int | None, "Optional[int]"),
    (typing.Literal["a", "b"], "Literal['a', 'b']"),
    (typing.Literal[MusicGenre.CLASSICAL, MusicGenre.JAZZ], "Literal['classical', 'jazz']"),
    (typing.Annotated[int, "meta", 123], "int"),
]


# ---------- CASES: extract_model_types ----------
# We assert that EXPECTED is a subset of the returned set.


class M(BaseModel):
    x: int


class A(BaseModel):
    pass


class Scale(StrEnum):
    A = "A"
    B = "B"


EXTRACT_MODEL_TYPES_CASES: list[tuple[typing.Any, set[type]]] = [
    (typing.Dict[str, M], {M}),
    (typing.List[typing.Optional[A]], {A}),
    (typing.Literal[Scale.A, Scale.B], {Scale}),  # Literal enum members -> collect enum type
]


# ---------- CASES: is_renderable_type ----------


@dataclasses.dataclass
class D:
    x: int


class E(enum.Enum):
    X = 1


class DomainThing:
    pass


DomainThing.__module__ = "pipelex.somewhere"

IS_RENDERABLE_TYPE_CASES: list[tuple[type, bool]] = [
    (BaseModel, True),  # strictly, a subclass would be truer, but BaseModel itself passes our predicate
    (D, True),
    (E, True),
    (DomainThing, True),
    (int, False),
    (str, False),
]


class ConceptBlueprint(ConceptBlueprintBaseModel, StructuredContent):
    the_concept_code: str = Field(description="Concept code. Must be PascalCase.")


# ---------- CASES: render_model (exact match) ----------

RENDER_MODEL_CASES: list[tuple[type, str]] = [
    (
        SimpleTextContent,
        "\n".join(
            [
                "class SimpleTextContent(TextContent):",
                '    """A simple text content class"""',
                "    # No fields",
            ]
        ),
    ),
    (
        SimpleStructuredContent,
        "\n".join(
            [
                "class SimpleStructuredContent(StructuredContent):",
                '    """A simple structured content with primitive types"""',
                "    name: str",
                "    age: int",
                "    active: bool",
            ]
        ),
    ),
    (
        DocumentTypeContent,
        "\n".join(
            [
                "class DocumentTypeContent(StructuredContent):",
                '    """Content with enum type"""',
                "    document_type: DocumentType",
                "",
                "class DocumentType(StrEnum):",
                '    INVOICE = "INVOICE"',
                '    RECEIPT = "RECEIPT"',
            ]
        ),
    ),
    (
        PersonContent,
        "\n".join(
            [
                "class PersonContent(StructuredContent):",
                '    """Complex nested content with various types"""',
                "    name: str",
                "    age: int",
                "    address: AddressContent  # Address of the person",
                "    documents: List[DocumentTypeContent]",
                "    priority: Optional[Priority]",
                "",
                "class AddressContent(StructuredContent):",
                '    """Nested address content"""',
                "    street: str",
                "    city: str",
                "    country: str",
                "",
                "class DocumentTypeContent(StructuredContent):",
                '    """Content with enum type"""',
                "    document_type: DocumentType",
                "",
                "class DocumentType(StrEnum):",
                '    INVOICE = "INVOICE"',
                '    RECEIPT = "RECEIPT"',
                "",
                "class Priority(StrEnum):",
                '    HIGH = "HIGH"',
                '    LOW = "LOW"',
            ]
        ),
    ),
    (
        ComplexListContent,
        "\n".join(
            [
                "class ComplexListContent(ListContent):",
                '    """List content with complex items"""',
                "    items: List[PersonContent]",
                "",
                "class PersonContent(StructuredContent):",
                '    """Complex nested content with various types"""',
                "    name: str",
                "    age: int",
                "    address: AddressContent  # Address of the person",
                "    documents: List[DocumentTypeContent]",
                "    priority: Optional[Priority]",
                "",
                "class AddressContent(StructuredContent):",
                '    """Nested address content"""',
                "    street: str",
                "    city: str",
                "    country: str",
                "",
                "class DocumentTypeContent(StructuredContent):",
                '    """Content with enum type"""',
                "    document_type: DocumentType",
                "",
                "class DocumentType(StrEnum):",
                '    INVOICE = "INVOICE"',
                '    RECEIPT = "RECEIPT"',
                "",
                "class Priority(StrEnum):",
                '    HIGH = "HIGH"',
                '    LOW = "LOW"',
            ]
        ),
    ),
    (
        GanttChart,
        "\n".join(
            [
                "class GanttChart(StructuredContent):",
                "    tasks: Optional[List[GanttTaskDetails]]",
                "    milestones: Optional[List[Milestone]]",
                "",
                "class GanttTaskDetails(StructuredContent):",
                '    """Do not include timezone in the dates."""',
                "    name: str",
                "    start_date: Optional[datetime]",
                "    end_date: Optional[datetime]",
                "",
                "class Milestone(StructuredContent):",
                "    name: str",
                "    date: Optional[datetime]",
            ]
        ),
    ),
    (
        UsesDC,
        "\n".join(
            [
                "class UsesDC(StructuredContent):",
                "    dc: DC",
                "",
                "class DC(object):",
                "    a: int",
                "    b: str",
            ]
        ),
    ),
    (
        Song,
        "\n".join(
            [
                "class Song(StructuredContent):",
                "    tag: Literal['blues', 'folk']  # Tag",
                "",
                "class Genre(StrEnum):",
                '    BLUES = "blues"',
                '    FOLK = "folk"',
            ]
        ),
    ),
    (
        Employee,
        "\n".join(
            [
                "class Employee(Person):",
                "    job: str  # Job title, must be lowercase",
            ]
        ),
    ),
    (
        TaskContent,
        "\n".join(
            [
                "class TaskContent(StructuredContent):",
                '    """A task content model that represents a single task.',
                "",
                "    This model is used to store task information including its title,",
                "    description, and status.",
                '    """',
                "    title: str  # The title of the task",
                "    description: str  # Detailed description of what needs to be done",
                "    is_completed: bool  # Whether the task is completed",
            ]
        ),
    ),
    (
        Mixed,
        "\n".join(
            [
                "class Mixed(BaseLeft):",
                '    """Mixed inheritance"""',
                "    z: int",
            ]
        ),
    ),
    (
        ConceptBlueprint,
        "\n".join(
            [
                "class ConceptBlueprint(ConceptBlueprint):",
                "    the_concept_code: str  # Concept code. Must be PascalCase.",
                "    definition: str",
                "    structure: Union[str, Dict[str, Union[str, ConceptStructureBlueprint]]]",
                "    refines: Optional[str]",
                "",
                "class ConceptStructureBlueprint(BaseModel):",
                '    """Blueprint defining a field in the structure of a concept, used as a Pydantic V2 model.',
                "",
                "    This class represents the schema for a single field in a concept's structure. It supports",
                "    various field types including text, list, dict, integer, boolean, number, and date, as well",
                "    as choice-based fields (enums).",
                "",
                "    Attributes:",
                "        definition: Natural language description of the field's purpose and usage.",
                "        type: The field's data type. When 'dict', both key_type and value_type must be specified.",
                "              When None, choices must be provided (creating an enum field).",
                "        item_type: For 'list' type fields, specifies the type of items in the list.",
                "        key_type: For 'dict' type fields, specifies the type of dictionary keys. Required when type='dict'.",
                "        value_type: For 'dict' type fields, specifies the type of dictionary values. Required when type='dict'.",
                "        choices: List of valid string choices for enum fields. When provided, type must be None.",
                "        required: Whether the field is mandatory. Defaults to True unless explicitly set to False.",
                "        default_value: Default value for the field. Must match the specified type, and for choice",
                "                      fields must be one of the valid choices. When provided, type must be specified",
                "                      (unless choices are provided).",
                "",
                "    Validation Rules:",
                "        1. Choice fields (enums): When type is None, choices must be provided and non-empty.",
                "        2. Dictionary fields: When type is 'dict', both key_type and value_type are required.",
                "        3. Default values: When default_value is provided:",
                "           - For typed fields: type must be specified and default_value must match that type",
                "           - For choice fields: default_value must be one of the valid choices",
                "           - Type validation includes: text (str), integer (int), boolean (bool),",
                "             number (int/float), list (list), dict (dict)",
                "        4. List fields: When type is 'list', item_type should specify the type of list items.",
                "",
                "    Raises:",
                "        ConceptStructureBlueprintError: When validation rules are violated.",
                '    """',
                "    definition: str",
                "    type: Optional[ConceptStructureBlueprintFieldType]",
                "    item_type: Optional[str]",
                "    key_type: Optional[str]",
                "    value_type: Optional[str]",
                "    choices: Optional[List[str]]",
                "    required: Optional[bool]",
                "    default_value: Optional[Any]",
                "",
                "class ConceptStructureBlueprintFieldType(StrEnum):",
                '    TEXT = "text"',
                '    LIST = "list"',
                '    DICT = "dict"',
                '    INTEGER = "integer"',
                '    BOOLEAN = "boolean"',
                '    NUMBER = "number"',
                '    DATE = "date"',
            ]
        ),
    ),
    (
        PipelexBundleBlueprint,
        "\n".join(
            [
                "class PipelexBundleBlueprint(PipelexBundleBlueprint):",
                '    """A class that inherits from both custom base model and StructuredContent"""',
                "    domain: str",
                "    definition: Optional[str]",
                "    system_prompt: Optional[str]",
                "    system_prompt_to_structure: Optional[str]",
                "    prompt_template_to_structure: Optional[str]",
                "    concept: Optional[Dict[str, Union[ConceptBlueprint, str]]]",
                "    pipe: Optional[Dict[str, Union[PipeFuncBlueprint, PipeImgGenBlueprint, PipeJinja2Blueprint, PipeLLMBlueprint, "
                "PipeOcrBlueprint, PipeBatchBlueprint, PipeConditionBlueprint, PipeParallelBlueprint, PipeSequenceBlueprint]]]",
                "",
                "class ConceptBlueprint(BaseModel):",
                "    definition: str",
                "    structure: Union[str, Dict[str, Union[str, ConceptStructureBlueprint]]]",
                "    refines: Optional[str]",
                "",
                "class ConceptStructureBlueprint(BaseModel):",
                '    """Blueprint defining a field in the structure of a concept, used as a Pydantic V2 model.',
                "",
                "    This class represents the schema for a single field in a concept's structure. It supports",
                "    various field types including text, list, dict, integer, boolean, number, and date, as well",
                "    as choice-based fields (enums).",
                "",
                "    Attributes:",
                "        definition: Natural language description of the field's purpose and usage.",
                "        type: The field's data type. When 'dict', both key_type and value_type must be specified.",
                "              When None, choices must be provided (creating an enum field).",
                "        item_type: For 'list' type fields, specifies the type of items in the list.",
                "        key_type: For 'dict' type fields, specifies the type of dictionary keys. Required when type='dict'.",
                "        value_type: For 'dict' type fields, specifies the type of dictionary values. Required when type='dict'.",
                "        choices: List of valid string choices for enum fields. When provided, type must be None.",
                "        required: Whether the field is mandatory. Defaults to True unless explicitly set to False.",
                "        default_value: Default value for the field. Must match the specified type, and for choice",
                "                      fields must be one of the valid choices. When provided, type must be specified",
                "                      (unless choices are provided).",
                "",
                "    Validation Rules:",
                "        1. Choice fields (enums): When type is None, choices must be provided and non-empty.",
                "        2. Dictionary fields: When type is 'dict', both key_type and value_type are required.",
                "        3. Default values: When default_value is provided:",
                "           - For typed fields: type must be specified and default_value must match that type",
                "           - For choice fields: default_value must be one of the valid choices",
                "           - Type validation includes: text (str), integer (int), boolean (bool),",
                "             number (int/float), list (list), dict (dict)",
                "        4. List fields: When type is 'list', item_type should specify the type of list items.",
                "",
                "    Raises:",
                "        ConceptStructureBlueprintError: When validation rules are violated.",
                '    """',
                "    definition: str",
                "    type: Optional[ConceptStructureBlueprintFieldType]",
                "    item_type: Optional[str]",
                "    key_type: Optional[str]",
                "    value_type: Optional[str]",
                "    choices: Optional[List[str]]",
                "    required: Optional[bool]",
                "    default_value: Optional[Any]",
                "",
                "class ConceptStructureBlueprintFieldType(StrEnum):",
                '    TEXT = "text"',
                '    LIST = "list"',
                '    DICT = "dict"',
                '    INTEGER = "integer"',
                '    BOOLEAN = "boolean"',
                '    NUMBER = "number"',
                '    DATE = "date"',
                "",
                "class PipeBatchBlueprint(PipeBlueprint):",
                '    """Blueprint for batch processing pipe operations in the Pipelex framework.',
                "",
                "    PipeBatch enables parallel execution of a single pipe across multiple items",
                "    in a list. Each item is processed independently, making it ideal for data",
                "    transformation, enrichment, or analysis tasks on collections.",
                "",
                "    This controller is commonly used within PipeSequence for inline batch processing,",
                "    where the batch configuration is specified directly in the sequence step using",
                "    batch_over and batch_as parameters in SubPipeBlueprint.",
                "",
                "    Attributes:",
                "        type: Fixed to 'PipeBatch' for this pipe type.",
                "        branch_pipe_code: The pipe code to execute for each item in the input list.",
                "                         This pipe is instantiated once per item in parallel.",
                "        input_list_name: Name of the list in WorkingMemory to iterate over.",
                "                        Defaults to the PipeBatch's main input name if not specified.",
                "        input_item_name: Name assigned to individual items within each execution branch.",
                "                        This is how the branch pipe accesses its specific input item.",
                "",
                "    Validation Rules:",
                "        1. branch_pipe_code must reference an existing pipe in the pipeline.",
                "        2. When input_list_name is specified, it must reference a list in context.",
                "        3. The branch pipe should be designed to process single items.",
                "",
                "    Raises:",
                "        PipeDefinitionError: When validation rules are violated.",
                '    """',
                "    type: Literal['PipeBatch']",
                "    branch_pipe_code: str",
                "    input_list_name: Optional[str]",
                "    input_item_name: Optional[str]",
                "",
                "class PipeConditionBlueprint(PipeBlueprint):",
                '    """Blueprint for conditional pipe execution in the Pipelex framework.',
                "",
                "    PipeCondition enables branching logic in pipelines by evaluating expressions",
                "    and executing different pipes based on the results. Supports template-based",
                "    and direct expression evaluation with default fallback options.",
                "",
                "    Attributes:",
                "        type: Fixed to 'PipeCondition' for this pipe type.",
                "        expression_template: Template for building the expression to evaluate.",
                "                           Supports variable substitution for dynamic conditions.",
                "        expression: Direct expression to evaluate. Typically uses the result",
                "                   of the previous pipe. Mutually exclusive with expression_template.",
                "        pipe_map: Mapping of condition results to pipe codes. Each condition",
                "                 outcome triggers execution of its associated pipe.",
                "        default_pipe_code: Fallback pipe to execute when no conditions in pipe_map",
                "                          match the expression result.",
                "        add_alias_from_expression_to: Optional name to store the expression result",
                "                                     in the context for later reference.",
                "",
                "    Validation Rules:",
                "        1. Either expression or expression_template should be provided, not both.",
                "        2. pipe_map keys must be strings representing possible condition outcomes.",
                "        3. All pipe codes in pipe_map and default_pipe_code must be valid pipe references.",
                "",
                "    Raises:",
                "        PipeDefinitionError: When validation rules are violated.",
                '    """',
                "    type: Literal['PipeCondition']",
                "    expression_template: Optional[str]",
                "    expression: Optional[str]",
                "    pipe_map: PipeConditionPipeMapBlueprint",
                "    default_pipe_code: Optional[str]",
                "    add_alias_from_expression_to: Optional[str]",
                "",
                "class PipeConditionPipeMapBlueprint(RootModel):",
                "    root: Dict[str, str]",
                "",
                "class PipeFuncBlueprint(PipeBlueprint):",
                "    type: Literal['PipeFunc']",
                "    function_name: str  # The name of the function to call.",
                "",
                "class PipeImgGenBlueprint(PipeBlueprint):",
                '    """Blueprint for image generation pipe operations in the Pipelex framework.',
                "",
                "    PipeImgGen enables AI-powered image generation using various models like DALL-E or",
                "    diffusion models. Supports static and dynamic prompts with configurable generation",
                "    parameters.",
                "",
                "    Attributes:",
                "        type: Fixed to 'PipeImgGen' for this pipe type.",
                "        img_gen_prompt: Static text prompt for image generation. Use this or dynamic input.",
                "        imgg_handle: Image generation model handle (e.g., 'dall-e-3'). Defaults to global config.",
                "        aspect_ratio: Desired image aspect ratio (e.g., '16:9', '1:1').",
                "        quality: Generated image quality setting (e.g., 'standard', 'hd').",
                "        nb_steps: Number of diffusion steps for diffusion models. More steps increase detail",
                "                 but take longer. Must be > 0.",
                "        guidance_scale: Prompt adherence strength. Higher values mean closer adherence to prompt.",
                "                       Must be > 0.",
                "        is_moderated: Whether to apply content moderation to generated images.",
                "        safety_tolerance: Content moderation tolerance level. Must be between 1 and 6.",
                "        is_raw: Whether to return raw image data instead of processed format.",
                "        seed: Random seed for reproducibility. Use integer value or 'auto' for random seed.",
                "        nb_output: Number of images to generate. Defaults to single image. Must be >= 1.",
                "        img_gen_prompt_var_name: Variable name for dynamic prompt generation from inputs.",
                "",
                "    Validation Rules:",
                "        1. Quality and nb_steps are mutually exclusive (cannot specify both).",
                "        2. nb_steps must be greater than 0 when specified.",
                "        3. guidance_scale must be greater than 0 when specified.",
                "        4. safety_tolerance must be between 1 and 6 inclusive.",
                "        5. nb_output must be at least 1 when specified.",
                "",
                "    Raises:",
                "        PipeDefinitionError: When validation rules are violated or mutually exclusive",
                "                            fields are set simultaneously.",
                '    """',
                "    type: Literal['PipeImgGen']",
                "    img_gen_prompt: Optional[str]",
                "    imgg_handle: Optional[ImggHandle]",
                "    aspect_ratio: Optional[AspectRatio]",
                "    quality: Optional[Quality]",
                "    nb_steps: Optional[int]",
                "    guidance_scale: Optional[float]",
                "    is_moderated: Optional[bool]",
                "    safety_tolerance: Optional[int]",
                "    is_raw: Optional[bool]",
                "    seed: Union[int, Literal['auto']]",
                "    nb_output: Optional[int]",
                "    img_gen_prompt_var_name: Optional[str]",
                "",
                "class AspectRatio(StrEnum):",
                '    SQUARE = "square"',
                '    LANDSCAPE_4_3 = "landscape_4_3"',
                '    LANDSCAPE_3_2 = "landscape_3_2"',
                '    LANDSCAPE_16_9 = "landscape_16_9"',
                '    LANDSCAPE_21_9 = "landscape_21_9"',
                '    PORTRAIT_3_4 = "portrait_4_3"',
                '    PORTRAIT_2_3 = "portrait_2_3"',
                '    PORTRAIT_9_16 = "portrait_9_16"',
                '    PORTRAIT_9_21 = "portrait_9_21"',
                "",
                "class ImggHandle(StrEnum):",
                '    FLUX_1_PRO_LEGACY = "fal-ai/flux-pro"',
                '    FLUX_1_1_PRO = "fal-ai/flux-pro/v1.1"',
                '    FLUX_1_1_ULTRA = "fal-ai/flux-pro/v1.1-ultra"',
                '    SDXL_LIGHTNING = "fal-ai/fast-lightning-sdxl"',
                '    OPENAI_GPT_IMAGE_1 = "openai/gpt-image-1"',
                "",
                "class Quality(StrEnum):",
                '    LOW = "low"',
                '    MEDIUM = "medium"',
                '    HIGH = "high"',
                "",
                "class PipeJinja2Blueprint(PipeBlueprint):",
                "    type: Literal['PipeJinja2']",
                "",
                "class PipeLLMBlueprint(PipeBlueprint):",
                '    """Blueprint for LLM-based pipe operations in the Pipelex framework.',
                "",
                "    PipeLLM enables Large Language Model processing to generate text or structured output.",
                "    Supports text, structured data, and image inputs with flexible prompt configuration",
                "    and output structuring methods.",
                "",
                "    Attributes:",
                "        type: Fixed to 'PipeLLM' for this pipe type.",
                "        system_prompt_template: Template for system prompt with inline variables using $ syntax.",
                "        system_prompt_template_name: Name reference to a system prompt template.",
                "                                    Mutually exclusive with other system_prompt fields.",
                "        system_prompt_name: Name reference to a system prompt.",
                "                           Mutually exclusive with other system_prompt fields.",
                "        system_prompt: Direct system-level prompt to guide LLM behavior. Can be inline text",
                "                      or file reference ('file:path/to/prompt.md'). Mutually exclusive with",
                "                      other system_prompt fields.",
                "        prompt_template: User prompt template with variable substitution. Use $ for inline",
                "                        variables (e.g., $topic) and @ for entire input content (e.g., @text_to_summarize).",
                "                        Note: Don't use @ or $ for image variables. Mutually exclusive with other",
                "                        prompt fields.",
                "        template_name: Name reference to a prompt template. Mutually exclusive with other prompt fields.",
                "        prompt_name: Name reference to a prompt. Mutually exclusive with other prompt fields.",
                "        prompt: Static user prompt without variable injection. Mutually exclusive with other prompt fields.",
                "        llm: LLM preset(s) configuration. Can be single preset or mapping for different",
                "            generation modes (e.g., main, object_direct).",
                "        llm_to_structure: LLM preset specifically for output structuring in preliminary_text mode.",
                "        structuring_method: Method for structured output generation ('direct' or 'preliminary_text').",
                "                           Defaults to global configuration.",
                "        prompt_template_to_structure: Prompt template for second step in preliminary_text mode.",
                "        system_prompt_to_structure: System prompt for structuring step in preliminary_text mode.",
                "        nb_output: Fixed number of outputs to generate (e.g., 3 for exactly 3 outputs).",
                "                  Must be > 0. Mutually exclusive with multiple_output.",
                "        multiple_output: Enables variable-length list generation. Default is false (single output).",
                "                        Set to true for indeterminate number of outputs. Mutually exclusive with nb_output.",
                "",
                "    Validation Rules:",
                "        1. System prompt fields are mutually exclusive (only one can be set).",
                "        2. User prompt fields are mutually exclusive (only one can be set).",
                "        3. Output cardinality: nb_output and multiple_output are mutually exclusive.",
                "        4. nb_output must be greater than 0 when specified.",
                "        5. Structuring method must be 'direct' or 'preliminary_text' when specified.",
                "",
                "    Raises:",
                "        PipeDefinitionError: When validation rules are violated or mutually exclusive",
                "                            fields are set simultaneously.",
                '    """',
                "    type: Literal['PipeLLM']",
                "    system_prompt_template: Optional[str]",
                "    system_prompt_template_name: Optional[str]",
                "    system_prompt_name: Optional[str]",
                "    system_prompt: Optional[str]",
                "    prompt_template: Optional[str]",
                "    template_name: Optional[str]",
                "    prompt_name: Optional[str]",
                "    prompt: Optional[str]",
                "    llm: Union[LLMSetting, str]",
                "    llm_to_structure: Union[LLMSetting, str]",
                "    structuring_method: Optional[StructuringMethod]",
                "    prompt_template_to_structure: Optional[str]",
                "    system_prompt_to_structure: Optional[str]",
                "    nb_output: Optional[int]",
                "    multiple_output: Optional[bool]",
                "",
                "class LLMSetting(ConfigModel):",
                "    llm_handle: str",
                "    temperature: float",
                "    max_tokens: Optional[int]",
                "    prompting_target: Optional[LLMPromptingTarget]",
                "",
                "class LLMPromptingTarget(StrEnum):",
                '    OPENAI = "openai"',
                '    ANTHROPIC = "anthropic"',
                '    MISTRAL = "mistral"',
                '    GEMINI = "gemini"',
                "",
                "class StructuringMethod(StrEnum):",
                '    DIRECT = "direct"',
                '    PRELIMINARY_TEXT = "preliminary_text"',
                "",
                "class PipeOcrBlueprint(PipeBlueprint):",
                '    """Blueprint for OCR (Optical Character Recognition) pipe operations in the Pipelex framework.',
                "",
                "    PipeOcr enables text extraction from images and documents using OCR technology.",
                "    Supports various OCR platforms and output configurations including image detection,",
                "    caption generation, and page rendering.",
                "",
                "    Attributes:",
                "        type: Fixed to 'PipeOcr' for this pipe type.",
                "        ocr_platform: OCR platform to use for text extraction (e.g., Mistral, Tesseract).",
                "                     Defaults to Mistral or global configuration setting.",
                "        page_images: Whether to include detected images in the OCR output. When enabled,",
                "                    extracts and returns embedded images found in documents.",
                "        page_image_captions: Whether to generate captions for detected images using AI.",
                "                            Useful for understanding image content in documents.",
                "        page_views: Whether to include rendered page views in the output. Provides",
                "                   visual representation of document pages.",
                "        page_views_dpi: DPI (dots per inch) resolution for rendered page views.",
                "                       Higher values provide better quality but larger file sizes.",
                "                       Defaults to configuration setting.",
                "",
                "    Validation Rules:",
                "        1. OCR platform must be a valid OcrPlatform enum value when specified.",
                "        2. Boolean flags (page_images, page_image_captions, page_views) are optional.",
                "        3. page_views_dpi should be a positive integer when specified.",
                "",
                "    Raises:",
                "        ValidationError: When invalid OCR platform or DPI values are provided.",
                '    """',
                "    type: Literal['PipeOcr']",
                "    ocr_platform: Optional[OcrPlatform]",
                "    page_images: Optional[bool]",
                "    page_image_captions: Optional[bool]",
                "    page_views: Optional[bool]",
                "    page_views_dpi: Optional[int]",
                "",
                "class OcrPlatform(StrEnum):",
                '    MISTRAL = "mistral"',
                "",
                "class PipeParallelBlueprint(PipeBlueprint):",
                '    """Blueprint for parallel pipe execution in the Pipelex framework.',
                "",
                "    PipeParallel enables concurrent execution of multiple pipes, improving performance",
                "    for independent operations. All parallel pipes receive the same input context",
                "    and their outputs can be combined or kept separate.",
                "",
                "    Attributes:",
                "        type: Fixed to 'PipeParallel' for this pipe type.",
                "        parallels: List of SubPipeBlueprint instances to execute concurrently.",
                "                  All pipes run simultaneously with access to the same input context.",
                "        add_each_output: Whether to include individual pipe outputs in the combined",
                "                        result. Default is True. When False, only combined_output is used.",
                "        combined_output: Optional concept string/code for the combined output structure.",
                "                        When specified, all parallel outputs are merged into this concept.",
                "",
                "    Validation Rules:",
                "        1. Parallels list must not be empty.",
                "        2. Each parallel step must be a valid SubPipeBlueprint.",
                "        3. combined_output, when specified, must be a valid concept string or code.",
                "        4. Pipe codes in parallels must reference existing pipes.",
                "",
                "    Raises:",
                "        PipeDefinitionError: When validation rules are violated.",
                '    """',
                "    type: Literal['PipeParallel']",
                "    parallels: List[SubPipeBlueprint]",
                "    add_each_output: bool",
                "    combined_output: Optional[str]",
                "",
                "class SubPipeBlueprint(BaseModel):",
                '    """Blueprint for a single step within a pipe controller.',
                "",
                "    SubPipeBlueprint defines individual pipe executions within controller pipes",
                "    (PipeSequence, PipeParallel, PipeBatch, PipeCondition). Supports output",
                "    cardinality control and batch processing configuration.",
                "",
                "    Attributes:",
                "        pipe: The pipe code to execute. Must reference an existing pipe in the pipeline.",
                "        result: Optional name to assign to the pipe's output in the context.",
                "               If not specified, output is added directly to context.",
                "        nb_output: Fixed number of outputs to generate. Mutually exclusive with",
                "                  multiple_output.",
                "        multiple_output: When true, allows LLM to determine the number of outputs.",
                "                        Mutually exclusive with nb_output.",
                "        batch_over: Name of the list in context to iterate over for batch processing.",
                "                   When false (default), no batching occurs. When specified as string,",
                "                   references a list in context. Requires batch_as when set.",
                "        batch_as: Name to assign to the current item during batch iteration.",
                "                 Required when batch_over is specified.",
                "",
                "    Validation Rules:",
                "        1. nb_output and multiple_output are mutually exclusive.",
                "        2. batch_over and batch_as must be specified together (both or neither).",
                "        3. pipe must reference a valid pipe code.",
                "        4. result, when specified, should follow naming conventions.",
                "",
                "    Raises:",
                "        PipeDefinitionError: When validation rules are violated.",
                '    """',
                "    pipe: str",
                "    result: Optional[str]",
                "    nb_output: Optional[int]",
                "    multiple_output: Optional[bool]",
                "    batch_over: Union[bool, str]",
                "    batch_as: Optional[str]",
                "",
                "class PipeSequenceBlueprint(PipeBlueprint):",
                '    """Blueprint for sequential pipe execution in the Pipelex framework.',
                "",
                "    PipeSequence orchestrates the execution of multiple pipes in a defined order,",
                "    where each pipe's output can be used as input for subsequent pipes. This enables",
                "    building complex data processing workflows with step-by-step transformations.",
                "",
                "    Attributes:",
                "        type: Fixed to 'PipeSequence' for this pipe type.",
                "        steps: Ordered list of SubPipeBlueprint instances defining the pipes",
                "              to execute. Each step runs after the previous one completes,",
                "              with access to all prior outputs in the context.",
                "",
                "    Validation Rules:",
                "        1. Steps list must not be empty.",
                "        2. Each step must be a valid SubPipeBlueprint instance.",
                "        3. Pipe codes referenced in steps must exist in the pipeline.",
                "",
                "    Raises:",
                "        PipeDefinitionError: When validation rules are violated.",
                '    """',
                "    type: Literal['PipeSequence']",
                "    steps: List[SubPipeBlueprint]",
                # ------ end of your pasted output ------
            ]
        ),
    ),
]
