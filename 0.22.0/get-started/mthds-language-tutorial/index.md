# The MTHDS Language Tutorial

This tutorial walks you through writing `.mthds` files manually, step by step.

Set up your project and get free AI access:

```bash
pip install pipelex
pipelex init
pipelex login
```

`pipelex init` creates your project configuration. `pipelex login` opens your browser to authenticate with Pipelex Gateway (free). See [Configure AI Providers](./configure-ai-providers.md) for other options: bring your own keys, local AI, etc.

!!! tip "VS Code Extension"
    We **highly** recommend installing the Pipelex extension for `.mthds` syntax highlighting and flowchart visualization:

    - **VS Code**: Install from the [VS Code Marketplace](https://marketplace.visualstudio.com/items?itemName=pipelex.pipelex)
    - **Cursor, Windsurf, and other VS Code forks**: Install from the [Open VSX Registry](https://open-vsx.org/extension/Pipelex/pipelex)

    Running `pipelex init` will also offer to install the extension automatically if it detects your IDE.

## Step 1: Hello World

Create a file called `hello_world.mthds`:

```toml
domain      = "tutorial_hello_world"
description = "Your first Pipelex pipeline"
main_pipe   = "tutorial_hello_world"

[pipe]

[pipe.tutorial_hello_world]
type = "PipeLLM"
description = "Generate a creative story idea"
output = "Text"
prompt = """
Generate a one-paragraph creative story idea about a robot learning to paint.
"""
```

Run it:

```bash
pipelex run bundle hello_world.mthds
```

Here's what each part means:

- **`domain`** — a namespace for this bundle (like a Python package name)
- **`main_pipe`** — the entry point pipe that runs when you execute the bundle
- **`PipeLLM`** — a pipe type that makes an LLM call
- **`output = "Text"`** — the pipe returns plain text (a native concept)
- **`prompt`** — the prompt sent to the LLM

## Step 2: Chaining LLM Calls

Most real methods need multiple steps. `PipeSequence` chains pipes together, passing data between them.

Create `chaining_llm_calls.mthds`:

```toml
domain      = "chaining_llm_calls"
description = "Chain multiple LLM calls together"
main_pipe   = "generate_and_expand"

[pipe]

# First pipe: Generate a story idea
[pipe.chain_generate_idea]
type = "PipeLLM"
description = "Generate a creative story idea"
output = "Text"
prompt = """
Generate a one-paragraph creative story idea about a robot learning to paint.
"""

# Second pipe: Expand the story idea (uses result from first pipe)
[pipe.chain_expand_idea]
type = "PipeLLM"
description = "Expand a story idea into a detailed outline"
inputs = { story_idea = "Text" }
output = "Text"
prompt = """
Take this story idea and expand it into a 3-act outline:

@story_idea

Provide a brief description for each act.
"""

# PipeSequence: Chain the two pipes together
[pipe.generate_and_expand]
type = "PipeSequence"
description = "Generate a story idea then expand it"
output = "Text"
steps = [
  { pipe = "chain_generate_idea", result = "story_idea" },
  { pipe = "chain_expand_idea", result = "story_outline" },
]
```

Run it:

```bash
pipelex run bundle chaining_llm_calls.mthds
```

Key concepts:

- **`PipeSequence`** — runs pipes in order, passing results between them
- **`steps`** — each step names a pipe and stores its output in a `result` variable
- **`@story_idea`** — references data from a previous step's result in the prompt

## Step 3: Using Inputs

Instead of hardcoding everything in the prompt, you can pass data in at runtime.

Create `using_inputs.mthds`:

```toml
domain      = "using_inputs"
description = "Learn how to pass inputs to your pipeline"
main_pipe   = "write_about_topic"

[pipe]

# A pipe that takes an input and uses it
[pipe.write_about_topic]
type = "PipeLLM"
description = "Write a short paragraph about a given topic"
inputs = { topic = "Text" }
output = "Text"
prompt = """
Write a short, engaging paragraph about the following topic:

$topic

Keep it under 100 words.
"""
```

Create an `inputs.json` file:

```json
{
  "topic": "Photosynthesis"
}
```

Run it with the `-i` flag:

```bash
pipelex run bundle using_inputs.mthds -i inputs.json
```

Key concepts:

- **`inputs = { topic = "Text" }`** — declares what the pipe expects as input
- **`$topic`** — references an input variable in the prompt (as opposed to `@variable` which references data from working memory)
- **`-i inputs.json`** — provides input data at runtime

## Step 4: Structured Outputs

LLMs can return structured data instead of plain text. Define a **concept** with a **structure**, and the LLM output will be validated against it.

Create `structured_output.mthds`:

```toml
domain      = "structured_output"
description = "Get structured data from LLMs"
main_pipe   = "struct_generate_book_idea"

[concept]

# Define the structure of a book idea
[concept.BookIdea]
description = "A book idea with title, genre, and synopsis"

[concept.BookIdea.structure]
title           = { type = "text", description = "The book title", required = true }
genre           = { type = "text", description = "The genre of the book", required = true }
synopsis        = { type = "text", description = "A brief synopsis of the book" }
target_audience = { type = "text", description = "Who this book is for" }

[pipe]

# Generate a structured book idea
[pipe.struct_generate_book_idea]
type = "PipeLLM"
description = "Generate a structured book idea"
output = "BookIdea"
prompt = """
Generate a creative book idea. Provide a compelling title, genre, synopsis, and target audience.
"""
```

Run it:

```bash
pipelex run bundle structured_output.mthds
```

Key concepts:

- **`[concept.BookIdea]`** — declares a typed concept with a description
- **`[concept.BookIdea.structure]`** — defines the fields and their types
- **`output = "BookIdea"`** — the pipe returns a structured `BookIdea` object instead of plain text

Learn more about concepts in [Define Your Concepts](../building-methods/concepts/define_your_concepts.md).

---

## Next Steps

You now understand the building blocks: pipes, sequences, inputs, and structured outputs.

- **Tutorial** — more lessons in the [Cookbook](../cookbook/index.md) (document extraction, batch processing, and more)
- **Build Reliable AI Methods** — deep dive into [method project design](../building-methods/kick-off-a-methods-project.md)
- **Pipe Operators & Controllers** — reference for [pipe operators](../building-methods/pipes/pipe-operators/index.md) (PipeLLM, PipeExtract, PipeCompose, ...) and [pipe controllers](../building-methods/pipes/pipe-controllers/index.md) (PipeSequence, PipeParallel, PipeBatch, PipeCondition)
- **Cookbook Examples** — real-world [examples and patterns](../cookbook/index.md)
- **CLI Reference** — full [command-line reference](../tools/cli/index.md)
