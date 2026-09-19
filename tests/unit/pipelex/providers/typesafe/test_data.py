"""Replay material for the TypeSafe backend, recorded against the live API.

Every file under ``tests/data/typesafe/responses/`` was captured by the campaign's spike and is
kept verbatim. A success is the **wire body**, taken from the raw HTTP response rather than from
the SDK's own dump, so a replay test checks our reading of the API and not the SDK's reading of
itself — which matters here, because a rating answer's keys are strings on the wire and integers
only after the SDK has parsed them. A refusal is saved as an envelope describing the exception,
with the wire body nested under ``body``, and is rebuilt into a real SDK exception below.
"""

import json
import re
from pathlib import Path
from typing import Any, ClassVar, cast

import typesafe_sdk
from httpx2 import Headers
from typesafe_sdk import SystemOneResponse, TypeSafeAPIError, TypeSafeAPITimeoutError, TypeSafeError

RESPONSES_DIR = Path(__file__).parents[4] / "data" / "typesafe" / "responses"


def load_recorded(name: str) -> dict[str, Any]:
    """The recorded JSON document, whether it holds a wire body or an exception envelope."""
    return cast("dict[str, Any]", json.loads((RESPONSES_DIR / f"{name}.json").read_text(encoding="utf-8")))


def load_recorded_response(name: str) -> SystemOneResponse:
    """A recorded success, parsed by the SDK exactly as a live call would parse it.

    From the JSON *text*, not from a decoded dict, and the difference is not cosmetic: a rating's
    ``probabilities`` and ``legend`` are keyed by strings on the wire, and the SDK's models only
    coerce those keys to integers in JSON mode. Validating the decoded dict refuses every rating.
    """
    return SystemOneResponse.model_validate_json((RESPONSES_DIR / f"{name}.json").read_text(encoding="utf-8"))


def rebuild_recorded_exception(name: str) -> BaseException:
    """The SDK exception a recorded refusal produced, rebuilt from its envelope.

    Rebuilt as the real class rather than as a stand-in because the class name is itself part of
    what the classification reads: a bare ``TypeSafeError`` is a different verdict from any of its
    API subclasses, and a stand-in would let that distinction pass untested.
    """
    envelope = load_recorded(name)
    class_name: str = envelope["class"]
    if "status" in envelope:
        api_error_class = cast("type[TypeSafeAPIError]", getattr(typesafe_sdk, class_name))
        return api_error_class(
            status=envelope["status"],
            body=envelope.get("body"),
            headers=Headers(envelope.get("response_headers", {})),
            message=envelope["str"],
            endpoint=envelope.get("endpoint"),
        )
    if class_name == TypeSafeAPITimeoutError.__name__:
        timeout_match = re.search(r"timeout=([0-9.]+)\)", envelope["str"])
        assert timeout_match is not None, f"recorded timeout carries no duration: {envelope['str']!r}"
        return TypeSafeAPITimeoutError(timeout=float(timeout_match.group(1)))
    assert class_name == TypeSafeError.__name__, f"no rebuild rule for recorded class {class_name!r}"
    return TypeSafeError(envelope["str"])


class TestData:
    """The recorded cases each test reads, named by what they demonstrate."""

    # Successes — wire bodies.
    THREE_SHAPES = "01_three_shapes"
    USAGE_ONE_QUESTION = "02_usage_one_question"
    CHOICE_NULL_DESCRIPTIONS = "04_choice_null_descriptions"
    SCORE_TEN_LEVELS = "04_score_ten_levels"

    # Refusals — exception envelopes. The first four are the four verdicts a `400` can mean.
    STATE_TOO_LARGE = "04b_state_200k_chars_error"
    UNKNOWN_MODEL = "05_model_jev_does_not_exist_error"
    MALFORMED_QUESTION = "06_malformed_question"
    TOO_MANY_LEVELS = "04_score_eleven_levels_error"
    WRONG_KEY = "06_wrong_key"
    EMPTY_QUESTIONS = "06_empty_questions"
    TIMEOUT = "06_timeout"

    # The questions `01_three_shapes` was recorded from, spelled exactly as they were sent.
    THREE_SHAPES_INSTRUCTIONS: ClassVar[dict[str, str]] = {
        "is_urgent": "Is the message urgent?",
        "team": "Which team should handle this message?",
        "severity": "How severe is the reported issue?",
    }
