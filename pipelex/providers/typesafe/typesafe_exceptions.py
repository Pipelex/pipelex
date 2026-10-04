from pipelex.cogt.exceptions import CogtError


class TypesafeError(CogtError):
    """Base for every error this backend raises, so callers can catch the provider as a family."""


class TypesafeJudgmentResponseError(TypesafeError):
    """The TypeSafe API answered a judgment with an answer that is missing, or of the wrong kind.

    The worker asks a named question of a known kind and reads the answer back under the same
    name; an answer that is absent, or that came back as a choice where a rating was asked for,
    cannot be translated at all. The family's own guard in ``JudgmentWorkerAbstract`` catches the
    same two mistakes one layer up, but only after translation has already had to produce
    something — so this is where the wrong shape actually stops.
    """


class TypesafeQuestionUnsupportedError(TypesafeError):
    """The question is legal MTHDS that this backend will not serve.

    The vendor's own bounds, not the language's: a rating scale longer than this backend answers.
    Enforcing it here rather than in the blueprint is deliberate — a method that exceeds it stays
    valid and a different judgment backend may well accept it.
    """
