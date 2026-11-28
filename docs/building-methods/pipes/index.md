---
description: "Design composable pipelines by combining pipe operators and controllers. Break complex AI tasks into testable, deterministic units."
---

# Designing Pipelines

In Pipelex, a pipeline is not just a rigid sequence of steps; it's a dynamic and intelligent method built by composing individual, reusable components called **pipes**. This approach allows you to break down complex AI tasks into manageable, testable, and reliable units.

This guide provides an overview of how to design your pipelines.

## The Building Blocks: Pipes

A pipeline is composed of pipes. There are two fundamental types of pipes you will use to build your methods:

*   **[Pipe Operators](./pipe-operators/index.md)**: These are the "workers" of your pipeline. They perform concrete actions like calling an LLM (`PipeLLM`), extracting text from a document (`PipeExtract`), searching the web (`PipeSearch`), answering a closed question with a verdict (`PipeJudge`), or running a Python function (`PipeFunc`). Each operator is a specialized tool designed for a specific task.
*   **[Pipe Controllers](./pipe-controllers/index.md)**: These are the "managers" of your pipeline. They don't perform tasks themselves but orchestrate the execution flow of other pipes. They define the logic of your method, such as running pipes in sequence (`PipeSequence`), in parallel (`PipeParallel`), or based on a condition (`PipeCondition`).

A third, design-time-only kind of pipe — **[Signature Pipes](./signature-pipes.md)** — lets you stub a pipe's contract (inputs and output) by declaring it with no `type` and no implementation: a typeless, contract-only pipe *is* a signature. Signatures dry-run as mocks under `--allow-signatures`, so you can sketch a pipeline top-down before writing each operator. Strict validation refuses pipelines that still depend on a signature.

## Designing a Pipeline: Composition in MTHDS

The most common way to design a pipeline is by defining and composing pipes in a `.mthds` configuration file. This provides a clear, declarative way to see the structure of your method.

Each pipe, whether it's an operator or a controller, is defined in its own `[pipe.<pipe_code>]` table. The `<pipe_code>` becomes the unique identifier for that pipe.

!!! important "Pipe Code Naming Convention"
    Pipe codes **MUST** be in `snake_case` (lowercase with underscores). Use descriptive names that clearly indicate what the pipe does.
    
    **Valid pipe codes:**
    ```toml
    ✅ [pipe.generate_tagline]
    ✅ [pipe.extract_invoice]
    ✅ [pipe.validate_and_process]
    ✅ [pipe.send_email]
    ```
    
    **Invalid pipe codes:**
    ```toml
    ❌ [pipe.GenerateTagline]     # PascalCase not allowed
    ❌ [pipe.generateTagline]      # camelCase not allowed
    ❌ [pipe.generate-tagline]     # Hyphens not allowed
    ❌ [pipe.GENERATE_TAGLINE]     # All caps not allowed
    ```

Let's look at a simple example. Imagine we want a method that:
1.  Takes a product description.
2.  Generates a short, catchy marketing tagline for it.

We can achieve this with a `PipeLLM` operator.

`marketing_pipeline.mthds`
```toml
domain = "marketing"
description = "Marketing content generation domain"

# 1. Define the concepts used in our pipes
[concept]
ProductDescription = "A description of a product's features and benefits"
Tagline = "A catchy marketing tagline"

# 2. Define the pipe that does the work
[pipe.generate_tagline]
type = "PipeLLM"
description = "Generate a catchy tagline for a product"
inputs = { description = "ProductDescription" }
output = "Tagline"
prompt = """
Product Description:
@description

Generate a catchy tagline based on the above description.
The tagline should be memorable, concise, and highlight the key benefit.
"""
```

This defines a single-step pipeline. The pipe `generate_tagline` takes a `ProductDescription` as input and outputs a `Tagline` (both are custom concepts defined by a simple description, so they are Text-based by default — see more about native concepts [here](../concepts/native-concepts.md)).

The inputs specified will be required before the pipe is executed. Those inputs should be stored in the [Working Memory](working-memory.md).

The output concept is very important. Indeed, the output of your pipe will be corresponding to the concept you specify. If the concept is structured, the output will be a structured object. If the concept is Text-based — like `Tagline` here — the output is text. Other native concepts produce their corresponding content type (an `Image` output is an image, a `Number` output is a number, and so on).

### Understanding the Pipe Contract

Every pipe defines a **contract** through its `inputs` and `output` fields. This contract is fundamental to how Pipelex ensures reliability in your methods:

*   **`inputs`**: This dictionary defines the **mandatory and necessary** data that must be present in the [Working Memory](working-memory.md) before the pipe can execute. Each key in the dictionary becomes a variable name that you can reference in your pipe's logic (e.g., in prompts), and each value specifies the concept type that the data must conform to. If any required input is missing or doesn't match the expected concept, the pipeline will fail a clear error message.
You can specify multiple inputs by using a list of concepts. For example, `inputs = { description = "ProductDescription", keywords = "Keyword[]" }` will require a `ProductDescription` and a list of `Keyword`s. (See more about [Understanding Multiplicity](./understanding-multiplicity.md) for details.)

    An input name is a plain `snake_case` identifier, matching `[a-z][a-z0-9_]*`, and it names one whole value of the concept its slot declares. A dotted key such as `"invoice.total" = "Number"` does not declare a field of `invoice`: it is refused as `invalid_input_name`, on every pipe. A pipe that needs one field of a value declares the value with its whole concept, `invoice = "Invoice"`, and reads the field through it in its template, as `$invoice.total`. `pipelex fix bundle` deletes a dotted key whose root is declared beside it, since that root already supplies the field, unless the key, declared after its root, carries another presence marker or multiplicity than the root, such as `"data.text" = "Text!"` after `data = "Text?"`: deleting that key would change what the pipe requires, so the fix names only what differs, the multiplicity, the presence marker or both, with the edit that carries it onto the root (here, replace `?` with `!` on `data`), and is left for you to apply.

    Each input slot can be written in two equivalent ways. The **plain form** gives the concept as a string — `topic = "Text"` — and is what you want almost always. The **expanded form** gives a table instead, so the slot can say more about the value it takes:

    ```toml
    [pipe.review_nda.inputs]
    nda = { concept = "Document", description = "The signed NDA to review", hints = { role = "subject" } }
    budget = { concept = "Number", minimum = 0, unit = "EUR", examples = [5000] }
    tier = { concept = "Text", choices = [{ value = "strategic", label = "Strategic" }, "tactical"] }
    names = { concept = "Text[]", max_length = 80 }
    ```

    The `concept` key takes exactly the grammar the plain string does, presence markers and multiplicity included (`"Note?"`, `"Keyword[]"`). Beside it the table accepts:

    - `hints`, the slot's [intent hints](../concepts/intent-hints.md), including its `role`;
    - `description`, a non-empty sentence a form shows in place of the concept's description;
    - the [contract facts](../concepts/inline-structures.md#contract-facts) of the slot's value, when its concept is text-, number-, date- or time-valued, never `aggregate`; on a plural slot they apply to each item;
    - `choices`, on a text-valued slot only, as on a [choice field](../concepts/inline-structures.md#choice-fields-enums); beside `choices` a slot takes no length, `pattern`, `format` or `examples`.

    Anything else is a validation error, and a fact on a slot whose concept holds no plain value, a structured concept for instance, is refused with the reason `not_value_slot`. A slot's constraints and options are enforced on the value a caller sends to the run's entry pipe, a text given by URL or stored for being large included, which is read for the check and refused as `input.invalid` when it breaks one or cannot be read, and they are stated on the slot's input JSON Schema. A slot table carrying none of these keys is the same slot as the plain string: `x = { concept = "Text" }` and `x = "Text"` parse to identical blueprints.

*   **`activity`** (optional): A short phrase a person watching a run reads while the pipe works, such as `activity = "Reading the lease"`. It is one line, never empty, and a contract-only signature does not carry it. The run's graph carries it on the pipe's node as `activity`, beside its `description`, and so does the trace event that starts the node, so a timeline shows it in place of the description.

*   **`output_filename`** (optional): On an operator whose output is an `Image` or a `Document`, a Jinja2 template naming the file the pipe writes, such as `output_filename = "{{ counterparty }} - NDA review"`. It reads only declared inputs, counts as reading them, and must guard every optional input it names with `{% if %}`. A controller writes no file of its own, so it does not carry one. See [Naming the files a step produces](#naming-the-files-a-step-produces).

*   **`output`**: This field declares what the pipe will produce. The output will always be an instance of the specified concept. The structure and type of the output depend on the concept definition (See more about concepts [here](../concepts/native-concepts.md)).
    *   You can specify **multiple outputs** using bracket notation (e.g., `Keyword[]` for a variable list, or `Image[3]` for exactly 3 images)

### Naming the Files a Step Produces

When an operator stating `output_filename` has produced its output, the runtime renders the template once with the pipe's inputs and gives each `Image` or `Document` of the output the name it builds, as the file's `filename`, the name a download and `pipelex run --save-main-stuff` use. The name is built in these steps:

1. The rendered text is normalized to NFC, each run of white space becomes one space, each of `/ \ : * ? " < > |` and each control character becomes `-`, and white space and dots are trimmed from both ends. A name that is a device name Windows reserves, such as `CON` or `LPT1`, takes a trailing `_`.
2. The name keeps the extension of the name the runtime would have given the file: an extension the template already wrote, in any letter case, is kept as written, and any other is appended.
3. The whole name, extension included, is cut to 255 bytes of UTF-8, never inside a character.
4. When the template fails to render, or nothing is left before the extension, the file keeps the name the runtime would have given it, with a warning in the log. Naming a file never fails a run.
5. On a plural output, such as `Image[3]`, the second and later files take ` (2)`, ` (3)` and so on before the extension.

So `output_filename = "{{ client }} cover"` with the input `Acme/Corp` names two images `Acme-Corp cover.png` and `Acme-Corp cover (2).png`. The name never decides where a file is stored: the stored file and its URL are left as they were. A dry run names its placeholder files the same way.

### Multi-Step Methods

To create a multi-step method, you use a controller. The `PipeSequence` controller is the most common one. It executes a series of pipes in a specific order.


`marketing_pipeline.mthds`
```toml
domain = "marketing"
description = "Marketing content generation domain"

# 1. Define the concepts used in our pipes
[concept]
ProductDescription = "A description of a product's features and benefits"
Tagline = "A catchy marketing tagline"
Keyword = "A marketing keyword extracted from text"

# 2. Define the first step of your pipe
[pipe.generate_tagline]
type = "PipeLLM"
description = "Generate a catchy tagline for a product"
inputs = { description = "ProductDescription" }
output = "Tagline"
prompt = """
Product Description:
@description

Generate a catchy tagline based on the above description.
The tagline should be memorable, concise, and highlight the key benefit.
"""

# 3. Define the second step of your pipe
[pipe.extract_keywords_from_tagline]
type = "PipeLLM"
description = "Extract keywords from a tagline"
inputs = { tagline = "Tagline" }
output = "Keyword[]"
prompt = """
Extract the most relevant keywords from the following tagline. Focus on features, benefits, and unique selling points:

@tagline

"""

# 4. Define the controller that orchestrates the two steps
[pipe.description_to_keywords]
type = "PipeSequence"
description = "From product description to tagline keywords"
inputs = { description = "ProductDescription" }
output = "Keyword[]"
steps = [
    { pipe = "generate_tagline", result = "tagline" },
    { pipe = "extract_keywords_from_tagline", result = "keywords" },
]
```

!!! note "Multiple Outputs"
    The `[]` bracket notation in `output = "Keyword[]"` allows the LLM to generate as many keywords as it finds relevant. For a comprehensive guide on controlling how many items pipes produce or accept, see [Understanding Multiplicity](./understanding-multiplicity.md).


This defines a two-step pipeline. The `PipeSequence` controller `description_to_keywords` takes a `ProductDescription` as input and outputs a list of `Keyword`s — a sequence's declared `output` must match what its last step yields. The first step is `generate_tagline` which generates a `Tagline` from the `ProductDescription`. The second step is `extract_keywords_from_tagline` which extracts keywords from the `Tagline`.

See here all the different operators, see [Pipe Operators](./pipe-operators/index.md).
See here all the different controllers, see [Pipe Controllers](./pipe-controllers/index.md).

See more about the possibilities in designing your pipelines in the [Pipelex Bundle Specification](../pipelex-bundle-specification.md).