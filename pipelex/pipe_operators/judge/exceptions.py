from pipelex.base_exceptions import ErrorDomain, PipelexError


class PipeJudgeFactoryError(PipelexError):
    pass


class PipeJudgeError(PipelexError):
    pass


class PipeJudgeInputCapabilityError(PipeJudgeError):
    """A `PipeJudge` declares an image or a document input, and the judging model it resolves to does not read one.

    Raised when the method loads, before a run spends anything. The operator does not refuse files: the
    model's spec states what it reads, so a model that reads files gets them, and this refusal names the
    input and what the model reads. Its message names only the step, the input, the model and its
    declared inputs, so it is kept verbatim for the caller.
    """

    error_domain = ErrorDomain.INPUT
    _authors_caller_facing_message = True

    def __init__(self, *, pipe_code: str, input_name: str, file_kind: str, model_name: str, model_inputs: list[str]):
        self.pipe_code = pipe_code
        self.input_name = input_name
        self.file_kind = file_kind
        self.model_name = model_name
        self.model_inputs = model_inputs
        message = (
            f"PipeJudge '{pipe_code}' judges input '{input_name}', which is {_with_article(file_kind)}, and its judgment model "
            f"'{model_name}' does not read {file_kind}s: it reads {', '.join(model_inputs)}. Name a judgment model that reads "
            f"{file_kind}s, or turn the {file_kind} into text with a step before this one."
        )
        super().__init__(message)


def _with_article(noun: str) -> str:
    return f"an {noun}" if noun[0] in "aeiou" else f"a {noun}"
