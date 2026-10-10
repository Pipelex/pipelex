from __future__ import annotations

import io
import json
import logging
import uuid
from typing import TYPE_CHECKING, Annotated, Literal

import pytest
from pydantic import BaseModel, ConfigDict, Field, RootModel, ValidationError, field_validator, model_validator
from pydantic_core import PydanticCustomError

from pipelex.core.stuffs.date_content import DateContent
from pipelex.system.configuration.config_loader import ConfigLoader
from pipelex.tools.log.error_fields import ERROR_MESSAGE_FIELD, ERROR_TYPE_FIELD, error_fields
from pipelex.tools.log.json_log_sink import EXCEPTION_KEY, LOGGER_KEY, MESSAGE_KEY, JsonLogSink
from pipelex.tools.log.log import Log
from pipelex.tools.log.log_config import LogConfig
from pipelex.tools.misc.toml_utils import load_toml_from_path

if TYPE_CHECKING:
    from collections.abc import Iterator


class _ManifestParseError(ValueError):
    pass


class _Settings(BaseModel):
    retries: int
    limits: dict[str, int]


class _Retries(RootModel[int]):
    pass


# A value no secret pattern matches, so the redaction never hides it and only the field's own rule can keep it out.
_PAYLOAD = "confidential-patient-diagnosis"


class _Diagnosis(BaseModel):
    """A model whose validators quote the value they reject, as a custom validator is free to."""

    diagnosis: str
    severity: int = 0
    code: str = "none"
    reviewed: bool = False

    @field_validator("diagnosis")
    @classmethod
    def _diagnosis_is_coded(cls, value: str) -> str:
        if not value.startswith("ICD-"):
            msg = f"{value!r} is not a coded diagnosis"
            raise ValueError(msg)
        return value

    @field_validator("code")
    @classmethod
    def _code_is_known(cls, value: str) -> str:
        if value != "none":
            error_type = "unknown_code"
            message_template = "The code {code} is not known"
            raise PydanticCustomError(error_type, message_template, {"code": value})
        return value

    @field_validator("severity", mode="before")
    @classmethod
    def _severity_is_spelt_out(cls, value: object) -> object:
        if isinstance(value, str) and not value.isdigit():
            # A custom error borrowing a built-in type's name, with a message of its own that quotes the input.
            error_type = "int_parsing"
            message_template = "Severity {severity} is not a number"
            raise PydanticCustomError(error_type, message_template, {"severity": value})
        return value


class _Review(BaseModel):
    note: str

    @model_validator(mode="after")
    def _note_is_signed(self) -> _Review:
        assert self.note.endswith("-- signed"), f"unsigned note {self.note!r}"
        return self


class _Letter(BaseModel):
    kind: Literal["letter"]


class _Parcel(BaseModel):
    kind: Literal["parcel"]


class _Shipment(BaseModel):
    item: Annotated[_Letter | _Parcel, Field(discriminator="kind")]


class _Record(BaseModel):
    record_id: uuid.UUID


class _Limits(BaseModel):
    model_config = ConfigDict(extra="forbid")

    burst: int = 1


class _StrictSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    limits: _Limits = Field(default_factory=_Limits)


class _Bounded(BaseModel):
    code: Annotated[str, Field(max_length=8)]


class TestLogErrorFields:
    @pytest.mark.parametrize(
        ("topic", "exc", "text", "expected"),
        [
            ("the exception's own text", _ManifestParseError("line 3: expected a table"), None, ("_ManifestParseError", "line 3: expected a table")),
            (
                "the cause chain instead",
                KeyError("dep"),
                "dep: not found; git: repository not found",
                ("KeyError", "dep: not found; git: repository not found"),
            ),
            ("an exception with no text", RuntimeError(), None, ("RuntimeError", "")),
        ],
    )
    def test_the_fields_name_the_class_and_carry_the_text(self, topic: str, exc: BaseException, text: str | None, expected: tuple[str, str]) -> None:
        assert error_fields(exc=exc, text=text) == {ERROR_TYPE_FIELD: expected[0], ERROR_MESSAGE_FIELD: expected[1]}, topic

    def test_a_validation_error_is_written_as_its_locations_and_reasons_never_its_input(self) -> None:
        """A pydantic error's own text quotes every value it refused, which is payload: a run's input or a model's response."""
        secret_looking = "sk-live-4f9a8b7c6d5e4f3a2b1c"
        with pytest.raises(ValidationError) as caught:
            _Settings.model_validate({"retries": secret_looking, "limits": {"burst": secret_looking}})
        assert secret_looking in str(caught.value)

        fields = error_fields(exc=caught.value)

        assert fields == {
            ERROR_TYPE_FIELD: "ValidationError",
            ERROR_MESSAGE_FIELD: (
                "retries: Input should be a valid integer, unable to parse string as an integer; "
                "limits.burst: Input should be a valid integer, unable to parse string as an integer"
            ),
        }
        assert secret_looking not in fields[ERROR_MESSAGE_FIELD]

    def test_a_validation_error_at_the_root_names_its_reason_alone(self) -> None:
        with pytest.raises(ValidationError) as caught:
            _Retries.model_validate("sk-live-4f9a8b7c6d5e4f3a2b1c")

        assert error_fields(exc=caught.value)[ERROR_MESSAGE_FIELD] == "Input should be a valid integer, unable to parse string as an integer"

    @pytest.mark.parametrize(
        ("topic", "document", "expected"),
        [
            ("a field validator's ValueError", {"diagnosis": _PAYLOAD}, "diagnosis: value_error"),
            ("a PydanticCustomError of its own type", {"diagnosis": "ICD-10", "code": _PAYLOAD}, "code: unknown_code"),
            ("a PydanticCustomError borrowing a built-in type's name", {"diagnosis": "ICD-10", "severity": _PAYLOAD}, "severity: int_parsing"),
        ],
    )
    def test_a_custom_validator_message_is_written_as_its_type_never_its_text(self, topic: str, document: dict[str, object], expected: str) -> None:
        """A validator writes its own message, and a message can quote the very value the validator rejected."""
        with pytest.raises(ValidationError) as caught:
            _Diagnosis.model_validate(document)
        assert _PAYLOAD in str(caught.value), topic

        message = error_fields(exc=caught.value)[ERROR_MESSAGE_FIELD]

        assert message == expected, topic
        assert _PAYLOAD not in message, topic

    def test_a_model_validator_assertion_has_no_location_and_is_written_as_its_type(self) -> None:
        with pytest.raises(ValidationError) as caught:
            _Review.model_validate({"note": _PAYLOAD})
        assert _PAYLOAD in str(caught.value)

        assert error_fields(exc=caught.value)[ERROR_MESSAGE_FIELD] == "assertion_error"

    def test_a_date_content_rejection_is_written_without_the_value_it_quotes(self) -> None:
        """`DateContent`'s validator names the string it could not read as a date, which can be a run's input."""
        with pytest.raises(ValidationError) as caught:
            DateContent.model_validate({"date": _PAYLOAD})
        assert _PAYLOAD in caught.value.errors()[0]["msg"]

        assert error_fields(exc=caught.value) == {ERROR_TYPE_FIELD: "ValidationError", ERROR_MESSAGE_FIELD: "date: value_error"}

    def test_pydantic_own_reasons_are_kept_beside_a_custom_one(self) -> None:
        """Only the validator's message goes: the reasons pydantic wrote itself, which quote no input, stay readable."""
        with pytest.raises(ValidationError) as mixed:
            _Diagnosis.model_validate({"diagnosis": _PAYLOAD, "reviewed": "not a boolean"})

        assert error_fields(exc=mixed.value)[ERROR_MESSAGE_FIELD] == (
            "diagnosis: value_error; reviewed: Input should be a valid boolean, unable to interpret input"
        )

    @pytest.mark.parametrize(
        ("topic", "model", "document", "input_echo", "expected"),
        [
            ("an unknown tag of a discriminated union", _Shipment, {"item": {"kind": _PAYLOAD}}, _PAYLOAD, "item: union_tag_invalid"),
            ("a value that is no UUID", _Record, {"record_id": _PAYLOAD}, "found `o`", "record_id: uuid_parsing"),
            ("a key a nested model forbids", _StrictSettings, {"limits": {_PAYLOAD: 1}}, None, "limits: Extra inputs are not permitted"),
            ("a key the root model forbids", _StrictSettings, {_PAYLOAD: 1}, None, "Extra inputs are not permitted"),
        ],
    )
    def test_a_message_or_a_location_drawn_from_the_input_never_reaches_the_line(
        self,
        json_buffer: tuple[Log, io.StringIO],
        topic: str,
        model: type[BaseModel],
        document: dict[str, object],
        input_echo: str | None,
        expected: str,
    ) -> None:
        """Some of pydantic's own templates quote the input, and a forbidden key's location is the caller's key itself."""
        with pytest.raises(ValidationError) as caught:
            model.model_validate(document)
        (error,) = caught.value.errors(include_url=False, include_input=False)
        if input_echo is not None:
            assert input_echo in error["msg"], topic
        else:
            assert _PAYLOAD in [str(part) for part in error["loc"]], topic

        fields = error_fields(exc=caught.value)
        fresh, buffer = json_buffer
        fresh.warning("A document was refused", fields=fields)

        assert fields[ERROR_MESSAGE_FIELD] == expected, topic
        own_lines = [line for line in buffer.getvalue().splitlines() if line and json.loads(line)[LOGGER_KEY] == __name__]
        assert len(own_lines) == 1, topic
        assert json.loads(own_lines[0])[ERROR_MESSAGE_FIELD] == expected, topic
        assert _PAYLOAD not in own_lines[0], topic

    def test_a_bounded_value_keeps_pydantic_s_message_whose_bound_comes_from_the_schema(self) -> None:
        with pytest.raises(ValidationError) as caught:
            _Bounded.model_validate({"code": _PAYLOAD})

        assert error_fields(exc=caught.value)[ERROR_MESSAGE_FIELD] == "code: String should have at most 8 characters"

    def test_a_text_given_for_a_validation_error_is_carried_as_given(self) -> None:
        with pytest.raises(ValidationError) as caught:
            _Retries.model_validate("not a number")

        assert error_fields(exc=caught.value, text="line 3: invalid JSON")[ERROR_MESSAGE_FIELD] == "line 3: invalid JSON"

    @pytest.fixture
    def json_buffer(self, caplog: pytest.LogCaptureFixture) -> Iterator[tuple[Log, io.StringIO]]:
        """A fresh ``Log`` with the json sink installed on a buffer, torn down so the root logger is left as found."""
        caplog.set_level(logging.INFO, logger=__name__)
        config_dict = load_toml_from_path(ConfigLoader().pipelex_root_dir / "pipelex.toml")
        buffer = io.StringIO()
        fresh = Log()
        fresh.configure(log_config=LogConfig.model_validate(config_dict["runtime"]["log"]))
        fresh.install_sink(JsonLogSink(stream=buffer))
        try:
            yield fresh, buffer
        finally:
            fresh.reset()

    def test_a_handled_exception_reaches_a_structured_sink_as_two_keys_and_no_traceback(self, json_buffer: tuple[Log, io.StringIO]) -> None:
        """The dotted names are nobody's attribute, so they land unprefixed, and a warning carries no exception."""
        fresh, buffer = json_buffer
        error_text = "line 3: expected a table"
        try:
            raise _ManifestParseError(error_text)
        except _ManifestParseError as exc:
            fresh.warning("The package's METHODS.toml could not be parsed", fields=error_fields(exc=exc))
        lines = [json.loads(line) for line in buffer.getvalue().splitlines() if line]
        own_lines = [line for line in lines if line[LOGGER_KEY] == __name__]
        assert len(own_lines) == 1
        assert own_lines[0][MESSAGE_KEY] == "The package's METHODS.toml could not be parsed"
        assert own_lines[0][ERROR_TYPE_FIELD] == "_ManifestParseError"
        assert own_lines[0][ERROR_MESSAGE_FIELD] == "line 3: expected a table"
        assert EXCEPTION_KEY not in own_lines[0]
