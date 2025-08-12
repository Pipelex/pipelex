from __future__ import annotations

from typing import Optional

from pipelex import log, pretty_print
from pipelex.create.helpers import get_support_file
from pipelex.create.pipeline_toml import save_pipeline_blueprint_toml_to_path
from pipelex.create.structured_output_generator import generate_structured_outputs_from_toml_string
from pipelex.create.validate_blueprint import load_pipes_from_generated_blueprint, validate_blueprint
from pipelex.libraries.pipeline_blueprint import PipelineBlueprint
from pipelex.pipeline.execute import execute_pipeline
from pipelex.tools.misc.file_utils import save_text_to_path
from pipelex.tools.misc.json_utils import save_as_json_to_path


def _convert_blueprint_concepts_to_toml(blueprint: PipelineBlueprint) -> Optional[str]:
    """Convert blueprint concepts with structures to TOML format for StructuredOutputGenerator."""
    if not blueprint.concept:
        return None
    
    # Find concepts that have structure definitions
    structured_concepts = {}
    for concept_name, concept_blueprint in blueprint.concept.items():
        if concept_blueprint.structure:
            structured_concepts[concept_name] = {
                "definition": concept_blueprint.definition,
                "fields": concept_blueprint.structure
            }
    
    if not structured_concepts:
        return None
    
    # Generate TOML content
    toml_lines = []
    
    for concept_name, concept_data in structured_concepts.items():
        toml_lines.append(f"[structure.{concept_name}]")
        toml_lines.append(f'definition = "{concept_data["definition"]}"')
        toml_lines.append("")
        
        # Add fields
        toml_lines.append(f"[structure.{concept_name}.fields]")
        for field_name, field_def in concept_data["fields"].items():
            if isinstance(field_def, dict):
                # Complex field definition
                toml_lines.append(f"[structure.{concept_name}.fields.{field_name}]")
                for key, value in field_def.items():
                    if isinstance(value, str):
                        toml_lines.append(f'{key} = "{value}"')
                    elif isinstance(value, bool):
                        toml_lines.append(f'{key} = {str(value).lower()}')
                    else:
                        toml_lines.append(f'{key} = {value}')
            else:
                # Simple string field definition
                toml_lines.append(f'{field_name} = "{field_def}"')
        toml_lines.append("")
    
    return "\n".join(toml_lines)





async def do_build_blueprint(
    domain: str,
    pipeline_name: str,
    requirements: str,
    output_path: Optional[str],
    validate: bool,
) -> None:
    pipe_output = await execute_pipeline(
        pipe_code="build_blueprint",
        input_memory={
            "domain": domain,
            "pipeline_name": pipeline_name,
            "requirements": requirements,
            "draft_pipeline_rules": get_support_file(subpath="create/draft_pipelines.md"),
            "build_pipeline_rules": get_support_file(subpath="create/build_pipelines.md"),
            "create_structured_output_rules": get_support_file(subpath="create/structures.md"),
        },
    )
    pretty_print(pipe_output, title="Pipe Output")
    blueprint = pipe_output.main_stuff_as(content_type=PipelineBlueprint)
    pretty_print(blueprint, title="Pipeline Blueprint")
    pipeline_draft = pipe_output.working_memory.get_stuff_as_str(name="pipeline_draft")
    pretty_print(pipeline_draft, title="Pipeline Draft")

    # Save or display result
    output_path_base = output_path or "pipelex/libraries/pipelines/temp/gen_blueprint"
    draft_path = f"{output_path_base}_draft.md"
    save_text_to_path(text=pipeline_draft, path=draft_path)
    rough_toml_path = f"{output_path_base}_rough.toml"
    save_pipeline_blueprint_toml_to_path(blueprint=blueprint, path=rough_toml_path)
    rough_json_path = f"{output_path_base}_rough.json"
    save_as_json_to_path(object_to_save=blueprint, path=rough_json_path)
    log.info(f"✅ Rough blueprint saved to '{output_path_base}'")

    load_pipes_from_generated_blueprint(blueprint=blueprint)
    log.info("✅ Pipes loaded from blueprint")

    # Generate structured output Python classes from blueprint concepts
    # Use the already generated TOML and extract structure info from blueprint
    if blueprint.concept:
        structured_concepts = [name for name, concept in blueprint.concept.items() if concept.structure]
        if structured_concepts:
            try:
                toml_content = _convert_blueprint_concepts_to_toml(blueprint)
                if toml_content:
                    python_code = generate_structured_outputs_from_toml_string(toml_content)
                    python_path = f"{output_path_base}_structures.py"
                    save_text_to_path(text=python_code, path=python_path)
                    log.info(f"✅ Python structured outputs saved to '{python_path}' for: {', '.join(structured_concepts)}")
            except Exception as e:
                log.error(f"❌ Failed to generate structured outputs: {e}")
        else:
            log.info("ℹ️ No structured concepts found in blueprint")

    if validate:
        await validate_blueprint(blueprint=blueprint, is_error_fixing_enabled=True)
        fixed_toml_path = f"{output_path_base}_fixed.toml"
        save_pipeline_blueprint_toml_to_path(blueprint=blueprint, path=fixed_toml_path)
        fixed_json_path = f"{output_path_base}_fixed.json"
        save_as_json_to_path(object_to_save=blueprint, path=fixed_json_path)
        log.info(f"✅ Fixed blueprint saved to '{output_path_base}'")
