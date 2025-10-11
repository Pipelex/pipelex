# Example: Screenplay Generator

This example demonstrates how to use Pipelex for creative text generation. It takes a simple pitch and generates a full screenplay.

## Get the code

[**➡️ View on GitHub: examples/wip/write_screenplay.py**](https://github.com/Pipelex/pipelex-cookbook/blob/main/examples/wip/write_screenplay.py)

## The Pipeline Explained

The `generate_screenplay` function takes a pitch as a string, creates a `Stuff` object with the `screenplay.Pitch` concept, and then runs the `generate_screenplay` pipeline.

```python
async def generate_screenplay(pitch: str):
    """Generate a screenplay from a pitch using the pipeline."""

    # Create Stuff object for the pitch
    pitch_stuff = StuffFactory.make_from_concept_string(
        concept_string="screenplay.Pitch",
        content=TextContent(text=pitch),
        name="pitch",
    )

    # Create Working Memory
    working_memory = WorkingMemoryFactory.make_from_single_stuff(pitch_stuff)

    # Run the pipe
    pipe_output = await execute_pipeline(
        pipe_code="generate_screenplay",
        working_memory=working_memory,
    )
    pretty_print(pipe_output, title="Pipe Output")
```

This example shows how a simple text input can be used to kick off a complex, creative workflow.

## The Data Structures: `Screenplay` Models

This pipeline uses a rich set of Pydantic models to represent the different components of a screenplay, from the initial `Pitch` to the final `FormattedScreenplay`. This ensures that each step of the pipeline has clear, structured inputs and outputs.

```python
class DetailedPitch(StructuredContent):
    """A detailed pitch with character ideas and synopsis."""
    original_pitch: str
    expanded_pitch: str
    character_ideas: List[str]
    synopsis: str

class Character(StructuredContent):
    """A character in the screenplay."""
    name: str
    age: int
    description: str
    # ...

class Scene(StructuredContent):
    """A scene in the screenplay."""
    index: int
    title: str
    location: str
    script: str
    # ...

class Chapter(StructuredContent):
    """A chapter in the screenplay."""
    title: str
    description: str
    scenes: List[Scene]

class Screenplay(StructuredContent):
    """A complete screenplay with characters and scenes."""
    title: str
    pitch: DetailedPitch
    characters: "CharacterList"
    chapters: "ChapterList"
```

## The Pipeline Definition: `screenplay_writer.plx`

The `generate_screenplay` pipeline is a master `PipeSequence` that orchestrates a series of smaller, specialized pipes. This is a perfect example of how to build a complex, creative workflow by breaking it down into manageable steps.

```plx
[pipe.generate_screenplay]
type = "PipeSequence"
description = "Generate a complete screenplay from a pitch"
inputs = { pitch = "Pitch" }
output = "FormattedScreenplay"
steps = [
    # 1. Analyze the initial pitch to expand it.
    { pipe = "analyze_pitch", result = "detailed_pitch" },
    # 2. Create detailed character profiles.
    { pipe = "create_characters", result = "characters" },
    # 3. Break the story down into chapters.
    { pipe = "create_chapters", result = "chapters" },
    # 4. For each chapter, create the scenes. This is a nested sequence!
    { pipe = "create_scenes_sequence", batch_over = "chapters", batch_as = "chapter", result = "chapters_with_scenes" },
    # 5. Format the entire screenplay.
    { pipe = "create_formatted_screenplay", result = "formatted_screenplay" }
]

# This is the nested sequence that creates all the scenes for a single chapter.
[pipe.create_scenes_sequence]
type = "PipeSequence"
description = "Create all scenes for a chapter sequentially"
inputs = { chapter = "Chapter", characters = "CharacterList", detailed_pitch = "DetailedPitch" }
output = "Chapter"
steps = [
    # First, create the initial scene outlines for the chapter.
    { pipe = "create_initial_scenes", result = "initial_scenes" },
    # Then, for each scene outline, develop the full scene content.
    { pipe = "create_scene_sequence", batch_over = "initial_scenes", batch_as = "scene", result = "developed_scenes" }
]
```

This modular, step-by-step process, guided by the structured data models, allows Pipelex to generate a complete, well-structured screenplay from a single, simple pitch. It's a powerful demonstration of building complex, creative AI agents.
