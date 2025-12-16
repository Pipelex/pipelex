"""Blueprint for a single field in a construct section.

Defines how a field value is composed using one of 4 methods:
1. Fixed value: literal string, number, bool
2. Variable reference (from): path to variable in working memory
3. Template: Jinja2 template string (with $ preprocessing)
4. Nested construct: recursive ConstructBlueprint
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, model_validator

from pipelex.types import Self, StrEnum

if TYPE_CHECKING:
    from pipelex.pipe_operators.compose.construct_blueprint import ConstructBlueprint


class ConstructFieldMethod(StrEnum):
    """Method used to compose a field value."""

    FIXED = "fixed"
    FROM_VAR = "from_var"
    TEMPLATE = "template"
    NESTED = "nested"


class ConstructFieldBlueprint(BaseModel):
    """Blueprint for composing a single field in a StructuredContent.

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
        # Import here to avoid circular import
        from pipelex.pipe_operators.compose.construct_blueprint import ConstructBlueprint  # noqa: PLC0415

        if raw is None:
            msg = "Field value cannot be None"
            raise ValueError(msg)

        # Case 1: Scalar values are fixed (check dict first to handle bool which is subclass of int)
        if not isinstance(raw, dict):
            if isinstance(raw, (str, int, float, bool)):
                return cls(
                    method=ConstructFieldMethod.FIXED,
                    fixed_value=raw,
                )
            msg = f"Unsupported field value type: {type(raw).__name__}"
            raise ValueError(msg)

        # Case 2: Dict - need to determine if it's from_var, template, or nested
        from typing import cast  # noqa: PLC0415

        raw_dict = cast("dict[str, Any]", raw)
        if len(raw_dict) == 0:
            msg = "Field dict cannot be empty"
            raise ValueError(msg)

        has_from = "from" in raw_dict
        has_template = "template" in raw_dict

        # Check for mutually exclusive keys
        if has_from and has_template:
            msg = "'from' and 'template' are mutually exclusive in field definition"
            raise ValueError(msg)

        # Variable reference
        if has_from:
            if len(raw_dict) != 1:
                msg = "'from' field should only have the 'from' key"
                raise ValueError(msg)
            from_value = raw_dict["from"]
            if not isinstance(from_value, str):
                msg = "'from' value must be a string path"
                raise ValueError(msg)
            return cls(
                method=ConstructFieldMethod.FROM_VAR,
                from_path=from_value,
            )

        # Template
        if has_template:
            if len(raw_dict) != 1:
                msg = "'template' field should only have the 'template' key"
                raise ValueError(msg)
            template_value = raw_dict["template"]
            if not isinstance(template_value, str):
                msg = "'template' value must be a string"
                raise ValueError(msg)
            return cls(
                method=ConstructFieldMethod.TEMPLATE,
                template=template_value,
            )

        # Otherwise it's a nested construct
        nested_blueprint = ConstructBlueprint.make_from_raw(raw_dict)
        return cls(
            method=ConstructFieldMethod.NESTED,
            nested=nested_blueprint,
        )
