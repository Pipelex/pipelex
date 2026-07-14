from pipelex.core.pipes.exceptions import PipeValidationError, PipeValidationErrorType
from pipelex.core.pipes.handle_pipe_errors import categorize_pipe_validation_with_libraries_error


class TestRequiredProvidedSuffix:
    """The ``(required: …, provided: …)`` suffix the pipe categorizer appends to the message.

    Two rules: it is suppressed entirely for multiplicity errors (identical concept on both sides
    by definition), and for the cases where it stays the required refs render as joined author-syntax
    refs — never a Python ``['x']`` list repr whose brackets masquerade as ``[]`` multiplicity syntax.
    """

    def test_multiplicity_error_suppresses_the_suffix(self) -> None:
        base_message = "output multiplicity mismatch: 'brainstorm' declares 'StoryIdea' but yields 'StoryIdea[]'."
        pipe_error = PipeValidationError(
            message=base_message,
            error_type=PipeValidationErrorType.INADEQUATE_OUTPUT_MULTIPLICITY,
            domain_code="story_studio",
            pipe_code="brainstorm",
            required_concept_codes=["story_studio.StoryIdea"],
            provided_concept_code="story_studio.StoryIdea",
        )

        error_data = categorize_pipe_validation_with_libraries_error(pipe_error)

        # Equality proves no suffix was appended (the base message already speaks author syntax,
        # `StoryIdea` vs `StoryIdea[]`, so its own `[]` is the legitimate multiplicity marker).
        assert error_data.message == base_message
        assert "required:" not in error_data.message
        assert "provided:" not in error_data.message

    def test_concept_error_renders_author_syntax_suffix(self) -> None:
        pipe_error = PipeValidationError(
            message="PipeSequence concept mismatch",
            error_type=PipeValidationErrorType.INADEQUATE_OUTPUT_CONCEPT,
            domain_code="recipe_maker",
            pipe_code="make_recipe",
            required_concept_codes=["recipe_maker.Recipe"],
            provided_concept_code="recipe_maker.Draft",
        )

        error_data = categorize_pipe_validation_with_libraries_error(pipe_error)

        assert error_data.message == "PipeSequence concept mismatch (required: recipe_maker.Recipe, provided: recipe_maker.Draft)"
        # No Python list repr leaking through.
        assert "['" not in error_data.message
        assert "']" not in error_data.message

    def test_multiple_required_refs_join_without_brackets(self) -> None:
        pipe_error = PipeValidationError(
            message="PipeCompose input mismatch",
            error_type=PipeValidationErrorType.INADEQUATE_OUTPUT_CONCEPT,
            domain_code="doc_shop",
            pipe_code="compose_doc",
            required_concept_codes=["native.Text", "native.Html"],
            provided_concept_code="doc_shop.Draft",
        )

        error_data = categorize_pipe_validation_with_libraries_error(pipe_error)

        assert "(required: native.Text, native.Html, provided: doc_shop.Draft)" in error_data.message
        assert "[" not in error_data.message
