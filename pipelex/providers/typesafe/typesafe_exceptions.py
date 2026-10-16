from typing import ClassVar

from mthds.protocol.problem.registry import CoreCode

from pipelex.cogt.exceptions import CogtError
from pipelex.errors.error_code_declaration import ErrorCodeDeclaration, ErrorCodeSet
from pipelex.errors.registry.pipelex_codes import PipelexErrorCode


class TypesafeError(CogtError):
    """Base for every error this backend raises, so callers can catch the provider as a family.

    Raised itself for a backend with no API key, which is the deployment's missing credential.
    """

    error_code: ClassVar[ErrorCodeDeclaration] = PipelexErrorCode.CONFIG_CREDENTIAL_MISSING


class TypesafeJudgmentResponseError(TypesafeError):
    """The TypeSafe API answered a judgment with an answer that is missing, or of the wrong kind.

    The worker asks a named question of a known kind and reads the answer back under the same
    name; an answer that is absent, or that came back as a choice where a rating was asked for,
    cannot be translated at all. The family's own guard in ``JudgmentWorkerAbstract`` catches the
    same two mistakes one layer up, but only after translation has already had to produce
    something — so this is where the wrong shape actually stops.
    """

    error_code = CoreCode.PROVIDER_RESPONSE_INVALID


class TypesafeQuestionUnsupportedError(TypesafeError):
    """The question is legal MTHDS that this backend will not serve.

    The vendor's own bounds, not the language's: a rating scale longer than this backend answers.
    Enforcing it here rather than in the blueprint is deliberate — a method that exceeds it stays
    valid and a different judgment backend may well accept it. The scale is written in the method, so it is
    ``model.capability_unsupported``; a rating level with neither a label nor a description, which the blueprint
    already refuses, is ``runtime.unexpected``, which its raise site chooses.
    """

    error_code = ErrorCodeSet(default=CoreCode.MODEL_CAPABILITY_UNSUPPORTED, others=(CoreCode.RUNTIME_UNEXPECTED,))
