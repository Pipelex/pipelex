from datetime import date
from typing import Literal

from pydantic import field_validator
from typing_extensions import override

from pipelex.cogt.search.search_setting import SearchModelChoice
from pipelex.cogt.templating.template_category import TemplateCategory
from pipelex.cogt.templating.template_preprocessor import preprocess_template
from pipelex.core.pipes.pipe_blueprint import PipeBlueprint
from pipelex.tools.jinja2.jinja2_errors import Jinja2TemplateSyntaxError
from pipelex.tools.jinja2.jinja2_parsing import check_jinja2_parsing
from pipelex.tools.jinja2.jinja2_required_variables import detect_jinja2_required_variables
from pipelex.tools.misc.string_utils import get_root_from_dotted_path


class PipeSearchBlueprint(PipeBlueprint):
    type: Literal["PipeSearch"] = "PipeSearch"
    pipe_category: Literal["PipeOperator"] = "PipeOperator"
    prompt: str
    model: SearchModelChoice | None = None
    include_images: bool | None = None
    max_results: int | None = None
    from_date: str | None = None
    to_date: str | None = None
    include_domains: list[str] | None = None
    exclude_domains: list[str] | None = None

    @field_validator("from_date", "to_date", mode="before")
    @classmethod
    def validate_date_format(cls, date_value: str | None) -> str | None:
        if date_value is None:
            return date_value
        try:
            date.fromisoformat(date_value)
        except ValueError:
            msg = f"'{date_value}' is not a valid ISO 8601 date (expected YYYY-MM-DD)"
            raise ValueError(msg) from None
        return date_value

    @override
    def validate_inputs(self):
        template_category = TemplateCategory.BASIC
        preprocessed_template = preprocess_template(self.prompt)
        try:
            check_jinja2_parsing(
                template_source=preprocessed_template,
                template_category=template_category,
            )
        except Jinja2TemplateSyntaxError as exc:
            msg = f"Could not parse template for PipeSearch: {exc}"
            raise ValueError(msg) from exc

        full_paths = detect_jinja2_required_variables(
            template_category=template_category,
            template_source=preprocessed_template,
        )
        required_variables: set[str] = set()
        for path in full_paths:
            root = get_root_from_dotted_path(path)
            if not root.startswith("_"):
                required_variables.add(root)

        input_names: set[str] = set(self.inputs.keys()) if self.inputs else set()
        missing_variables: set[str] = required_variables - input_names

        if missing_variables:
            missing_vars_str = ", ".join(sorted(missing_variables))
            msg = (
                f"Missing input variable(s) in prompt template: {missing_vars_str}. "
                "These variables are used in the prompt but not declared in inputs."
            )
            raise ValueError(msg)
