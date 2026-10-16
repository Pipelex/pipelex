from __future__ import annotations

import importlib.util
import sys
from typing import TYPE_CHECKING, Any

import pytest
from pydantic import ValidationError

from pipelex.cli.dev_cli.commands.error_registry.codes_generator import render_pipelex_codes
from pipelex.errors.registry.pipelex_codes import (
    PIPELEX_ERROR_PARAMS,
    CatalogNotFoundParams,
    ConfigSyntaxParams,
    DocgenPrintTimeoutParams,
    PipelexErrorCode,
    SecurityReservedKeyParams,
    WebhookDeliveryFailedParams,
)
from pipelex.errors.registry.registry_document import ErrorRegistryDocument, load_pipelex_error_registry

if TYPE_CHECKING:
    from pathlib import Path

# Items of a list parameter typed as each constrained scalar, added to a code to test what the generator writes for them.
CONSTRAINED_LIST_PARAMS: dict[str, dict[str, Any]] = {
    "sizes": {"type": "list", "items": {"type": "bytes"}, "description": "Sizes."},
    "durations": {"type": "list", "items": {"type": "seconds"}, "description": "Durations."},
    "digests": {"type": "list", "items": {"type": "sha256"}, "description": "Digests."},
}


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
            ("an integer given as a string", ConfigSyntaxParams, {"surface": "backends", "file": "backends.toml", "line": "3", "column": 1}),
            ("an integer given as a boolean", ConfigSyntaxParams, {"surface": "backends", "file": "backends.toml", "line": True, "column": 1}),
            ("a number of seconds given as a string", DocgenPrintTimeoutParams, {"limit": "30"}),
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

    @pytest.mark.parametrize(
        ("topic", "values"),
        [
            ("a negative size", {"sizes": [-4], "durations": [], "digests": []}),
            ("a negative duration", {"sizes": [], "durations": [-0.5], "digests": []}),
            ("a digest that is not lowercase hexadecimal", {"sizes": [], "durations": [], "digests": ["NOT-HEX"]}),
        ],
    )
    def test_a_list_item_carries_the_constraints_of_its_type(
        self,
        composed_document: dict[str, Any],
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        topic: str,
        values: dict[str, Any],
    ) -> None:
        """An item of a list of sizes, durations or digests is refused where a single parameter of its type would be."""
        entry = next(entry for entry in composed_document["codes"] if entry["code"] == "pipelex.storage.unavailable")
        entry["params"].update(CONSTRAINED_LIST_PARAMS)
        text = render_pipelex_codes(registry=ErrorRegistryDocument.model_validate(composed_document))
        assert "    sizes: list[Annotated[int, Field(ge=0)]]" in text
        assert "    durations: list[Annotated[float, Field(ge=0)]]" in text
        assert '    digests: list[Annotated[str, Field(pattern="^[0-9a-f]{64}$")]]' in text
        module_path = tmp_path / "generated_pipelex_codes.py"
        module_path.write_text(text, encoding="utf-8")
        spec = importlib.util.spec_from_file_location("generated_pipelex_codes", module_path)
        assert spec is not None
        assert spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        # Pydantic resolves the module's postponed annotations through sys.modules.
        monkeypatch.setitem(sys.modules, spec.name, module)
        spec.loader.exec_module(module)
        model: Any = module.StorageUnavailableParams
        valid = model(scheme="s3", sizes=[0, 4096], durations=[0.5], digests=["a" * 64])
        assert valid.sizes == [0, 4096]
        with pytest.raises(ValidationError):
            model(scheme="s3", **values)
        assert topic
