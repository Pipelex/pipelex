# Example: Gantt Chart Extraction

This example showcases the ability of Pipelex to extract structured information from images. In this case, it processes an image of a Gantt chart and extracts the tasks, dates, and dependencies.

## Get the code

[**➡️ View on GitHub: examples/extract_gantt.py**](https://github.com/Pipelex/pipelex-cookbook/blob/main/examples/extract_gantt.py)

## The Pipeline Explained

The pipeline takes an image as input, creates a working memory, and then executes the `extract_gantt_by_steps` pipeline to produce a structured `GanttChart` object.

```python
async def extract_gantt(image_url: str) -> GanttChart:
    # Create Working Memory
    working_memory = WorkingMemoryFactory.make_from_image(
        image_url=image_url,
        concept_string="gantt.GanttImage",
        name="gantt_chart_image",
    )

    # Run the pipe
    pipe_output = await execute_pipeline(
        pipe_code="extract_gantt_by_steps",
        working_memory=working_memory,
    )

    # Output the result
    return pipe_output.main_stuff_as(content_type=GanttChart)
```

This is a powerful demonstration of multi-modal capabilities, combining vision and language understanding.

## The Data Structure: `GanttChart` Model

The final output is a `GanttChart` object, which contains lists of tasks and milestones. These are themselves structured objects, ensuring the data is clean and easy to work with.

```python
class GanttTaskDetails(StructuredContent):
    """Do not include timezone in the dates."""
    name: str
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    # ...

class Milestone(StructuredContent):
    name: str
    date: Optional[datetime]
    # ...

class GanttChart(StructuredContent):
    tasks: Optional[List[GanttTaskDetails]]
    milestones: Optional[List[Milestone]]
```

## The Pipeline Definition: `gantt.plx`

The `extract_gantt_by_steps` pipeline is a sequence of smaller, focused pipes. This is a great example of building a complex workflow from simple, reusable components.

```plx
[pipe.extract_gantt_by_steps]
type = "PipeSequence"
description = "Extract all details from a gantt chart"
inputs = { gantt_chart_image = "GanttChartImage" }
output = "GanttChart"
steps = [
    # First, figure out the timescale of the chart
    { pipe = "extract_gantt_timescale", result = "gantt_timescale" },
    # Then, get the names of all the tasks
    { pipe = "extract_gantt_task_names", result = "gantt_task_names" },
    # Then, for each task, extract the details
    { pipe = "extract_details_of_task", batch_as = "gantt_task_name", result = "details_of_all_tasks" },
    # Finally, assemble everything into a single GanttChart object
    { pipe = "gather_in_a_gantt_chart", result = "gantt_chart" },
]

# This is the pipe that extracts the details for a single task
[pipe.extract_details_of_task]
type = "PipeLLM"
description = "Extract the precise dates of the task, start_date and end_date"
inputs = { gantt_chart_image = "GanttChartImage", gantt_timescale = "GanttTimescaleDescription", gantt_task_name = "GanttTaskName" }
output = "GanttTaskDetails" # The output is structured as a GanttTaskDetails object
structuring_method = "preliminary_text"
llm = "llm_to_extract_diagram"
prompt_template = """
I am sharing an image of a Gantt chart.
Please analyse the image and for a given task name (and only this task), extract the information of the task, if relevant.

Be careful, the time unit is this:
@gantt_timescale

If the task is a milestone, then only output the start_date.

Here is the name of the task you have to extract the dates for:
@gantt_task_name
"""
```
This demonstrates the "divide and conquer" approach that Pipelex encourages. By breaking down a complex problem into smaller steps, each step can be handled by a specialized pipe, making the overall workflow more robust and easier to debug. 

## Flowchart

```mermaid
---
config:
  layout: dagre
  theme: base
---
flowchart LR
    subgraph "extract_gantt_by_steps"
    direction LR
        ZJNLe["gantt_chart_image:<br>**Gantt image**"]
        Bh9Ab["gantt_timescale:<br>**Gantt timescale description**"]
        R2oLH["gantt_task_names:<br>**List of [Gantt task name]**"]
    end
    subgraph "extract_details_of_task"
    direction LR
        R2oLH-branch-0["**Gantt task name** #1"]
        QFEdmVvYVHdL6DsCRtwqHq-branch-0["**Gantt task details** #1"]
        R2oLH-branch-1["**Gantt task name** #2"]
        QFEdmVvYVHdL6DsCRtwqHq-branch-1["**Gantt task details** #2"]
        R2oLH-branch-2["**Gantt task name** #3"]
        QFEdmVvYVHdL6DsCRtwqHq-branch-2["**Gantt task details** #3"]
        R2oLH-branch-3["**Gantt task name** #4"]
        QFEdmVvYVHdL6DsCRtwqHq-branch-3["**Gantt task details** #4"]
        R2oLH-branch-4["**Gantt task name** #5"]
        QFEdmVvYVHdL6DsCRtwqHq-branch-4["**Gantt task details** #5"]
        R2oLH-branch-5["**Gantt task name** #6"]
        QFEdmVvYVHdL6DsCRtwqHq-branch-5["**Gantt task details** #6"]
        R2oLH-branch-6["**Gantt task name** #7"]
        QFEdmVvYVHdL6DsCRtwqHq-branch-6["**Gantt task details** #7"]
        R2oLH-branch-7["**Gantt task name** #8"]
        QFEdmVvYVHdL6DsCRtwqHq-branch-7["**Gantt task details** #8"]
        R2oLH-branch-8["**Gantt task name** #9"]
        QFEdmVvYVHdL6DsCRtwqHq-branch-8["**Gantt task details** #9"]
        R2oLH-branch-9["**Gantt task name** #10"]
        QFEdmVvYVHdL6DsCRtwqHq-branch-9["**Gantt task details** #10"]
        R2oLH-branch-10["**Gantt task name** #11"]
        QFEdmVvYVHdL6DsCRtwqHq-branch-10["**Gantt task details** #11"]
        R2oLH-branch-11["**Gantt task name** #12"]
        QFEdmVvYVHdL6DsCRtwqHq-branch-11["**Gantt task details** #12"]
        nCmpx["details_of_all_tasks:<br>**List of [Gantt task details]**"]
        NuMVc["gantt_chart:<br>**Gantt chart**"]
    end
class extract_gantt_by_steps sub_a;
class extract_details_of_task sub_b;

    classDef sub_a fill:#e6f5ff,color:#333,stroke:#333;

    classDef sub_b fill:#fff5f7,color:#333,stroke:#333;

    classDef sub_c fill:#f0fff0,color:#333,stroke:#333;
    ZJNLe -- "Extract gantt timescale" ----> Bh9Ab
    ZJNLe -- "Extract gantt task names" ----> R2oLH
    ZJNLe -- "Extract details of task" ----> QFEdmVvYVHdL6DsCRtwqHq-branch-0
    ZJNLe -- "Extract details of task" ----> QFEdmVvYVHdL6DsCRtwqHq-branch-1
    ZJNLe -- "Extract details of task" ----> QFEdmVvYVHdL6DsCRtwqHq-branch-2
    ZJNLe -- "Extract details of task" ----> QFEdmVvYVHdL6DsCRtwqHq-branch-3
    ZJNLe -- "Extract details of task" ----> QFEdmVvYVHdL6DsCRtwqHq-branch-4
    ZJNLe -- "Extract details of task" ----> QFEdmVvYVHdL6DsCRtwqHq-branch-5
    ZJNLe -- "Extract details of task" ----> QFEdmVvYVHdL6DsCRtwqHq-branch-6
    ZJNLe -- "Extract details of task" ----> QFEdmVvYVHdL6DsCRtwqHq-branch-7
    ZJNLe -- "Extract details of task" ----> QFEdmVvYVHdL6DsCRtwqHq-branch-8
    ZJNLe -- "Extract details of task" ----> QFEdmVvYVHdL6DsCRtwqHq-branch-9
    ZJNLe -- "Extract details of task" ----> QFEdmVvYVHdL6DsCRtwqHq-branch-10
    ZJNLe -- "Extract details of task" ----> QFEdmVvYVHdL6DsCRtwqHq-branch-11
    Bh9Ab -- "Extract details of task" ----> QFEdmVvYVHdL6DsCRtwqHq-branch-0
    Bh9Ab -- "Extract details of task" ----> QFEdmVvYVHdL6DsCRtwqHq-branch-1
    Bh9Ab -- "Extract details of task" ----> QFEdmVvYVHdL6DsCRtwqHq-branch-2
    Bh9Ab -- "Extract details of task" ----> QFEdmVvYVHdL6DsCRtwqHq-branch-3
    Bh9Ab -- "Extract details of task" ----> QFEdmVvYVHdL6DsCRtwqHq-branch-4
    Bh9Ab -- "Extract details of task" ----> QFEdmVvYVHdL6DsCRtwqHq-branch-5
    Bh9Ab -- "Extract details of task" ----> QFEdmVvYVHdL6DsCRtwqHq-branch-6
    Bh9Ab -- "Extract details of task" ----> QFEdmVvYVHdL6DsCRtwqHq-branch-7
    Bh9Ab -- "Extract details of task" ----> QFEdmVvYVHdL6DsCRtwqHq-branch-8
    Bh9Ab -- "Extract details of task" ----> QFEdmVvYVHdL6DsCRtwqHq-branch-9
    Bh9Ab -- "Extract details of task" ----> QFEdmVvYVHdL6DsCRtwqHq-branch-10
    Bh9Ab -- "Extract details of task" ----> QFEdmVvYVHdL6DsCRtwqHq-branch-11
    R2oLH -...- R2oLH-branch-0
    R2oLH -...- R2oLH-branch-1
    R2oLH -...- R2oLH-branch-2
    R2oLH -...- R2oLH-branch-3
    R2oLH -...- R2oLH-branch-4
    R2oLH -...- R2oLH-branch-5
    R2oLH -...- R2oLH-branch-6
    R2oLH -...- R2oLH-branch-7
    R2oLH -...- R2oLH-branch-8
    R2oLH -...- R2oLH-branch-9
    R2oLH -...- R2oLH-branch-10
    R2oLH -...- R2oLH-branch-11
    R2oLH-branch-0 -- "Extract details of task" ----> QFEdmVvYVHdL6DsCRtwqHq-branch-0
    QFEdmVvYVHdL6DsCRtwqHq-branch-0 -...- nCmpx
    R2oLH-branch-1 -- "Extract details of task" ----> QFEdmVvYVHdL6DsCRtwqHq-branch-1
    QFEdmVvYVHdL6DsCRtwqHq-branch-1 -...- nCmpx
    R2oLH-branch-2 -- "Extract details of task" ----> QFEdmVvYVHdL6DsCRtwqHq-branch-2
    QFEdmVvYVHdL6DsCRtwqHq-branch-2 -...- nCmpx
    R2oLH-branch-3 -- "Extract details of task" ----> QFEdmVvYVHdL6DsCRtwqHq-branch-3
    QFEdmVvYVHdL6DsCRtwqHq-branch-3 -...- nCmpx
    R2oLH-branch-4 -- "Extract details of task" ----> QFEdmVvYVHdL6DsCRtwqHq-branch-4
    QFEdmVvYVHdL6DsCRtwqHq-branch-4 -...- nCmpx
    R2oLH-branch-5 -- "Extract details of task" ----> QFEdmVvYVHdL6DsCRtwqHq-branch-5
    QFEdmVvYVHdL6DsCRtwqHq-branch-5 -...- nCmpx
    R2oLH-branch-6 -- "Extract details of task" ----> QFEdmVvYVHdL6DsCRtwqHq-branch-6
    QFEdmVvYVHdL6DsCRtwqHq-branch-6 -...- nCmpx
    R2oLH-branch-7 -- "Extract details of task" ----> QFEdmVvYVHdL6DsCRtwqHq-branch-7
    QFEdmVvYVHdL6DsCRtwqHq-branch-7 -...- nCmpx
    R2oLH-branch-8 -- "Extract details of task" ----> QFEdmVvYVHdL6DsCRtwqHq-branch-8
    QFEdmVvYVHdL6DsCRtwqHq-branch-8 -...- nCmpx
    R2oLH-branch-9 -- "Extract details of task" ----> QFEdmVvYVHdL6DsCRtwqHq-branch-9
    QFEdmVvYVHdL6DsCRtwqHq-branch-9 -...- nCmpx
    R2oLH-branch-10 -- "Extract details of task" ----> QFEdmVvYVHdL6DsCRtwqHq-branch-10
    QFEdmVvYVHdL6DsCRtwqHq-branch-10 -...- nCmpx
    R2oLH-branch-11 -- "Extract details of task" ----> QFEdmVvYVHdL6DsCRtwqHq-branch-11
    QFEdmVvYVHdL6DsCRtwqHq-branch-11 -...- nCmpx
    nCmpx -- "Gather in a gantt chart" ----> NuMVc
```