from typing import Any, ClassVar, Dict

from jinja2 import TemplateSyntaxError
from pydantic import Field, RootModel, ValidationError
from typing_extensions import override

from pipelex import log
from pipelex.libraries.library_config import LibraryConfig
from pipelex.tools.exceptions import ToolException
from pipelex.tools.misc.toml_utils import load_toml_from_path
from pipelex.tools.templating.jinja2_parsing import check_jinja2_parsing
from pipelex.tools.templating.jinja2_template_category import Jinja2TemplateCategory
from pipelex.tools.templating.template_preprocessor import preprocess_template
from pipelex.tools.templating.template_provider_abstract import TemplateNotFoundError, TemplateProviderAbstract
from pipelex.tools.typing.pydantic_utils import format_pydantic_validation_error

TemplateLibraryRoot = Dict[str, str]


class TemplateLibraryError(ToolException):
    pass


class TemplateLibrary(TemplateProviderAbstract, RootModel[TemplateLibraryRoot]):
    root: TemplateLibraryRoot = Field(default_factory=dict)
    library_config: ClassVar[LibraryConfig]

    @classmethod
    def make_empty(cls, config_dir_path: str) -> "TemplateLibrary":
        cls.library_config = LibraryConfig(config_dir_path=config_dir_path)
        return cls()

    @override
    def setup(self) -> None:
        template_toml_paths = self.library_config.get_templates_paths()
        for template_toml_path in template_toml_paths:
            self._load_from_toml(toml_path=template_toml_path)
        self.validate_templates(template_category=Jinja2TemplateCategory.LLM_PROMPT)

    @override
    def teardown(self) -> None:
        self.root = {}

    @override
    def get_template(self, template_name: str) -> str:
        try:
            return self.root[template_name]
        except KeyError as exc:
            raise TemplateNotFoundError(f"Template '{template_name}' not found in template library") from exc

    def _set_template(self, template: str, name: str):
        preprocessed_template = preprocess_template(template)
        self.root[name] = preprocessed_template

    def _add_new_template(self, template: str, name: str):
        if name in self.root:
            raise TemplateLibraryError(f"Template '{name}' already exists in the library")
        self._set_template(template=template, name=name)

    def _load_from_toml(self, toml_path: str):
        nb_concepts_before = len(self.root)
        library_dict = load_toml_from_path(path=toml_path)
        for start_domain, templates in library_dict.items():
            self._load_from_recursive_dict(domain=start_domain, recursive_dict=templates)
        toml_name = toml_path.split("/")[-1]
        log.debug(f"Loaded {len(self.root) - nb_concepts_before} templates from '{toml_name}'")

    def _load_from_recursive_dict(self, domain: str, recursive_dict: Dict[str, Any]):
        for name, obj in recursive_dict.items():
            try:
                if isinstance(obj, str):
                    # it's a template
                    template = obj
                    self._add_new_template(template=template, name=name)
                elif isinstance(obj, dict):
                    # this is not a templae but a subdomain
                    sub_recursive_dict: Dict[str, str] = obj
                    domain = f"{domain}/{name}"
                    self._load_from_recursive_dict(domain=domain, recursive_dict=sub_recursive_dict)
                else:
                    raise TemplateLibraryError(f"Unexpected type for key '{name}' in recursive_dict: {type(obj)}")
            except ValidationError as exc:
                error_msg = format_pydantic_validation_error(exc)
                raise TemplateLibraryError(f"Error loading concept '{name}' of domain '{domain}' because of: {error_msg}") from exc

    def validate_templates(self, template_category: Jinja2TemplateCategory):
        for template_name, template in self.root.items():
            try:
                check_jinja2_parsing(
                    jinja2_template_source=template,
                    template_category=template_category,
                )
            except TemplateSyntaxError as exc:
                error_msg = f"Jinja2 syntax error in template '{template_name}': {exc}."
                if template:
                    error_msg += f"\nThe template is:\n{template}"
                else:
                    error_msg += "The template is empty."
                raise TemplateLibraryError(error_msg) from exc
