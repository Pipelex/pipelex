# Suspects — package `pipe_run`

Reviewed: 18 Section A + 3 primitive lone-subjects. Suspects: 3.

## High confidence

- `pipelex/pipe_run/delivery_executor.py:201` — `DeliveryExecutor._try_add_rendered_file` — `async def _try_add_rendered_file(cls, files: dict[str, ResultFile], *, filename: str, render: Awaitable[str], content_type: str) -> None` — `files` is a mutable accumulator dict (output container), not the semantic subject being acted on. The real subjects of the "add" operation are `filename`/`render`/`content_type`. At the call site: `self._try_add_rendered_file(files, filename="main_stuff.json", ...)` — the positional `files` reads as a registry/sink, not the thing the function is about. Suggested fix: make fully keyword-only — `async def _try_add_rendered_file(cls, *, files: dict[str, ResultFile], filename: str, render: Awaitable[str], content_type: str) -> None`.

- `pipelex/pipe_run/delivery_executor.py:219` — `DeliveryExecutor._add_optional_text_file` — `def _add_optional_text_file(cls, files: dict[str, ResultFile], *, filename: str, text: str | None, content_type: str) -> None` — Same pattern as `_try_add_rendered_file`: `files` is the accumulator dict carried positionally, while `filename`/`text`/`content_type` are the content being added (the actual "what"). Call site: `self._add_optional_text_file(files, filename="graphspec.json", text=..., content_type=...)`. Suggested fix: make fully keyword-only — `def _add_optional_text_file(cls, *, files: dict[str, ResultFile], filename: str, text: str | None, content_type: str) -> None`.

## Medium / low confidence

- `pipelex/pipe_run/pipe_run_params.py:28` — `output_multiplicity_to_apply` — `def output_multiplicity_to_apply(base_multiplicity: VariableMultiplicity | None, *, override_multiplicity: VariableMultiplicity | None) -> VariableMultiplicityResolution` — This is a two-operand resolution function: `base_multiplicity` and `override_multiplicity` are both inputs to a priority merge. Neither is clearly "the object the function acts on" — the function computes a result from two equal-standing inputs. The docstring examples (`output_multiplicity_to_apply(None, None)`) also show positional calling with raw `None` values, which is opaque. Suggested fix: make fully keyword-only — `def output_multiplicity_to_apply(*, base_multiplicity: VariableMultiplicity | None, override_multiplicity: VariableMultiplicity | None) -> VariableMultiplicityResolution`.
