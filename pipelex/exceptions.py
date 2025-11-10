from __future__ import annotations

from typing import TYPE_CHECKING

from typing_extensions import override

from pipelex.system.exceptions import RootException

if TYPE_CHECKING:
    from pipelex.cogt.extract.extract_setting import ExtractModelChoice
    from pipelex.cogt.img_gen.img_gen_setting import ImgGenModelChoice
    from pipelex.cogt.llm.llm_setting import LLMModelChoice
    from pipelex.pipe_run.pipe_run_params import PipeRunMode
    from pipelex.cogt.model_backends.model_type import ModelType


class PipelexException(RootException):
    pass


class PipelexUnexpectedError(PipelexException):
    pass


class PipelexConfigError(PipelexException):
    pass


class PipelexSetupError(PipelexException):
    pass


class PipeOperatorModelChoiceError(PipelexException):
    def __init__(
        self,
        message: str,
        pipe_type: str,
        pipe_code: str,
        model_type: ModelType,
        model_choice: LLMModelChoice | ExtractModelChoice | ImgGenModelChoice,
    ):
        self.pipe_type = pipe_type
        self.pipe_code = pipe_code
        self.model_type = model_type
        self.model_choice = model_choice
        super().__init__(message)

    def desc(self) -> str:
        msg = f"{self.message}"
        msg += f" • pipe='{self.pipe_code}' ({self.pipe_type})"
        msg += f" • model_type='{self.model_type}'"

        # Extract the choice identifier from the model_choice union type
        if isinstance(self.model_choice, str):
            # It's a preset/alias string
            msg += f" • choice='{self.model_choice}'"
        else:
            # It's a Setting object with a model field and optional desc()
            msg += f" • choice={self.model_choice.desc()}"

        return msg

    @override
    def __str__(self) -> str:
        return self.desc()

class PipeOperatorModelAvailabilityError(PipelexException):
    def __init__(
        self,
        message: str,
        run_mode: PipeRunMode,
        pipe_type: str,
        pipe_code: str,
        pipe_stack: list[str],
        model_handle: str,
        fallback_list: list[str] | None = None,
    ):
        self.run_mode = run_mode
        self.pipe_type = pipe_type
        self.pipe_code = pipe_code
        self.pipe_stack = pipe_stack
        self.model_handle = model_handle
        self.fallback_list = fallback_list
        super().__init__(message)
