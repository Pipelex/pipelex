# Suspects — package `pipelex`

Reviewed: 3 Section A + 1 primitive lone-subject. Suspects: 2.

## High confidence

- `pipelex/pipelex.py:512` — `Pipelex.make` — `def make(cls, integration_mode: IntegrationMode = IntegrationMode.PYTHON, *, ...)` — `integration_mode` is a mode/configuration option, not the semantic subject of the factory (the subject is `cls` / the instance being created). All observed call sites either omit it (accepting the default) or already pass it as `integration_mode=...`. A positional call `Pipelex.make(IntegrationMode.CLI)` reads opaquely — the bare enum value conveys no context. Since this is the primary public API entry point, keyword-only is the right default. Suggested fix: `def make(cls, *, integration_mode: IntegrationMode = IntegrationMode.PYTHON, needs_inference: bool = True, ...)`.

## Medium / low confidence

- `pipelex/pipelex.py:145` — `Pipelex._get_validation_error_msg` — `def _get_validation_error_msg(component_name: str, *, validation_exc: Exception) -> str` — `component_name` is a descriptive string label ("routing profile library", "model deck"), not the object being operated on. It behaves more like a context parameter alongside `validation_exc`. Call sites: `self._get_validation_error_msg("routing profile library", validation_exc=exc)` — the bare positional string reads somewhat opaquely without the label. Private method, low call-site count, but the pattern is inconsistent: `validation_exc` is already keyword-only while `component_name` is not, despite both being descriptive context params. Suggested fix: `def _get_validation_error_msg(*, component_name: str, validation_exc: Exception) -> str`.

- `pipelex/pipelex.py:165` — `Pipelex.setup` — `def setup(self, integration_mode: IntegrationMode, *, ...)` — same logic as `make`: `integration_mode` is a mode-flag, not the subject (`self` is the subject). The sole internal call site (line 588) already uses `integration_mode=integration_mode` as keyword. Part of the public API surface (though `make` is the primary entry point). Suggested fix: `def setup(self, *, integration_mode: IntegrationMode, ...)`.
