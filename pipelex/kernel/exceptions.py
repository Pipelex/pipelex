class PromptContentError(ValueError):
    """A prompt's image or document reference could not be resolved out of working memory.

    A `ValueError` rather than a `PipelexError` subclass, matching what the prompt-assembly code
    raised before it moved into the kernel: callers that already handle it as a value error keep
    working, and nothing in the error taxonomy changes.
    """


class JudgmentOutputFieldsError(ValueError):
    """A judgment asking several questions was handed an output class whose fields are not exactly its questions' names.

    Each question's verdict fills the field of its name, so a question with no field would be answered for
    nothing and a field no question answers could never be filled. A `PipeJudge` has its output checked
    against its questions when its method loads, so this is a programmatic caller's contract broken, and
    it is raised before the judging model is called. A `ValueError`, as `PromptContentError` is: the
    caller handed the kernel a value it cannot work with.
    """
