"""Runner code generation utilities for Pipelex pipelines.

This module provides functions to generate executable Python code for Pipelex pipelines.

Main Functions:
--------------
- generate_runner_code(pipe): Generate complete executable Python script
"""

from dataclasses import dataclass
from typing import Any

from pipelex.core.concepts.concept import Concept
from pipelex.core.concepts.concept_representation_generator import (
    ConceptRepresentationFormat,
    ConceptRepresentationGenerator,
)
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.domains.domain import SpecialDomain
from pipelex.core.pipes.inputs.input_stuff_specs import InputStuffSpecs
from pipelex.core.pipes.pipe_abstract import PipeAbstract
from pipelex.core.pipes.variable_multiplicity import VariableMultiplicity
from pipelex.tools.misc.string_utils import pascal_case_to_snake_case


@dataclass
class CustomClassInfo:
    """Information about a custom structure class for import generation."""

    class_name: str
    domain_code: str
    concept_code: str

    @property
    def module_name(self) -> str:
        """Get the module name (filename without .py) for this class."""
        concept_snake_case = pascal_case_to_snake_case(self.concept_code)
        return f"{self.domain_code}__{concept_snake_case}"

    @property
    def import_statement(self) -> str:
        """Get the import statement for this class (uses sys.path from script directory)."""
        return f"from structures.{self.module_name} import {self.class_name}"


def _is_multiple(multiplicity: VariableMultiplicity | None) -> bool:
    """Check if the multiplicity indicates multiple items.

    Args:
        multiplicity: The multiplicity value (None, bool, or int)

    Returns:
        True if multiple items are expected
    """
    if multiplicity is None:
        return False
    if isinstance(multiplicity, bool):
        return multiplicity
    # int means specific count, which is multiple
    return multiplicity > 1


def _format_representation_as_python(representation: dict[str, Any], is_multiple: bool = False) -> str:
    """Format a representation dict as Python code.

    Args:
        representation: Dict with concept and content
        is_multiple: If True, wrap content in a list

    Returns:
        Python code string
    """
    concept = representation["concept"]
    content = representation["content"]

    # If multiple, wrap content in a list
    if is_multiple:
        content = f"[{content}]"

    # Content is already a Python instantiation string from the generator
    return f'{{\n            "concept": "{concept}",\n            "content": {content},\n        }}'


def _get_structure_class_import(class_name: str) -> str | None:
    """Get the import statement for a native structure class.

    The import statement is generated dynamically from the class's actual module location,
    so it will automatically reflect any file relocations.

    Args:
        class_name: The name of the structure class

    Returns:
        Import statement string, or None if not a native structure class
    """
    cls = NativeConceptCode.get_native_structure_class(class_name)
    if cls is None:
        return None
    return f"from {cls.__module__} import {cls.__name__}"


def _collect_concept_info(concept: Concept) -> CustomClassInfo | None:
    """Collect information about a concept for import generation.

    Args:
        concept: The concept to collect info for

    Returns:
        CustomClassInfo if it's a custom concept, None if native
    """
    if SpecialDomain.is_native(concept.domain_code):
        return None

    # For custom concepts, use the concept code as the class name
    # The structure class name should match the concept code
    return CustomClassInfo(
        class_name=concept.structure_class_name,
        domain_code=concept.domain_code,
        concept_code=concept.code,
    )


def _collect_imports_for_inputs(inputs: InputStuffSpecs) -> tuple[set[str], dict[str, CustomClassInfo]]:
    """Collect all imports needed for a pipe's inputs.

    Args:
        inputs: The pipe inputs

    Returns:
        Tuple of (set of native class names, dict mapping class name to CustomClassInfo)
    """
    native_classes: set[str] = set()
    custom_classes: dict[str, CustomClassInfo] = {}

    for input_req in inputs.root.values():
        concept = input_req.concept
        structure_class = concept.get_structure_class()

        # Get imports from the representation generator
        generator = ConceptRepresentationGenerator(ConceptRepresentationFormat.PYTHON)
        generator.generate_representation(concept.concept_ref, structure_class)

        for class_name in generator.imports_needed:
            if NativeConceptCode.is_native_structure_class(class_name):
                native_classes.add(class_name)
            else:
                # For custom classes, we need the concept info
                # The class name should be the structure class name which is the concept code
                custom_info = _collect_concept_info(concept)
                if custom_info and custom_info.class_name == class_name:
                    custom_classes[class_name] = custom_info

    return native_classes, custom_classes


def generate_runner_code(pipe: PipeAbstract, output_multiplicity: bool = False, library_dir: str | None = None) -> str:
    """Generate the complete Python runner code for a pipe.

    This generates a runnable Python script with:
    - Import statements for all required structure classes
    - An async function to run the pipeline with proper return type
    - Example input values based on the pipe's input concepts
    - Output handling with main_stuff_as

    Args:
        pipe: The pipe to generate runner code for
        output_multiplicity: Whether the output is a list (e.g., Text[])
        library_dir: Directory containing the PLX bundles to load
    """
    # Get output information
    structure_class_name = pipe.output.concept.structure_class_name
    is_native = NativeConceptCode.is_native_structure_class(structure_class_name)
    custom_info = None if is_native else _collect_concept_info(pipe.output.concept)

    # Collect all imports needed for inputs
    native_classes, custom_classes = _collect_imports_for_inputs(pipe.inputs)

    # Add output class to appropriate set
    if is_native:
        native_classes.add(structure_class_name)
    elif custom_info:
        custom_classes[structure_class_name] = custom_info

    # Build import section
    import_lines: list[str] = []

    # Add path setup for custom structure imports (must be before other imports)
    if custom_classes:
        import_lines.extend(
            [
                "import sys",
                "from pathlib import Path",
                "",
                "# Add script directory to path for local imports",
                "sys.path.insert(0, str(Path(__file__).parent))",
                "",
            ]
        )

    import_lines.extend(["import asyncio", ""])

    # Add native content class imports
    native_imports: list[str] = []
    for class_name in sorted(native_classes):
        import_stmt = _get_structure_class_import(class_name)
        if import_stmt:
            native_imports.append(import_stmt)
    import_lines.extend(native_imports)

    # Add custom structure class imports from structures folder
    if custom_classes:
        import_lines.append("")
        for class_name in sorted(custom_classes.keys()):
            custom_info = custom_classes[class_name]
            import_lines.append(custom_info.import_statement)

    import_lines.extend(
        [
            "",
            "from pipelex.pipelex import Pipelex",
            "from pipelex.pipeline.execute import execute_pipeline",
        ]
    )

    # Build inputs entries
    if not pipe.inputs.is_empty:
        input_entries: list[str] = []
        for var_name, input_req in pipe.inputs.root.items():
            is_multiple = _is_multiple(input_req.multiplicity)
            result, _ = input_req.concept.generate_input_representation(
                output_format=ConceptRepresentationFormat.PYTHON,
                is_multiple=is_multiple,
            )
            python_code = _format_representation_as_python(result, is_multiple=is_multiple)
            input_entries.append(f'            "{var_name}": {python_code},')
        input_memory_block = "\n".join(input_entries)
    else:
        input_memory_block = "            # No inputs required"

    # Determine return type annotation
    if output_multiplicity:
        return_type = f"list[{structure_class_name}]"
        result_call = f"pipe_output.main_stuff_as_items(item_type={structure_class_name})"
    else:
        return_type = structure_class_name
        result_call = f"pipe_output.main_stuff_as(content_type={structure_class_name})"

    # Build the main function
    function_lines = [
        "",
        "",
        f"async def run_{pipe.code}() -> {return_type}:",
        "    pipe_output = await execute_pipeline(",
        f'        pipe_code="{pipe.code}",',
    ]

    if not pipe.inputs.is_empty:
        function_lines.extend(
            [
                "        inputs={",
                input_memory_block,
                "        },",
            ]
        )

    function_lines.extend(
        [
            "    )",
            f"    return {result_call}",
            "",
            "",
            'if __name__ == "__main__":',
            "    # Initialize Pipelex",
        ]
    )

    # Add Pipelex.make() with library_dirs if provided
    if library_dir:
        function_lines.append(f'    with Pipelex.make(library_dirs=["{library_dir}"]):')
    else:
        function_lines.append("    with Pipelex.make():")

    function_lines.extend(
        [
            "        # Run the pipeline",
            f"        result = asyncio.run(run_{pipe.code}())",
            "",
        ]
    )

    # Combine everything
    code_lines = import_lines + function_lines
    return "\n".join(code_lines)
