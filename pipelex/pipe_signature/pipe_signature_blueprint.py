from typing import Literal, Self

from pydantic import Field, model_validator
from typing_extensions import override

from pipelex.pipe_machinery.pipe_blueprint import PipeBlueprint, PipeType

SIGNATURE_REFUSED_FIELDS: tuple[str, ...] = ("activity", "output_filename")
"""The base pipe fields a signature does not carry: it runs nothing, so it has no activity to show and writes no file. The
published schema leaves them off the signature arm (`pipelex.language.mthds_schema_generator`)."""


class PipeSignatureBlueprint(PipeBlueprint):
    """Contract-only pipe blueprint.

    A `PipeSignature` declares inputs and output but has no implementation. It exists so
    that an in-progress pipeline can be validated (dry-run mocks the declared output)
    before all its pipes are implemented.
    """

    # `exclude=True`: the tag is an internal union discriminator, not a language-surface field. A
    # signature has no `type` in `.mthds` (the author omits it — omitting the type IS the signature),
    # so it must not serialize one. This also keeps internal dump→revalidate round-trips typeless: the
    # dumped section carries no `type`, so the bundle before-validator re-injects it via
    # `normalize_typeless_signature_section` instead of tripping the explicit-tag migration error.
    type: Literal["PipeSignature"] = Field(default="PipeSignature", exclude=True)
    # Outside the executable taxonomy: no `PipeCategory`. Keep `exclude=True` (overriding the field
    # type drops the base's `Field(exclude=True)` unless re-specified) so it never serializes into `.mthds`.
    pipe_category: None = Field(default=None, exclude=True)
    # `signature_for=PipeSignature` is now rejected structurally: `PipeSignature` is no longer a
    # `PipeType` member, so Pydantic cannot coerce it into this field — no guard validator needed.
    signature_for: PipeType | None = Field(
        default=None,
        description="Intended downstream pipe type when this signature is implemented (optional hint for agents).",
    )

    @model_validator(mode="after")
    def refuse_execution_words(self) -> Self:
        """Refuse `activity` and `output_filename` on a signature, which describe a run and a file a contract never makes."""
        authored = [field_name for field_name in SIGNATURE_REFUSED_FIELDS if getattr(self, field_name) is not None]
        if authored:
            msg = (
                f"A signature (a pipe with no `type`) runs nothing, so it does not carry {', '.join(f'`{name}`' for name in authored)}: "
                "set it on the pipe that implements the signature"
            )
            raise ValueError(msg)
        return self

    @property
    @override
    def is_signature(self) -> bool:
        return True

    @override
    def validate_inputs(self) -> None:
        pass

    @override
    def validate_output(self) -> None:
        pass
