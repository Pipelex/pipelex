from pathlib import Path
from typing import Any, Dict, List, Optional

import toml
from pydantic import BaseModel, model_validator
from typing_extensions import Self

from pipelex.core.bundles.pipelex_bundle_blueprint import PipelexBundleBlueprint
from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.pipe_controllers.pipe_batch_factory import PipeBatchBlueprint
from pipelex.pipe_controllers.pipe_condition_factory import PipeConditionBlueprint
from pipelex.pipe_controllers.pipe_parallel_factory import PipeParallelBlueprint
from pipelex.pipe_controllers.pipe_sequence_factory import PipeSequenceBlueprint
from pipelex.pipe_operators.pipe_func_factory import PipeFuncBlueprint
from pipelex.pipe_operators.pipe_img_gen_factory import PipeImgGenBlueprint
from pipelex.pipe_operators.pipe_jinja2_factory import PipeJinja2Blueprint
from pipelex.pipe_operators.pipe_llm_factory import PipeLLMBlueprint
from pipelex.pipe_operators.pipe_ocr_factory import PipeOcrBlueprint
from pipelex.tools.misc.toml_utils import clean_trailing_whitespace, dict_to_toml, validate_toml_content, validate_toml_file


class PipelexInterpreter(BaseModel):
    """TOML -> PipelexBundleBlueprint"""

    file_path: Optional[Path] = None
    file_content: Optional[str] = None

    @model_validator(mode="after")
    def check_file_path_or_file_content(self) -> Self:
        """Need to check if there is at least one of file_path or file_content"""
        if self.file_path is None and self.file_content is None:
            raise ValueError("Either file_path or file_content must be provided")
        return self

    @model_validator(mode="after")
    def validate_file_path(self) -> Self:
        if self.file_path:
            validate_toml_file(path=str(self.file_path))
        if self.file_content:
            validate_toml_content(content=self.file_content, file_path=str(self.file_path))
        return self

    @staticmethod
    def is_pipelex_file(file_path: Path) -> bool:
        """Check if a file is a valid Pipelex TOML file.

        Args:
            file_path: Path to the file to check

        Returns:
            True if the file is a Pipelex file, False otherwise

        Criteria:
            - Has .toml extension
            - Starts with "domain =" (ignoring leading whitespace)
        """
        # Check if it has .toml extension
        if file_path.suffix != ".toml":
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

    def _load_toml_content(self) -> str:
        """Load TOML content from file_path or use file_content directly."""
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
                raise ValueError(f"Failed to read TOML file '{self.file_path}': {exc}") from exc
        else:
            if self.file_content is None:
                raise ValueError("file_content must be provided if file_path is not provided")
            return self.file_content

    def _parse_toml_content(self, content: str) -> Dict[str, Any]:
        """Parse TOML content and return the dictionary."""
        try:
            return toml.loads(content)
        except toml.TomlDecodeError as exc:
            file_path_str = str(self.file_path) if self.file_path else "content"
            raise toml.TomlDecodeError(f"TOML parsing error in '{file_path_str}': {exc}", exc.doc, exc.pos) from exc

    def make_pipelex_bundle_blueprint(self) -> PipelexBundleBlueprint:
        """Make a PipelexBundleBlueprint from the file_path or file_content"""
        file_content = self._load_toml_content()
        toml_data = self._parse_toml_content(file_content)
        return PipelexBundleBlueprint.model_validate(toml_data)

    @staticmethod
    def make_toml_content(blueprint: PipelexBundleBlueprint) -> str:
        """Convert a PipelexBundleBlueprint to properly formatted TOML content."""
        toml_data: Dict[str, Any] = {}

        # Domain-level fields
        toml_data["domain"] = blueprint.domain
        if blueprint.definition:
            toml_data["definition"] = blueprint.definition
        if blueprint.system_prompt:
            toml_data["system_prompt"] = blueprint.system_prompt
        if blueprint.system_prompt_to_structure:
            toml_data["system_prompt_to_structure"] = blueprint.system_prompt_to_structure
        if blueprint.prompt_template_to_structure:
            toml_data["prompt_template_to_structure"] = blueprint.prompt_template_to_structure

        # Concepts section - always include if concepts is not None
        if blueprint.concept is not None:
            toml_data["concept"] = PipelexInterpreter._serialize_concepts(blueprint.concept, blueprint.domain)

        # Pipes section
        if blueprint.pipe:
            toml_data["pipe"] = PipelexInterpreter._serialize_pipes(blueprint.pipe, blueprint.domain)

        return dict_to_toml(toml_data)

    @staticmethod
    def _serialize_concepts(concepts: Optional[Dict[str, ConceptBlueprint | str]], domain: str) -> Dict[str, Any]:
        """Serialize concepts section with domain context."""
        result: Dict[str, Any] = {}
        if concepts is None:
            return {}

        for concept_name, concept_blueprint in concepts.items():
            if isinstance(concept_blueprint, str):
                # Simple string concept
                result[concept_name] = concept_blueprint
            else:
                # Complex ConceptBlueprint
                if hasattr(concept_blueprint, "structure") and concept_blueprint.structure:
                    # Structured concept - create nested structure
                    concept_data: Dict[str, Any] = {}
                    if concept_blueprint.definition:
                        concept_data["definition"] = concept_blueprint.definition
                    if concept_blueprint.structure:
                        concept_data["structure"] = {}
                        if isinstance(concept_blueprint.structure, str):
                            concept_data["structure"] = concept_blueprint.structure
                        else:
                            for field_name, field_value in concept_blueprint.structure.items():
                                if isinstance(field_value, str):
                                    concept_data["structure"][field_name] = field_value
                                else:
                                    # ConceptStructureBlueprint
                                    field_data: Dict[str, Any] = {}
                                    field_data["type"] = field_value.type
                                    field_data["definition"] = field_value.definition
                                    field_data["required"] = field_value.required
                                    concept_data["structure"][field_name] = field_data
                    result[concept_name] = concept_data
                elif hasattr(concept_blueprint, "refines") and concept_blueprint.refines:
                    # Concept with refines
                    concept_data = {}
                    if concept_blueprint.definition:
                        concept_data["definition"] = concept_blueprint.definition
                    concept_data["refines"] = concept_blueprint.refines
                    result[concept_name] = concept_data
                else:
                    # Simple concept with just definition
                    result[concept_name] = concept_blueprint.definition if concept_blueprint.definition else f"Concept {concept_name}"
        return result

    @staticmethod
    def _serialize_pipes(pipes: Dict[str, Any], domain: str) -> Dict[str, Any]:
        """Serialize pipes section with domain context."""
        result: Dict[str, Any] = {}
        for pipe_name, pipe_blueprint in pipes.items():
            result[pipe_name] = PipelexInterpreter._serialize_pipe(pipe_blueprint, domain)
        return result

    @staticmethod
    def _serialize_pipe(pipe_blueprint: Any, domain: str) -> Dict[str, Any]:
        """Serialize a single pipe blueprint with domain context."""

        if isinstance(pipe_blueprint, PipeLLMBlueprint):
            return PipelexInterpreter._serialize_llm_pipe(pipe_blueprint, domain)
        elif isinstance(pipe_blueprint, PipeOcrBlueprint):
            return PipelexInterpreter._serialize_ocr_pipe(pipe_blueprint, domain)
        elif isinstance(pipe_blueprint, PipeFuncBlueprint):
            return PipelexInterpreter._serialize_func_pipe(pipe_blueprint, domain)
        elif isinstance(pipe_blueprint, PipeImgGenBlueprint):
            return PipelexInterpreter._serialize_img_gen_pipe(pipe_blueprint, domain)
        elif isinstance(pipe_blueprint, PipeJinja2Blueprint):
            return PipelexInterpreter._serialize_jinja2_pipe(pipe_blueprint, domain)
        elif isinstance(pipe_blueprint, PipeSequenceBlueprint):
            return PipelexInterpreter._serialize_sequence_pipe(pipe_blueprint, domain)
        elif isinstance(pipe_blueprint, PipeConditionBlueprint):
            return PipelexInterpreter._serialize_condition_pipe(pipe_blueprint, domain)
        elif isinstance(pipe_blueprint, PipeParallelBlueprint):
            return PipelexInterpreter._serialize_parallel_pipe(pipe_blueprint, domain)
        elif isinstance(pipe_blueprint, PipeBatchBlueprint):
            return PipelexInterpreter._serialize_batch_pipe(pipe_blueprint, domain)
        else:
            raise ValueError(f"Unknown pipe blueprint type: {type(pipe_blueprint)}")

    @staticmethod
    def _serialize_llm_pipe(pipe: PipeLLMBlueprint, domain: str) -> Dict[str, Any]:
        """Serialize PipeLLM blueprint."""
        result: Dict[str, Any] = {
            "type": pipe.type,
            "definition": pipe.definition,
            "output": pipe.output,
        }

        # Add optional fields only if they have values
        if pipe.inputs:
            result["inputs"] = PipelexInterpreter._serialize_inputs(pipe.inputs)
        if pipe.prompt_template:
            result["prompt_template"] = pipe.prompt_template
        if pipe.system_prompt:
            result["system_prompt"] = pipe.system_prompt

        return result

    @staticmethod
    def _serialize_ocr_pipe(pipe: PipeOcrBlueprint, domain: str) -> Dict[str, Any]:
        """Serialize PipeOcr blueprint."""
        result: Dict[str, Any] = {
            "type": pipe.type,
            "definition": pipe.definition,
            "output": pipe.output,
        }

        # Add optional fields only if they have values
        if pipe.inputs:
            result["inputs"] = PipelexInterpreter._serialize_inputs(pipe.inputs)

        return result

    @staticmethod
    def _serialize_func_pipe(pipe: PipeFuncBlueprint, domain: str) -> Dict[str, Any]:
        """Serialize PipeFunc blueprint."""
        result: Dict[str, Any] = {
            "type": pipe.type,
            "definition": pipe.definition,
            "output": pipe.output,
            "function_name": pipe.function_name,
        }

        # Add optional fields only if they have values
        if pipe.inputs:
            result["inputs"] = PipelexInterpreter._serialize_inputs(pipe.inputs)

        return result

    @staticmethod
    def _serialize_img_gen_pipe(pipe: PipeImgGenBlueprint, domain: str) -> Dict[str, Any]:
        """Serialize PipeImgGen blueprint."""
        result: Dict[str, Any] = {
            "type": pipe.type,
            "definition": pipe.definition,
            "output": pipe.output,
        }

        # Add optional fields only if they have values
        if pipe.inputs:
            result["inputs"] = PipelexInterpreter._serialize_inputs(pipe.inputs)
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
    def _serialize_jinja2_pipe(pipe: PipeJinja2Blueprint, domain: str) -> Dict[str, Any]:
        """Serialize PipeJinja2 blueprint."""
        result: Dict[str, Any] = {
            "type": pipe.type,
            "definition": pipe.definition,
            "output": pipe.output,
        }

        # Add optional fields only if they have values
        if pipe.inputs:
            result["inputs"] = PipelexInterpreter._serialize_inputs(pipe.inputs)
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
    def _serialize_sequence_pipe(pipe: PipeSequenceBlueprint, domain: str) -> Dict[str, Any]:
        """Serialize PipeSequence blueprint."""
        result: Dict[str, Any] = {
            "type": pipe.type,
            "definition": pipe.definition,
            "output": pipe.output,
        }

        # Add optional fields only if they have values
        if pipe.inputs:
            result["inputs"] = PipelexInterpreter._serialize_inputs(pipe.inputs)
        if pipe.steps:
            # Serialize steps, but only include non-default values
            serialized_steps: List[Dict[str, Any]] = []
            for step in pipe.steps:
                step_data: Dict[str, Any] = {
                    "pipe": step.pipe,
                    "result": step.result,
                }
                # Only include optional fields if they have non-default values
                if step.nb_output is not None:
                    step_data["nb_output"] = step.nb_output
                if step.multiple_output is not None:
                    step_data["multiple_output"] = step.multiple_output
                if step.batch_over is not False:  # Only include if not default False
                    step_data["batch_over"] = step.batch_over
                if step.batch_as is not None:
                    step_data["batch_as"] = step.batch_as
                serialized_steps.append(step_data)
            result["steps"] = serialized_steps

        return result

    @staticmethod
    def _serialize_condition_pipe(pipe: PipeConditionBlueprint, domain: str) -> Dict[str, Any]:
        """Serialize PipeCondition blueprint."""
        result: Dict[str, Any] = {
            "type": pipe.type,
            "definition": pipe.definition,
            "output": pipe.output,
            "pipe_map": pipe.pipe_map,
        }

        # Add optional fields only if they have values
        if pipe.inputs:
            result["inputs"] = PipelexInterpreter._serialize_inputs(pipe.inputs)
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
            "output": pipe.output,
        }

        # Add optional fields only if they have values
        if pipe.inputs:
            result["inputs"] = PipelexInterpreter._serialize_inputs(pipe.inputs)
        if pipe.parallels:
            # Serialize parallels, but only include non-default values
            serialized_parallels: List[Dict[str, Any]] = []
            for parallel in pipe.parallels:
                parallel_data: Dict[str, Any] = {
                    "pipe": parallel.pipe,
                    "result": parallel.result,
                }
                # Only include optional fields if they have non-default values
                if parallel.nb_output is not None:
                    parallel_data["nb_output"] = parallel.nb_output
                if parallel.multiple_output is not None:
                    parallel_data["multiple_output"] = parallel.multiple_output
                if parallel.batch_over is not False:  # Only include if not default False
                    parallel_data["batch_over"] = parallel.batch_over
                if parallel.batch_as is not None:
                    parallel_data["batch_as"] = parallel.batch_as
                serialized_parallels.append(parallel_data)
            result["parallels"] = serialized_parallels
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
            "output": pipe.output,
            "branch_pipe_code": pipe.branch_pipe_code,
        }

        # Add optional fields only if they have values
        if pipe.inputs:
            result["inputs"] = PipelexInterpreter._serialize_inputs(pipe.inputs)
        if pipe.input_list_name:
            result["input_list_name"] = pipe.input_list_name
        if pipe.input_item_name:
            result["input_item_name"] = pipe.input_item_name

        return result

    @staticmethod
    def _serialize_inputs(inputs: Dict[str, Any]) -> Dict[str, str]:
        """Convert InputRequirementBlueprint objects to concept code strings for TOML serialization."""
        result: Dict[str, str] = {}
        for key, value in inputs.items():
            if hasattr(value, "concept_code"):
                # InputRequirementBlueprint object
                result[key] = value.concept_code
            else:
                # Already a string
                result[key] = str(value)
        return result
