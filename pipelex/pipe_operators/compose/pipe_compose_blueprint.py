from typing import Any, Literal

from pydantic import ConfigDict, Field, model_validator
from typing_extensions import override

from pipelex.cogt.templating.template_blueprint import TemplateBlueprint
from pipelex.cogt.templating.template_category import TemplateCategory
from pipelex.cogt.templating.template_preprocessor import preprocess_template
from pipelex.cogt.templating.templating_style import TemplatingStyle
from pipelex.core.pipes.pipe_blueprint import PipeBlueprint
from pipelex.core.pipes.variable_multiplicity import parse_concept_with_multiplicity
from pipelex.pipe_operators.compose.construct_blueprint import ConstructBlueprint
from pipelex.tools.jinja2.jinja2_errors import Jinja2TemplateSyntaxError
from pipelex.tools.jinja2.jinja2_parsing import check_jinja2_parsing
from pipelex.tools.jinja2.jinja2_required_variables import detect_jinja2_required_variables
from pipelex.tools.misc.string_utils import get_root_from_dotted_path


class PipeComposeBlueprint(PipeBlueprint):
    model_config = ConfigDict(populate_by_name=True)

    type: Literal["PipeCompose"] = "PipeCompose"
    pipe_category: Literal["PipeOperator"] = "PipeOperator"

    # Either template or construct must be provided, but not both
    # Note: The field is named 'construct_spec' internally to avoid conflict with Pydantic's
    # BaseModel.construct() method. In PLX/TOML files, use 'construct' (via validation_alias).
    template: str | TemplateBlueprint | None = None
    construct_blueprint: ConstructBlueprint | None = Field(default=None, validation_alias="construct")

    @model_validator(mode="before")
    @classmethod
    def validate_template_or_construct(cls, values: dict[str, Any]) -> dict[str, Any]:
        """Validate that exactly one of template or construct is provided."""
        has_template = values.get("template") is not None
        construct_raw = values.get("construct")

        if not has_template and construct_raw is None:
            msg = "PipeComposeBlueprint requires either 'template' or 'construct' to be provided"
            raise ValueError(msg)
        if has_template and construct_raw is not None:
            msg = "PipeComposeBlueprint cannot have both 'template' and 'construct' - use one or the other"
            raise ValueError(msg)

        if construct_raw is not None:
            construct_blueprint = ConstructBlueprint.make_from_raw(raw=construct_raw)
            values["construct_blueprint"] = construct_blueprint
            # Remove the raw 'construct' key to avoid conflict with the validation_alias
            values.pop("construct")
        return values

    @property
    def template_source(self) -> str | None:
        """Get the template source string, or None if in construct mode."""
        if self.template is None:
            return None
        if isinstance(self.template, TemplateBlueprint):
            return self.template.template
        return self.template

    @property
    def template_category(self) -> TemplateCategory:
        """Get the template category (only relevant in template mode)."""
        if isinstance(self.template, TemplateBlueprint):
            return self.template.category
        return TemplateCategory.BASIC

    @property
    def templating_style(self) -> TemplatingStyle | None:
        """Get the templating style (only relevant in template mode)."""
        if isinstance(self.template, TemplateBlueprint):
            return self.template.templating_style
        return None

    @property
    def extra_context(self) -> dict[str, Any] | None:
        """Get extra context (only relevant in template mode)."""
        if isinstance(self.template, TemplateBlueprint):
            return self.template.extra_context
        return None

    @override
    def validate_inputs(self):
        """Validate inputs based on mode (template or construct)."""
        if self.construct_blueprint is not None:
            self._validate_construct_inputs()
        else:
            self._validate_template_inputs()

    def _validate_template_inputs(self):
        """Validate inputs for template mode."""
        if self.template_source is None:
            return

        preprocessed_template = preprocess_template(self.template_source)
        try:
            check_jinja2_parsing(
                template_source=preprocessed_template,
                template_category=self.template_category,
            )
        except Jinja2TemplateSyntaxError as exc:
            msg = f"Could not parse template for PipeCompose: {exc}"
            raise ValueError(msg) from exc
        full_paths = detect_jinja2_required_variables(
            template_category=self.template_category,
            template_source=preprocessed_template,
        )
        required_variables: set[str] = set()
        for path in full_paths:
            root = get_root_from_dotted_path(path)
            if not root.startswith("_") and root not in {"preliminary_text", "place_holder"}:
                required_variables.add(root)
        for required_variable_name in required_variables:
            if required_variable_name not in self.input_names:
                msg = f"Required variable '{required_variable_name}' is not in the inputs of PipeCompose."
                raise ValueError(msg)

    def _validate_construct_inputs(self):
        """Validate inputs for construct mode.

        The construct blueprint may reference variables from working memory.
        We validate that the root variable names (before any dots) are declared in inputs.
        For example, 'deal.customer_name' requires 'deal' to be in inputs.
        """
        construct_bp = self.construct_blueprint
        if construct_bp is None:
            return

        required_variables = construct_bp.get_required_variables()

        for required_variable in required_variables:
            root_variable_name = get_root_from_dotted_path(required_variable)
            if root_variable_name not in self.input_names:
                msg = f"Required variable '{root_variable_name}' from construct is not in the inputs of PipeCompose for field '{required_variable}'."
                raise ValueError(msg)

    @override
    def validate_output(self):
        parsed_output = parse_concept_with_multiplicity(concept_ref=self.output)
        if parsed_output.multiplicity:
            msg = (
                "PipeCompose does not support multiple output generation. The output of PipeCompose must be a single stuff, "
                f"from a concept that refines the native Text concept. Current output: {self.output}"
            )
            raise ValueError(msg)
