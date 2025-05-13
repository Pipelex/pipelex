# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from pipelex.tools.exceptions import FatalError, RootException


class ConfigValidationError(FatalError):
    pass


class ConfigNotFoundError(RootException):
    pass


class LLMPresetNotFoundError(ConfigNotFoundError):
    pass


class LLMSettingsValidationError(ConfigValidationError):
    pass


class LLMDeckValidatonError(ConfigValidationError):
    pass


class LLMHandleNotFoundError(ConfigNotFoundError):
    pass


class ConfigModelError(ValueError, FatalError):
    pass
