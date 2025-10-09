import pytest
from pytest import FixtureRequest

from pipelex import pretty_print
from pipelex.cogt.exceptions import LLMHandleNotFoundError
from pipelex.cogt.extract.extract_input import ExtractInput
from pipelex.cogt.extract.extract_job_components import ExtractJobConfig, ExtractJobParams
from pipelex.cogt.extract.extract_output import ExtractOutput
from pipelex.cogt.image.generated_image import GeneratedImage
from pipelex.cogt.img_gen.img_gen_prompt import ImgGenPrompt
from pipelex.cogt.llm.llm_prompt import LLMPrompt
from pipelex.cogt.llm.llm_setting import LLMSetting
from pipelex.hub import get_content_generator, get_model_deck
from pipelex.pipeline.job_metadata import JobMetadata
from tests.cases import ImageTestCases, PDFTestCases
from tests.integration.pipelex.cogt.test_data import Employee

USER_TEXT_FOR_BASE = """
Write a detailed description of a woman's clothing in the style of a 19th-century novel.
Keep it short: 3 sentences max
"""

USER_TEXT_FOR_SINGLE_PERSON = "name: John, age: 30, job: bank teller"
USER_TEXT_FOR_SINGLE_PERSON_TEXT_THEN_OBJECT = """
Imagine a female character that decides to become a cop once reaching middle age.
Present this character in a couple of very short sentences.
Be sure to include the character's full name, age and job.
"""
MULTIPLE_USER_TEXTS_FOR_PEOPLE = [
    "name: Bob, age: 25, job: banker",
    "name: Maria, age: 35, job: consultant",
    "name: SLartiblfastikur, age: 30, job: fizzy buzzer",
    "name: Alice, age: 40, job: developer",
    "name: Tom, age: 45, job: TV presenter",
    "name: Jerry, age: 50, job: nurse",
]
USER_TEXTS_FOR_PEOPLE_STR = "\n".join(MULTIPLE_USER_TEXTS_FOR_PEOPLE)
USER_TEXT_FOR_MULTIPLE_PEOPLE_TEXT_THEN_OBJECT = """
Imagine the 4 main characters for a sitcom in Paris.
Present each character in one very short sentence.
Be sure to include each character's full name, age and job.
"""

USER_TEXT_FOR_HAIKU = """
Write a haiku about the meaning of life
"""


# The ContentGenerator has features that xork without inference (jinja2) or with LLM, Image generation, OCR
# So to run them all you need to bypass the marker restrictions defined in the pyproject.toml pytest section
# like this:
# pytest -m "" -k TestContentGenerator
# and if you cant more prints:
# pytest -m "" -k TestContentGenerator -s -vv
@pytest.mark.asyncio(loop_scope="class")
class TestContentGenerator:
    @pytest.mark.llm
    @pytest.mark.inference
    async def test_make_llm_text_only(self, request: FixtureRequest):
        llm_setting_main = get_model_deck().get_llm_setting(llm_choice="llm_for_testing_gen_text")

        text: str = await get_content_generator().make_llm_text(
            job_metadata=JobMetadata(job_name=request.node.originalname),  # pyright: ignore[reportUnknownMemberType,reportUnknownArgumentType]
            llm_prompt_for_text=LLMPrompt(user_text=USER_TEXT_FOR_BASE),
            llm_setting_main=llm_setting_main,
        )
        pretty_print(text, title="make_llm_text")

        assert isinstance(text, str)

    @pytest.mark.llm
    @pytest.mark.inference
    async def test_make_object_direct(self, request: FixtureRequest):
        llm_setting_for_object = get_model_deck().get_llm_setting(llm_choice="llm_for_testing_gen_object")

        person_direct: Employee = await get_content_generator().make_object_direct(
            job_metadata=JobMetadata(job_name=request.node.originalname),  # pyright: ignore[reportUnknownMemberType,reportUnknownArgumentType]
            object_class=Employee,
            llm_prompt_for_object=LLMPrompt(user_text=USER_TEXT_FOR_SINGLE_PERSON),
            llm_setting_for_object=llm_setting_for_object,
        )
        pretty_print(person_direct, title="make_object_direct")

        assert isinstance(person_direct, Employee)

    @pytest.mark.llm
    @pytest.mark.inference
    async def test_make_object_list_direct(self, request: FixtureRequest):
        llm_setting_for_object = get_model_deck().get_llm_setting(llm_choice="llm_for_testing_gen_object")

        person_list_direct: list[Employee] = await get_content_generator().make_object_list_direct(
            job_metadata=JobMetadata(job_name=request.node.originalname),  # pyright: ignore[reportUnknownMemberType,reportUnknownArgumentType]
            object_class=Employee,
            llm_prompt_for_object_list=LLMPrompt(user_text=USER_TEXTS_FOR_PEOPLE_STR),
            llm_setting_for_object_list=llm_setting_for_object,
        )
        pretty_print(person_list_direct, title="make_object_list_direct")

        assert isinstance(person_list_direct, list)
        assert all(isinstance(person, Employee) for person in person_list_direct)

    @pytest.mark.img_gen
    @pytest.mark.inference
    async def test_make_image(self, request: FixtureRequest):
        img_gen_handle = "fast-lightning-sdxl"
        positive_text = "A dog with sunglasses coding on a laptop"
        image: GeneratedImage = await get_content_generator().make_single_image(
            job_metadata=JobMetadata(job_name=request.node.originalname),  # pyright: ignore[reportUnknownMemberType,reportUnknownArgumentType]
            img_gen_handle=img_gen_handle,
            img_gen_prompt=ImgGenPrompt(
                positive_text=positive_text,
            ),
        )
        pretty_print(image, title=f"Image generated by '{img_gen_handle}' for '{positive_text}'")
        assert isinstance(image, GeneratedImage)

    @pytest.mark.usefixtures("request")
    async def test_make_templated_text(self):
        context = {
            "the_answer": "elementary, my dear Watson",
        }

        jinja2_text: str = await get_content_generator().make_templated_text(
            context=context,
            template="The answer is: {{ the_answer }}",
        )
        assert isinstance(jinja2_text, str)
        assert jinja2_text == "The answer is: elementary, my dear Watson"

    @pytest.mark.extract
    @pytest.mark.inference
    async def test_make_extract_pages_from_image(self, extract_handle_from_image: str, request: FixtureRequest):
        extract_output = await get_content_generator().make_extract_pages(
            job_metadata=JobMetadata(job_name=request.node.originalname),  # pyright: ignore[reportUnknownMemberType,reportUnknownArgumentType]
            extract_handle=extract_handle_from_image,
            extract_input=ExtractInput(image_uri=ImageTestCases.IMAGE_FILE_PATH_PNG),
            extract_job_params=ExtractJobParams.make_default_extract_job_params(),
            extract_job_config=ExtractJobConfig(),
        )
        pretty_print(extract_output, title="extract_pages")
        assert isinstance(extract_output, ExtractOutput)

    @pytest.mark.extract
    @pytest.mark.inference
    async def test_make_extract_pages_from_pdf(self, extract_handle: str, request: FixtureRequest):
        extract_output = await get_content_generator().make_extract_pages(
            job_metadata=JobMetadata(job_name=request.node.originalname),  # pyright: ignore[reportUnknownMemberType,reportUnknownArgumentType]
            extract_handle=extract_handle,
            extract_input=ExtractInput(pdf_uri=PDFTestCases.PDF_FILE_PATH_1),
            extract_job_params=ExtractJobParams.make_default_extract_job_params(),
            extract_job_config=ExtractJobConfig(),
        )
        pretty_print(extract_output, title="extract_pages")
        assert isinstance(extract_output, ExtractOutput)

    @pytest.mark.llm
    @pytest.mark.inference
    async def test_make_llm_text_with_error(self, request: FixtureRequest):
        llm_setting_main = LLMSetting(model="bad_handle_to_test_failure", temperature=0.5, max_tokens=100)
        with pytest.raises(LLMHandleNotFoundError) as excinfo:
            await get_content_generator().make_llm_text(
                job_metadata=JobMetadata(job_name=request.node.originalname),  # pyright: ignore[reportUnknownMemberType,reportUnknownArgumentType]
                llm_prompt_for_text=LLMPrompt(user_text=USER_TEXT_FOR_BASE),
                llm_setting_main=llm_setting_main,
            )
        error = excinfo.value
        pretty_print(f"Caught expected error: {error}")
        assert str(error).startswith("Model handle 'bad_handle_to_test_failure' not found")
