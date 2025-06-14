# Pipes

A pipe is a **Pipeline step**.
It can integrate **both LLM-based** or software-based knowledge processing.

:bulb: **Remember the Quick-start chapter?** We defined a pipe (in toml, using the [pipe.create_character] section) to generate a character. It constituted a one-pipe-long pipeline.

## Define pipes

Like concepts, Pipes are defined using a **`toml` syntax.**

- This part is meant to be **written in a library `toml` file, in the same one as concepts** (see [Libraries](../Libraries/libraries.md)).
  💡*In the quick-start example (text summary generator) this is the role of `summarize.toml`.*

### General Structure

This is how to define a Pipe using the Pipelex `toml` syntax:

```toml
[pipe]
[pipe.<pipe_name>]
Pipe<Type> = "Pipe definition"          # required, str
input = "InputConcept"                  # required, str
output = "OutputConcept"                # required, str
... then come the Pipe specific fields
```

The `Pipe<Type>` determines what kind of operation the pipe performs. For a complete list of available pipe types and their specific configurations, see our [Pipe Operators Guide](Pipe%20Operators.md).

## Working Memory

![Pipelex working memory cloud](working_memory_cloud.png)

In a pipeline, processed Stuff are stored in the **Working Memory.** The working memory is accessible from any Pipe in the pipeline.

Basically, the Working Memory is a wrapper on a Dict of Stuff objects.

```python
StuffDict = Dict[str, Stuff]

class WorkingMemory(BaseModel):
    root: StuffDict = Field(default_factory=dict)
```

### Using Working Memory

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

```toml
[pipe.get_answer_with_extract]
PipeLLM = "Answer the question with extract"
input = "QuestionWithExtract"
output = "AnswerToAQuestionWithExtract"
prompt_template = """
I am asking you to read an extract and answer a question about it.
{{ question_with_extract|tag("extract") }}
{{ question_with_extract|tag("question") }}
Please return your answer in english.
"""
```

## Related Topics

- [Pipe Operators Guide](Pipe%20Operators.md) - Detailed information about each pipe type
- [Concepts Documentation](../Concepts/Concepts.md)
- [Libraries Documentation](../Libraries/libraries.md)

---

"Pipelex" is a trademark of Evotis S.A.S.

© 2025 Evotis S.A.S.
