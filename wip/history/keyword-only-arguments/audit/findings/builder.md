# Suspects — package `builder`

Reviewed: 20 Section A + 2 primitive lone-subjects. Suspects: 4.

## High confidence

- `pipelex/builder/operations/models_ops.py:36` — `_resolve_preset_backend` — `def _resolve_preset_backend(model_deck: ModelDeck, *, model_handle: str, model_type: ModelType) -> InferenceModelSpec | None` — The docstring says "Resolve a preset's model handle to an InferenceModelSpec": the thing being resolved is `model_handle`; `model_deck` is a lookup registry used as lookup context. Call sites confirm: `_resolve_preset_backend(model_deck, model_handle=setting.model, model_type=model_type)` — the deck reads as an unlabeled blob, while the real semantic target (`model_handle`) is buried in keyword args. Suggested fix: make fully keyword-only (`def _resolve_preset_backend(*, model_deck, model_handle, model_type)`).

- `pipelex/builder/operations/output_ops.py:14` — `build_output_for_pipe` — `async def build_output_for_pipe(mthds_contents: list[str], *, pipe_code: str, output_format: ...) -> dict[str, Any]` — The function name says "for_pipe", signalling that the pipe is the semantic subject. `mthds_contents` is raw bundle source material (context/input) not the object being acted on. A caller reading `build_output_for_pipe(some_list, pipe_code="my.pipe")` must think twice about what that first list is. Pair with `build_runner_code_for_pipe` which has the same shape and semantics. Suggested fix: make fully keyword-only (`def build_output_for_pipe(*, mthds_contents, pipe_code, output_format)`), or reorder so `pipe_code` is the positional subject.

- `pipelex/builder/operations/runner_code_ops.py:17` — `build_runner_code_for_pipe` — `async def build_runner_code_for_pipe(mthds_contents: list[str], *, pipe_code: str) -> str` — Same pattern as `build_output_for_pipe` above: the name says "for_pipe", the pipe is the semantic object, but `mthds_contents` (the source bundle data) was made positional. Suggested fix: make fully keyword-only, or promote `pipe_code` to the positional subject.

## Medium / low confidence

- `pipelex/builder/operations/models_ops.py:101` — `_build_presets_for_category` (and the parallel `_build_aliases_for_category` line 135, `_build_waterfalls_for_category` line 160) — `def _build_presets_for_category(model_deck: ModelDeck, *, category: ModelCategory, backend: str | None)` — The function name says "for_category"; the function matches on `category` to select which field of the deck to read. `model_deck` is the data source/registry, `category` is what drives the behavior. At call sites (`_build_presets_for_category(model_deck, category=ModelCategory.LLM, backend=backend)`) the deck reads as an unnamed blob. Lower confidence than the `_resolve_preset_backend` case because the deck is a richer object (not just a registry lookup), so it has a plausible claim to being the "subject" that is queried. Suggested fix: make fully keyword-only.
