# tests/unit/pipelex/tools/typing/testdata_structure_printer.py
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
                "    definition: str  # The definition of the concept, in natural language",
                "    structure: Union[str, Dict[str, Union[str, ConceptStructureBlueprint]]]  # The structure of the concept: The key is the field name, in snake_case format, and the value is the structure blueprint of the field.You cannot have a structure and refine at the same time.",
                "    refines: Optional[str]  # The native concept (Text, Image, PDF, TextAndImages, Number, Page) that this concept refines, in PascalCase format.You cannot have a structure and refine at the same time.",
                "",
                "class ConceptStructureBlueprint(BaseModel):",
                '    """This Blueprint defines a field in the structure of a concept, that will be used as a pydantic v2 model."""',
                "    definition: str  # The definition of the field, in natural language",
                "    type: Optional[ConceptStructureBlueprintFieldType]  # The type of the concept structure. When 'dict', both key_type and value_type must be specified. When 'None', "
                "choices must be provided.",
                "    item_type: Optional[str]  # The type of the item of the concept structure",
                "    key_type: Optional[str]  # The type of the key of the concept structure. Required when type='dict'",
                "    value_type: Optional[str]  # The type of the value of the concept structure. Required when type='dict'",
                "    choices: Optional[List[str]]  # The choices of the concept structure. When provided, type must be None",
                "    required: Optional[bool]  # Whether the concept structure is required. Defaults to True - field is mandatory unless explicitly set to False",
                "    default_value: Optional[Any]  # The default value of the concept structure. Must match the specified type,  and for choice fields must be one of the valid choices. When provided, type must be specified (unless choices are provided)",
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
                "    domain: str  # The domain of the current bundle: snake_case format",
                "    definition: Optional[str]  # The definition depicting the whole pipeline",
                "    system_prompt: Optional[str]  # The system prompt of the current bundle, used by default for all pipes.",
                "    system_prompt_to_structure: Optional[str]  # The system prompt to structure the output of the current bundle",
                "    prompt_template_to_structure: Optional[str]  # The prompt template to structure the output of the current bundle",
                "    concept: Optional[Dict[str, Union[ConceptBlueprint, str]]]  # The concepts used in this domain, to characterise "
                "inputs and ouputs of pipes. The key is the concept code, in PascalCase format.",
                "    pipe: Optional[Dict[str, Union[PipeFuncBlueprint, PipeImgGenBlueprint, PipeJinja2Blueprint, PipeLLMBlueprint, "
                "PipeOcrBlueprint, PipeBatchBlueprint, PipeConditionBlueprint, PipeParallelBlueprint, PipeSequenceBlueprint]]]  "
                "# The pipes of this domain, to transform inputs into outputs. The key is the pipe code, in snake_case format.",
                "",
                "class ConceptBlueprint(BaseModel):",
                "    definition: str  # The definition of the concept, in natural language",
                "    structure: Union[str, Dict[str, Union[str, ConceptStructureBlueprint]]]  # The structure of the concept: The "
                "key is the field name, in snake_case format, and the value is the structure blueprint of the field.You cannot have a structure and refine at the same time.",
                "    refines: Optional[str]  # The native concept (Text, Image, PDF, TextAndImages, Number, Page) that this concept refines, in PascalCase format."
                "You cannot have a structure and refine at the same time.",
                "",
                "class ConceptStructureBlueprint(BaseModel):",
                '    """This Blueprint defines a field in the structure of a concept, that will be used as a pydantic v2 model."""',
                "    definition: str  # The definition of the field, in natural language",
                "    type: Optional[ConceptStructureBlueprintFieldType]  # The type of the concept structure. When 'dict', both "
                "key_type and value_type must be specified. When 'None', choices must be provided.",
                "    item_type: Optional[str]  # The type of the item of the concept structure",
                "    key_type: Optional[str]  # The type of the key of the concept structure. Required when type='dict'",
                "    value_type: Optional[str]  # The type of the value of the concept structure. Required when type='dict'",
                "    choices: Optional[List[str]]  # The choices of the concept structure. When provided, type must be None",
                "    required: Optional[bool]  # Whether the concept structure is required. Defaults to True - field is mandatory "
                "unless explicitly set to False",
                "    default_value: Optional[Any]  # The default value of the concept structure. Must match the specified type,  "
                "and for choice fields must be one of the valid choices. When provided, type must be specified "
                "(unless choices are provided)",
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
                '    """PipeBatch is used to run a pipe on a list of items in parallel.',
                "    This is a pipe Controller, it orchestrates the execution of a pipe on a list of items.",
                "",
                "    This pipe is mostly used directly inside a `PipeSequence` pipe like so:",
                "    ```toml",
                "    [pipe.sequence_with_batch]",
                '    type = "Sequence"',
                '    description = "A Sequence of pipes"',
                '    inputs = { input_data = "ConceptName" }',
                '    output = "OutputConceptName"',
                "    steps = [",
                '    { pipe = "pipe_to_apply", batch_over = "input_list", batch_as = "current_item", result = "batch_results" }',
                "    ]",
                "    ```",
                "    ## Key Parameters",
                "    - `pipe`: The pipe operation to apply to each element in the batch",
                "    - `batch_over`: The name of the list in the context to iterate over",
                "    - `batch_as`: The name to use for the current element in the pipe's context",
                "    - `result`: Where to store the results of the batch operation",
                '    """',
                "    type: Literal['PipeBatch']",
                "    branch_pipe_code: str  # The name of the single pipe to execute for each item in the input list.",
                "    input_list_name: Optional[str]  # The name of the list in the `WorkingMemory` to iterate over. If not "
                "provided, it defaults to the name of the `PipeBatch`'s main `input`.",
                "    input_item_name: Optional[str]  # The name that an individual item from the list will have inside its "
                "execution branch. This is how the branch pipe finds its input.",
                "",
                "class PipeConditionBlueprint(PipeBlueprint):",
                '    """PipeCondition is used to execute different pipes based on a condition."""',
                "    type: Literal['PipeCondition']",
                "    expression_template: Optional[str]  # The template for the expression to evaluate.",
                "    expression: Optional[str]  # The expression to evaluate in order to determine which pipe to execute. "
                "(This the result of the previous pipe)",
                "    pipe_map: PipeConditionPipeMapBlueprint",
                "    default_pipe_code: Optional[str]  # The pipe to execute if the condition is not met.",
                "    add_alias_from_expression_to: Optional[str]  # The name to use for the expression in the context.",
                "",
                "class PipeConditionPipeMapBlueprint(RootModel):",
                "    root: Dict[str, str]  # The map of pipes to execute based on the condition. The key is the condition, "
                "the value is the pipe code to execute.",
                "",
                "class PipeFuncBlueprint(PipeBlueprint):",
                "    type: Literal['PipeFunc']",
                "    function_name: str  # The name of the function to call.",
                "",
                "class PipeImgGenBlueprint(PipeBlueprint):",
                '    """PipeImgGen is used to generate images."""',
                "    type: Literal['PipeImgGen']",
                "    img_gen_prompt: Optional[str]  # A static text prompt for image generation. Use this or input",
                "    imgg_handle: Optional[ImggHandle]  # The handle for the image generation model to use (e.g., 'dall-e-3'). "
                "Defaults to the model specified in the global config",
                "    aspect_ratio: Optional[AspectRatio]  # The desired aspect ratio of the image (e.g., '16:9', '1:1')",
                "    quality: Optional[Quality]  # The quality of the generated image (e.g., 'standard', 'hd')",
                "    nb_steps: Optional[int]  # For diffusion models, the number of steps to run. More steps can increase detail "
                "but take longer. Must be > 0",
                "    guidance_scale: Optional[float]  # How strictly the model should adhere to the prompt. Higher values mean "
                "closer adherence. Must be > 0",
                "    is_moderated: Optional[bool]  # Whether content moderation should be applied",
                "    safety_tolerance: Optional[int]  # Safety tolerance level for content moderation. Must be between 1 and 6",
                "    is_raw: Optional[bool]  # Whether to return raw image data",
                "    seed: Union[int, Literal['auto']]  # A seed for the random number generator to ensure reproducibility. "
                "'auto' uses a random seed",
                "    nb_output: Optional[int]  # The number of images to generate. If omitted, a single image is generated. Must be >= 1",
                "    img_gen_prompt_var_name: Optional[str]  # Variable name for dynamic prompt generation",
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
                '    """PipeLLM is used to run a LLM, to generate text, structured output. It can take as input text, '
                'structured information or images."""',
                "    type: Literal['PipeLLM']",
                "    system_prompt_template: Optional[str]  # The system prompt template to use. Can use inline variables with $ syntax",
                "    system_prompt_template_name: Optional[str]  # The name of the system prompt template to use. "
                "Mutually exclusive with system_prompt, system_prompt_name, and system_prompt_template",
                "    system_prompt_name: Optional[str]  # The name of the system prompt to use. Mutually exclusive "
                "with system_prompt, system_prompt_template, and system_prompt_template_name",
                "    system_prompt: Optional[str]  # A system-level prompt to guide the LLM's behavior (e.g., 'You "
                "are a helpful assistant'). Can be inline text or a reference to a template file ('file:path/to/prompt.md'). "
                "Mutually exclusive with other system_prompt fields",
                "    prompt_template: Optional[str]  # A template for the user prompt. Use $ for inline variables (e.g., $topic) "
                "and @ to insert the content of an entire input (e.g., @text_to_summarize). Note: Do not use @ or $ for image variables. "
                "Mutually exclusive with prompt, prompt_name, and template_name",
                "    template_name: Optional[str]  # The name of the prompt template to use. Mutually exclusive with prompt, prompt_name, "
                "and prompt_template",
                "    prompt_name: Optional[str]  # The name of the prompt to use. Mutually exclusive with prompt, prompt_template, and template_name",
                "    prompt: Optional[str]  # A simple, static user prompt. Use this when you don't need to inject any variables. "
                "Mutually exclusive with other prompt fields",
                "    llm: Union[LLMSetting, str]  # Specifies the LLM preset(s) to use. Can be a single preset or a table mapping "
                "different presets for different generation modes (e.g., main, object_direct)",
                "    llm_to_structure: Union[LLMSetting, str]  # LLM preset to use specifically for structuring output in preliminary_text mode",
                "    structuring_method: Optional[StructuringMethod]  # The method for generating structured output. Can be 'direct' "
                "or 'preliminary_text'. Defaults to the global configuration",
                "    prompt_template_to_structure: Optional[str]  # The prompt template for the second step in 'preliminary_text' mode",
                "    system_prompt_to_structure: Optional[str]  # The system prompt for the structuring step in 'preliminary_text' mode",
                "    nb_output: Optional[int]  # Specifies exactly how many outputs to generate (e.g., nb_output = 3 for exactly 3 outputs). "
                "Use when you need a fixed number of results. Mutually exclusive with multiple_output. Must be > 0",
                "    multiple_output: Optional[bool]  # Controls output generation mode. Default is false (single output). Set to true for "
                "variable-length list generation when you need an indeterminate number of outputs. Mutually exclusive with nb_output",
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
                '    """PipeOcr is used to extract text from images with OCR technology."""',
                "    type: Literal['PipeOcr']",
                "    ocr_platform: Optional[OcrPlatform]  # OCR platform to use for text extraction. Defaults to Mistral",
                "    page_images: Optional[bool]  # Include detected images in the OCR output",
                "    page_image_captions: Optional[bool]  # Generate captions for detected images",
                "    page_views: Optional[bool]  # Include rendered page views in the output",
                "    page_views_dpi: Optional[int]  # DPI resolution for page views. Defaults to configuration setting",
                "",
                "class OcrPlatform(StrEnum):",
                '    MISTRAL = "mistral"',
                "",
                "class PipeParallelBlueprint(PipeBlueprint):",
                '    """PipeParallel is used to run multiple different pipes in parallel."""',
                "    type: Literal['PipeParallel']",
                "    parallels: List[SubPipeBlueprint]  # The list of pipe steps to run in parallel.",
                "    add_each_output: bool  # Whether to add each output to the combined output.",
                "    combined_output: Optional[str]  # The name of the combined output.",
                "",
                "class SubPipeBlueprint(BaseModel):",
                '    """SubPipeBlueprint is used to charaterize a step in a Pipe Controller (PipeSequence, PipeParallel, PipeBatch, PipeCondition).',
                "    It should have no more than '1' of nb_output or multiple_output.",
                "    When batch_over is specified, batch_as must also be provided.",
                "    When batch_as is specified, batch_over must also be provided.",
                '    """',
                "    pipe: str  # The pipe code to run.",
                "    result: Optional[str]  # The name to assign to the output of the pipe.",
                "    nb_output: Optional[int]  # The number of outputs to generate.",
                "    multiple_output: Optional[bool]  # Whether to generate multiple outputs. (if yes, it leaves to the "
                "LLM the choice of the number of outputs)",
                "    batch_over: Union[bool, str]  # The name of the list in the context to iterate over.",
                "    batch_as: Optional[str]  # The name to assign to the current item in the batch.",
                "",
                "class PipeSequenceBlueprint(PipeBlueprint):",
                '    """PipeSequence is used to run a list of pipes in sequence."""',
                "    type: Literal['PipeSequence']",
                "    steps: List[SubPipeBlueprint]  # The list of pipe steps to run in sequence.",
                # ------ end of your pasted output ------
            ]
        ),
    ),
]
