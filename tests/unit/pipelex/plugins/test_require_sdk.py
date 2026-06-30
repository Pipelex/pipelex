from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from pipelex.plugins.inference_backend_registry import require_sdk
from pipelex.system.exceptions import MissingDependencyError

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

REGISTRY_MODULE = "pipelex.plugins.inference_backend_registry"


class TestRequireSdk:
    def test_present_spec_does_not_raise(self, mocker: MockerFixture) -> None:
        """An importable spec is a no-op: find_spec returns a spec object."""
        mocker.patch(f"{REGISTRY_MODULE}.importlib.util.find_spec", return_value=object())
        require_sdk(spec="anything", extra="anything", msg="should not raise")

    def test_missing_spec_raises_missing_dependency(self, mocker: MockerFixture) -> None:
        """A spec that resolves to None raises MissingDependencyError with the install hint."""
        mocker.patch(f"{REGISTRY_MODULE}.importlib.util.find_spec", return_value=None)
        with pytest.raises(MissingDependencyError) as exc_info:
            require_sdk(spec="ghost", extra="ghost", msg="install it")
        message = str(exc_info.value)
        assert "ghost" in message
        assert "pipelex[ghost]" in message

    def test_dotted_spec_with_absent_parent_raises_missing_dependency(self, mocker: MockerFixture) -> None:
        """find_spec imports the dotted parent first; an absent parent raises ModuleNotFoundError,
        which must surface as MissingDependencyError (with the pipelex[<extra>] hint), not a raw import error.
        """
        mocker.patch(
            f"{REGISTRY_MODULE}.importlib.util.find_spec",
            side_effect=ModuleNotFoundError("No module named 'google'"),
        )
        with pytest.raises(MissingDependencyError) as exc_info:
            require_sdk(spec="google.genai", dependency_name="google-genai", extra="google", msg="install it")
        message = str(exc_info.value)
        assert "google-genai" in message
        assert "pipelex[google]" in message

    def test_multi_spec_partial_missing_names_only_absent(self, mocker: MockerFixture) -> None:
        """With several required specs and no explicit dependency_name, the error names ONLY the
        absent spec(s) — a user who already has one of them must not be told to (re)install it.
        """

        def fake_find_spec(name: str) -> object | None:
            return None if name == "aioboto3" else object()

        mocker.patch(f"{REGISTRY_MODULE}.importlib.util.find_spec", side_effect=fake_find_spec)
        with pytest.raises(MissingDependencyError) as exc_info:
            require_sdk(spec=["boto3", "aioboto3"], extra="bedrock", msg="install it")
        # boto3 is present, so only aioboto3 should be named (the trailing comma proves the old
        # joined "boto3,aioboto3" form is gone — "boto3" alone is a substring of "aioboto3").
        assert exc_info.value.dependency_name == "aioboto3"
        assert "boto3," not in str(exc_info.value)
