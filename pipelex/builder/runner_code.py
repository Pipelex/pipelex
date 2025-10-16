from pipelex.core.concepts.concept import Concept
from pipelex.core.pipes.pipe_abstract import PipeAbstract
from pipelex.tools.codegen.runner_generator import value_to_python_code


def generate_compact_memory_entry(var_name: str, concept: Concept) -> str:
    """Generate the compact_memory dictionary entry for a given input."""
    example_value = concept.get_compact_memory_example(var_name)

    # Convert the example value to a Python code string
    value_str = value_to_python_code(example_value, indent_level=3)

    return f'            "{var_name}": {value_str},'


def generate_runner_code(pipe: PipeAbstract) -> str:
    """Generate the complete Python runner code for a pipe."""
    pipe_code = pipe.code
    inputs = pipe.inputs

    # Determine which imports are needed based on input concepts
    needs_pdf = False
    needs_image = False
    for input_req in inputs.root.values():
        concept = input_req.concept
        if concept.structure_class_name == "PDFContent":
            needs_pdf = True
        elif concept.structure_class_name == "ImageContent":
            needs_image = True

    # Build import section
    import_lines = ["import asyncio", ""]

    # Add content class imports if needed
    if needs_pdf:
        import_lines.append("from pipelex.core.stuffs.pdf_content import PDFContent")
    if needs_image:
        import_lines.append("from pipelex.core.stuffs.image_content import ImageContent")

    import_lines.extend(
        [
            "from pipelex.pipelex import Pipelex",
            "from pipelex.pipeline.execute import execute_pipeline",
        ]
    )

    # Build input_memory entries
    if inputs.nb_inputs > 0:
        input_memory_entries: list[str] = []
        for var_name, input_req in inputs.root.items():
            concept = input_req.concept
            entry = generate_compact_memory_entry(var_name, concept)
            input_memory_entries.append(entry)
        input_memory_block = "\n".join(input_memory_entries)
    else:
        input_memory_block = "        # No inputs required"

    # Build the main function
    function_lines = [
        "",
        "",
        f"async def run_{pipe_code}():",
        "    return await execute_pipeline(",
        f'        pipe_code="{pipe_code}",',
    ]

    if inputs.nb_inputs > 0:
        function_lines.extend(
            [
                "        input_memory={",
                input_memory_block,
                "        },",
            ]
        )

    function_lines.extend(
        [
            "    )",
            "",
            "",
            'if __name__ == "__main__":',
            "    # Initialize Pipelex",
            "    Pipelex.make()",
            "",
            "    # Run the pipeline",
            f"    result = asyncio.run(run_{pipe_code}())",
            "",
        ]
    )

    # Combine everything
    code_lines = import_lines + function_lines
    return "\n".join(code_lines)
