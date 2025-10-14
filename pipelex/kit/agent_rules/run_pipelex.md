# Guide to execute a pipeline and write example code

## Example to execute a pipeline with text output

```python
import asyncio

from pipelex import pretty_print
from pipelex.pipelex import Pipelex
from pipelex.pipeline.execute import execute_pipeline


async def hello_world() -> str:
    """
    This function demonstrates the use of a super simple Pipelex pipeline to generate text.
    """
    # Run the pipe
    pipe_output = await execute_pipeline(
        pipe_code="hello_world",
    )

    return pipe_output.main_stuff_as_str


# start Pipelex
Pipelex.make()
# run sample using asyncio
output_text = asyncio.run(hello_world())
pretty_print(output_text, title="Your first Pipelex output")
```

## Example to execute a pipeline with structured output

```python
import asyncio

from pipelex import pretty_print
from pipelex.pipelex import Pipelex
from pipelex.pipeline.execute import execute_pipeline
from pipelex.core.stuffs.image_content import ImageContent

from my_project.gantt.gantt_struct import GanttChart

SAMPLE_NAME = "extract_gantt"
IMAGE_URL = "assets/gantt/gantt_tree_house.png"


async def extract_gantt(image_url: str) -> GanttChart:
    # Run the pipe
    pipe_output = await execute_pipeline(
        pipe_code="extract_gantt_by_steps",
        input_memory={
            "gantt_chart_image": {
                "concept": "gantt.GanttImage",
                "content": ImageContent(url=image_url),
            }
        },
    )
    # Output the result
    return pipe_output.main_stuff_as(content_type=GanttChart)


# start Pipelex
Pipelex.make()

# run sample using asyncio
gantt_chart = asyncio.run(extract_gantt(image_url=IMAGE_URL))
pretty_print(gantt_chart, title="Gantt Chart")
```

## Setting up the input memory

### Explanation of input memory

The input memory is a dictionary, where the key is the name of the input variable and the value provides details to make it a stuff object. The relevant definitions are:
```python
StuffContentOrData = dict[str, Any] | StuffContent | list[Any] | str
ImplicitMemory = dict[str, StuffContentOrData]
```
As you can seen, we made it so different ways can be used to define that stuff using structured content or data.

### Different ways to set up the input memory

So here are a few concrete examples of calls to execute_pipeline with various ways to set up the input memory:

```python
# Here we have a single input and it's a Text.
# If you assign a string, by default it will be considered as a TextContent.
    pipe_output = await execute_pipeline(
        pipe_code="master_advisory_orchestrator",
        input_memory={
            "user_input": problem_description,
        },
    )

# Here we have a single input and it's a PDF.
# Because PDFContent is a native concept, we can use it directly as a value,
# the system knows what content it corresponds to:
    pipe_output = await execute_pipeline(
        pipe_code="power_extractor_dpe",
        input_memory={
            "document": PDFContent(url=pdf_url),
        },
    )

# Here we have a single input and it's an Image.
# Because ImageContent is a native concept, we can use it directly as a value:
    pipe_output = await execute_pipeline(
        pipe_code="fashion_variation_pipeline",
        input_memory={
            "fashion_photo": ImageContent(url=image_url),
        },
    )

# Here we have a single input, it's an image but
# its actually a more specific concept gantt.GanttImage which refines Image,
# so we must provide it using a dict with the concept and the content:
    pipe_output = await execute_pipeline(
        pipe_code="extract_gantt_by_steps",
        input_memory={
            "gantt_chart_image": {
                "concept": "gantt.GanttImage",
                "content": ImageContent(url=image_url),
            }
        },
    )

# Here is a more complex example with multiple inputs assigned using different ways:
    pipe_output = await execute_pipeline(
        pipe_code="retrieve_then_answer",
        dynamic_output_concept_code="contracts.Fees",
        input_memory={
            "text": load_text_from_path(path=text_path),
            "question": {
                "concept": "answer.Question",
                "content": question,
            },
            "client_instructions": client_instructions,
        },
    )
```

## Using the outputs of a pipeline

All pipe executions return a `PipeOutput` object.
It's a BaseModel which contains the resulting working memory at the end of the execution and the pipeline run id.
It also provides a bunch of accessor functions and properties to unwrap the main stuff, which is the last stuff added to the working memory:

```python

class PipeOutput(BaseModel):
    working_memory: WorkingMemory = Field(default_factory=WorkingMemory)
    pipeline_run_id: str = Field(default=SpecialPipelineId.UNTITLED)

    @property
    def main_stuff(self) -> Stuff:
        ...

    def main_stuff_as_list(self, item_type: type[StuffContentType]) -> ListContent[StuffContentType]:
        ...

    def main_stuff_as_items(self, item_type: type[StuffContentType]) -> list[StuffContentType]:
        ...

    def main_stuff_as(self, content_type: type[StuffContentType]) -> StuffContentType:
        ...

    @property
    def main_stuff_as_text(self) -> TextContent:
        ...

    @property
    def main_stuff_as_str(self) -> str:
        ...

    @property
    def main_stuff_as_image(self) -> ImageContent:
        ...

    @property
    def main_stuff_as_text_and_image(self) -> TextAndImagesContent:
        ...

    @property
    def main_stuff_as_number(self) -> NumberContent:
        ...

    @property
    def main_stuff_as_html(self) -> HtmlContent:
        ...

    @property
    def main_stuff_as_mermaid(self) -> MermaidContent:
        ...
```

As you can see, you can extract any variable from the output working memory.

### Getting the main stuff as a specific type

Simple text as a string:

```python
result = pipe_output.main_stuff_as_str
```
Structured object (BaseModel):

```python
result = pipe_output.main_stuff_as(content_type=GanttChart)
```

If it's a list, you can get a `ListContent` of the specific type.

```python
result_list_content = pipe_output.main_stuff_as_list(item_type=GanttChart)
```

or if you want, you can get the actual items as a regular python list:

```python
result_list = pipe_output.main_stuff_as_items(item_type=GanttChart)
```

---

