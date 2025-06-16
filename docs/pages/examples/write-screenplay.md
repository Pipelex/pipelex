# Example: Screenplay Generator

This example demonstrates how to use Pipelex for creative text generation. It takes a simple pitch and generates a full screenplay.

## Get the code

[**➡️ View on GitHub: examples/wip/write_screen_play.py**](https://github.com/Pipelex/pipelex-cookbook/blob/main/examples/wip/write_screen_play.py)

## The Pipeline Explained

The `generate_screenplay` function takes a pitch as a string, creates a `Stuff` object with the `screenplay.Pitch` concept, and then runs the `generate_screenplay` pipeline.

```python
async def generate_screenplay(pitch: str):
    """Generate a screenplay from a pitch using the pipeline."""

    # Create Stuff object for the pitch
    pitch_stuff = StuffFactory.make_from_str(
        str_value=pitch,
        concept_str="screenplay.Pitch",
        name="pitch",
    )

    # Create Working Memory
    working_memory = WorkingMemoryFactory.make_from_single_stuff(pitch_stuff)

    # Run the pipe
    pipe_output, _ = await execute_pipeline(
        pipe_code="generate_screenplay",
        working_memory=working_memory,
    )
    pretty_print(pipe_output, title="Pipe Output")
```

This example shows how a simple text input can be used to kick off a complex, creative workflow. 