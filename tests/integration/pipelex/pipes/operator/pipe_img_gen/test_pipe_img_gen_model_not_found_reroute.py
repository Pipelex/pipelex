from typing import Callable

import pytest
from pytest_mock import MockerFixture

from pipelex.cogt.exceptions import ImgGenGenerationError, ImgGenModelNotFoundError, InferenceErrorCategory
from pipelex.cogt.inference.error_classification import UserAction, UserActionKind
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.pipes.pipe_factory import PipeFactory
from pipelex.interpreter_hub import get_pipe_library, get_pipe_router
from pipelex.pipe_operators.exceptions import PipeOperatorModelAvailabilityError
from pipelex.pipe_operators.img_gen.pipe_img_gen import PipeImgGen
from pipelex.pipe_operators.img_gen.pipe_img_gen_blueprint import PipeImgGenBlueprint
from pipelex.pipe_run.pipe_job_factory import PipeJobFactory
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.pipe_run.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.system.job_metadata import JobMetadata


@pytest.mark.asyncio(loop_scope="class")
class TestPipeImgGenModelNotFoundReroute:
    async def test_img_gen_model_not_found_reroutes_to_model_availability_error(
        self,
        job_metadata: JobMetadata,
        load_empty_library: Callable[[], None],
        mocker: MockerFixture,
    ) -> None:
        """A provider 404 raised as ImgGenModelNotFoundError from the content generator escapes the
        img-gen operator's generic-error handling, reaches `except ModelNotFoundError` in
        PipeOperator._live_run_pipe, and surfaces as PipeOperatorModelAvailabilityError.
        """
        load_empty_library()

        not_found_error = ImgGenModelNotFoundError(
            message="Image-gen model 'sd-not-a-real-model' not found",
            model_handle="sd-not-a-real-model",
            error_category=InferenceErrorCategory.CONFIGURATION,
            user_action=UserAction(kind=UserActionKind.CHANGE_MODEL, detail="pick an available model"),
        )
        fake_content_generator = mocker.MagicMock()
        fake_content_generator.make_single_image = mocker.AsyncMock(side_effect=not_found_error)
        mocker.patch("pipelex.pipe_operators.img_gen.pipe_img_gen.get_content_generator", return_value=fake_content_generator)

        pipe = PipeFactory[PipeImgGen].make_from_blueprint(
            domain_code="generic",
            pipe_code="adhoc_for_test_img_gen_model_not_found_reroute",
            blueprint=PipeImgGenBlueprint(
                description="Img-gen model-not-found reroute test",
                output=NativeConceptCode.IMAGE,
                prompt="A red cube on a white background.",
            ),
        )
        get_pipe_library().add_new_pipe(pipe)

        pipe_job = PipeJobFactory.make_pipe_job(
            pipe=pipe,
            pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=PipeRunMode.LIVE),
            job_metadata=job_metadata,
        )

        with pytest.raises(PipeOperatorModelAvailabilityError) as exc_info:
            await get_pipe_router().run(pipe_job=pipe_job)

        availability_error = exc_info.value
        assert availability_error.model_handle == "sd-not-a-real-model"
        assert availability_error.fallback_list is None
        assert availability_error.pipe_type == "PipeImgGen"
        assert availability_error.pipe_code == "adhoc_for_test_img_gen_model_not_found_reroute"
        assert isinstance(availability_error.__cause__, ImgGenModelNotFoundError)
        # The reroute hinges on this: ImgGenModelNotFoundError is a sibling of ImgGenGenerationError.
        assert not isinstance(availability_error.__cause__, ImgGenGenerationError)
        assert availability_error.__cause__.error_category is InferenceErrorCategory.CONFIGURATION
        assert availability_error.__cause__.error_category.is_retryable is False
