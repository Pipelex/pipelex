"""Blueprint for construct sections in PipeCompose.

This module defines how to compose StructuredContent objects from working memory:
- ConstructFieldMethod: Enum defining the 4 composition methods
- ConstructFieldBlueprint: How a single field is composed
- ConstructBlueprint: Container for all field blueprints in a construct
"""

from __future__ import annotations

from typing import Any, cast

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from pipelex.cogt.templating.template_category import TemplateCategory
from pipelex.cogt.templating.template_preprocessor import preprocess_template
from pipelex.pipe_operators.compose.exceptions import ConstructFieldBlueprintTypeError, ConstructFieldBlueprintValueError
from pipelex.tools.jinja2.jinja2_errors import Jinja2DetectVariablesError
from pipelex.tools.jinja2.jinja2_required_variables import detect_jinja2_required_variables
from pipelex.tools.misc.string_utils import get_root_from_dotted_path
from pipelex.types import Self, StrEnum


class ConstructFieldMethod(StrEnum):
    """Method used to compose a field value."""

    FIXED = "fixed"
    FROM_VAR = "from_var"
    TEMPLATE = "template"
    NESTED = "nested"


class ConstructFieldBlueprint(BaseModel):
    """Blueprint for composing a single field in a StructuredContent.

    Defines how a field value is composed using one of 4 methods:
    1. Fixed value: literal string, number, bool
    2. Variable reference (from): path to variable in working memory
    3. Template: Jinja2 template string (with $ preprocessing)
    4. Nested construct: recursive ConstructBlueprint

    Attributes:
        method: The composition method to use
        fixed_value: Literal value (for FIXED method)
        from_path: Variable path in working memory (for FROM_VAR method)
        template: Jinja2 template string (for TEMPLATE method)
        nested: Nested ConstructBlueprint (for NESTED method)
    """

    model_config = ConfigDict(extra="forbid")

    method: ConstructFieldMethod
    fixed_value: Any | None = None
    from_path: str | None = None
    template: str | None = None
    nested: ConstructBlueprint | None = None

    @model_validator(mode="after")
    def validate_method_data_consistency(self) -> Self:
        """Ensure the data matches the declared method."""
        match self.method:
            case ConstructFieldMethod.FIXED:
                if self.fixed_value is None:
                    msg = "fixed_value is required for FIXED method"
                    raise ValueError(msg)
            case ConstructFieldMethod.FROM_VAR:
                if self.from_path is None:
                    msg = "from_path is required for FROM_VAR method"
                    raise ValueError(msg)
            case ConstructFieldMethod.TEMPLATE:
                if self.template is None:
                    msg = "template is required for TEMPLATE method"
                    raise ValueError(msg)
            case ConstructFieldMethod.NESTED:
                if self.nested is None:
                    msg = "nested is required for NESTED method"
                    raise ValueError(msg)
        return self

    @classmethod
    def make_from_raw(cls, raw: Any) -> ConstructFieldBlueprint:
        """Create a ConstructFieldBlueprint from raw TOML input.

        Args:
            raw: The raw value from TOML parsing. Can be:
                - str/int/float/bool: Fixed value
                - dict with 'from' key: Variable reference
                - dict with 'template' key: Template
                - dict with other keys: Nested construct

        Returns:
            ConstructFieldBlueprint with appropriate method and data

        Raises:
            ValueError: If the raw input is invalid or ambiguous
        """
        if raw is None:
            msg = "Field value cannot be None"
            raise ConstructFieldBlueprintValueError(msg)

        if isinstance(raw, (str, int, float, bool)):
            return cls(
                method=ConstructFieldMethod.FIXED,
                fixed_value=raw,
            )
        elif isinstance(raw, dict):
            raw_dict = cast("dict[str, Any]", raw)
            if len(raw_dict) == 0:
                msg = "Field dict cannot be empty"
                raise ConstructFieldBlueprintValueError(msg)

            has_from = "from" in raw_dict
            has_template = "template" in raw_dict

            # Check for mutually exclusive keys
            if has_from and has_template:
                msg = "'from' and 'template' are mutually exclusive in field definition"
                raise ConstructFieldBlueprintValueError(msg)

            if has_from:
                # Variable reference
                if len(raw_dict) != 1:
                    msg = "'from' field should only have the 'from' key"
                    raise ConstructFieldBlueprintValueError(msg)
                from_value = raw_dict["from"]
                if not isinstance(from_value, str):
                    msg = "'from' value must be a string path"
                    raise ConstructFieldBlueprintTypeError(msg)
                return cls(
                    method=ConstructFieldMethod.FROM_VAR,
                    from_path=from_value,
                )
            elif has_template:
                # Template
                if len(raw_dict) != 1:
                    msg = "'template' field should only have the 'template' key"
                    raise ConstructFieldBlueprintValueError(msg)
                template_value = raw_dict["template"]
                if not isinstance(template_value, str):
                    msg = "'template' value must be a string"
                    raise ConstructFieldBlueprintTypeError(msg)
                return cls(
                    method=ConstructFieldMethod.TEMPLATE,
                    template=template_value,
                )
            else:
                # Otherwise it's a nested construct
                nested_blueprint = ConstructBlueprint.make_from_raw(raw_dict)
                return cls(
                    method=ConstructFieldMethod.NESTED,
                    nested=nested_blueprint,
                )
        else:
            msg = f"Unsupported field value type: {type(raw).__name__}"
            raise ConstructFieldBlueprintTypeError(msg)


class ConstructBlueprint(BaseModel):
    """Blueprint for composing a StructuredContent from working memory.

    Parsed from `[pipe.name.construct]` section in PLX files.

    Attributes:
        fields: Dictionary mapping field names to their composition blueprints
    """

    model_config = ConfigDict(extra="forbid")

    fields: dict[str, ConstructFieldBlueprint]

    @field_validator("fields", mode="before")
    @classmethod
    def validate_fields(cls, fields: dict[str, ConstructFieldBlueprint]) -> dict[str, ConstructFieldBlueprint]:
        if len(fields) == 0:
            msg = "Construct fields dictionary cannot be empty"
            raise ValueError(msg)
        return fields

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
                        base_var = get_root_from_dotted_path(field_blueprint.from_path)
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
                        # Extract root names and filter out internal variables (same approach as template mode)
                        for var in template_vars:
                            root_var = get_root_from_dotted_path(var)
                            if not root_var.startswith("_") and root_var not in {"preliminary_text", "place_holder"}:
                                required.add(root_var)

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
        fields: dict[str, ConstructFieldBlueprint] = {}
        for field_name, field_raw in raw.items():
            fields[field_name] = ConstructFieldBlueprint.make_from_raw(field_raw)

        return cls(fields=fields)


# The two models reference each other, so we need to rebuild the model to resolve forward references
ConstructFieldBlueprint.model_rebuild()
