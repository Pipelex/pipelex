from __future__ import annotations

import shutil
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast

import pytest

from pipelex.cogt.doc_gen.doc_gen_format import DocGenFormat, DocGenSource
from pipelex.cogt.exceptions import PluginModelDeclarationError
from pipelex.cogt.model_backends.backend import PipelexBackend
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.cogt.models.model_manager import ModelManager
from pipelex.cogt.models.model_reference import ModelReference
from pipelex.kit.paths import get_kit_configs_dir
from pipelex.plugins.contract import PLUGIN_API_VERSION
from pipelex.plugins.plugin_group import PluginGroup
from pipelex.plugins.registrar import PluginOrigin, PluginRegistrar
from pipelex.system.configuration.config_loader import INFERENCE_DIR_NAME
from pipelex.tools.secrets.env_secrets_provider import EnvSecretsProvider

if TYPE_CHECKING:
    from pipelex.plugins.plugin_model_declarations import PluginModelDeclarations
    from pipelex.system.configuration.configs import PipelexConfig

PIPELEX_XLSX_SPEC: dict[str, Any] = {
    "model_type": "doc_gen",
    "sdk": "openpyxl",
    "model_id": "write-xlsx",
    "inputs": ["layout", "template_file"],
    "outputs": ["xlsx"],
    "costs": {},
}


def _declarations(
    *, doc_gen_defaults: dict[tuple[DocGenFormat, DocGenSource], str], internal_models: dict[str, dict[str, Any]]
) -> PluginModelDeclarations:
    """The declarations of one plugin, built the way the registrar builds them at boot."""
    config = cast("PipelexConfig", SimpleNamespace(runtime=SimpleNamespace(plugins=SimpleNamespace(disabled=[]))))
    registrar = PluginRegistrar(config=config)
    registrar.begin_plugin(name="doc-gen", origin=PluginOrigin.EXTERNAL, targets_api=PLUGIN_API_VERSION, group=PluginGroup.KERNEL)
    for name, spec in internal_models.items():
        registrar.add_internal_model(name=name, spec=spec)
    for (doc_gen_format, source), model in doc_gen_defaults.items():
        registrar.add_doc_gen_default(doc_gen_format=doc_gen_format, source=source, model=model)
    return registrar.make_model_declarations()


def _xlsx_plugin_declarations() -> PluginModelDeclarations:
    """A plugin declaring one engine, its default for its own format, and a default for the kit's pdf.layout, which the kit's deck file overrides."""
    return _declarations(
        internal_models={"pipelex-xlsx": PIPELEX_XLSX_SPEC},
        doc_gen_defaults={(DocGenFormat.XLSX, DocGenSource.LAYOUT): "pipelex-xlsx", (DocGenFormat.PDF, DocGenSource.LAYOUT): "pipelex-xlsx"},
    )


class TestPluginModelMerge:
    @pytest.fixture
    def inference_dir(self, tmp_path: Path) -> Path:
        """The kit's inference tree, routed to the internal backend so a keyless setup needs no credential."""
        inference_dir = tmp_path / INFERENCE_DIR_NAME
        shutil.copytree(Path(str(get_kit_configs_dir())) / INFERENCE_DIR_NAME, inference_dir)
        routing_profiles_path = inference_dir / "routing_profiles.toml"
        routing_profiles = routing_profiles_path.read_text(encoding="utf-8")
        assert 'active = "all_enabled_backends"' in routing_profiles
        routing_profiles_path.write_text(routing_profiles.replace('active = "all_enabled_backends"', 'active = "all_internal"', 1), encoding="utf-8")
        return inference_dir

    @staticmethod
    def _setup(*, inference_dir: Path, plugin_model_declarations: PluginModelDeclarations) -> ModelManager:
        models_manager = ModelManager()
        models_manager.setup(
            secrets_provider=EnvSecretsProvider(),
            plugin_model_declarations=plugin_model_declarations,
            needs_inference=False,
            backends_library_paths=[inference_dir / "backends.toml"],
            backends_dir_path=str(inference_dir / "backends"),
            routing_profile_library_paths=[inference_dir / "routing_profiles.toml"],
            deck_dir_path=str(inference_dir / "deck"),
        )
        return models_manager

    def test_a_plugin_model_and_its_default_are_merged(self, inference_dir: Path) -> None:
        """The plugin's model is served by the internal backend, and its default resolves to it."""
        model_deck = self._setup(inference_dir=inference_dir, plugin_model_declarations=_xlsx_plugin_declarations()).get_model_deck()

        inference_model = model_deck.get_required_inference_model(model_handle="pipelex-xlsx", model_type=ModelType.DOC_GEN)
        assert inference_model.backend_name == PipelexBackend.INTERNAL
        assert inference_model.sdk == "openpyxl"
        assert inference_model.inputs == ["layout", "template_file"]
        assert inference_model.outputs == ["xlsx"]
        choice = model_deck.get_doc_gen_choice_default(doc_gen_format=DocGenFormat.XLSX, source=DocGenSource.LAYOUT)
        assert choice is not None
        assert model_deck.get_doc_gen_setting(doc_gen_choice=choice).model == "pipelex-xlsx"

    def test_a_deck_file_overrides_a_plugin_default(self, inference_dir: Path) -> None:
        """The plugin's defaults sit beneath the deck files: the kit's own and a user's x_custom file both win."""
        (inference_dir / "deck" / "x_custom_doc_gen_deck.toml").write_text(
            '[doc_gen.choice_defaults]\n"xlsx.layout" = "@my-xlsx"\n\n[doc_gen.aliases]\nmy-xlsx = "pipelex-xlsx"\n', encoding="utf-8"
        )

        model_deck = self._setup(inference_dir=inference_dir, plugin_model_declarations=_xlsx_plugin_declarations()).get_model_deck()

        pdf_choice = model_deck.get_doc_gen_choice_default(doc_gen_format=DocGenFormat.PDF, source=DocGenSource.LAYOUT)
        assert pdf_choice is not None
        assert model_deck.get_doc_gen_setting(doc_gen_choice=pdf_choice).model == "reportlab-pdf"
        xlsx_choice = model_deck.get_doc_gen_choice_default(doc_gen_format=DocGenFormat.XLSX, source=DocGenSource.LAYOUT)
        assert isinstance(xlsx_choice, ModelReference)
        assert xlsx_choice.raw == "@my-xlsx"

    def test_a_plugin_model_internal_toml_declares_too_fails_the_boot_naming_the_plugin_and_the_file(self, inference_dir: Path) -> None:
        internal_toml_path = inference_dir / "backends" / "internal.toml"
        internal_toml = internal_toml_path.read_text(encoding="utf-8")
        internal_toml_path.write_text(
            f'{internal_toml}\n[pipelex-xlsx]\nmodel_type = "doc_gen"\nsdk = "openpyxl"\ninputs = ["layout"]\noutputs = ["xlsx"]\ncosts = {{}}\n',
            encoding="utf-8",
        )

        with pytest.raises(PluginModelDeclarationError) as exc_info:
            self._setup(inference_dir=inference_dir, plugin_model_declarations=_xlsx_plugin_declarations())

        assert exc_info.value.plugin == "doc-gen"
        assert "'doc-gen'" in str(exc_info.value)
        assert "'pipelex-xlsx'" in str(exc_info.value)
        assert str(internal_toml_path) in str(exc_info.value)

    def test_a_plugin_may_declare_another_kind_of_a_name_internal_toml_declares(self, inference_dir: Path) -> None:
        """A handle names one model per model type: the file's document engine and the plugin's extractor share a name."""
        declarations = _declarations(
            internal_models={"reportlab-pdf": {**PIPELEX_XLSX_SPEC, "model_type": "text_extractor", "model_id": "read-pdf"}}, doc_gen_defaults={}
        )

        model_deck = self._setup(inference_dir=inference_dir, plugin_model_declarations=declarations).get_model_deck()

        assert model_deck.inference_models.types_serving(handle="reportlab-pdf") == [ModelType.TEXT_EXTRACTOR, ModelType.DOC_GEN]
        assert model_deck.get_required_inference_model(model_handle="reportlab-pdf", model_type=ModelType.TEXT_EXTRACTOR).model_id == "read-pdf"
        assert model_deck.get_required_inference_model(model_handle="reportlab-pdf", model_type=ModelType.DOC_GEN).model_id == "print-pdf"

    def test_a_plugin_table_takes_no_file_defaults(self, inference_dir: Path) -> None:
        """The plugin's table is complete on its own: `internal.toml`'s `[defaults]` reaches the file's models only."""
        internal_toml_path = inference_dir / "backends" / "internal.toml"
        internal_toml = internal_toml_path.read_text(encoding="utf-8")
        internal_toml_path.write_text(
            internal_toml.replace('[defaults]\nthinking_mode = "none"', '[defaults]\nthinking_mode = "none"\nmax_tokens = 99', 1), encoding="utf-8"
        )

        model_deck = self._setup(inference_dir=inference_dir, plugin_model_declarations=_xlsx_plugin_declarations()).get_model_deck()

        assert model_deck.get_required_inference_model(model_handle="reportlab-pdf", model_type=ModelType.DOC_GEN).max_tokens == 99
        assert model_deck.get_required_inference_model(model_handle="pipelex-xlsx", model_type=ModelType.DOC_GEN).max_tokens is None

    def test_an_invalid_plugin_table_fails_the_boot_naming_the_plugin(self, inference_dir: Path) -> None:
        declarations = _declarations(internal_models={"pipelex-xlsx": {**PIPELEX_XLSX_SPEC, "not_a_field": 1}}, doc_gen_defaults={})

        with pytest.raises(PluginModelDeclarationError, match="Plugin 'doc-gen' declares the internal model 'pipelex-xlsx'"):
            self._setup(inference_dir=inference_dir, plugin_model_declarations=declarations)

    def test_a_plugin_default_no_step_uses_fails_the_boot_naming_the_plugin(self, inference_dir: Path) -> None:
        declarations = _declarations(internal_models={}, doc_gen_defaults={(DocGenFormat.PPTX, DocGenSource.LAYOUT): "pipelex-pptx"})

        with pytest.raises(PluginModelDeclarationError, match="Plugin 'doc-gen' declares a default document engine that no step can use"):
            self._setup(inference_dir=inference_dir, plugin_model_declarations=declarations)

    def test_without_an_internal_backend_the_plugin_adds_nothing(self, inference_dir: Path) -> None:
        """A disabled internal backend loads none of its models, the plugin's included, and the plugin's defaults stay out with them."""
        backends_toml_path = inference_dir / "backends.toml"
        backends_toml = backends_toml_path.read_text(encoding="utf-8")
        backends_toml_path.write_text(
            backends_toml.replace(
                "[internal] # software-only backend, runs internally, without AI\nenabled = true", "[internal]\nenabled = false", 1
            ),
            encoding="utf-8",
        )
        routing_profiles_path = inference_dir / "routing_profiles.toml"
        routing_profiles_path.write_text(
            routing_profiles_path.read_text(encoding="utf-8").replace('active = "all_internal"', 'active = "all_openai"', 1), encoding="utf-8"
        )

        model_deck = self._setup(inference_dir=inference_dir, plugin_model_declarations=_xlsx_plugin_declarations()).get_model_deck()

        assert not model_deck.inference_models.types_serving(handle="pipelex-xlsx")
        assert model_deck.get_doc_gen_choice_default(doc_gen_format=DocGenFormat.XLSX, source=DocGenSource.LAYOUT) is None
