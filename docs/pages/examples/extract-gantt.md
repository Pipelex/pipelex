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
        concept_str="gantt.GanttImage",
        name="gantt_chart_image",
    )

    # Run the pipe
    pipe_output, _ = await execute_pipeline(
        pipe_code="extract_gantt_by_steps",
        working_memory=working_memory,
    )

    # Output the result
    return pipe_output.main_stuff_as(content_type=GanttChart)
```

This is a powerful demonstration of multi-modal capabilities, combining vision and language understanding. 