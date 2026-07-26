import re
from typing import Literal

from pydantic import field_validator
from typing_extensions import override

from pipelex.cogt.search.search_setting import SearchModelChoice
from pipelex.cogt.templating.exceptions import TemplateSigilSyntaxError
from pipelex.cogt.templating.template_preprocessor import preprocess_template
from pipelex.core.pipes.pipe_blueprint import PipeBlueprint
from pipelex.tools.jinja2.exceptions import Jinja2TemplateSyntaxError
from pipelex.tools.jinja2.jinja2_parsing import check_jinja2_parsing
from pipelex.tools.jinja2.jinja2_required_variables import detect_jinja2_required_variables
from pipelex.tools.jinja2.template_category import TemplateCategory
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
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date_value):
            msg = f"'{date_value}' is not a valid ISO 8601 date (expected YYYY-MM-DD)"
            raise ValueError(msg)
        return date_value

    @override
    def validate_inputs(self):
        template_category = TemplateCategory.BASIC
        declared_inputs: set[str] = set(self.inputs.keys()) if self.inputs else set()
        try:
            preprocessed_template = preprocess_template(self.prompt, declared_inputs=declared_inputs)
        except TemplateSigilSyntaxError as exc:
            msg = f"Template sigil error in PipeSearch prompt: {exc}"
            raise ValueError(msg) from exc
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

        missing_variables: set[str] = required_variables - declared_inputs

        if missing_variables:
            missing_vars_str = ", ".join(sorted(missing_variables))
            msg = (
                f"Missing input variable(s) in prompt template: {missing_vars_str}. "
                "These variables are used in the prompt but not declared in inputs."
            )
            raise ValueError(msg)
