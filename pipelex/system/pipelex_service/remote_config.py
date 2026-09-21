from typing import cast

from pydantic import BaseModel, ConfigDict

from pipelex.cogt.model_backends.model_spec_factory import BackendModelSpecs


class RemoteConfig(BaseModel):
    """The single artifact the Pipelex service publishes, carrying one model-specs section per managed gateway.

    Every section — `manifold_model_specs` today — arrives through `extra="allow"`, which is what
    makes adding one a non-breaking change for a client that predates it: an older runtime parses the
    artifact and simply never asks for the new section. The same tolerance covers the keys the
    artifact still carries for other consumers (the hosted plane reads it too): the runtime declares
    no field of its own and reads only the sections its enabled managed backends name.
    """

    model_config = ConfigDict(extra="allow")

    def get_model_specs_section(self, section_name: str) -> BackendModelSpecs | None:
        """The named model-specs section, or ``None`` when the artifact does not carry one.

        Looked up by name rather than by field, because which section a managed backend reads is
        declared in that backend's configuration and the runtime learns it at boot. ``None`` is a
        real answer and not an error here: a backend declaring a section the published artifact does
        not carry is disabled with a named warning, the same posture as a missing variable.

        **The lookup is confined to the artifact's own content** — the sections it was published
        with — rather than being a bare ``getattr`` on the model. The name arrives from
        `model_specs_section` in the user's own `backends.toml`, and a bare ``getattr`` would answer
        for pydantic's machinery too: ``model_config`` and ``model_fields`` are both plain dicts on a
        v2 model, so either would pass the shape check below and be carried onwards as if the
        service had published it. Confined this way, an unmeant name is simply a section the
        artifact does not carry, and earns the named disabling warning it should.
        """
        raw: object | None = (self.__pydantic_extra__ or {}).get(section_name)
        if not isinstance(raw, dict):
            return None
        return cast("BackendModelSpecs", raw)
