from mthds.protocol.problem.registry import CoreCode

from pipelex.base_exceptions import PipelexError
from pipelex.errors.error_code_declaration import ErrorCodeSet


class PromptContentError(PipelexError):
    """A prompt's image or document reference could not be resolved out of working memory.

    ``runtime.unexpected`` when the reference names nothing the context holds, which load-time validation and the
    entry checks guarantee against, and ``method.wiring_invalid``, chosen by its raise site, when the wired value is
    not the content type the prompt reads.
    """

    error_code = ErrorCodeSet(default=CoreCode.RUNTIME_UNEXPECTED, others=(CoreCode.METHOD_WIRING_INVALID,))


class JudgmentOutputFieldsError(PipelexError):
    """A judgment asking several questions was handed an output class whose fields are not exactly its questions' names.

    Each question's verdict fills the field of its name, so a question with no field would be answered for
    nothing and a field no question answers could never be filled. A `PipeJudge` has its output checked
    against its questions when its method loads, so this is a programmatic caller's contract broken, and
    it is raised before the judging model is called.
    """

    error_code = CoreCode.RUNTIME_UNEXPECTED


class TraceContextRunModeError(PipelexError):
    """A kernel run was handed a trace context stating a run mode other than the one the run takes.

    Every trace event of a run states the mode its steps run in, and the usage events of a kernel run state the mode
    of the trace context its caller supplied. The caller opened that trace, and may share it with writers the kernel
    never sees, so the kernel cannot correct it: it refuses the context before any step runs, rather than let the run
    write events that say live while its steps run dry, as a keyless boot forces them to. The mode a run takes is the
    one `resolve_effective_run_mode` returns, which is what the caller states on the context. Our own host
    integration is that caller, so the refusal is an invariant of ours.
    """

    error_code = CoreCode.RUNTIME_UNEXPECTED


class FuncOutputTypeError(PipelexError):
    """A registered function returned a value that is neither a stuff content, a list nor a string.

    The function is the method's, so the step's output is what failed, not the runtime.
    """

    error_code = CoreCode.PIPE_OUTPUT_INVALID
