# Suspects — package `system`

Reviewed: 38 Section A + 27 primitive lone-subjects. Suspects: 4.

## High confidence

- `pipelex/system/pipelex_service/gateway_config_merger.py:69` — `GatewayConfigMerger._apply_overrides_to_model` — `def _apply_overrides_to_model(cls, model_name: str, *, gateway_model_specs: BackendModelSpecs, local_model_config: BackendModelSpecs) -> None` — `model_name` is a string identifier used only in log/warning messages; the real operands being acted on are the two keyword args `gateway_model_specs` and `local_model_config`. The sole call site already passes `model_name=model_name` as a keyword. Suggested fix: make fully keyword-only (`def _apply_overrides_to_model(cls, *, model_name, gateway_model_specs, local_model_config)`).

## Medium / low confidence

- `pipelex/system/pipelex_service/pipelex_service_agreement.py:29` — `update_service_terms_acceptance` — `def update_service_terms_acceptance(accepted: bool, *, config_dir: Path | None=None) -> None` — `accepted` is a bare `bool` positional; `update_service_terms_acceptance(True)` is opaque without the keyword. All actual call sites already use `accepted=True/False` as keyword. Suggested fix: move `*` before `accepted` (make fully keyword-only).

- `pipelex/system/pipelex_service/pipelex_service_agreement.py:53` — `update_inference_setup_completed` — `def update_inference_setup_completed(completed: bool, *, config_dir: Path | None=None) -> None` — same pattern as above: bare `bool` positional, always called as `completed=True` at every call site. Suggested fix: make fully keyword-only.

- `pipelex/system/configuration/config_check.py:12` — `check_is_initialized` — `def check_is_initialized(print_warning_if_not: bool=True) -> bool` — Section B: single `bool` param with a descriptive name, but `check_is_initialized(False)` would be opaque; every call site in tests already uses `print_warning_if_not=False/True` or the no-arg default form. Low priority since it has a default and callers always keyword it — but making it keyword-only would enforce that. Suggested fix: `def check_is_initialized(*, print_warning_if_not: bool=True)`.
