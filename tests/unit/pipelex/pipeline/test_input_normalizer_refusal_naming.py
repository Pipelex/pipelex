"""Every refusal of a file input names it the same way: the root input as `input`, the path down to the file as the location's `field`.

The convention is `InputShapingError`'s. A list item's path, such as `documents[1]`, is never the `input`, which is the
name a caller gave the run's input.
"""

import pytest
from pytest_mock import MockerFixture

from pipelex.base_exceptions import PipelexError
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.stuffs.document_content import DocumentContent
from pipelex.core.stuffs.image_content import ImageContent
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.errors.problem import ProblemView
from pipelex.pipeline.input_normalizer import prepare_file_inputs
from pipelex.tools.storage.exceptions import StorageFileNotFoundError
from pipelex.tools.storage.storage_provider_abstract import StorageProviderAbstract
from tests.unit.pipelex.pipeline.test_data import FileInputRefusalCase, InputRefusalNamingTestData


def _file_content(*, native_concept_code: NativeConceptCode, url: str) -> StuffContent:
    if native_concept_code == NativeConceptCode.IMAGE:
        return ImageContent(url=url)
    return DocumentContent(url=url)


async def _refusal_of_the_second_item(*, mocker: MockerFixture, case: FileInputRefusalCase) -> PipelexError:
    """Normalize a list input whose second file the case refuses, and return the refusal."""
    storage = mocker.Mock(spec=StorageProviderAbstract)
    storage.load_head = mocker.AsyncMock(side_effect=StorageFileNotFoundError("no stored file"))
    mocker.patch("pipelex.pipeline.input_normalizer.get_storage_provider", return_value=storage)
    mocker.patch(
        "pipelex.pipeline.input_normalizer.get_config",
        return_value=mocker.Mock(runtime=mocker.Mock(storage=mocker.Mock(is_upload_local_content_enabled=True))),
    )
    urls = (InputRefusalNamingTestData.FINE_URL, case.refused_url)
    items = [_file_content(native_concept_code=case.native_concept_code, url=url) for url in urls]
    memory = WorkingMemoryFactory.make_from_single_stuff(
        StuffFactory.make_stuff(
            concept=ConceptFactory.make_native_concept(native_concept_code=case.native_concept_code),
            content=ListContent[StuffContent](items=items),
            name=case.input_name,
        )
    )
    with pytest.raises(PipelexError) as exc_info:
        await prepare_file_inputs(memory, storage_scope="org_abc/run_1", read_scope=case.read_scope, is_relocation_enabled=True)
    return exc_info.value


def _assert_named_by_root_and_path(*, refusal: PipelexError, case: FileInputRefusalCase) -> None:
    caller = refusal.to_problem(view=ProblemView.CALLER)
    assert caller.code == case.expected_code
    assert caller.params is not None
    wire_params = caller.params.as_wire()
    assert {name: wire_params.get(name) for name in case.expected_params} == case.expected_params
    assert caller.location is not None
    assert caller.location.model_dump(exclude_none=True) == {"input": case.input_name, "field": f"{case.input_name}[1]"}


@pytest.mark.asyncio(loop_scope="class")
class TestInputNormalizerRefusalNaming:
    @pytest.mark.parametrize(("_topic", "case"), InputRefusalNamingTestData.CASES)
    async def test_a_refused_list_item_is_named_by_its_root_input_and_its_path(
        self, mocker: MockerFixture, _topic: str, case: FileInputRefusalCase
    ) -> None:
        refusal = await _refusal_of_the_second_item(mocker=mocker, case=case)

        _assert_named_by_root_and_path(refusal=refusal, case=case)

    @pytest.mark.builds_problems_without_required_params(reason="an Image input holding a PDF is refused before any model reads it")
    async def test_an_image_item_holding_a_pdf_is_named_by_its_root_input_and_its_path(self, mocker: MockerFixture) -> None:
        refusal = await _refusal_of_the_second_item(mocker=mocker, case=InputRefusalNamingTestData.IMAGE_HOLDING_A_PDF)

        _assert_named_by_root_and_path(refusal=refusal, case=InputRefusalNamingTestData.IMAGE_HOLDING_A_PDF)
