from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from pipelex import pretty_print
from pipelex.core.stuffs.number_content import NumberContent
from pipelex.core.stuffs.text_content import TextContent
from pipelex.pipeline.bundle_validator import DryRunStatus
from pipelex.pipeline.runner import PipelexMTHDSProtocol
from pipelex.pipeline.validate_bundle import validate_bundle
from pipelex.system.pipe_run_mode import PipeRunMode

_FIXTURE_DIR = Path(__file__).parent / "fixtures" / "compose_whole_stuff"
_BUNDLE = _FIXTURE_DIR / "compose_whole_stuff.mthds"


@pytest.mark.asyncio(loop_scope="class")
class TestPipeComposeWholeStuffConstruct:
    """PipeCompose construct `{ from = "<stuff_name>" }` must copy a whole native stuff into a native-typed target field.

    The documented contract (PipeCompose reference, "Copy value from input variable or nested field") is that
    referencing a whole input stuff converts its content wrapper to the target field's native type:
    TextContent -> str, ListContent[TextContent] -> list[str], NumberContent -> float. This must hold for
    required AND optional (non-required, hence Optional[...]-annotated) target fields, both at the dry-run
    runnable gate and in live execution.
    """

    async def test_validate_bundle_dry_run_passes(self) -> None:
        """The whole-stuff construct bundle must pass the runnable gate: dry-run success on every pipe."""
        result = await validate_bundle(mthds_file_path=_BUNDLE)
        assert result.pending_signatures == []
        for pipe_ref, dry_run_output in result.dry_run_result.items():
            assert dry_run_output.status is DryRunStatus.SUCCESS, f"dry-run failed for '{pipe_ref}': {dry_run_output.error_message}"

    @pytest.mark.parametrize(
        ("pipe_code", "inputs", "field_name", "expected_value"),
        [
            pytest.param(
                "fill_required_text",
                {"text_input": TextContent(text="Alpha title")},
                "title",
                "Alpha title",
                id="whole_text_to_required_text_field",
            ),
            pytest.param(
                "fill_optional_text",
                {"text_input": TextContent(text="Sorry, not this time")},
                "note",
                "Sorry, not this time",
                id="whole_text_to_optional_text_field",
            ),
            pytest.param(
                "fill_required_text_list",
                {"texts_input": [TextContent(text="alpha"), TextContent(text="bravo"), TextContent(text="charlie")]},
                "tags",
                ["alpha", "bravo", "charlie"],
                id="whole_text_list_to_required_list_field",
            ),
            pytest.param(
                "fill_optional_text_list",
                {"texts_input": [TextContent(text="alpha"), TextContent(text="bravo"), TextContent(text="charlie")]},
                "tags",
                ["alpha", "bravo", "charlie"],
                id="whole_text_list_to_optional_list_field",
            ),
            pytest.param(
                "fill_required_number",
                {"number_input": NumberContent(number=42.5)},
                "score",
                42.5,
                id="whole_number_to_required_number_field",
            ),
        ],
    )
    async def test_live_compose_whole_stuff_into_native_field(
        self,
        pipe_code: str,
        inputs: dict[str, Any],
        field_name: str,
        expected_value: Any,
    ) -> None:
        """Live-run each compose pipe with real inputs and check the composed native field value."""
        runner = PipelexMTHDSProtocol(
            library_dirs=[str(_FIXTURE_DIR)],
            pipe_run_mode=PipeRunMode.LIVE,
        )
        response = await runner.execute(pipe_code=pipe_code, inputs=inputs)
        main_stuff = response.pipe_output.main_stuff
        assert main_stuff is not None
        pretty_print(main_stuff.content, title=f"Composed output of '{pipe_code}'")

        composed_value = getattr(main_stuff.content, field_name)
        assert composed_value == expected_value
        assert type(composed_value) is type(expected_value)
