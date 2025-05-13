# Pipes

A pipe is a **Pipeline step**.
It can integrate **both LLM-based** or software-based knowledge processing.

:bulb: **Remember the Quick-start chapter?** We defined a pipe (in toml, using the [pipe.create_character] section) to generate a character. It constituted a one-pipe-long pipeline.

## Define pipes

Like concepts, Pipes are defined using a **`toml` syntax.**

- This part is meant to be **written in a library `toml` file, in the same one as concepts** (see [Libraries](../Libraries/library.md)).
  💡*In the quick-start example (text summary generator) this is the role of `summarize.toml`.*

### General case

This is how to define a Pipe using the Pipelex `toml` syntax.

![Diagram showing the general structure of a Pipe definition in TOML format](pipe_toml.png)

#### **Fields definition**

```toml
[pipe]
[pipe.<pipe_name>]
Pipe<Type> = "Pipe definition"          # required, str
input = "InputConcept"                  # required, str
output = "OutputConcept"                # required, str
... then come the Pipe specific fields
```

- `Pipe<Type>`(str, required) The presence of this field indicates what type of pipe your are defining and adds a specific definition for it (explaining what it does).
- Productive Pipes:
  - `PipeLLM`: A call to an LLM whihc generates either text or a structured object, or a list of those.
  - `PipeJinja2`: Application of a Jinja2 template to generate Text.
- Control Pipes, to orchestrate the flow of the pipeline:

  - `PipeSequence`: Sequence of Pipes that share a common working memory
  - `PipeParallel`: Executes several pipes in parallel (asynchronously) and output a list of the results
  - `PipeBatch`: Executes the same pipe on each item of a list and output a list of the results
  - `PipeCondition`: Evaluate a test expression and choose which pipe to run according to the test's result

- `input` (str, required) The expected input Concept (PascalCase)
- `output` (str, required) The expected output Concept (PascalCase)
- `additional specific fields` depending on the kind of Pipe you define.

### Type 1: Pipe LLM

If you specifically want to call an LLM and benefit from Pipelex scaffolding, PipeLLM is made for you.

Pipe LLM embeds all you need to run reliable LLM calls in your pipeline.

#### **PipeLLM fields description**

```toml
[pipe.<pipe_name>]
PipeLLM = "Pipe definition" # required, str
input = "InputConcept"  # required, str
output = "OutputConcept" # required, str
llm = "llm_preset_name" # optional, str
llm_to_structure = "llm_preset_name" # optional, str
llm_to_structure_direct = "llm_preset_name" # optional, str
system_prompt = """system prompt""" # optional, str
prompt_template = """jinja2 prompt template""" # required, str
images = [] # optional
```

- `PipeLLM`(str, required) The presence of this field indicates that your pipe is a PipeLLM and stores a definition of it (explaining what it does).
- `input` (str, required) The expected input Concept (PascalCase)
- `output` (str, required) The expected output Concept (PascalCase)
- `llm` (str, optional) What llm_preset to use for text generation
- `llm_to_structure` (str, optional) What llm_preset to use for structured object generation
- `llm_to_structure_direct` (str, optional) What llm_preset to use for structured object list generation
- `system_prompt` (str, optional) system prompt used in the LLM call
- `prompt_template` (str, optional) prompt used in the LLM call. This can be a jinja template. See #Jinja
- `images` (List[str], optional) A list of stuff names that contains images.

#### **Example**

This pipe outputs an html table from a table screenshot. It basically converts an image of a table into the html representation of it.

```toml
[pipe.get_html_table_from_image]
PipeLLM = "Get an HTML table"
input = "TableScreenshot"
output = "HtmlTable"
images = ["table_screenshot"]
system_prompt = """
You are a vision-based table extractor.
"""
prompt_template = """
You are given a picture (screenshot) of a table, taken from a PDF document. Your goal is to extract the table from the image **in html**.
Make sure you do not forget any text. Make sure you do not invent any text. Make sure your merge is consistent. Make sure you replicate the formatting (borders, text formatting, colors, text alignment...)
"""
llm = "llm_to_extract_tables"
llm_to_structure = "llm_to_extract_tables"
```

### Type 2: PipeSequence

PipeSequence embeds all you need to run multi-steps processing with a sequence of pipes.

#### **PipeSequence fields description**

- `PipeSequence` (str, required) The presence of this field indicates that your pipe is a PipeSequence and stores a definition of it (explaining what it does).
- `input` (str, required) The expected input Concept (PascalCase)
- `output` (str, required) The expected output Concept (PascalCase)
- `steps` (List[Dict], required) The steps in the Pipe
  - `result` (str, required) The name of the output stuff
  - `pipe` (str, required) The `pipe_code` of the Pipe used for this step.

```toml
[pipe.<pipe_name>]
PipeSequence = "Pipe definition" # required, str
input = "InputConcept" # required, str
output = "OutputConcept" # required, str
steps = [ # required, List[Dict]
    { result = "pipe_1_output_name", pipe = "pipe_1" },
    { result = "pipe_2_output_name", pipe = "pipe_2" },
    ...,
    {result = "pipe_n_output_name", pipe = "pipe_n" },
]
```

#### **PipeSequence example**

```toml
[pipe.answer_question_with_instructions]
PipeSequence = "Answer a question with instructions"
input = "Question"
output = "FormattedAnswer"
steps = [
{ result = "instructions", pipe = "enrich_instructions" },
{ result = "answer", pipe = "answer_enriched_question" },
{ result = "formatted_answer", pipe = "format_answer" },
]
```

#### **PipeParallel example**

```toml
[pipe.extract_expense_report]
PipeParallel = "Extract useful information from an expense report"
input = "ExpenseReportText"
output = "Composite"
parallels = [
   { pipe = "extract_employee_from_expense_report", result = "employee" },
   { pipe = "extract_expenses_from_expense_report", result = "expenses" },
]
```

#### **PipeCondition example**

```toml
[pipe.expense_conditional_validation]
PipeCondition = "Choose the rules to apply"
input = "Expense"
output = "RulesToApply"
expression = "expense_category.category"
```

## Working Memory

![Pipelex working memory cloud](working_memory_cloud.png)

In a pipeline, processed Stuff are stored in the **Working** **Memory.** The working memory is accessible from any Pipe in the pipeline.

Basically, the Working Memory is a wrapper on a Dict of Stuff objects.

```python
StuffDict = Dict[str, Stuff]

class WorkingMemory(BaseModel):
    root: StuffDict = Field(default_factory=dict)
```

**You can easily preload the memory with the dedicated Factory**

```python
from pipelex.core.stuff_factory import StuffFactory
from pipelex.core.working_memory_factory import WorkingMemoryFactory

# Here is a Stuff object
table_screenshot_stuff = StuffFactory.make_from_str(
    name="table_screenshot",
    concept_code="TableScreenshot",
    str_value=table_screenshot,
)

# And we load it in the memory
working_memory = WorkingMemoryFactory.make_from_single_stuff(
    table_screenshot_stuff,
)
```

### Access memory in prompts

You can access working memory stuffs directly in prompts using the jinja2 syntax.

You just need to call them by their name.

_PS: what comes after the | (stuff("extract") for instance) will be explained later._

```toml
[pipe.get_answer_with_extract]
PipeLLM = "Answer the question with extract"
input = "QuestionWithExtract"
output = "AnswerToAQuestionWithExtract"
prompt_template = """
I am asking you to read an extract and answer a question about it.
{{ question_with_extract|tag("extract") }} # question_with_extract
{{ question_with_extract|tag("question") }}
Please return your answer in english.
"""
```

## Run Pipes

Running pipes requires:

### **A Pipe**

```toml
[concept]
[concept.TableImage]
Concept = "An image of a table, in the sense of a data structure used to organize information in rows and columns."
structure = "ImageContent"
refines = ["Image"]

[concept.HtmlTable]
Concept = "An HTML table"
structure = "HtmlTable"

[pipe]
[pipe.get_html_table_from_image]
PipeLLM = "Get an HTML table"
input = "TableImage"
output = "HtmlTable"
images = ["table_image"]
system_prompt = """You are a vision-based table extractor."""
prompt_template = """You are given a picture (screenshot) of a table,
taken from a PDF document.
Your goal is to extract the table from the image **in html**.
Make sure you do not forget any text.
Make sure you do not invent any text.
Make sure your merge is consistent.
Make sure you replicate the formatting (borders, text formatting, colors, text alignment...)
"""

[pipe.review_html_table]
PipeLLM = "Review an HTML table"
input = "HtmlTable"
output = "HtmlTable"
images = ["table_image"]
system_prompt = "You are a vision-based html checker."
prompt_template = """Your role is to correct an html_table to make sure that it matches the one in the provided image.
Here is the html table:{{ html_table|tag("html_table") }}
Pay attention to the text and formatting (color, borders, ...).
Rewrite the entire html table with your potential corrections.
Make sure you do not forget any text.
"""

[pipe.get_html_table_and_review]
PipeSequence = "Get an HTML table and review it"
input = "TableScreenshot"
output = "HtmlTable"
steps = [
    { pipe = "get_html_table_from_image", result = "html_table" },
    { pipe = "review_html_table", result = "reviewed_html_table" },
]
```

### Loading the Working Memory with the required Pipes and running it

TODO

## Run pipes with any LLM

How to use a specific LLM for a specific pipe?

### **`.env`**

Make sure you have the appropriate API key(s) in your .env.

| **LLM provider** | **API KEY NAME**        |
| ---------------- | ----------------------- |
| Anthropic        | `ANTHROPIC_API_KEY`     |
| Azure OpenAI     | `AZURE_OPENAI_API_KEY`  |
| AWS              | `AWS_ACCESS_KEY_ID`     |
| AWS              | `AWS_SECRET_ACCESS_KEY` |
| Mistral AI       | `MISTRAL_API_KEY`       |
| OpenAI           | `OPENAI_API_KEY`        |

### **`config_<your_workdir_name>_llm_presets.toml`**

Create LLM presets to specify your model settings:

```python
[cogt.llm_config.llm_deck.llm_presets]
llm_for_reviewing_code = { llm_handle = "gpt-4-turbo", prompting_target = "openai", temperature = 0.1, max_tokens = "auto" }
```

- `llm_preset_<your_name_for_this_llm_preset>`(optional): Define LLM presets to store your LLM settings and use them when running pipes
  - `llm_handle` (required, str) the codename for the LLM
- `prompting_target` (required, str) indicates what prompting style to apply when processing your input prompt_templates.
- `temperature`(required, float) LLM temperature
- `max_tokens` (required, int or "auto") auto means maximum value provided by the LLM provider

#### Available LLMs

- **Anthropic**

| **Model Family** | **Model**            | **LLM handle**         |
| ---------------- | -------------------- | ---------------------- |
| claude-3         | Claude 3 Haiku       | `claude-3-haiku`       |
| claude-3         | Claude 3 Opus        | `claude-3-opus`        |
| claude-3.5       | Claude 3.5 Sonnet    | `claude-3-5-sonnet`    |
| claude-3.5       | Claude 3.5 Sonnet v2 | `claude-3-5-sonnet-v2` |
| claude-3.7       | Claude 3.7 Sonnet    | `claude-3-7-sonnet`    |

- **Mistral AI**

| **Model Family** | **Model**     | **LLM handle**      |
| ---------------- | ------------- | ------------------- |
| Ministral        | Ministral 3B  | `ministral-3b`      |
| Ministral        | Ministral 8B  | `ministral-8b`      |
| Mistral          | Mistral 7B    | `mistral-7b`        |
| Mistral          | Mixtral 8x7B  | `mistral-8x7b`      |
| Mistral          | Codestral     | `mistral-codestral` |
| Mistral          | Mistral Large | `mistral-large`     |
| Mistral          | Mistral Small | `mistral-small`     |
| Pixtral          | Pixtral 12B   | `pixtral-12b`       |
| Pixtral          | Pixtral Large | `pixtral-large`     |

- **Open AI**

| **Model Family** | **Model**              | **LLM handle**           |
| ---------------- | ---------------------- | ------------------------ |
| GPT-4            | GPT-4 Turbo            | `gpt-4-turbo`            |
| GPT-4            | GPT-4o (May 2024)      | `gpt-4o-2024-05-13`      |
| GPT-4            | GPT-4o (Aug 2024)      | `gpt-4o-2024-08-06`      |
| GPT-4            | GPT-4o (Nov 2024)      | `gpt-4o-2024-11-20`      |
| GPT-4            | GPT-4o                 | `gpt-4o`                 |
| GPT-4            | GPT-4o Mini (Jul 2024) | `gpt-4o-mini-2024-07-18` |
| GPT-4            | GPT-4o Mini            | `gpt-4o-mini`            |
| GPT-4.5          | GPT-4.5 Preview        | `gpt-4.5-preview`        |
| o                | o1-mini                | `o1-mini`                |
| o                | o1                     | `o1`                     |
| o                | o3-mini                | `o3-mini`                |

:arrow_left: [**Back to Concepts**](../Concepts/Concepts.md)

---

"Pipelex" is a trademark of Evotis S.A.S.

© 2025 Evotis S.A.S.
