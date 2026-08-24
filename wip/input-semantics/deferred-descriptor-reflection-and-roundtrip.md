# Deferred: two input-form descriptor gaps surfaced by the D2 pre-landing review

Neither is a live bug on the surfaces that exist today; both need a decision before code, so they are recorded here rather than fixed in D2 (`feature/Input-semantics-D2`).

## Reflected classes never read a field's default

`pipelex/codegen/native_expansion.py` derives `required` for a reflected class field from an `X | None` annotation only and never reads `field_info.default`, so a class field such as `count: int = Field(default=0)` lands in the descriptor as `required: true` with no `default_value` (the blueprint-side fields do carry `default_value`). The mechanical fix is small — `field_info.is_required()` for the flag and `field_info.default` unless it is `PydanticUndefined`, stamped in `_with_reflected_constraints` in `pipelex/pipeline/input_form.py` — but it changes what "required" means for reflected classes relative to the schema chain (the S2 finding E3), and the spec says defaults are authored facts. Decide whether a pydantic default counts as an authored fact first; then it is a one-function change plus a row in `TestKindAssignmentTable`.

## The wire descriptor does not round-trip through its own model

`InputFormField` serializes `datetime_flag` under the spec's `datetime` wire name but declares no validation alias, so `InputFormField.model_validate(field.model_dump(mode="json"))` fails on every `date` node, and the FastAPI `response_model` documents the attribute name rather than the wire name. No consumer re-validates the descriptor with the Python model today (neither `pipelex-api`, `pipelex-server`, `mthds-python` nor `pipelex-sdk-python` reference it yet), so this bites only when the Python SDK grows descriptor models — that is D4's concern, where the right move is a `validation_alias` / `populate_by_name` pair or a renamed attribute, chosen together with the SDK types.
