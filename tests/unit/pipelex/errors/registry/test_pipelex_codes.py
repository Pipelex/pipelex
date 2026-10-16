from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from pipelex.errors.registry.pipelex_codes import (
    PIPELEX_ERROR_PARAMS,
    CatalogNotFoundParams,
    ConfigSyntaxParams,
    DocgenPrintTimeoutParams,
    PipelexErrorCode,
    SecurityReservedKeyParams,
    WebhookDeliveryFailedParams,
)
from pipelex.errors.registry.registry_document import load_pipelex_error_registry


class TestPipelexCodes:
    def test_each_parameters_model_declares_the_registry_parameters(self) -> None:
        """A code's model has a field per declared parameter, optional ones defaulting to None, and names its operator-only ones."""
        for entry in load_pipelex_error_registry().codes:
            model = PIPELEX_ERROR_PARAMS[PipelexErrorCode(entry.code)]
            assert list(model.model_fields) == list(entry.params), entry.code
            for param_name, param in entry.params.items():
                field = model.model_fields[param_name]
                assert field.is_required() is not param.optional, f"{entry.code}.{param_name}"
            expected_operator_only = {param_name for param_name, param in entry.params.items() if param.operator_only}
            assert model.operator_only_params == expected_operator_only, entry.code

    @pytest.mark.parametrize(
        ("topic", "model", "values"),
        [
            ("an undeclared parameter", ConfigSyntaxParams, {"surface": "backends", "file": "backends.toml", "line": 3, "column": 1, "path": "x"}),
            ("a missing parameter", ConfigSyntaxParams, {"surface": "backends", "file": "backends.toml", "line": 3}),
            ("a value outside the enum", WebhookDeliveryFailedParams, {"reason": "timeout"}),
            ("a negative number of seconds", DocgenPrintTimeoutParams, {"limit": -1.0}),
            ("a list item of the wrong type", SecurityReservedKeyParams, {"keys": [{"name": "__class__"}]}),
        ],
    )
    def test_a_parameters_model_refuses_what_the_registry_does_not_declare(self, topic: str, model: Any, values: dict[str, Any]) -> None:
        """The models are closed and typed as the registry declares, so a raise site cannot carry a fact the code does not."""
        with pytest.raises(ValidationError):
            model(**values)
        assert topic

    def test_a_parameters_model_holds_the_declared_values(self) -> None:
        """A valid occurrence validates, its optional parameters may be absent, and the model is frozen."""
        params = CatalogNotFoundParams(resource="method", method_id="mt_abc")
        assert params.version is None
        assert params.code == PipelexErrorCode.CATALOG_NOT_FOUND
        with pytest.raises(ValidationError):
            params.method_id = "mt_other"  # type: ignore[misc]  # pyright: ignore[reportAttributeAccessIssue]
        delivery = WebhookDeliveryFailedParams(reason="http_status", receiver_status=500)
        assert delivery.model_dump() == {"reason": "http_status", "receiver_status": 500}
        timeout = DocgenPrintTimeoutParams(limit=30)
        assert timeout.limit == 30.0
