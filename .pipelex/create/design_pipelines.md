## Designing Pipelex pipelines

This section explains how to design pipelines for Pipelex.

### Workflow for a designer agent

- Plan the pipeline in natural language (goal, inputs, steps, outputs).

- Translate the plan into a `PipelexBundleBlueprint` object graph: domain, concepts, pipes.

- Define controllers first (`PipeSequence`, `PipeParallel`, `PipeCondition`), then operators (`PipeLLM`, `PipeOcr`, etc.).

- For each new pipe, detail its `type` and `definition`.

- Ensure each pipe’s `inputs` shows all required variables, including those used by nested steps or conditional branches. `inputs` is a dict mapping variable names to concept codes.

- Choose appropriate native or structured output concepts.

### Root blueprint object: PipelexBundleBlueprint

`PipelexBundleBlueprint` fields:

- `domain: str` — required. Single word or snake_case code for the domain.

- `definition: Optional[str]` — optional textual description of the domain.

- `system_prompt: Optional[str]` — default system prompt applied by LLM pipes in this domain if they don’t provide one.

- `system_prompt_to_structure: Optional[str]` — domain-level instructions to structure outputs.

- `prompt_template_to_structure: Optional[str]` — domain-level instructions to structure prompts.

- `concept: Dict[str, Union[str, ConceptBlueprint]]` — concept section. Keys are concept names (PascalCase). Values are either:

  - a string (quick form): the concept definition; or

  - a `ConceptBlueprint` object (full form).

- `pipe: Dict[str, Dict[str, Any]]` — pipes section. Keys are pipe codes (snake_case). Values are per-pipe details dicts that will be validated into concrete `PipeBlueprint` subclasses based on their `type`.

### Concepts

- Conceiving and naming concepts:
  - Use PascalCase for concept names.

  - DO NOT use plurals in concept names (use `Item` not `Items`).

  - DO NOT use adjectives in concept names (use `Text`, not `LargeText`).

  - When a concept or concept reference is unqualified (no `domain.` prefix), it will be prefixed with the current blueprint `domain` during validation/expansion, unless its name corresponds to one of the native concepts.

  - Do not redefine native concepts (use them directly): `Text`, `Image`, `PDF`, `TextAndImages`, `Number`, `Page`, `LLMPrompt`.

  - Textual concepts refining `native.Text` are acceptable too, and you don't need to specify their structure: by default it'll be text.
  
  - Reuse existing concepts whenever possible. For instance if you take a `Poem` and make it dark, the result is a `Poem` too: you MUST NOT create a new `DarkPoem` concept in this kind of situation.

  - Concepts from the base library are also provided and must be used whenever possible:

    - `documents.TextAndImagesContent` = "A content that comprises text and images where the text can include local links to the images"

    - `images.VisualDescription` = "Visual description of something"

    - `images.ImgGenPrompt`:
      - definition = "Prompt to generate an image"
      - refines = "Text"

    - `images.Photo`:
      - definition = "Photo"
      - structure = "ImageContent"
      - refines = "Image"

  - DO NOT create a concept qualified with circumstances like `InputPhoto`: it's just a `Photo`, it so happens that we're using it as input, OK, but that will be convened by the rest of the structure.

- Quick form (string):

  - `concept["ConceptName"] = "Definition of the concept"`

  - If no `structure` is specified and the name isn’t a known structure class, it implicitly refines `native.Text`.

- Full form (`ConceptBlueprint` from `pipelex/core/concept_factory.py`):

  - `definition: str` — required.

  - `structure: Optional[str]` — name of a registered `StructuredContent` subclass (typically defined in `pipelex_libraries/pipelines/<domain>.py`). If provided, it must exist in the class registry.

  - `refines: Union[str, List[str]]` — concept codes or names it refines. May be a single string or a list. Unqualified names are prefixed with the current `domain` automatically.

  - `domain: Optional[str]` — not required when provided via the library loader.

### Pipes: overall rules

Each entry under `pipe` is a dict that will be converted into a typed `PipeBlueprint` (see `pipelex/core/blueprint.py` for the base and factories in `pipe_controllers/` and `pipe_operators/`). Use the new format:

- `type: str` — the pipe class name, e.g., `PipeLLM`, `PipeOcr`, `PipeSequence`, `PipeParallel`, `PipeCondition`, `PipeFunc`, `PipeImgGen`.

- `definition: str` — human-readable description of the pipe’s responsibility.

- `inputs: Optional[Dict[str, str]]` — map of variable name -> concept code or name. Unqualified names are prefixed with `domain`.

- `output: str` — target concept code or name. Unqualified names are prefixed with `domain`.

Important:

- For controller pipes (`PipeSequence`, `PipeParallel`, `PipeCondition`), the parent pipe’s `inputs` must include all variables required by its sub-pipes or conditional branches that come from the initial working memory (i.e., not produced by previous steps).

- Multiplicity: some pipes and sub-steps can produce multiple outputs (see below). Plan result names accordingly.

### Pipe-specific blueprint schemas

Below are the additional fields expected per type, on top of the base fields above (`type`, `definition`, `inputs`, `output`). All fields are validated by their blueprint classes.

#### PipeLLM (operators/pipe_llm_factory.py)

- Prompt sources (choose at most one per group):

  - System prompt: one of `system_prompt`, `system_prompt_name`, `system_prompt_template`, `system_prompt_template_name`.

  - User prompt: one of `prompt`, `prompt_name`, `prompt_template`, `template_name`.

- LLM selection:

  - `llm: Optional[LLMSettingOrPresetId]` — model for text.

  - `llm_to_structure: Optional[LLMSettingOrPresetId]` — model for object structuring.

- Structuring:

  - `structuring_method: Optional[StructuringMethod]`

  - `prompt_template_to_structure: Optional[str]`

  - `system_prompt_to_structure: Optional[str]`

- Multiplicity:

  - `nb_output: Optional[int]` — exact number of outputs; mutually exclusive with `multiple_output`.

  - `multiple_output: Optional[bool]` — allow variable number of outputs.

Behavioral notes:

- If no system prompt is provided, the domain’s `system_prompt` (from the root blueprint) is used if available.

- Inputs that are `Image` concepts are automatically exposed as user images to the LLM; other inputs become text blocks.

- Prompt template insertion style for the agent:

  - Use block insertion (equivalent to `@name`) for long, multi-line stuff.

  - Use inline insertion (equivalent to `$name`) for short tokens embedded in sentences.

  - Do not synthesize literal markers; provide structured prompt fields and let the runtime render appropriately.

#### PipeOcr (operators/pipe_ocr_factory.py)

- Required input variable name: `ocr_input`.

- The `ocr_input` concept must be `Image` or `PDF`.

- Additional options:

  - `ocr_platform: Optional[OcrPlatform]` — defaults to Mistral.

  - `page_images: bool` — include detected images.

  - `page_image_captions: bool` — caption images.

  - `page_views: bool` — include rendered page views.

  - `page_views_dpi: Optional[int]` — DPI for page views; defaults to config.

- Output concept should be `Page`. The operational result is a list of `Page` items.

#### PipeSequence (controllers/pipe_sequence_factory.py)

- `steps: List[SubPipeBlueprint]`

- `SubPipeBlueprint` fields (controllers/sub_pipe_factory.py):

  - `pipe: str` — referenced pipe code to execute.

  - `result: Optional[str]` — name to assign to this step’s output in working memory.

  - Multiplicity (choose at most one): `nb_output: Optional[int]`, `multiple_output: Optional[bool]`.

  - Batch (both or none): `batch_over: Union[bool, str]` and `batch_as: Optional[str]`.

Rules:

- If `batch_over` is provided, `batch_as` is required; if `batch_as` is provided, `batch_over` is required.

- When batching, the step runs in parallel over each element of the specified list, and the `result` becomes a list.

#### PipeParallel (controllers/pipe_parallel_factory.py)

- `parallels: List[SubPipeBlueprint]` — each must specify `result`.

- `add_each_output: bool = True` — whether to add each parallel result separately to memory.

- `combined_output: Optional[str]` — optional combined output concept code; if provided without a domain prefix, it’s prefixed automatically.

Rules:

- At least one of `add_each_output` or `combined_output` must be set appropriately (cannot disable both behaviors).

#### PipeCondition (controllers/pipe_condition_factory.py)

- Choose exactly one of:

  - `expression: Optional[str]` — direct expression.

  - `expression_template: Optional[str]` — Jinja2 template expression.

- `pipe_map: Dict[str, str]` — map of evaluated expression values to pipe codes to execute.

- `default_pipe_code: Optional[str]` — optional fallback pipe code if no key matches.

- `add_alias_from_expression_to: Optional[str]` — if set, store the evaluated expression under this variable name in working memory.

### Input and output concepts resolution

- Unqualified concept names in `inputs` and `output` are automatically prefixed with the current `domain` during blueprint validation (see `PipeBlueprint.add_domain_prefix`).

- For `PipeParallel.combined_output`, the same domain-prefixing rule applies.

### Checklist for the agent

- Define `domain` and optional domain-level prompts (`system_prompt`, `system_prompt_to_structure`, `prompt_template_to_structure`).

- Create `concept` entries using either quick string form or full `ConceptBlueprint` with `definition`, optional `structure`, and `refines`.

- For each pipe under `pipe`:

  - Provide `type`, `definition`, `inputs`, `output`.

  - Add type-specific fields (see sections above).

  - Ensure controller pipes include all upstream inputs needed by nested steps/branches.

  - Set multiplicity (`nb_output`/`multiple_output`) and batch settings where needed.

  - For OCR, use `ocr_input` with `Image` or `PDF`, and set `output` to `Page`.

- Validate mentally that every referenced sub-pipe exists and every input it requires is either provided by the parent `inputs` or produced by a previous step.

### Minimal skeleton (object form)

The agent should generate a structure similar to the following (illustrative, not exhaustive):

```json
{
  "domain": "my_domain",
  "definition": "What this domain covers",
  "system_prompt": "Global system prompt for LLM pipes (optional)",
  "concept": {
    "UserQuery": "Natural language question from a user",
    "Answer": { "definition": "Answer text" }
  },
  "pipe": {
    "answer_question": {
      "type": "PipeLLM",
      "definition": "Produce an answer from a question and context",
      "inputs": { "question": "UserQuery", "context": "Text" },
      "output": "Answer",
      "prompt_template": "Analyze the question and context, then answer concisely.\n\n@question\n\n@context"
    }
  }
}
```
