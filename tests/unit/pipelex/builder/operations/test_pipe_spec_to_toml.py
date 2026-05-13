"""Unit tests for pipe_spec_to_toml from pipelex.builder.operations.pipe_ops."""

from __future__ import annotations

from pipelex.builder.operations.pipe_ops import parse_pipe_spec, pipe_spec_to_toml
from tests.unit.pipelex.builder.operations.test_data import PipeOpsTestData

_BASE_LLM = PipeOpsTestData.BASE_LLM_SPEC


class TestPipeSpecToToml:
    """Comprehensive tests for pipe_spec_to_toml covering all pipe types."""

    # -- PipeLLM ----------------------------------------------------------

    def test_llm_basic_structure(self) -> None:
        spec = parse_pipe_spec("PipeLLM", {**_BASE_LLM})
        toml = pipe_spec_to_toml(spec)
        assert "[pipe.test_pipe]" in toml
        assert 'type = "PipeLLM"' in toml
        assert 'description = "Test LLM pipe"' in toml
        assert 'output = "Text"' in toml

    def test_llm_inputs_as_inline_table(self) -> None:
        spec = parse_pipe_spec("PipeLLM", {**_BASE_LLM})
        toml = pipe_spec_to_toml(spec)
        assert 'inputs = {text = "Text"}' in toml

    def test_llm_model_in_toml(self) -> None:
        spec = parse_pipe_spec("PipeLLM", {**_BASE_LLM})
        toml = pipe_spec_to_toml(spec)
        assert 'model = "$writing-creative"' in toml

    def test_llm_no_model_omits_field(self) -> None:
        data = {key: val for key, val in _BASE_LLM.items() if key != "model"}
        spec = parse_pipe_spec("PipeLLM", data)
        toml = pipe_spec_to_toml(spec)
        assert "model" not in toml

    def test_llm_system_prompt_in_toml(self) -> None:
        spec = parse_pipe_spec("PipeLLM", {**_BASE_LLM, "system_prompt": "You are a helpful writer."})
        toml = pipe_spec_to_toml(spec)
        assert "system_prompt" in toml
        assert "You are a helpful writer." in toml

    def test_llm_prompt_in_toml(self) -> None:
        spec = parse_pipe_spec("PipeLLM", {**_BASE_LLM})
        toml = pipe_spec_to_toml(spec)
        assert "prompt" in toml
        assert "Write about $text" in toml

    def test_llm_no_inputs_omits_inputs(self) -> None:
        empty_inputs: dict[str, str] = {}
        data = {**_BASE_LLM, "inputs": empty_inputs}
        spec = parse_pipe_spec("PipeLLM", data)
        toml = pipe_spec_to_toml(spec)
        assert "inputs" not in toml

    def test_llm_multiple_inputs(self) -> None:
        data = {**_BASE_LLM, "inputs": {"text": "Text", "context": "Document"}}
        spec = parse_pipe_spec("PipeLLM", data)
        toml = pipe_spec_to_toml(spec)
        assert 'text = "Text"' in toml
        assert 'context = "Document"' in toml

    # -- PipeFunc ---------------------------------------------------------

    def test_func_function_name_in_toml(self) -> None:
        spec = parse_pipe_spec(
            "PipeFunc",
            {"pipe_code": "my_func", "description": "Run a function", "inputs": {"data": "Text"}, "output": "Text", "function_name": "process_data"},
        )
        toml = pipe_spec_to_toml(spec)
        assert 'function_name = "process_data"' in toml
        assert 'type = "PipeFunc"' in toml

    # -- PipeImgGen -------------------------------------------------------

    def test_img_gen_model_and_prompt_in_toml(self) -> None:
        spec = parse_pipe_spec(
            "PipeImgGen",
            {
                "pipe_code": "gen_image",
                "description": "Generate image",
                "inputs": {"prompt_text": "ImgGenPrompt"},
                "output": "Image",
                "model": "$gen-image",
                "prompt": "Generate: $prompt_text",
            },
        )
        toml = pipe_spec_to_toml(spec)
        assert 'model = "$gen-image"' in toml
        assert "Generate: $prompt_text" in toml

    def test_img_gen_no_model_omits_field(self) -> None:
        spec = parse_pipe_spec(
            "PipeImgGen",
            {
                "pipe_code": "gen_image",
                "description": "Generate image",
                "inputs": {"prompt_text": "ImgGenPrompt"},
                "output": "Image",
                "prompt": "Generate: $prompt_text",
            },
        )
        toml = pipe_spec_to_toml(spec)
        assert "model" not in toml

    # -- PipeExtract ------------------------------------------------------

    def test_extract_model_in_toml(self) -> None:
        spec = parse_pipe_spec(
            "PipeExtract",
            {
                "pipe_code": "my_extract",
                "description": "Extract text",
                "inputs": {"doc": "Document"},
                "output": "Page[]",
                "model": "@default-extract-document",
            },
        )
        toml = pipe_spec_to_toml(spec)
        assert 'model = "@default-extract-document"' in toml

    def test_extract_max_page_images_in_toml(self) -> None:
        spec = parse_pipe_spec(
            "PipeExtract",
            {
                "pipe_code": "my_extract",
                "description": "Extract text",
                "inputs": {"doc": "Document"},
                "output": "Page[]",
                "max_page_images": 5,
            },
        )
        toml = pipe_spec_to_toml(spec)
        assert "max_page_images = 5" in toml

    def test_extract_page_views_in_toml(self) -> None:
        spec = parse_pipe_spec(
            "PipeExtract",
            {
                "pipe_code": "my_extract",
                "description": "Extract text",
                "inputs": {"doc": "Document"},
                "output": "Page[]",
                "page_views": True,
            },
        )
        toml = pipe_spec_to_toml(spec)
        assert "page_views = true" in toml

    def test_extract_no_optional_fields_omits_them(self) -> None:
        spec = parse_pipe_spec(
            "PipeExtract",
            {"pipe_code": "my_extract", "description": "Extract text", "inputs": {"doc": "Document"}, "output": "Page[]"},
        )
        toml = pipe_spec_to_toml(spec)
        assert "model" not in toml
        assert "max_page_images" not in toml
        assert "page_views" not in toml

    # -- PipeSearch -------------------------------------------------------

    def test_search_all_fields_in_toml(self) -> None:
        spec = parse_pipe_spec(
            "PipeSearch",
            {
                "pipe_code": "web_search",
                "description": "Search the web",
                "inputs": {"query_text": "Text"},
                "output": "Text",
                "model": "$search-model",
                "prompt": "Search for $query_text",
                "from_date": "2024-01-01",
                "to_date": "2024-12-31",
                "include_domains": ["example.com", "docs.example.com"],
                "exclude_domains": ["spam.com"],
                "max_results": 10,
            },
        )
        toml = pipe_spec_to_toml(spec)
        assert 'model = "$search-model"' in toml
        assert "Search for $query_text" in toml
        assert 'from_date = "2024-01-01"' in toml
        assert 'to_date = "2024-12-31"' in toml
        assert "example.com" in toml
        assert "spam.com" in toml
        assert "max_results = 10" in toml

    def test_search_minimal(self) -> None:
        spec = parse_pipe_spec(
            "PipeSearch",
            {"pipe_code": "web_search", "description": "Search", "inputs": {"query_text": "Text"}, "output": "Text", "prompt": "Find $query_text"},
        )
        toml = pipe_spec_to_toml(spec)
        assert "Find $query_text" in toml
        assert "from_date" not in toml
        assert "to_date" not in toml
        assert "include_domains" not in toml
        assert "exclude_domains" not in toml
        assert "max_results" not in toml
        assert "model" not in toml

    # -- PipeSequence -----------------------------------------------------

    def test_sequence_steps_in_toml(self) -> None:
        spec = parse_pipe_spec(
            "PipeSequence",
            {
                "pipe_code": "my_seq",
                "description": "A sequence",
                "inputs": {"doc": "Document"},
                "output": "Text",
                "steps": [
                    {"pipe_code": "step_one", "result": "intermediate"},
                    {"pipe_code": "step_two", "result": "final"},
                ],
            },
        )
        toml = pipe_spec_to_toml(spec)
        assert 'type = "PipeSequence"' in toml
        assert "step_one" in toml
        assert "step_two" in toml
        assert "intermediate" in toml
        assert "final" in toml

    def test_sequence_step_with_batch_over(self) -> None:
        spec = parse_pipe_spec(
            "PipeSequence",
            {
                "pipe_code": "my_seq",
                "description": "A sequence with batch",
                "inputs": {"items": "Text[]"},
                "output": "Text[]",
                "steps": [
                    {"pipe_code": "process", "result": "processed", "batch_over": "items", "batch_as": "item"},
                ],
            },
        )
        toml = pipe_spec_to_toml(spec)
        assert "batch_over" in toml
        assert "batch_as" in toml
        assert "items" in toml

    # -- PipeParallel -----------------------------------------------------

    def test_parallel_branches_and_add_each_output(self) -> None:
        spec = parse_pipe_spec(
            "PipeParallel",
            {
                "pipe_code": "my_par",
                "description": "Parallel branches",
                "inputs": {"doc": "Document"},
                "output": "Text",
                "add_each_output": True,
                "branches": [
                    {"pipe_code": "branch_a", "result": "result_a"},
                    {"pipe_code": "branch_b", "result": "result_b"},
                ],
            },
        )
        toml = pipe_spec_to_toml(spec)
        assert 'type = "PipeParallel"' in toml
        assert "add_each_output = true" in toml
        assert "branch_a" in toml
        assert "branch_b" in toml

    def test_parallel_combined_output_in_toml(self) -> None:
        spec = parse_pipe_spec(
            "PipeParallel",
            {
                "pipe_code": "my_par",
                "description": "Parallel with combined output",
                "inputs": {"doc": "Document"},
                "output": "Text",
                "add_each_output": False,
                "combined_output": "MergedResult",
                "branches": [
                    {"pipe_code": "branch_a", "result": "result_a"},
                ],
            },
        )
        toml = pipe_spec_to_toml(spec)
        assert 'combined_output = "MergedResult"' in toml

    # -- PipeCondition ----------------------------------------------------

    def test_condition_expression_outcomes_default(self) -> None:
        spec = parse_pipe_spec(
            "PipeCondition",
            {
                "pipe_code": "my_cond",
                "description": "Route by status",
                "inputs": {"status": "Text"},
                "output": "Text",
                "jinja2_expression_template": "{{ status }}",
                "outcomes": {"high": "handle_high", "low": "handle_low"},
                "default_outcome": "handle_default",
            },
        )
        toml = pipe_spec_to_toml(spec)
        assert 'type = "PipeCondition"' in toml
        assert "{{ status }}" in toml
        assert "handle_high" in toml
        assert "handle_low" in toml
        assert 'default_outcome = "handle_default"' in toml

    # -- PipeBatch --------------------------------------------------------

    def test_batch_fields_in_toml(self) -> None:
        spec = parse_pipe_spec(
            "PipeBatch",
            {
                "pipe_code": "my_batch",
                "description": "Batch process",
                "inputs": {"items": "Text[]"},
                "output": "Text[]",
                "branch_pipe_code": "process_one",
                "input_list_name": "items",
                "input_item_name": "item",
            },
        )
        toml = pipe_spec_to_toml(spec)
        assert 'type = "PipeBatch"' in toml
        assert 'branch_pipe_code = "process_one"' in toml
        assert 'input_list_name = "items"' in toml
        assert 'input_item_name = "item"' in toml

    # -- PipeCompose (template mode) --------------------------------------

    def test_compose_template_mode_fields(self) -> None:
        spec = parse_pipe_spec(
            "PipeCompose",
            {
                "pipe_code": "render_greeting",
                "description": "Render a greeting",
                "inputs": {"name": "native.Text"},
                "output": "native.Text",
                "target_format": "markdown",
                "template": "Hello $name!",
            },
        )
        toml = pipe_spec_to_toml(spec)
        assert 'type = "PipeCompose"' in toml
        assert 'target_format = "markdown"' in toml
        assert 'template = "Hello $name!"' in toml

    def test_compose_no_construct_in_template_mode(self) -> None:
        spec = parse_pipe_spec(
            "PipeCompose",
            {
                "pipe_code": "render_greeting",
                "description": "Render a greeting",
                "inputs": {"name": "native.Text"},
                "output": "native.Text",
                "target_format": "markdown",
                "template": "Hello $name!",
            },
        )
        toml = pipe_spec_to_toml(spec)
        assert "construct" not in toml

    # -- PipeCompose (construct mode) -------------------------------------

    def test_compose_construct_with_from_mappings(self) -> None:
        spec = parse_pipe_spec(
            "PipeCompose",
            {
                "pipe_code": "compose_sheet",
                "description": "Compose interview sheet",
                "inputs": {"analysis": "MatchAnalysis", "questions": "InterviewQuestion[]"},
                "output": "InterviewSheet",
                "construct": {
                    "score": {"from": "analysis.overall_score"},
                    "questions": {"from": "questions"},
                },
            },
        )
        toml = pipe_spec_to_toml(spec)
        assert "[pipe.compose_sheet.construct]" in toml
        assert 'score = {from = "analysis.overall_score"}' in toml

    def test_compose_construct_with_static_values(self) -> None:
        spec = parse_pipe_spec(
            "PipeCompose",
            {
                "pipe_code": "compose_report",
                "description": "Compose a report",
                "inputs": {"title": "native.Text"},
                "output": "Report",
                "construct": {
                    "title": {"from": "title"},
                    "version": "1.0",
                    "page_count": 42,
                },
            },
        )
        toml = pipe_spec_to_toml(spec)
        assert 'version = "1.0"' in toml
        assert "page_count = 42" in toml

    def test_compose_no_template_in_construct_mode(self) -> None:
        spec = parse_pipe_spec(
            "PipeCompose",
            {
                "pipe_code": "compose_report",
                "description": "Compose a report",
                "inputs": {"title": "native.Text"},
                "output": "Report",
                "construct": {"title": {"from": "title"}},
            },
        )
        toml = pipe_spec_to_toml(spec)
        assert "target_format" not in toml
        assert "template" not in toml
