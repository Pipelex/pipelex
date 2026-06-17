# Suspects — package `tools`

Reviewed: 128 Section A + 77 primitive lone-subjects. Suspects: 4.

## High confidence

- `pipelex/tools/jinja2/jinja2_required_variables.py:121` — `detect_jinja2_required_variables` — `def detect_jinja2_required_variables(template_category: TemplateCategory, *, template_source: str) -> set[str]` — `template_source` is the object being analyzed; `template_category` is a configuration/mode parameter. All call sites already pass `template_category=` as a keyword — the positional exemption provides zero benefit and buries the real subject keyword-only. Suggested fix: `def detect_jinja2_required_variables(template_source: str, *, template_category: TemplateCategory) -> set[str]`

- `pipelex/tools/jinja2/jinja2_required_variables.py:255` — `detect_jinja2_variable_references` — `def detect_jinja2_variable_references(template_category: TemplateCategory, *, template_source: str) -> list[VariableReference]` — same pattern as above: template_source is the object analyzed, template_category is configuration. All call sites use `template_category=` as keyword. Suggested fix: swap order so `template_source` is the positional subject.

- `pipelex/tools/jinja2/jinja2_filters.py:110` — `apply_tag_style` — `def apply_tag_style(context: Context, *, value: str, tag_name: str | None=None) -> str` — `context` is a Jinja2 `Context` used only as a lookup table to retrieve `TAG_STYLE`; `value` is the string being wrapped. The real subject is `value`, not `context`. Single call site already passes `context` positionally (framework-driven), but conceptually the positional arg is a lookup registry, not the acted-on object. Suggested fix: fully keyword-only `def apply_tag_style(*, context: Context, value: str, tag_name: str | None = None)`.

## Medium / low confidence

- `pipelex/tools/jinja2/jinja2_environment.py:9` — `make_jinja2_env_from_loader` — `def make_jinja2_env_from_loader(template_category: TemplateCategory, *, loader: BaseLoader, enable_async: bool=True) -> Environment` — the function name says "from loader", which points to `loader` as the operative argument; `template_category` is a configuration parameter. Minor — `template_category` is a valid configuration object that drives the env construction, so reasonable to keep it positional. Suggested fix: `def make_jinja2_env_from_loader(loader: BaseLoader, *, template_category: TemplateCategory, enable_async: bool = True)` or fully keyword-only.
