# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from typing import Optional

from pipelex.tools.exceptions import FatalError, RootException


class CogtError(RootException):
    pass


class InferenceManagerWorkerSetupError(CogtError, FatalError):
    pass


class InferenceReportManagerError(CogtError):
    pass


class LLMWorkerError(CogtError):
    pass


class LLMSDKError(CogtError):
    pass


class LLMModelProviderError(CogtError):
    pass


class LLMModelPlatformError(ValueError, CogtError):
    pass


class LLMModelDefinitionError(CogtError):
    pass


class LLMCapabilityError(CogtError):
    pass


class LLMCompletionError(CogtError):
    pass


class LLMAssignmentError(CogtError):
    pass


class LLMPromptFactoryError(CogtError):
    pass


class LLMPromptTemplateInputsError(CogtError):
    pass


class LLMPromptError(CogtError):
    pass


class PromptImageFactoryError(CogtError):
    pass


class PromptImageFormatError(CogtError):
    pass


class ImggPromptError(CogtError):
    pass


class MissingDependencyError(CogtError):
    """Raised when a required dependency is not installed."""

    def __init__(self, dependency_name: str, extra_name: str, message: Optional[str] = None):
        self.dependency_name = dependency_name
        self.extra_name = extra_name
        error_msg = f"Required dependency '{dependency_name}' is not installed."
        if message:
            error_msg += f" {message}"
        error_msg += f" Please install it with 'pip install pipelex[{extra_name}]'."
        super().__init__(error_msg)
