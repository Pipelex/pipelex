"""Blueprint for a construct section in PipeCompose.

A ConstructBlueprint defines how to compose a StructuredContent object
by specifying how each field should be constructed from inputs.
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, ConfigDict

# pyright: reportImportCycles=false
from pipelex.pipe_operators.compose.construct_field_blueprint import ConstructFieldBlueprint, ConstructFieldMethod


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
                        # Add the full path
                        required.add(field_blueprint.from_path)
                        # Also add the base variable name for input validation
                        base_var = field_blueprint.from_path.split(".")[0]
                        required.add(base_var)

                case ConstructFieldMethod.TEMPLATE:
                    if field_blueprint.template:
                        # Extract variable names from template
                        # This is a simplified extraction - full implementation would use
                        # the template preprocessor to find all variables
                        template_vars = self._extract_template_variables(field_blueprint.template)
                        required.update(template_vars)

                case ConstructFieldMethod.NESTED:
                    if field_blueprint.nested:
                        nested_vars = field_blueprint.nested.get_required_variables()
                        required.update(nested_vars)

                case ConstructFieldMethod.FIXED:
                    # Fixed values don't require any variables
                    pass

        return required

    def _extract_template_variables(self, template: str) -> set[str]:
        """Extract variable names from a template string.

        Handles both $var and {{ var }} syntax.
        Returns base variable names (e.g., 'deal' from '$deal.amount').

        Args:
            template: Template string to parse

        Returns:
            Set of base variable names found in the template
        """
        variables: set[str] = set()

        # Match $variable.path patterns (our preprocessor syntax)
        dollar_pattern = r"\$([a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)*)"
        for match in re.finditer(dollar_pattern, template):
            full_path = match.group(1)
            variables.add(full_path)
            # Also add base variable name
            base_var = full_path.split(".")[0]
            variables.add(base_var)

        # Match {{ variable }} Jinja2 patterns (simplified)
        jinja2_pattern = r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)*)"
        for match in re.finditer(jinja2_pattern, template):
            full_path = match.group(1)
            variables.add(full_path)
            base_var = full_path.split(".")[0]
            variables.add(base_var)

        return variables

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
