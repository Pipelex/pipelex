from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from pipelex.base_exceptions import PipelexUnexpectedError
from pipelex.cli.judged_target import JudgedBundleTarget, fix_judged_target
from pipelex.pipeline.fixes.fix_loop import FixBundleResult

_MODULE = "pipelex.cli.judged_target"
_RESULT = FixBundleResult(is_valid=True, iterations=0, fixes_applied=[], remaining_errors=[], is_runnable=True)


@pytest.mark.asyncio(loop_scope="class")
class TestJudgedTarget:
    @pytest.mark.parametrize(
        ("bundle_path", "method_dir", "expected"),
        [
            (Path("my_bundle.mthds"), None, Path("my_bundle.mthds")),
            (None, Path("my_method"), Path("my_method")),
        ],
        ids=["bundle_file", "method_folder"],
    )
    async def test_the_judged_path_is_the_folder_else_the_file(self, bundle_path: Path | None, method_dir: Path | None, expected: Path) -> None:
        target = JudgedBundleTarget(bundle_path=bundle_path, method_dir=method_dir, method_tree=None, library_dirs=None)

        assert target.judged_path == expected

    async def test_a_target_naming_neither_is_unexpected(self) -> None:
        target = JudgedBundleTarget(bundle_path=None, method_dir=None, method_tree=None, library_dirs=None)

        with pytest.raises(PipelexUnexpectedError, match="neither a bundle file nor a method's folder"):
            _ = target.judged_path

    async def test_a_folder_is_fixed_whole(self, mocker: MockerFixture) -> None:
        folder_fix = mocker.patch(f"{_MODULE}.fix_method_folder", new=mocker.AsyncMock(return_value=_RESULT))
        file_fix = mocker.patch(f"{_MODULE}.fix_bundle_file", new=mocker.AsyncMock(return_value=_RESULT))
        method_dir = Path("my_method")
        library_dirs = [method_dir, Path("libs")]
        target = JudgedBundleTarget(bundle_path=None, method_dir=method_dir, method_tree=None, library_dirs=library_dirs)

        result = await fix_judged_target(
            target=target, writable_library_dirs=None, allow_signatures=True, max_iterations=4, select_codes=None, ignore_codes=("strip-namespace",)
        )

        assert result is _RESULT
        folder_fix.assert_awaited_once_with(
            method_dir=method_dir,
            library_dirs=library_dirs,
            writable_library_dirs=None,
            allow_signatures=True,
            max_iterations=4,
            select_codes=None,
            ignore_codes=("strip-namespace",),
        )
        file_fix.assert_not_called()

    async def test_a_bundle_file_is_fixed_as_a_file(self, mocker: MockerFixture) -> None:
        folder_fix = mocker.patch(f"{_MODULE}.fix_method_folder", new=mocker.AsyncMock(return_value=_RESULT))
        file_fix = mocker.patch(f"{_MODULE}.fix_bundle_file", new=mocker.AsyncMock(return_value=_RESULT))
        bundle_path = Path("my_bundle.mthds")
        writable = [Path("copy")]
        target = JudgedBundleTarget(bundle_path=bundle_path, method_dir=None, method_tree=None, library_dirs=None)

        await fix_judged_target(
            target=target, writable_library_dirs=writable, allow_signatures=False, max_iterations=None, select_codes=None, ignore_codes=None
        )

        file_fix.assert_awaited_once_with(
            bundle_path,
            library_dirs=None,
            writable_library_dirs=writable,
            allow_signatures=False,
            max_iterations=None,
            select_codes=None,
            ignore_codes=None,
        )
        folder_fix.assert_not_called()
