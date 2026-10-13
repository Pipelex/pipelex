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


class TraceContextRunModeError(ValueError):
    """A kernel run was handed a trace context stating a run mode other than the one the run takes.

    Every trace event of a run states the mode its steps run in, and the usage events of a kernel run state the mode
    of the trace context its caller supplied. The caller opened that trace, and may share it with writers the kernel
    never sees, so the kernel cannot correct it: it refuses the context before any step runs, rather than let the run
    write events that say live while its steps run dry, as a keyless boot forces them to. The mode a run takes is the
    one `resolve_effective_run_mode` returns, which is what the caller states on the context. A `ValueError`, as the
    other refusals of `PipelexKernel.make` are: the caller handed the kernel a value it cannot work with.
    """
