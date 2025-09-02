from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Union

import toml
from pydantic import BaseModel, model_validator
from typing_extensions import Self

from pipelex.core.bundles.pipelex_bundle_blueprint import PipelexBundleBlueprint
from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.exceptions import PipelexConfigurationError, PipelexFileError, PipelexUnknownPipeError
from pipelex.core.pipes.pipe_input_spec_blueprint import InputRequirementBlueprint
from pipelex.pipe_controllers.batch.pipe_batch_blueprint import PipeBatchBlueprint
from pipelex.pipe_controllers.condition.pipe_condition_blueprint import PipeConditionBlueprint
from pipelex.pipe_controllers.parallel.pipe_parallel_blueprint import PipeParallelBlueprint
from pipelex.pipe_controllers.sequence.pipe_sequence_blueprint import PipeSequenceBlueprint
from pipelex.pipe_operators.func.pipe_func_blueprint import PipeFuncBlueprint
from pipelex.pipe_operators.img_gen.pipe_img_gen_blueprint import PipeImgGenBlueprint
from pipelex.pipe_operators.jinja2.pipe_jinja2_blueprint import PipeJinja2Blueprint
from pipelex.pipe_operators.llm.pipe_llm_blueprint import PipeLLMBlueprint
from pipelex.pipe_operators.ocr.pipe_ocr_blueprint import PipeOcrBlueprint
from pipelex.tools.misc.toml_utils import clean_trailing_whitespace, validate_toml_content, validate_toml_file


class PLXDecodeError(toml.TomlDecodeError):
    """Raised when PLX decoding fails."""

    pass


class PipelexInterpreter(BaseModel):
    """plx -> PipelexBundleBlueprint"""

    file_path: Optional[Path] = None
    file_content: Optional[str] = None

    @staticmethod
    def escape_plx_string(value: Optional[str]) -> str:
        """Escape a string for plx serialization."""
        if value is None:
            return ""
        # Escape backslashes first (must be done first)
        value = value.replace("\\", "\\\\")
        # Escape quotes
        value = value.replace('"', '\\"')
        # Replace actual newlines with escaped newlines
        value = value.replace("\n", "\\n")
        value = value.replace("\r", "\\r")
        value = value.replace("\t", "\\t")
        return value

    @model_validator(mode="after")
    def check_file_path_or_file_content(self) -> Self:
        """Need to check if there is at least one of file_path or file_content"""
        if self.file_path is None and self.file_content is None:
            raise PipelexConfigurationError("Either file_path or file_content must be provided")
        return self

    @model_validator(mode="after")
    def validate_file_path(self) -> Self:
        if self.file_path:
            validate_toml_file(path=str(self.file_path))
        if self.file_content:
            validate_toml_content(content=self.file_content, file_path=str(self.file_path))
        return self

    def get_file_content(self) -> str:
        """Load PLX content from file_path or use file_content directly."""
        if self.file_path:
            try:
                with open(self.file_path, "r", encoding="utf-8") as file:
                    file_content = file.read()

                # Clean trailing whitespace and write back if needed
                cleaned_content = clean_trailing_whitespace(file_content)
                if file_content != cleaned_content:
                    with open(self.file_path, "w", encoding="utf-8") as file:
                        file.write(cleaned_content)
                    return cleaned_content
                return file_content

            except Exception as exc:
                raise PipelexFileError(f"Failed to read PLX file '{self.file_path}': {exc}") from exc
        elif self.file_content is None:
            raise PipelexConfigurationError("file_content must be provided if file_path is not provided")
        return self.file_content

    @staticmethod
    def is_pipelex_file(file_path: Path) -> bool:
        """Check if a file is a valid Pipelex PLX file.

        Args:
            file_path: Path to the file to check

        Returns:
            True if the file is a Pipelex file, False otherwise

        Criteria:
            - Has .plx extension
            - Starts with "domain =" (ignoring leading whitespace)
        """
        # Check if it has .toml extension
        if file_path.suffix != ".plx":
            return False

        # Check if file exists
        if not file_path.exists() or not file_path.is_file():
            return False

        try:
            # Read the first few lines to check for "domain ="
            with open(file_path, "r", encoding="utf-8") as f:
                # Read first 100 characters (should be enough to find domain)
                content = f.read(100)
                # Remove leading whitespace and check if it starts with "domain ="
                stripped_content = content.lstrip()
                return stripped_content.startswith("domain =")
        except Exception:
            # If we can't read the file, it's not a valid Pipelex file
            return False

    def _parse_plx_content(self, content: str) -> Dict[str, Any]:
        """Parse PLX content and return the dictionary."""
        try:
            return toml.loads(content)
        except toml.TomlDecodeError as exc:
            file_path_str = str(self.file_path) if self.file_path else "content"
            raise PLXDecodeError(f"PLX parsing error in '{file_path_str}': {exc}", exc.doc, exc.pos) from exc

    def make_pipelex_bundle_blueprint(self) -> PipelexBundleBlueprint:
        """Make a PipelexBundleBlueprint from the file_path or file_content"""
        file_content = self.get_file_content()
        plx_data = self._parse_plx_content(file_content)
        return PipelexBundleBlueprint.model_validate(plx_data)

    @staticmethod
    def make_plx_content(blueprint: PipelexBundleBlueprint) -> str:
        """Convert a PipelexBundleBlueprint to properly formatted PLX content."""
        plx_parts: list[str] = []

        # Domain-level fields
        domain_fields: list[str] = []
        domain_fields.append(f'domain = "{PipelexInterpreter.escape_plx_string(blueprint.domain)}"')
        if blueprint.definition:
            domain_fields.append(f'definition = "{PipelexInterpreter.escape_plx_string(blueprint.definition)}"')
        if blueprint.system_prompt:
            domain_fields.append(f'system_prompt = "{PipelexInterpreter.escape_plx_string(blueprint.system_prompt)}"')
        if blueprint.system_prompt_to_structure:
            domain_fields.append(f'system_prompt_to_structure = "{PipelexInterpreter.escape_plx_string(blueprint.system_prompt_to_structure)}"')
        if blueprint.prompt_template_to_structure:
            domain_fields.append(f'prompt_template_to_structure = "{PipelexInterpreter.escape_plx_string(blueprint.prompt_template_to_structure)}"')

        plx_parts.append("\n".join(domain_fields))

        # Concepts section
        if blueprint.concept:
            concept_plx = PipelexInterpreter.concepts_to_plx_string(blueprint.concept, blueprint.domain)
            if concept_plx:  # Only add if not empty
                plx_parts.append(concept_plx)

        # Pipes section
        if blueprint.pipe:
            pipes_plx = PipelexInterpreter.pipes_to_plx_string(blueprint.pipe, blueprint.domain)
            if pipes_plx:  # Only add if not empty
                plx_parts.append(pipes_plx)

        result = "\n\n".join(plx_parts)
        if result and not result.endswith("\n"):
            result += "\n"
        return result

    @staticmethod
    def concepts_to_plx_string(concepts: Dict[str, ConceptBlueprint | str], domain: str) -> str:
        """Convert concepts dict to PLX string."""
        if not concepts:
            return ""

        plx_parts: list[str] = []
        simple_concepts: list[str] = []
        complex_concepts: list[str] = []

        for concept_name, concept_blueprint in concepts.items():
            if isinstance(concept_blueprint, str):
                simple_concepts.append(f'{concept_name} = "{PipelexInterpreter.escape_plx_string(concept_blueprint)}"')
            else:
                # Handle ConceptBlueprint objects
                if concept_blueprint.structure is None and concept_blueprint.refines is None:
                    # Simple concept with just definition
                    simple_concepts.append(f'{concept_name} = "{PipelexInterpreter.escape_plx_string(concept_blueprint.definition)}"')
                else:
                    # Complex concept needs its own section
                    complex_concept_plx = PipelexInterpreter.complex_concept_to_plx_string(concept_name, concept_blueprint)
                    complex_concepts.append(complex_concept_plx)

        # Add simple concepts section if we have any
        if simple_concepts:
            plx_parts.append("[concept]")
            plx_parts.extend(simple_concepts)

        # Add complex concepts with proper spacing
        if complex_concepts:
            # If we had simple concepts, add an empty line before complex ones
            if simple_concepts:
                plx_parts.append("")
            # Add each complex concept with empty lines between them
            for i, complex_concept in enumerate(complex_concepts):
                if i > 0:  # Add empty line between complex concepts
                    plx_parts.append("")
                plx_parts.append(complex_concept)

        return "\n".join(plx_parts)

    @staticmethod
    def complex_concept_to_plx_string(concept_name: str, concept: ConceptBlueprint) -> str:
        """Convert a complex ConceptBlueprint to PLX string."""
        lines: list[str] = [f"[concept.{concept_name}]"]

        if concept.definition:
            lines.append(f'definition = "{PipelexInterpreter.escape_plx_string(concept.definition)}"')

        if concept.refines:
            lines.append(f'refines = "{PipelexInterpreter.escape_plx_string(concept.refines)}"')

        if concept.structure:
            if isinstance(concept.structure, str):
                lines.append(f'structure = "{PipelexInterpreter.escape_plx_string(concept.structure)}"')
            else:
                # Complex structure with fields
                lines.append("")
                lines.append(f"[concept.{concept_name}.structure]")
                for field_name, field_def in concept.structure.items():
                    field_plx = PipelexInterpreter.structure_field_to_plx_string(field_name, field_def)
                    lines.append(field_plx)

        return "\n".join(lines)

    @staticmethod
    def structure_field_to_plx_string(field_name: str, field_def: Any) -> str:
        """Convert a structure field to PLX string."""
        if isinstance(field_def, str):
            return f'{field_name} = "{PipelexInterpreter.escape_plx_string(field_def)}"'
        else:
            # Complex field with type, definition, required, etc.
            field_parts: list[str] = []

            if hasattr(field_def, "type") and field_def.type:
                type_value = field_def.type.value if hasattr(field_def.type, "value") else field_def.type
                field_parts.append(f'type = "{PipelexInterpreter.escape_plx_string(str(type_value))}"')

            if hasattr(field_def, "definition") and field_def.definition:
                field_parts.append(f'definition = "{PipelexInterpreter.escape_plx_string(field_def.definition)}"')

            if hasattr(field_def, "required") and field_def.required is not None:
                field_parts.append(f"required = {str(field_def.required).lower()}")

            return f"{field_name} = {{ {', '.join(field_parts)} }}"

    @staticmethod
    def pipes_to_plx_string(pipes: Dict[str, Any], domain: str) -> str:
        """Convert pipes dict to PLX string."""
        plx_parts: list[str] = []
        for pipe_name, blueprint in pipes.items():
            pipe_plx = PipelexInterpreter.pipe_to_plx_string(pipe_name, blueprint, domain)
            plx_parts.append(pipe_plx)
        return "\n\n".join(plx_parts)

    @staticmethod
    def pipe_to_plx_string(pipe_name: str, blueprint: Any, domain: str) -> str:
        """Convert a single pipe blueprint to PLX string."""
        if isinstance(blueprint, PipeLLMBlueprint):
            return PipelexInterpreter.llm_pipe_to_plx_string(pipe_name, blueprint, domain)
        elif isinstance(blueprint, PipeSequenceBlueprint):
            return PipelexInterpreter.sequence_pipe_to_plx_string(pipe_name, blueprint, domain)
        elif isinstance(blueprint, PipeOcrBlueprint):
            return PipelexInterpreter.ocr_pipe_to_plx_string(pipe_name, blueprint, domain)
        elif isinstance(blueprint, PipeFuncBlueprint):
            return PipelexInterpreter.func_pipe_to_plx_string(pipe_name, blueprint, domain)
        elif isinstance(blueprint, PipeImgGenBlueprint):
            return PipelexInterpreter.img_gen_pipe_to_plx_string(pipe_name, blueprint, domain)
        elif isinstance(blueprint, PipeJinja2Blueprint):
            return PipelexInterpreter.jinja2_pipe_to_plx_string(pipe_name, blueprint, domain)
        elif isinstance(blueprint, PipeConditionBlueprint):
            return PipelexInterpreter.condition_pipe_to_plx_string(pipe_name, blueprint, domain)
        elif isinstance(blueprint, PipeParallelBlueprint):
            return PipelexInterpreter.parallel_pipe_to_plx_string(pipe_name, blueprint, domain)
        elif isinstance(blueprint, PipeBatchBlueprint):
            return PipelexInterpreter.batch_pipe_to_plx_string(pipe_name, blueprint, domain)
        else:
            # Fallback to old dict approach for unknown pipe types
            pipe_dict = PipelexInterpreter.serialize_pipe(blueprint, domain)
            return f"[pipe.{pipe_name}]\n" + "\n".join([f'{k} = "{v}"' if isinstance(v, str) else f"{k} = {v}" for k, v in pipe_dict.items()])

    @staticmethod
    def llm_pipe_to_plx_string(pipe_name: str, pipe: PipeLLMBlueprint, domain: str) -> str:
        """Convert a PipeLLM blueprint directly to PLX section string."""
        lines: list[str] = [
            f"[pipe.{pipe_name}]",
            f'type = "{PipelexInterpreter.escape_plx_string(pipe.type)}"',
            f'definition = "{PipelexInterpreter.escape_plx_string(pipe.definition)}"',
        ]

        # Add inputs first if they exist
        PipelexInterpreter.add_inputs_to_lines_if_exist(lines, pipe.inputs)

        # Add output after inputs (or immediately if no inputs)
        lines.append(f'output = "{PipelexInterpreter.escape_plx_string(pipe.output_concept_string_or_concept_code)}"')

        # Add optional fields
        if pipe.nb_output is not None:
            lines.append(f"nb_output = {pipe.nb_output}")
        if pipe.multiple_output is not None:
            lines.append(f"multiple_output = {str(pipe.multiple_output).lower()}")
        if pipe.system_prompt_template:
            lines.append(f'system_prompt_template = "{PipelexInterpreter.escape_plx_string(pipe.system_prompt_template)}"')
        if pipe.system_prompt:
            lines.append(f'system_prompt = "{PipelexInterpreter.escape_plx_string(pipe.system_prompt)}"')
        if pipe.prompt_template:
            lines.append(f'prompt_template = "{PipelexInterpreter.escape_plx_string(pipe.prompt_template)}"')
        if pipe.template_name:
            lines.append(f'template_name = "{PipelexInterpreter.escape_plx_string(pipe.template_name)}"')
        if pipe.prompt:
            lines.append(f'prompt = "{PipelexInterpreter.escape_plx_string(pipe.prompt)}"')

        return "\n".join(lines)

    @staticmethod
    def ocr_pipe_to_plx_string(pipe_name: str, pipe: PipeOcrBlueprint, domain: str) -> str:
        """Convert a PipeOcr blueprint directly to PLX section string."""
        lines: list[str] = [
            f"[pipe.{pipe_name}]",
            f'type = "{pipe.type}"',
            f'definition = "{pipe.definition}"',
        ]

        # Add inputs if they exist
        PipelexInterpreter.add_inputs_to_lines_if_exist(lines, pipe.inputs)

        lines.append(f'output = "{PipelexInterpreter.escape_plx_string(pipe.output_concept_string_or_concept_code)}"')

        return "\n".join(lines)

    @staticmethod
    def func_pipe_to_plx_string(pipe_name: str, pipe: PipeFuncBlueprint, domain: str) -> str:
        """Convert a PipeFunc blueprint directly to PLX section string."""
        lines: list[str] = [
            f"[pipe.{pipe_name}]",
            f'type = "{pipe.type}"',
            f'definition = "{pipe.definition}"',
        ]

        # Add inputs if they exist
        PipelexInterpreter.add_inputs_to_lines_if_exist(lines, pipe.inputs)

        lines.append(f'output = "{PipelexInterpreter.escape_plx_string(pipe.output_concept_string_or_concept_code)}"')
        lines.append(f'function_name = "{PipelexInterpreter.escape_plx_string(pipe.function_name)}"')

        return "\n".join(lines)

    @staticmethod
    def img_gen_pipe_to_plx_string(pipe_name: str, pipe: PipeImgGenBlueprint, domain: str) -> str:
        """Convert a PipeImgGen blueprint directly to PLX section string."""
        lines: list[str] = [
            f"[pipe.{pipe_name}]",
            f'type = "{pipe.type}"',
            f'definition = "{pipe.definition}"',
        ]

        # Add inputs if they exist
        PipelexInterpreter.add_inputs_to_lines_if_exist(lines, pipe.inputs)

        lines.append(f'output = "{PipelexInterpreter.escape_plx_string(pipe.output_concept_string_or_concept_code)}"')

        # Add optional fields
        if pipe.img_gen_prompt:
            lines.append(f'img_gen_prompt = "{PipelexInterpreter.escape_plx_string(pipe.img_gen_prompt)}"')
        if pipe.imgg_handle:
            lines.append(f'imgg_handle = "{PipelexInterpreter.escape_plx_string(pipe.imgg_handle)}"')
        if pipe.aspect_ratio:
            lines.append(f'aspect_ratio = "{pipe.aspect_ratio}"')
        if pipe.quality:
            lines.append(f'quality = "{pipe.quality}"')
        if pipe.nb_steps:
            lines.append(f"nb_steps = {pipe.nb_steps}")
        if pipe.guidance_scale:
            lines.append(f"guidance_scale = {pipe.guidance_scale}")
        if pipe.is_moderated is not None:
            lines.append(f"is_moderated = {str(pipe.is_moderated).lower()}")
        if pipe.safety_tolerance:
            lines.append(f'safety_tolerance = "{pipe.safety_tolerance}"')
        if pipe.is_raw is not None:
            lines.append(f"is_raw = {str(pipe.is_raw).lower()}")
        if pipe.seed:
            lines.append(f"seed = {pipe.seed}")
        if pipe.nb_output:
            lines.append(f"nb_output = {pipe.nb_output}")

        return "\n".join(lines)

    @staticmethod
    def jinja2_pipe_to_plx_string(pipe_name: str, pipe: PipeJinja2Blueprint, domain: str) -> str:
        """Convert a PipeJinja2 blueprint directly to PLX section string."""
        lines: list[str] = [
            f"[pipe.{pipe_name}]",
            f'type = "{pipe.type}"',
            f'definition = "{pipe.definition}"',
        ]

        # Add inputs if they exist
        PipelexInterpreter.add_inputs_to_lines_if_exist(lines, pipe.inputs)

        lines.append(f'output = "{PipelexInterpreter.escape_plx_string(pipe.output_concept_string_or_concept_code)}"')

        # Add jinja2 template
        if pipe.jinja2:
            lines.append(f'jinja2 = "{PipelexInterpreter.escape_plx_string(pipe.jinja2)}"')
        if pipe.jinja2_name:
            lines.append(f'jinja2_name = "{PipelexInterpreter.escape_plx_string(pipe.jinja2_name)}"')

        return "\n".join(lines)

    @staticmethod
    def condition_pipe_to_plx_string(pipe_name: str, pipe: PipeConditionBlueprint, domain: str) -> str:
        """Convert a PipeCondition blueprint directly to PLX section string."""
        lines: list[str] = [
            f"[pipe.{pipe_name}]",
            f'type = "{pipe.type}"',
            f'definition = "{pipe.definition}"',
        ]

        # Add inputs if they exist
        PipelexInterpreter.add_inputs_to_lines_if_exist(lines, pipe.inputs)

        lines.append(f'output = "{PipelexInterpreter.escape_plx_string(pipe.output_concept_string_or_concept_code)}"')

        # Add pipe_map
        if pipe.pipe_map:
            pipe_map_parts: list[str] = []
            pipe_map_dict = pipe.pipe_map.root
            for key, value in pipe_map_dict.items():
                pipe_map_parts.append(f'{key} = "{value}"')
            lines.append(f"pipe_map = {{ {', '.join(pipe_map_parts)} }}")

        # Add optional fields
        if pipe.expression_template:
            lines.append(f'expression_template = "{pipe.expression_template}"')
        if pipe.expression:
            lines.append(f'expression = "{pipe.expression}"')
        if pipe.default_pipe_code:
            lines.append(f'default_pipe_code = "{pipe.default_pipe_code}"')
        if pipe.add_alias_from_expression_to:
            lines.append(f'add_alias_from_expression_to = "{pipe.add_alias_from_expression_to}"')

        return "\n".join(lines)

    @staticmethod
    def parallel_pipe_to_plx_string(pipe_name: str, pipe: PipeParallelBlueprint, domain: str) -> str:
        """Convert a PipeParallel blueprint directly to PLX section string."""
        lines: list[str] = [
            f"[pipe.{pipe_name}]",
            f'type = "{pipe.type}"',
            f'definition = "{pipe.definition}"',
        ]

        # Add inputs if they exist
        PipelexInterpreter.add_inputs_to_lines_if_exist(lines, pipe.inputs)

        lines.append(f'output = "{PipelexInterpreter.escape_plx_string(pipe.output_concept_string_or_concept_code)}"')

        # Add parallels array
        if pipe.parallels:
            lines.append("parallels = [")
            for parallel in pipe.parallels:
                parallel_string = PipelexInterpreter.sub_pipe_to_plx_string(parallel)
                lines.append(f"    {parallel_string},")
            lines.append("]")

        # Add optional fields
        if pipe.add_each_output is not True:  # Only include if not default True
            lines.append(f"add_each_output = {str(pipe.add_each_output).lower()}")
        if pipe.combined_output:
            lines.append(f'combined_output = "{pipe.combined_output}"')

        return "\n".join(lines)

    @staticmethod
    def batch_pipe_to_plx_string(pipe_name: str, pipe: PipeBatchBlueprint, domain: str) -> str:
        """Convert a PipeBatch blueprint directly to PLX section string."""
        lines: list[str] = [
            f"[pipe.{pipe_name}]",
            f'type = "{pipe.type}"',
            f'definition = "{pipe.definition}"',
        ]

        # Add inputs if they exist
        PipelexInterpreter.add_inputs_to_lines_if_exist(lines, pipe.inputs)

        lines.append(f'output = "{PipelexInterpreter.escape_plx_string(pipe.output_concept_string_or_concept_code)}"')
        lines.append(f'branch_pipe_code = "{pipe.branch_pipe_code}"')

        # Add optional fields
        if pipe.input_list_name:
            lines.append(f'input_list_name = "{pipe.input_list_name}"')
        if pipe.input_item_name:
            lines.append(f'input_item_name = "{pipe.input_item_name}"')

        return "\n".join(lines)

    @staticmethod
    def serialize_concept_structure_field(field_value: Any) -> Any:
        """Serialize a single concept structure field."""
        from pipelex.core.concepts.concept_blueprint import ConceptStructureBlueprint

        if isinstance(field_value, str):
            return field_value
        elif isinstance(field_value, ConceptStructureBlueprint):
            field_data: Dict[str, Any] = {
                "definition": field_value.definition,
                "required": field_value.required,
            }
            if field_value.type is not None:
                field_data["type"] = field_value.type
            if field_value.item_type is not None:
                field_data["item_type"] = field_value.item_type
            if field_value.key_type is not None:
                field_data["key_type"] = field_value.key_type
            if field_value.value_type is not None:
                field_data["value_type"] = field_value.value_type
            if field_value.choices:
                field_data["choices"] = field_value.choices
            if field_value.default_value is not None:
                field_data["default_value"] = field_value.default_value
            return field_data
        else:
            return field_value

    @staticmethod
    def serialize_concept_structure(structure: Union[str, Dict[str, Any]]) -> Union[str, Dict[str, Any]]:
        """Serialize concept structure field."""
        if isinstance(structure, str):
            return structure
        else:
            result: Dict[str, Any] = {}
            for field_name, field_value in structure.items():
                result[field_name] = PipelexInterpreter.serialize_concept_structure_field(field_value)
            return result

    @staticmethod
    def serialize_single_concept(concept_blueprint: Union[ConceptBlueprint, str]) -> Union[str, Dict[str, Any]]:
        """Serialize a single concept blueprint."""
        if isinstance(concept_blueprint, str):
            return concept_blueprint

        # Handle ConceptBlueprint object
        if concept_blueprint.structure is not None:
            # Structured concept
            concept_data = {
                "definition": concept_blueprint.definition,
                "structure": PipelexInterpreter.serialize_concept_structure(concept_blueprint.structure),
            }
            return concept_data
        elif concept_blueprint.refines is not None:
            # Concept with refines
            concept_data = {"definition": concept_blueprint.definition, "refines": concept_blueprint.refines}
            return concept_data
        else:
            # Simple concept with just definition
            return concept_blueprint.definition

    @staticmethod
    def serialize_concepts(concepts: Optional[Dict[str, ConceptBlueprint | str]], domain: str) -> Dict[str, Any]:
        """Serialize concepts section with domain context."""
        if concepts is None:
            return {}

        result: Dict[str, Any] = {}
        for concept_name, concept_blueprint in concepts.items():
            result[concept_name] = PipelexInterpreter.serialize_single_concept(concept_blueprint)
        return result

    @staticmethod
    def serialize_pipes(pipes: Dict[str, Any], domain: str) -> Dict[str, Any]:
        """Serialize pipes section with domain context."""
        result: Dict[str, Any] = {}
        for pipe_name, blueprint in pipes.items():
            result[pipe_name] = PipelexInterpreter.serialize_pipe(blueprint, domain)
        return result

    @staticmethod
    def serialize_pipe(blueprint: Any, domain: str) -> Dict[str, Any]:
        """Serialize a single pipe blueprint with domain context."""

        if isinstance(blueprint, PipeLLMBlueprint):
            return PipelexInterpreter.serialize_llm_pipe(blueprint, domain)
        elif isinstance(blueprint, PipeOcrBlueprint):
            return PipelexInterpreter.serialize_ocr_pipe(blueprint, domain)
        elif isinstance(blueprint, PipeFuncBlueprint):
            return PipelexInterpreter._serialize_func_pipe(blueprint, domain)
        elif isinstance(blueprint, PipeImgGenBlueprint):
            return PipelexInterpreter._serialize_img_gen_pipe(blueprint, domain)
        elif isinstance(blueprint, PipeJinja2Blueprint):
            return PipelexInterpreter.serialize_jinja2_pipe(blueprint, domain)
        elif isinstance(blueprint, PipeSequenceBlueprint):
            return PipelexInterpreter.serialize_sequence_pipe(blueprint, domain)
        elif isinstance(blueprint, PipeConditionBlueprint):
            return PipelexInterpreter._serialize_condition_pipe(blueprint, domain)
        elif isinstance(blueprint, PipeParallelBlueprint):
            return PipelexInterpreter._serialize_parallel_pipe(blueprint, domain)
        elif isinstance(blueprint, PipeBatchBlueprint):
            return PipelexInterpreter._serialize_batch_pipe(blueprint, domain)
        else:
            raise PipelexUnknownPipeError(f"Unknown pipe blueprint type: {type(blueprint)}")

    @staticmethod
    def serialize_llm_pipe(pipe: PipeLLMBlueprint, domain: str) -> Dict[str, Any]:
        """Serialize PipeLLM blueprint."""
        result: Dict[str, Any] = {
            "type": pipe.type,
            "definition": pipe.definition,
        }

        # Add inputs first if they exist
        if pipe.inputs:
            result["inputs"] = PipelexInterpreter.serialize_inputs(pipe.inputs)

        # Then output
        result["output"] = pipe.output_concept_string_or_concept_code

        # Add optional fields in expected order based on test cases
        if pipe.nb_output is not None:
            result["nb_output"] = pipe.nb_output
        if pipe.multiple_output is not None:
            result["multiple_output"] = pipe.multiple_output

        if pipe.system_prompt_template:
            result["system_prompt_template"] = pipe.system_prompt_template
        if pipe.system_prompt:
            result["system_prompt"] = pipe.system_prompt

        if pipe.prompt_template:
            result["prompt_template"] = pipe.prompt_template
        if pipe.template_name:
            result["template_name"] = pipe.template_name
        if pipe.prompt:
            result["prompt"] = pipe.prompt

        # Less common fields
        if pipe.system_prompt_template_name:
            result["system_prompt_template_name"] = pipe.system_prompt_template_name
        if pipe.system_prompt_name:
            result["system_prompt_name"] = pipe.system_prompt_name
        if pipe.prompt_name:
            result["prompt_name"] = pipe.prompt_name
        if pipe.llm:
            result["llm"] = pipe.llm
        if pipe.llm_to_structure:
            result["llm_to_structure"] = pipe.llm_to_structure
        if pipe.structuring_method:
            result["structuring_method"] = pipe.structuring_method
        if pipe.prompt_template_to_structure:
            result["prompt_template_to_structure"] = pipe.prompt_template_to_structure
        if pipe.system_prompt_to_structure:
            result["system_prompt_to_structure"] = pipe.system_prompt_to_structure

        return result

    @staticmethod
    def add_common_pipe_fields(result: Dict[str, Any], pipe: Any) -> None:
        """Add common pipe fields (inputs) to result dict if they exist."""
        if hasattr(pipe, "inputs") and pipe.inputs:
            result["inputs"] = PipelexInterpreter.serialize_inputs(pipe.inputs)

    @staticmethod
    def _serialize_ocr_pipe(pipe: PipeOcrBlueprint, domain: str) -> Dict[str, Any]:
        """Serialize PipeOcr blueprint."""
        result: Dict[str, Any] = {
            "type": pipe.type,
            "definition": pipe.definition,
            "output": pipe.output_concept_string_or_concept_code,
        }

        PipelexInterpreter.add_common_pipe_fields(result, pipe)
        return result

    @staticmethod
    def _serialize_func_pipe(pipe: PipeFuncBlueprint, domain: str) -> Dict[str, Any]:
        """Serialize PipeFunc blueprint."""
        result: Dict[str, Any] = {
            "type": pipe.type,
            "definition": pipe.definition,
            "output": pipe.output_concept_string_or_concept_code,
            "function_name": pipe.function_name,
        }

        PipelexInterpreter.add_common_pipe_fields(result, pipe)
        return result

    @staticmethod
    def _serialize_img_gen_pipe(pipe: PipeImgGenBlueprint, domain: str) -> Dict[str, Any]:
        """Serialize PipeImgGen blueprint."""
        result: Dict[str, Any] = {
            "type": pipe.type,
            "definition": pipe.definition,
            "output": pipe.output_concept_string_or_concept_code,
        }

        PipelexInterpreter.add_common_pipe_fields(result, pipe)

        # Add optional fields only if they have values
        if pipe.img_gen_prompt:
            result["img_gen_prompt"] = pipe.img_gen_prompt
        if pipe.imgg_handle:
            result["imgg_handle"] = pipe.imgg_handle
        if pipe.aspect_ratio:
            result["aspect_ratio"] = pipe.aspect_ratio
        if pipe.quality:
            result["quality"] = pipe.quality
        if pipe.nb_steps:
            result["nb_steps"] = pipe.nb_steps
        if pipe.guidance_scale:
            result["guidance_scale"] = pipe.guidance_scale
        if pipe.is_moderated is not None:
            result["is_moderated"] = pipe.is_moderated
        if pipe.safety_tolerance:
            result["safety_tolerance"] = pipe.safety_tolerance
        if pipe.is_raw is not None:
            result["is_raw"] = pipe.is_raw
        if pipe.seed:
            result["seed"] = pipe.seed
        if pipe.nb_output:
            result["nb_output"] = pipe.nb_output

        return result

    @staticmethod
    def serialize_ocr_pipe(pipe: PipeOcrBlueprint, domain: str) -> Dict[str, Any]:
        """Serialize a PipeOcr blueprint."""
        result: Dict[str, Any] = {
            "type": pipe.type,
            "definition": pipe.definition,
        }

        # Add common pipe fields
        PipelexInterpreter.add_common_pipe_fields(result, pipe)

        # Add output
        result["output"] = pipe.output_concept_string_or_concept_code

        # Add optional fields
        if pipe.ocr_platform:
            result["ocr_platform"] = pipe.ocr_platform
        if pipe.page_images:
            result["page_images"] = pipe.page_images
        if pipe.page_image_captions:
            result["page_image_captions"] = pipe.page_image_captions
        if pipe.page_views:
            result["page_views"] = pipe.page_views
        if pipe.page_views_dpi:
            result["page_views_dpi"] = pipe.page_views_dpi

        return result

    @staticmethod
    def serialize_sequence_pipe(pipe: PipeSequenceBlueprint, domain: str) -> Dict[str, Any]:
        """Serialize a PipeSequence blueprint."""
        result: Dict[str, Any] = {
            "type": pipe.type,
            "definition": pipe.definition,
        }

        # Add common pipe fields
        PipelexInterpreter.add_common_pipe_fields(result, pipe)

        # Add output
        result["output"] = pipe.output_concept_string_or_concept_code

        # Add steps
        if pipe.steps:
            result["steps"] = [PipelexInterpreter.serialize_sub_pipe(step) for step in pipe.steps]

        return result

    @staticmethod
    def serialize_jinja2_pipe(pipe: PipeJinja2Blueprint, domain: str) -> Dict[str, Any]:
        """Serialize PipeJinja2 blueprint."""
        result: Dict[str, Any] = {
            "type": pipe.type,
            "definition": pipe.definition,
            "output": pipe.output_concept_string_or_concept_code,
        }

        PipelexInterpreter.add_common_pipe_fields(result, pipe)

        # Add optional fields only if they have values
        if pipe.jinja2_name:
            result["jinja2_name"] = pipe.jinja2_name
        if pipe.jinja2:
            result["jinja2"] = pipe.jinja2
        if pipe.prompting_style:
            result["prompting_style"] = pipe.prompting_style
        # Only include template_category if it's not the default value
        if pipe.template_category and pipe.template_category.value != "llm_prompt":
            result["template_category"] = pipe.template_category

        return result

    @staticmethod
    def serialize_sub_pipe(sub_pipe: Any) -> Dict[str, Any]:
        """Serialize a sub pipe (step or parallel) blueprint."""
        step_data: Dict[str, Any] = {
            "pipe": sub_pipe.pipe,
            "result": sub_pipe.result,
        }
        # Only include optional fields if they have non-default values
        if sub_pipe.nb_output is not None:
            step_data["nb_output"] = sub_pipe.nb_output
        if sub_pipe.multiple_output is not None:
            step_data["multiple_output"] = sub_pipe.multiple_output
        if sub_pipe.batch_over is not False:  # Only include if not default False
            step_data["batch_over"] = sub_pipe.batch_over
        if sub_pipe.batch_as is not None:
            step_data["batch_as"] = sub_pipe.batch_as
        return step_data

    @staticmethod
    def sub_pipe_to_plx_string(sub_pipe: Any) -> str:
        """Convert a sub pipe blueprint directly to a PLX inline table string."""
        parts = [f'pipe = "{sub_pipe.pipe}"', f'result = "{sub_pipe.result}"']

        # Add optional fields if they have non-default values
        if sub_pipe.nb_output is not None:
            parts.append(f"nb_output = {sub_pipe.nb_output}")
        if sub_pipe.multiple_output is not None:
            parts.append(f"multiple_output = {str(sub_pipe.multiple_output).lower()}")
        if sub_pipe.batch_over is not False:  # Only include if not default False
            if isinstance(sub_pipe.batch_over, str):
                parts.append(f'batch_over = "{sub_pipe.batch_over}"')
            else:
                parts.append(f"batch_over = {str(sub_pipe.batch_over).lower()}")
        if sub_pipe.batch_as is not None:
            parts.append(f'batch_as = "{sub_pipe.batch_as}"')

        return "{ " + ", ".join(parts) + " }"

    @staticmethod
    def _serialize_sequence_pipe(pipe: PipeSequenceBlueprint, domain: str) -> Dict[str, Any]:
        """Serialize PipeSequence blueprint."""
        result: Dict[str, Any] = {
            "type": pipe.type,
            "definition": pipe.definition,
            "output": pipe.output_concept_string_or_concept_code,
        }

        PipelexInterpreter.add_common_pipe_fields(result, pipe)

        if pipe.steps:
            result["steps"] = [PipelexInterpreter.serialize_sub_pipe(step) for step in pipe.steps]

        return result

    @staticmethod
    def sequence_pipe_to_plx_string(pipe_name: str, pipe: PipeSequenceBlueprint, domain: str) -> str:
        """Convert a PipeSequence blueprint directly to PLX section string."""
        lines: list[str] = [
            f"[pipe.{pipe_name}]",
            f'type = "{pipe.type}"',
            f'definition = "{pipe.definition}"',
        ]

        # Add inputs first if they exist
        if hasattr(pipe, "inputs"):
            PipelexInterpreter.add_inputs_to_lines_if_exist(lines, pipe.inputs)

        # Add output after inputs
        lines.append(f'output = "{pipe.output_concept_string_or_concept_code}"')

        # Add steps array with proper spacing
        if pipe.steps:
            lines.append("steps = [")
            for step in pipe.steps:
                step_string = PipelexInterpreter.sub_pipe_to_plx_string(step)
                lines.append(f"    {step_string},")
            lines.append("]")

        return "\n".join(lines)

    @staticmethod
    def _serialize_condition_pipe(pipe: PipeConditionBlueprint, domain: str) -> Dict[str, Any]:
        """Serialize PipeCondition blueprint."""
        result: Dict[str, Any] = {
            "type": pipe.type,
            "definition": pipe.definition,
            "output": pipe.output_concept_string_or_concept_code,
            "pipe_map": pipe.pipe_map,
        }

        PipelexInterpreter.add_common_pipe_fields(result, pipe)

        # Add optional fields only if they have values
        if pipe.expression_template:
            result["expression_template"] = pipe.expression_template
        if pipe.expression:
            result["expression"] = pipe.expression
        if pipe.default_pipe_code:
            result["default_pipe_code"] = pipe.default_pipe_code
        if pipe.add_alias_from_expression_to:
            result["add_alias_from_expression_to"] = pipe.add_alias_from_expression_to

        return result

    @staticmethod
    def _serialize_parallel_pipe(pipe: PipeParallelBlueprint, domain: str) -> Dict[str, Any]:
        """Serialize PipeParallel blueprint."""
        result: Dict[str, Any] = {
            "type": pipe.type,
            "definition": pipe.definition,
            "output": pipe.output_concept_string_or_concept_code,
        }

        PipelexInterpreter.add_common_pipe_fields(result, pipe)

        if pipe.parallels:
            result["parallels"] = [PipelexInterpreter.serialize_sub_pipe(parallel) for parallel in pipe.parallels]
        if pipe.add_each_output is not True:  # Only include if not default True
            result["add_each_output"] = pipe.add_each_output
        if pipe.combined_output:
            result["combined_output"] = pipe.combined_output

        return result

    @staticmethod
    def _serialize_batch_pipe(pipe: PipeBatchBlueprint, domain: str) -> Dict[str, Any]:
        """Serialize PipeBatch blueprint."""
        result: Dict[str, Any] = {
            "type": pipe.type,
            "definition": pipe.definition,
            "output": pipe.output_concept_string_or_concept_code,
            "branch_pipe_code": pipe.branch_pipe_code,
        }

        PipelexInterpreter.add_common_pipe_fields(result, pipe)

        if pipe.input_list_name:
            result["input_list_name"] = pipe.input_list_name
        if pipe.input_item_name:
            result["input_item_name"] = pipe.input_item_name

        return result

    @staticmethod
    def serialize_input_requirement(input_req: InputRequirementBlueprint) -> Dict[str, Any]:
        """Serialize a single InputRequirementBlueprint to PLX format."""
        result: Dict[str, Any] = {"concept": input_req.concept}
        if input_req.multiplicity is not None:
            result["multiplicity"] = input_req.multiplicity
        return result

    @staticmethod
    def serialize_inputs(inputs: Mapping[str, Union[str, InputRequirementBlueprint]]) -> Dict[str, Any]:
        """Convert InputRequirementBlueprint objects to proper PLX format for serialization."""
        result: Dict[str, Any] = {}
        for key, value in inputs.items():
            if isinstance(value, InputRequirementBlueprint):
                result[key] = PipelexInterpreter.serialize_input_requirement(value)
            else:
                # Already a string - simple case
                result[key] = str(value)
        return result

    @staticmethod
    def inputs_to_plx_string(inputs: Mapping[str, Union[str, InputRequirementBlueprint]]) -> str:
        """Convert inputs dictionary to PLX string format."""
        inputs_dict = PipelexInterpreter.serialize_inputs(inputs)
        inputs_parts: list[str] = []

        for key, value in inputs_dict.items():
            if isinstance(value, dict):
                # Nested dict (like InputRequirementBlueprint)
                nested_parts: list[str] = []
                nested_dict: Dict[str, Any] = value
                for nested_key, nested_value in nested_dict.items():
                    if isinstance(nested_value, str):
                        nested_parts.append(f'{nested_key} = "{PipelexInterpreter.escape_plx_string(nested_value)}"')
                    else:
                        nested_parts.append(f"{nested_key} = {str(nested_value).lower()}")
                inputs_parts.append(f"{key} = {{ {', '.join(nested_parts)} }}")
            else:
                # Simple string value
                if isinstance(value, str):
                    inputs_parts.append(f'{key} = "{PipelexInterpreter.escape_plx_string(value)}"')
                else:
                    # Fallback for any other type
                    inputs_parts.append(f'{key} = "{PipelexInterpreter.escape_plx_string(str(value))}"')

        return f"{{ {', '.join(inputs_parts)} }}"

    @staticmethod
    def add_inputs_to_lines_if_exist(lines: list[str], pipe_inputs: Optional[Mapping[str, Union[str, InputRequirementBlueprint]]]) -> None:
        """Add inputs line to PLX lines if inputs exist."""
        if pipe_inputs:
            inputs_dict = PipelexInterpreter.serialize_inputs(pipe_inputs)
            inputs_parts: list[str] = []
            for key, value in inputs_dict.items():
                if isinstance(value, dict):
                    nested_parts: list[str] = []
                    nested_dict: Dict[str, Any] = value
                    for nested_key, nested_value in nested_dict.items():
                        if isinstance(nested_value, str):
                            nested_parts.append(f'{nested_key} = "{PipelexInterpreter.escape_plx_string(nested_value)}"')
                        else:
                            nested_parts.append(f"{nested_key} = {str(nested_value).lower()}")
                    inputs_parts.append(f"{key} = {{ {', '.join(nested_parts)} }}")
                else:
                    if isinstance(value, str):
                        inputs_parts.append(f'{key} = "{PipelexInterpreter.escape_plx_string(value)}"')
                    else:
                        inputs_parts.append(f'{key} = "{PipelexInterpreter.escape_plx_string(str(value))}"')
            lines.append(f"inputs = {{ {', '.join(inputs_parts)} }}")
