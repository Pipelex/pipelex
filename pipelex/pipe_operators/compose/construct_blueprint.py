"""Blueprint for a construct section in PipeCompose.

A ConstructBlueprint defines how to compose a StructuredContent object
by specifying how each field should be constructed from inputs.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from pipelex.cogt.templating.template_category import TemplateCategory
from pipelex.cogt.templating.template_preprocessor import preprocess_template

# pyright: reportImportCycles=false
from pipelex.pipe_operators.compose.construct_field_blueprint import ConstructFieldBlueprint, ConstructFieldMethod
from pipelex.tools.jinja2.jinja2_errors import Jinja2DetectVariablesError
from pipelex.tools.jinja2.jinja2_required_variables import detect_jinja2_required_variables


class ConstructBlueprint(BaseModel):
    """Blueprint for composing a StructuredContent from working memory.

    Parsed from `[pipe.name.construct]` section in PLX files.

    Attributes:
        fields: Dictionary mapping field names to their composition blueprints
    """

    model_config = ConfigDict(extra="forbid")

    fields: dict[str, ConstructFieldBlueprint]

    @property
    def field_names(self) -> list[str]:
        """Return list of all top-level field names."""
        return list(self.fields.keys())

    def get_required_variables(self) -> set[str]:
        """Extract all variable names/paths required to compose this construct.

        This includes:
        - All 'from' paths (variable references)
        - All variables used in templates (base names only, e.g., 'deal' from 'deal.amount')
        - Variables from nested constructs (recursively)

        Returns:
            Set of variable names/paths needed from working memory
        """
        required: set[str] = set()

        for field_blueprint in self.fields.values():
            match field_blueprint.method:
                case ConstructFieldMethod.FROM_VAR:
                    if field_blueprint.from_path:
                        # Also only the base variable name for input validation
                        base_var = field_blueprint.from_path.split(".")[0]
                        required.add(base_var)

                case ConstructFieldMethod.TEMPLATE:
                    if field_blueprint.template:
                        # Use the same approach as template mode: preprocess then detect variables
                        preprocessed = preprocess_template(field_blueprint.template)
                        try:
                            template_vars = detect_jinja2_required_variables(
                                template_category=TemplateCategory.BASIC,
                                template_source=preprocessed,
                            )
                        except Jinja2DetectVariablesError as exc:
                            msg = f"Error detecting required variables in construct template: {exc}"
                            raise ValueError(msg) from exc
                        # Filter out internal variables
                        template_vars = {var for var in template_vars if not var.startswith("_") and var not in {"preliminary_text", "place_holder"}}
                        required.update(template_vars)

                case ConstructFieldMethod.NESTED:
                    if field_blueprint.nested:
                        nested_vars = field_blueprint.nested.get_required_variables()
                        required.update(nested_vars)

                case ConstructFieldMethod.FIXED:
                    # Fixed values don't require any variables
                    pass

        return required

    @classmethod
    def make_from_raw(cls, raw: dict[str, Any]) -> ConstructBlueprint:
        """Create a ConstructBlueprint from raw TOML construct section.

        Args:
            raw: The raw dict from TOML parsing of construct section

        Returns:
            ConstructBlueprint with all field blueprints

        Raises:
            TypeError: If the raw input is not a dict
            ValueError: If the raw dict is empty
        """
        # Runtime type check - the signature says dict but callers may pass wrong types
        if type(raw) is not dict:
            msg = f"Construct must be a dict, got {type(raw).__name__}"
            raise TypeError(msg)

        if len(raw) == 0:
            msg = "Construct cannot be empty"
            raise ValueError(msg)

        fields: dict[str, ConstructFieldBlueprint] = {}
        for field_name, field_raw in raw.items():
            fields[field_name] = ConstructFieldBlueprint.make_from_raw(field_raw)

        return cls(fields=fields)
