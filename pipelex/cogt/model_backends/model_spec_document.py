"""One backend definition file, read as a document — the shape both of its readers share.

A backend file is not one model. It is an optional `[defaults]` table plus one root table per model
name, and neither half is an `InferenceModelSpecBlueprint` on its own: `sdk` is required and
normally lives in `[defaults]`, so only the merge of the two validates. Two readers need that
stated, and they must never disagree:

- **the loader** (`InferenceBackendLibrary.load`) merges and validates for real, to build the specs;
- **the `inference-backend` migration surface**, which needs the same verdict on a whole document
  (is the migrated file still one the loader accepts?) and a *field-level* projection of one root
  table (what paths does a backend file have, for the fingerprint?).

So both live here rather than in the migration package: a surface that validated a backend document
its own way would let the gate go green over a file that does not boot, which is the one thing the
gate exists to prevent.

One asymmetry in the loader is load-bearing and reproduced faithfully below: **`[defaults]` is not
passed through `split_model_spec_keys`.** It is copied wholesale into every model's blueprint dict,
so a key the blueprint no longer knows fails *every* table with `extra_forbidden`, while the same key
on one model is rejected by name as `NOT_HEADER_SHAPED`. That is why one dead key in `[defaults]`
breaks a whole backend and why the two halves need two different remedies in the migration ledger.
"""

from typing import Any, cast

from pydantic import ValidationError

from pipelex.cogt.model_backends.model_spec_factory import InferenceModelSpecBlueprint
from pipelex.cogt.model_backends.model_spec_keys import describe_rejected_keys, split_model_spec_keys
from pipelex.tools.typing.pydantic_utils import format_pydantic_validation_error

MODEL_SPEC_DEFAULTS_TABLE = "defaults"
"""The one root table of a backend file that is not a model: what every model in it starts from."""


class InferenceModelSpecFileNode(InferenceModelSpecBlueprint):
    """One root table of a backend file, on its own — every field optional.

    **A projection for the fingerprint, never a validator.** Nothing loads a backend file through
    this model: it exists so the migration fingerprint can record what paths a backend file *has*
    without claiming that any one table must carry them. Every root table is a partial spec —
    `[defaults]` holds what the models share, a model table holds what it overrides — so the only
    honest projection is one in which nothing is required.

    It is a subclass rather than a hand-written twin so that **nothing** can drift: not the field
    set, and not the annotations and bounds either. A twin kept honest by a name-comparison test
    would still let a field's *type* move on the blueprint alone, and the fingerprint would go on
    recording the old one — a narrowing the coverage gate is meant to catch, going quiet. The one
    thing to keep true is that nothing here is required, which `sdk` is the only field to override
    today; a new required field on the blueprint turns the guard in
    `tests/unit/pipelex/cogt/model_backends/test_model_spec_document.py` red, which is the moment to
    decide whether it is genuinely required of a *file* or only of a merged spec.

    The widening of `sdk` is what makes this a subclass a type checker objects to, and the objection
    is right in general: something holding a blueprint may read `.sdk` as a `str`. It is silenced
    rather than designed around because this model is never constructed and never validated against
    — only `model_fields` is ever read — and the alternatives all cost more than they buy: a
    hand-written twin reopens the type-drift hole above, a `create_model` derivation drops the
    per-field metadata the fingerprint reads, and a placeholder default (`sdk: str = ""`) buys the
    type checker's silence by putting a value in the model that no file ever has.
    """

    sdk: str | None = None  # type: ignore[assignment] # pyright: ignore[reportIncompatibleVariableOverride]


def describe_model_spec_document_rejection(*, document: dict[str, Any]) -> str | None:
    """Why the current schema refuses this backend document, or `None` when it accepts it.

    Faithful to `InferenceBackendLibrary.load` and to nothing else — it pops `[defaults]`, splits the
    header-shaped keys off each model table, merges, and validates the result against the real
    blueprint. A document this accepts is one the loader loads; a document this refuses is one that
    breaks a boot.

    A **reason string rather than an exception** on purpose. The caller is the migration gate, which
    reports the reason as one issue among many in its own vocabulary, and a new error class here
    would buy nothing and cost the error-identity snapshot and the generated reference page.
    """
    defaults = document.get(MODEL_SPEC_DEFAULTS_TABLE, {})
    if not isinstance(defaults, dict):
        return f"'{MODEL_SPEC_DEFAULTS_TABLE}' is not a table"
    typed_defaults = cast("dict[str, Any]", defaults)
    for model_name, value in document.items():
        if model_name == MODEL_SPEC_DEFAULTS_TABLE:
            continue
        if not isinstance(value, dict):
            return f"model '{model_name}' is not a table"
        typed_model_table = cast("dict[str, Any]", value)
        key_split = split_model_spec_keys(model_spec_dict=typed_model_table)
        if key_split.rejected:
            return f"model '{model_name}': {describe_rejected_keys(rejected=key_split.rejected)}"
        try:
            InferenceModelSpecBlueprint.model_validate({**typed_defaults, **key_split.fields})
        except ValidationError as exc:
            return f"model '{model_name}': {format_pydantic_validation_error(exc)}"
    return None
