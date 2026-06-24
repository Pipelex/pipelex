# Suspects — package `pipe_operators`

Reviewed: 40 Section A + 3 primitive lone-subjects. Suspects: 4.

## High confidence

- `pipelex/pipe_operators/img_gen/img_gen_prompt_blueprint.py:269` — `ImgGenPromptBlueprint._render_text` — `async def _render_text(self, context_provider: ContextProviderAbstract, *, template_blueprint: TemplateBlueprint, ...)` — `context_provider` is a lookup environment/registry, not the thing being rendered. `template_blueprint` is the real subject. Call sites always pass `context_provider=` as a keyword: `self._render_text(context_provider=context_provider, template_blueprint=..., ...)`. Suggested fix: make fully keyword-only — `def _render_text(self, *, context_provider, template_blueprint, ...)`.

- `pipelex/pipe_operators/llm/llm_prompt_blueprint.py:350` — `LLMPromptBlueprint._unravel_text` — `async def _unravel_text(self, context_provider: ContextProviderAbstract, *, jinja2_blueprint: TemplateBlueprint, ...)` — identical pattern to `_render_text`: `context_provider` is the resolution environment, `jinja2_blueprint` is what gets unraveled. Call sites always use `context_provider=` as keyword. Suggested fix: make fully keyword-only — `def _unravel_text(self, *, context_provider, jinja2_blueprint, ...)`.

## Medium / low confidence

- `pipelex/pipe_operators/compose/structured_content_composer.py:392` — `StructuredContentComposer._expects_type` — `def _expects_type(self, expected_type: type[Any], *, target_type: type)` — symmetric type-comparison pair (`issubclass(expected_type, target_type)`); neither argument is more "subject" than the other. Call sites always pass `expected_type=expected_type` as keyword (e.g. `self._expects_type(expected_type=expected_type, target_type=StuffContent)`), suggesting both args are directional operands. Suggested fix: make fully keyword-only — `def _expects_type(self, *, expected_type, target_type)`.

- `pipelex/pipe_operators/img_gen/img_gen_prompt_blueprint.py:65` — `ImgGenPromptBlueprint.make_img_gen_prompt` — `async def make_img_gen_prompt(self, context_provider: ContextProviderAbstract, *, extra_params, max_prompt_images)` — `context_provider` is a resolution environment, not what's being generated (the prompt is being built from `self`, the blueprint). Call site uses `context_provider=working_memory` as keyword. Lower confidence because "context to use for building" is a defensible subject role. Suggested fix: make fully keyword-only — `def make_img_gen_prompt(self, *, context_provider, ...)`.
