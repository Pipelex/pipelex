"""What plugins declare to the model manager: the internal models they ship, and the model deck defaults they set.

A plugin that ships an engine running inside Pipelex declares its model itself, rather than leaving it to the kit's
`internal.toml`, which only describes what open Pipelex ships. The registrar collects the declarations
(`add_internal_model`, `add_doc_gen_default`), `PluginRegistrar.make_model_declarations` freezes them into this value
object, and boot hands it to `ModelManagerAbstract.setup`, which merges the models into the internal backend and the
defaults beneath the model deck files. Nothing is validated when a plugin registers: the model manager validates each
declaration as it merges it, and names the plugin when one is refused.
"""

from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field

from pipelex.cogt.doc_gen.doc_gen_format import DocGenFormat, DocGenSource, doc_gen_choice_key


class PluginInternalModel(BaseModel):
    """One model a plugin declares in the internal backend, and the plugin that declared it.

    `spec` is exactly the table a backend file would hold for the model (`model_type`, `sdk`, `model_id`, `inputs`,
    `outputs`, `costs`…). It is complete on its own: no backend file's `[defaults]` table is applied to it.
    """

    model_config = ConfigDict(frozen=True)

    spec: dict[str, Any]
    plugin: str


class PluginDocGenDefault(BaseModel):
    """The engine a plugin declares as the model deck's default for one format and source, and the plugin that declared it."""

    model_config = ConfigDict(frozen=True)

    doc_gen_format: DocGenFormat
    source: DocGenSource
    model: str
    plugin: str

    @property
    def choice_key(self) -> str:
        """The key the model deck lists this default under: 'xlsx.layout'."""
        return doc_gen_choice_key(doc_gen_format=self.doc_gen_format, source=self.source)


class PluginModelDeclarations(BaseModel):
    """Every internal model and model deck default the registered plugins declared, frozen for the model manager to merge."""

    model_config = ConfigDict(frozen=True)

    internal_models: dict[str, PluginInternalModel] = Field(default_factory=dict)
    """The plugins' internal models, keyed by model name."""
    doc_gen_defaults: tuple[PluginDocGenDefault, ...] = ()

    @classmethod
    def make_empty(cls) -> Self:
        """No declarations: what a boot without such plugins, or a test that builds no registrar, hands the model manager."""
        return cls()

    def make_deck_base(self) -> dict[str, Any]:
        """The model deck document the defaults make, which the deck files, a user's `x_custom_*.toml` included, are merged over."""
        if not self.doc_gen_defaults:
            return {}
        choice_defaults = {doc_gen_default.choice_key: doc_gen_default.model for doc_gen_default in self.doc_gen_defaults}
        return {"doc_gen": {"choice_defaults": choice_defaults}}
