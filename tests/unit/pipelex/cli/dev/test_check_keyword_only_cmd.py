"""Unit tests for the `pipelex-dev check-keyword-only` AST guard."""

from __future__ import annotations

import textwrap

from pipelex.cli.dev_cli.commands.keyword_only_guard import (
    Violation,
    find_violations_in_source,
)


def _violate(source: str, *, module_qname: str = "pipelex.sample.module", relative_path: str = "pipelex/sample/module.py") -> list[Violation]:
    """Run the guard over an inline snippet and return its violations."""
    return find_violations_in_source(textwrap.dedent(source), module_qname=module_qname, relative_path=relative_path)


def _keys(violations: list[Violation]) -> set[str]:
    return {violation.key for violation in violations}


class TestCheckKeywordOnly:
    def test_compliant_with_bare_star(self) -> None:
        """A subject followed by keyword-only options is compliant."""
        violations = _violate(
            """
            def build_pipe(spec, *, dry_run, retries, validate):
                ...
            """
        )
        assert violations == []

    def test_violation_two_positional_non_subject(self) -> None:
        """Subject plus a second positional-or-keyword param is a violation."""
        violations = _violate(
            """
            def build_pipe(spec, dry_run, retries, validate):
                ...
            """
        )
        assert _keys(violations) == {"pipelex/sample/module.py::build_pipe"}

    def test_violation_single_extra_positional(self) -> None:
        """Subject plus exactly one more bare positional param is already a violation."""
        violations = _violate(
            """
            def copy_file(source_path, target_path):
                ...
            """
        )
        assert _keys(violations) == {"pipelex/sample/module.py::copy_file"}

    def test_exception_1_subject_only_positional_compliant(self) -> None:
        """A lone subject (single positional-or-keyword param) is compliant — Exception 1."""
        violations = _violate(
            """
            def render(node):
                ...
            """
        )
        assert violations == []

    def test_exception_1_subject_plus_one_keyword_only_compliant(self) -> None:
        """Subject plus a single keyword-only option is compliant — Exception 1."""
        violations = _violate(
            """
            def truncate(text, *, max_length=80):
                ...
            """
        )
        assert violations == []

    def test_method_self_dropped_then_subject_only_compliant(self) -> None:
        """`self` is dropped, leaving a lone subject — compliant."""
        violations = _violate(
            """
            class Foo:
                def render(self, node):
                    ...
            """
        )
        assert violations == []

    def test_method_self_dropped_then_violation(self) -> None:
        """`self` dropped, subject + one more positional => violation, qualified by class name."""
        violations = _violate(
            """
            class FooBuilder:
                def build(self, spec, options):
                    ...
            """
        )
        assert _keys(violations) == {"pipelex/sample/module.py::FooBuilder.build"}

    def test_classmethod_cls_dropped(self) -> None:
        """`cls` is dropped like `self`."""
        violations = _violate(
            """
            class Bar:
                @classmethod
                def make(cls, source, target):
                    ...
            """
        )
        assert _keys(violations) == {"pipelex/sample/module.py::Bar.make"}

    def test_args_kwargs_do_not_count(self) -> None:
        """A lone subject followed only by *args/**kwargs is compliant."""
        violations = _violate(
            """
            def dispatch(subject, *args, **kwargs):
                ...
            """
        )
        assert violations == []

    def test_exception_2_allowlisted_symmetric_tuple_skipped(self) -> None:
        """An allowlisted symmetric tuple is exempt entirely."""
        violations = _violate(
            """
            def set_env(key, value):
                ...
            """,
            module_qname="pipelex.system.environment",
            relative_path="pipelex/system/environment.py",
        )
        assert violations == []

    def test_allowlist_requires_both_name_and_path(self) -> None:
        """Same qualified name in the wrong file is NOT exempt by the allowlist."""
        violations = _violate(
            """
            def set_env(key, value):
                ...
            """,
            module_qname="pipelex.elsewhere",
            relative_path="pipelex/elsewhere.py",
        )
        assert _keys(violations) == {"pipelex/elsewhere.py::set_env"}

    def test_carveout_dunder_skipped(self) -> None:
        """A dunder method is skipped regardless of its parameter shape."""
        violations = _violate(
            """
            class Box:
                def __setitem__(self, key, value):
                    ...
            """
        )
        assert violations == []

    def test_half_dunder_not_carved_out(self) -> None:
        """A name-mangled half-dunder (no trailing __) is NOT carved out."""
        violations = _violate(
            """
            class Box:
                def __store(self, key, value):
                    ...
            """
        )
        assert _keys(violations) == {"pipelex/sample/module.py::Box.__store"}

    def test_degenerate_underscores_not_dunder(self) -> None:
        """`____` must not match the dunder carve-out."""
        violations = _violate(
            """
            def ____(subject, other):
                ...
            """
        )
        assert _keys(violations) == {"pipelex/sample/module.py::____"}

    def test_carveout_pydantic_field_validator_skipped(self) -> None:
        """A pydantic @field_validator is skipped."""
        violations = _violate(
            """
            class Model:
                @field_validator("name", mode="before")
                def normalize(cls, value, info):
                    ...
            """
        )
        assert violations == []

    def test_carveout_pydantic_model_validator_bare_skipped(self) -> None:
        """A bare (non-call) @model_validator is skipped."""
        violations = _violate(
            """
            class Model:
                @model_validator
                def check(self, value, info):
                    ...
            """
        )
        assert violations == []

    def test_carveout_typer_command_decorator_skipped(self) -> None:
        """A @app.command() Typer entrypoint is skipped (attr suffix match, any receiver)."""
        violations = _violate(
            """
            @graph_app.command(name="show")
            def show(path, fmt, output):
                ...
            """
        )
        assert violations == []

    def test_carveout_temporal_activity_defn_in_stack_skipped(self) -> None:
        """@activity.defn anywhere in the decorator stack is skipped (scan whole stack)."""
        violations = _violate(
            """
            @activity.defn
            @convert_pipelex_errors
            def act_render(job, context, options):
                ...
            """
        )
        assert violations == []

    def test_carveout_workflow_run_skipped(self) -> None:
        """@workflow.run is skipped."""
        violations = _violate(
            """
            class MyWorkflow:
                @workflow.run
                async def run(self, request, options):
                    ...
            """
        )
        assert violations == []

    def test_carveout_pytest_fixture_skipped(self) -> None:
        """@pytest.fixture is skipped."""
        violations = _violate(
            """
            @pytest.fixture(scope="session")
            def my_fixture(request, config, tmp_path):
                ...
            """
        )
        assert violations == []

    def test_carveout_bare_fixture_skipped(self) -> None:
        """A bare @fixture (from pytest import fixture) is skipped like @pytest.fixture."""
        violations = _violate(
            """
            @fixture(scope="session")
            def my_fixture(request, config, tmp_path):
                ...
            """
        )
        assert violations == []

    def test_carveout_jinja2_pass_context_skipped(self) -> None:
        """@pass_context filters are invoked positionally by the Jinja2 engine — skipped."""
        violations = _violate(
            """
            @pass_context
            async def text_format(context, value, text_format=None):
                ...
            """
        )
        assert violations == []

    def test_carveout_jinja2_attributed_pass_environment_skipped(self) -> None:
        """The attributed @jinja2.pass_environment form is skipped like the bare form."""
        violations = _violate(
            """
            @jinja2.pass_environment
            def my_filter(environment, value, arg):
                ...
            """
        )
        assert violations == []

    def test_carveout_override_skipped(self) -> None:
        """@override defs are skipped — the convention lives on the base."""
        violations = _violate(
            """
            class Impl:
                @override
                def _store(self, data, key, content_type):
                    ...
            """
        )
        assert violations == []

    def test_carveout_typer_annotated_argument_skipped(self) -> None:
        """A call-style Typer command (no decorator) is detected via Annotated typer.Argument/Option."""
        violations = _violate(
            """
            def serve(host: Annotated[str, typer.Argument(help="host")], port: Annotated[int, typer.Option()]):
                ...
            """
        )
        assert violations == []

    def test_carveout_bare_typer_annotated_skipped(self) -> None:
        """Bare Argument/Option (from typer import Argument, Option) are detected like the qualified form."""
        violations = _violate(
            """
            def serve(host: Annotated[str, Argument(help="host")], port: Annotated[int, Option()]):
                ...
            """
        )
        assert violations == []

    def test_escape_hatch_suppresses(self) -> None:
        """An inline `# kw-only: ignore` on the def line suppresses the violation."""
        violations = _violate(
            """
            def build_pipe(spec, dry_run, retries):  # kw-only: ignore
                ...
            """
        )
        assert violations == []

    def test_escape_hatch_does_not_suppress_other_defs(self) -> None:
        """The escape hatch is scoped to its own def line only."""
        violations = _violate(
            """
            def safe(spec, dry_run):  # kw-only: ignore
                ...

            def unsafe(spec, dry_run):
                ...
            """
        )
        assert _keys(violations) == {"pipelex/sample/module.py::unsafe"}

    def test_escape_hatch_survives_form_feed_earlier_in_file(self) -> None:
        r"""A form-feed before an escaped def must not shift line indexing off the marker.

        ``str.splitlines()`` splits on ``\x0c`` but ``ast`` line numbers do not, so a form-feed earlier
        in the file used to make the escape-hatch lookup read the marker off the wrong physical line — a
        false-positive violation on an explicitly-suppressed def (which would wrongly block a hook edit).
        """
        source = 'page = "one\x0ctwo"\ndef safe(spec, dry_run):  # kw-only: ignore\n    return spec\n'
        violations = find_violations_in_source(source, module_qname="pipelex.sample.module", relative_path="pipelex/sample/module.py")
        assert violations == []

    def test_async_def_supported(self) -> None:
        """Async functions are inspected too."""
        violations = _violate(
            """
            async def fetch(url, retries, timeout):
                ...
            """
        )
        assert _keys(violations) == {"pipelex/sample/module.py::fetch"}

    def test_nested_function_qualified_name(self) -> None:
        """Nested defs are inspected and qualified through their enclosing scope."""
        violations = _violate(
            """
            class Outer:
                def method(self, subject):
                    def inner(first, second):
                        ...
            """
        )
        assert _keys(violations) == {"pipelex/sample/module.py::Outer.method.inner"}
