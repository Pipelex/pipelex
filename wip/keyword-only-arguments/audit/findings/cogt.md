# Suspects — package `cogt`

Reviewed: 119 Section A + 42 primitive lone-subjects. Suspects: 3.

## High confidence

- `pipelex/cogt/usage/costs_per_token.py:4` — `model_cost_per_token` — `def model_cost_per_token(costs: CostsByCategoryDict, *, cost_category: CostCategory) -> float` — `costs` is a dict used purely as a lookup table; the function dispatches on `cost_category` and returns `costs.get(cost_category) / 1_000_000`. The real "subject" the function acts on is `cost_category`, while `costs` is context/registry. All three real call sites already use `costs=...` as a keyword. Suggested fix: move `*` before `costs` too — `def model_cost_per_token(*, costs: CostsByCategoryDict, cost_category: CostCategory) -> float` — or reorder with `cost_category` first.

- `pipelex/cogt/llm/reasoning_config_base.py:40` — `get_reasoning_level_str` — `def get_reasoning_level_str(effort_to_level_map: EffortToLevelMap, *, effort: ReasoningEffort) -> str | None` — `effort_to_level_map` is a `dict[str, str]` passed as contextual configuration; the function body is simply `effort_to_level_map.get(effort)`. The semantic object is `effort` (the query), while the map is a lookup table. All four call sites pass the map positionally via `self.effort_to_level_map` without a label, which reads opaquely. Suggested fix: fully keyword-only `def get_reasoning_level_str(*, effort_to_level_map: EffortToLevelMap, effort: ReasoningEffort)`.

## Medium / low confidence

- `pipelex/cogt/model_backends/backend_credentials.py:26` — `BackendCredentialsErrorMsgFactory.make_one_variable_missing_error_msg` — `def make_one_variable_missing_error_msg(cls, secrets_provider: SecretsProviderAbstract, *, backend_name: str | None, var_name: str) -> str` — `secrets_provider` acts as a dispatch context (the function `isinstance`-branches on its type to select message wording), while `backend_name` and `var_name` are the real domain objects the message describes. The sole call site already uses `secrets_provider=secrets_provider` as a keyword. This is lower-confidence because `secrets_provider` does meaningfully control branching. Suggested fix: fully keyword-only, or at least keep asymmetry noted; low urgency.
