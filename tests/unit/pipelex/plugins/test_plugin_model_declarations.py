"""The model declarations seam: a plugin declares internal models and model deck defaults, and the registrar freezes them.

Pins the registrar half independent of the model manager: each entry stores its data and records a contribution for
`pipelex plugins list`, a second declaration of the same name or the same format and source fails loud naming both
plugins, nothing is validated at registration, and `make_model_declarations` hands the model manager copies it can
merge, with the plugin that declared each one.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast

import pytest

from pipelex.cogt.doc_gen.doc_gen_format import DocGenFormat, DocGenSource
from pipelex.plugins.contract import PLUGIN_API_VERSION
from pipelex.plugins.exceptions import DuplicateDocGenDefaultError, DuplicateInternalModelError
from pipelex.plugins.plugin_group import PluginGroup
from pipelex.plugins.plugin_model_declarations import PluginModelDeclarations
from pipelex.plugins.registrar import PluginOrigin, PluginRegistrar

if TYPE_CHECKING:
    from pipelex.system.configuration.configs import PipelexConfig

PIPELEX_XLSX_SPEC: dict[str, Any] = {
    "model_type": "doc_gen",
    "sdk": "openpyxl",
    "model_id": "write-xlsx",
    "inputs": ["layout", "template_file"],
    "outputs": ["xlsx"],
    "costs": {},
}


def _make_registrar() -> PluginRegistrar:
    config = cast("PipelexConfig", SimpleNamespace(runtime=SimpleNamespace(plugins=SimpleNamespace(disabled=[]))))
    return PluginRegistrar(config=config)


class TestPluginModelDeclarations:
    def test_an_internal_model_is_stored_and_recorded_as_a_contribution(self) -> None:
        registrar = _make_registrar()
        discovery = registrar.begin_plugin(name="doc-gen", origin=PluginOrigin.EXTERNAL, targets_api=PLUGIN_API_VERSION, group=PluginGroup.KERNEL)

        registrar.add_internal_model(name="pipelex-xlsx", spec=PIPELEX_XLSX_SPEC)

        assert registrar.internal_models == {"pipelex-xlsx": PIPELEX_XLSX_SPEC}
        assert "internal model pipelex-xlsx" in discovery.contributions

    def test_a_doc_gen_default_is_stored_and_recorded_as_a_contribution(self) -> None:
        registrar = _make_registrar()
        discovery = registrar.begin_plugin(name="doc-gen", origin=PluginOrigin.EXTERNAL, targets_api=PLUGIN_API_VERSION, group=PluginGroup.KERNEL)

        registrar.add_doc_gen_default(doc_gen_format=DocGenFormat.XLSX, source=DocGenSource.LAYOUT, model="pipelex-xlsx")

        assert registrar.doc_gen_defaults == {(DocGenFormat.XLSX, DocGenSource.LAYOUT): "pipelex-xlsx"}
        assert "doc_gen default xlsx.layout = pipelex-xlsx" in discovery.contributions

    def test_an_internal_model_declared_twice_names_both_plugins(self) -> None:
        registrar = _make_registrar()
        registrar.begin_plugin(name="alpha", origin=PluginOrigin.EXTERNAL, targets_api=PLUGIN_API_VERSION, group=PluginGroup.KERNEL)
        registrar.add_internal_model(name="pipelex-xlsx", spec=PIPELEX_XLSX_SPEC)
        registrar.begin_plugin(name="beta", origin=PluginOrigin.EXTERNAL, targets_api=PLUGIN_API_VERSION, group=PluginGroup.KERNEL)

        with pytest.raises(DuplicateInternalModelError) as exc_info:
            registrar.add_internal_model(name="pipelex-xlsx", spec=PIPELEX_XLSX_SPEC)

        assert exc_info.value.first_plugin == "alpha"
        assert exc_info.value.second_plugin == "beta"
        assert "'alpha'" in str(exc_info.value)
        assert "'beta'" in str(exc_info.value)

    def test_a_doc_gen_default_declared_twice_names_both_plugins(self) -> None:
        registrar = _make_registrar()
        registrar.begin_plugin(name="alpha", origin=PluginOrigin.EXTERNAL, targets_api=PLUGIN_API_VERSION, group=PluginGroup.KERNEL)
        registrar.add_doc_gen_default(doc_gen_format=DocGenFormat.PDF, source=DocGenSource.HTML, model="pipelex-pdf")
        registrar.begin_plugin(name="beta", origin=PluginOrigin.EXTERNAL, targets_api=PLUGIN_API_VERSION, group=PluginGroup.KERNEL)

        with pytest.raises(DuplicateDocGenDefaultError) as exc_info:
            registrar.add_doc_gen_default(doc_gen_format=DocGenFormat.PDF, source=DocGenSource.HTML, model="other-pdf")

        assert exc_info.value.choice_key == "pdf.html"
        assert exc_info.value.first_plugin == "alpha"
        assert exc_info.value.second_plugin == "beta"

    def test_a_kernel_group_plugin_may_declare_both(self) -> None:
        """Plain data at the kernel tier: a kernel-group plugin reaches both entries without a layer violation."""
        registrar = _make_registrar()
        registrar.begin_plugin(name="doc-gen", origin=PluginOrigin.EXTERNAL, targets_api=PLUGIN_API_VERSION, group=PluginGroup.KERNEL)

        registrar.add_internal_model(name="pipelex-xlsx", spec=PIPELEX_XLSX_SPEC)
        registrar.add_doc_gen_default(doc_gen_format=DocGenFormat.XLSX, source=DocGenSource.LAYOUT, model="pipelex-xlsx")

    def test_nothing_is_validated_at_registration(self) -> None:
        """A table that is no model spec and a pair no step composes are stored: the model manager refuses them at boot."""
        registrar = _make_registrar()
        registrar.begin_plugin(name="doc-gen", origin=PluginOrigin.EXTERNAL, targets_api=PLUGIN_API_VERSION, group=PluginGroup.KERNEL)

        registrar.add_internal_model(name="broken", spec={"not_a_field": True})
        registrar.add_doc_gen_default(doc_gen_format=DocGenFormat.PPTX, source=DocGenSource.LAYOUT, model="pipelex-pptx")

        assert "broken" in registrar.internal_models
        assert (DocGenFormat.PPTX, DocGenSource.LAYOUT) in registrar.doc_gen_defaults

    def test_the_declarations_carry_each_entry_and_the_plugin_that_declared_it(self) -> None:
        registrar = _make_registrar()
        registrar.begin_plugin(name="doc-gen", origin=PluginOrigin.EXTERNAL, targets_api=PLUGIN_API_VERSION, group=PluginGroup.KERNEL)
        registrar.add_internal_model(name="pipelex-xlsx", spec=PIPELEX_XLSX_SPEC)
        registrar.add_doc_gen_default(doc_gen_format=DocGenFormat.XLSX, source=DocGenSource.LAYOUT, model="pipelex-xlsx")

        declarations = registrar.make_model_declarations()

        assert declarations.internal_models["pipelex-xlsx"].spec == PIPELEX_XLSX_SPEC
        assert declarations.internal_models["pipelex-xlsx"].plugin == "doc-gen"
        (doc_gen_default,) = declarations.doc_gen_defaults
        assert doc_gen_default.choice_key == "xlsx.layout"
        assert doc_gen_default.model == "pipelex-xlsx"
        assert doc_gen_default.plugin == "doc-gen"
        assert declarations.make_deck_base() == {"doc_gen": {"choice_defaults": {"xlsx.layout": "pipelex-xlsx"}}}

    def test_the_declarations_do_not_follow_a_table_the_plugin_changes_afterwards(self) -> None:
        registrar = _make_registrar()
        registrar.begin_plugin(name="doc-gen", origin=PluginOrigin.EXTERNAL, targets_api=PLUGIN_API_VERSION, group=PluginGroup.KERNEL)
        spec = dict(PIPELEX_XLSX_SPEC, inputs=["layout", "template_file"])
        registrar.add_internal_model(name="pipelex-xlsx", spec=spec)
        declarations = registrar.make_model_declarations()

        spec["sdk"] = "changed"
        spec["inputs"].append("html")
        declarations.internal_models["pipelex-xlsx"].spec["inputs"].append("html")

        recorded_spec = registrar.make_model_declarations().internal_models["pipelex-xlsx"].spec
        assert recorded_spec["sdk"] == "openpyxl"
        assert recorded_spec["inputs"] == ["layout", "template_file"]

    def test_no_declarations_make_no_deck_base(self) -> None:
        assert PluginModelDeclarations.make_empty().make_deck_base() == {}
        assert _make_registrar().make_model_declarations() == PluginModelDeclarations.make_empty()
