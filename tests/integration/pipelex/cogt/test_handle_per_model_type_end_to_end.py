"""One handle, one model per model type, end to end: backend files declaring a twin, then a method naming it from both families.

The backends directory is the kit's, plus one backend whose file declares `acme-one` as an LLM and, through
the `handle` key, as a judgment model. The deck that boot builds stands in for the session's for one test,
and a method naming `acme-one` from a `PipeLLM` and from a `PipeJudge` loads and runs dry. A dry run calls
no provider, so what each pipe reached is read from the deck's own lookups, which every resolution goes
through.
"""

import shutil
from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.cogt.models.model_deck import ModelDeck
from pipelex.cogt.models.model_manager import ModelManager
from pipelex.kit.paths import get_kit_configs_dir
from pipelex.pipeline.exceptions import ValidateBundleError
from pipelex.pipeline.validate_bundle import validate_bundle
from pipelex.plugins.plugin_model_declarations import PluginModelDeclarations
from pipelex.runtime_hub import get_models_manager
from pipelex.system.configuration.config_loader import INFERENCE_DIR_NAME
from pipelex.tools.secrets.env_secrets_provider import EnvSecretsProvider

TWIN_HANDLE = "acme-one"
LLM_ONLY_HANDLE = "acme-two"

TWIN_BACKEND_FILE = f"""
[defaults]
model_type = "llm"
sdk = "openai_responses"
thinking_mode = "none"

["{TWIN_HANDLE}"]
model_id = "acme-one-chat"
inputs = ["text"]
outputs = ["text", "structured"]
costs = {{ input = 0.1, output = 0.5 }}

["{LLM_ONLY_HANDLE}"]
inputs = ["text"]
outputs = ["text"]
costs = {{ input = 0.1, output = 0.5 }}

["{TWIN_HANDLE}-judgment"]
handle = "{TWIN_HANDLE}"
model_type = "judgment"
sdk = "typesafe"
model_id = "acme-one-judge"
inputs = ["text"]
outputs = ["judgments"]
costs = {{ input = 0.1, output = 0 }}
"""

ROUTING_PROFILES = f"""
active = "twin"

[profiles.twin]
description = "Route the twin's name to the backend declaring it, and everything else to the internal backend"
default = "internal"
routes = {{ "{TWIN_HANDLE}" = "acme", "{LLM_ONLY_HANDLE}" = "acme" }}
"""

BUNDLE = f"""
domain = "twin_handle"
description = "One handle reached by two pipe families"
main_pipe = "write_then_judge"

[pipe.write_then_judge]
type = "PipeSequence"
description = "Write a reply, then judge it"
inputs = {{ message = "Text" }}
output = "YesNo"
steps = [
  {{ pipe = "write_it", result = "reply" }},
  {{ pipe = "judge_it", result = "verdict" }},
]

[pipe.write_it]
type = "PipeLLM"
description = "Write a reply"
inputs = {{ message = "Text" }}
output = "Text"
model = "{TWIN_HANDLE}"
prompt = "Reply to this message: $message"

[pipe.judge_it]
type = "PipeJudge"
description = "Judge the reply"
inputs = {{ reply = "Text" }}
output = "YesNo"
model = "{TWIN_HANDLE}"
question = "Is $reply polite?"
"""


@pytest.fixture
def twin_model_manager(tmp_path: Path) -> ModelManager:
    """A keyless boot over the kit's inference tree plus a backend whose file declares a twin."""
    inference_dir = tmp_path / INFERENCE_DIR_NAME
    shutil.copytree(Path(str(get_kit_configs_dir())) / INFERENCE_DIR_NAME, inference_dir)
    backends_toml_path = inference_dir / "backends.toml"
    backends_toml_path.write_text(
        f'{backends_toml_path.read_text(encoding="utf-8")}\n[acme]\nenabled = true\napi_key = "not-a-real-key"\n', encoding="utf-8"
    )
    (inference_dir / "backends" / "acme.toml").write_text(TWIN_BACKEND_FILE, encoding="utf-8")
    routing_profiles_path = inference_dir / "routing_profiles.toml"
    routing_profiles_path.write_text(ROUTING_PROFILES, encoding="utf-8")

    model_manager = ModelManager()
    model_manager.setup(
        secrets_provider=EnvSecretsProvider(),
        plugin_model_declarations=PluginModelDeclarations.make_empty(),
        needs_inference=False,
        backends_library_paths=[backends_toml_path],
        backends_dir_path=str(inference_dir / "backends"),
        routing_profile_library_paths=[routing_profiles_path],
        deck_dir_path=str(inference_dir / "deck"),
    )
    return model_manager


@pytest.fixture
def twin_deck_in_session(twin_model_manager: ModelManager, mocker: MockerFixture) -> ModelDeck:
    """The twin boot's deck and backends, standing in for the session's for one test."""
    session_model_manager = get_models_manager()
    mocker.patch.object(session_model_manager, "model_deck", twin_model_manager.get_model_deck())
    mocker.patch.object(session_model_manager, "inference_backend_library", twin_model_manager.inference_backend_library)
    return twin_model_manager.get_model_deck()


class TestHandlePerModelTypeEndToEnd:
    def test_the_boot_serves_both_kinds_of_the_twin(self, twin_model_manager: ModelManager) -> None:
        llm_spec = twin_model_manager.get_inference_model(TWIN_HANDLE, model_type=ModelType.LLM)
        judgment_spec = twin_model_manager.get_inference_model(TWIN_HANDLE, model_type=ModelType.JUDGMENT)

        assert (llm_spec.backend_name, llm_spec.sdk, llm_spec.model_id) == ("acme", "openai_responses", "acme-one-chat")
        assert (judgment_spec.backend_name, judgment_spec.sdk, judgment_spec.model_id) == ("acme", "typesafe", "acme-one-judge")

    @pytest.mark.asyncio(loop_scope="function")
    @pytest.mark.usefixtures("twin_deck_in_session")
    async def test_a_method_naming_the_twin_from_both_families_runs_dry_each_reaching_its_own_spec(self, mocker: MockerFixture) -> None:
        lookup_spy = mocker.spy(ModelDeck, "get_optional_inference_model")

        await validate_bundle(mthds_contents=[BUNDLE])

        reached: dict[ModelType, set[str]] = {}
        for call, returned in zip(lookup_spy.call_args_list, lookup_spy.spy_return_list, strict=True):
            if call.kwargs.get("model_handle") == TWIN_HANDLE and isinstance(returned, InferenceModelSpec):
                reached.setdefault(call.kwargs["model_type"], set()).add(returned.model_id)
        assert reached == {ModelType.LLM: {"acme-one-chat"}, ModelType.JUDGMENT: {"acme-one-judge"}}

    @pytest.mark.asyncio(loop_scope="function")
    async def test_a_judgment_naming_a_handle_served_only_as_an_llm_is_refused_at_load(self, twin_deck_in_session: ModelDeck) -> None:
        assert twin_deck_in_session.inference_models.types_serving(handle=LLM_ONLY_HANDLE) == [ModelType.LLM]
        judging_the_llm_only_model = BUNDLE.replace(f'output = "YesNo"\nmodel = "{TWIN_HANDLE}"', f'output = "YesNo"\nmodel = "{LLM_ONLY_HANDLE}"')
        assert judging_the_llm_only_model != BUNDLE

        with pytest.raises(ValidateBundleError) as exc_info:
            await validate_bundle(mthds_contents=[judging_the_llm_only_model])

        report = str(exc_info.value.to_error_report().model_dump())
        assert LLM_ONLY_HANDLE in report
        assert "'unknown_model'" in report
        assert "'model_type': 'judgment'" in report
