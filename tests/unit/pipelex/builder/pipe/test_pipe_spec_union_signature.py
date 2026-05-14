from pydantic import TypeAdapter

from pipelex.builder.pipe.pipe_llm_spec import PipeLLMSpec
from pipelex.builder.pipe.pipe_signature import PipeSignature
from pipelex.builder.pipe.pipe_spec_union import PipeSpecUnion


class TestPipeSpecUnionDispatch:
    def test_union_dispatches_pipe_signature(self) -> None:
        adapter: TypeAdapter[PipeSpecUnion] = TypeAdapter(PipeSpecUnion)
        result = adapter.validate_python(
            {
                "type": "PipeSignature",
                "pipe_category": "PipeSignature",
                "pipe_code": "sig_dispatch",
                "description": "A signature in the union.",
                "inputs": {"doc": "Document"},
                "output": "Summary",
                "pipe_dependencies": [],
            }
        )
        assert isinstance(result, PipeSignature)

    def test_union_dispatches_pipe_llm_unchanged(self) -> None:
        adapter: TypeAdapter[PipeSpecUnion] = TypeAdapter(PipeSpecUnion)
        result = adapter.validate_python(
            {
                "type": "PipeLLM",
                "pipe_category": "PipeOperator",
                "pipe_code": "llm_pipe",
                "description": "An LLM pipe in the union.",
                "inputs": {"text": "Text"},
                "output": "Text",
                "prompt": "Echo $text",
            }
        )
        assert isinstance(result, PipeLLMSpec)
