"""Unit tests for the `pipelex-dev check-keyword-only` AST guard."""

from __future__ import annotations

import textwrap

from pipelex.cli.dev_cli.commands.keyword_only_guard import (
    SubjectGrant,
    Violation,
    ViolationKind,
    find_violations_in_source,
)


def _grant(key: str, *, param: str, seeded: bool = False) -> dict[str, SubjectGrant]:
    """A one-entry grants mapping for an inline snippet."""
    return {key: SubjectGrant(param=param, rationale="test grant", seeded=seeded)}


def _violate(
    source: str,
    *,
    module_qname: str = "pipelex.sample.module",
    relative_path: str = "pipelex/sample/module.py",
    grants: dict[str, SubjectGrant] | None = None,
) -> list[Violation]:
    """Run the guard over an inline snippet and return its violations."""
    return find_violations_in_source(textwrap.dedent(source), module_qname=module_qname, relative_path=relative_path, grants=grants or {})


def _keys(violations: list[Violation]) -> set[str]:
    return {violation.key for violation in violations}


def _kinds(violations: list[Violation]) -> set[ViolationKind]:
    return {violation.kind for violation in violations}


class TestCheckKeywordOnly:
    def test_compliant_with_bare_star_and_grant(self) -> None:
        """A granted subject followed by keyword-only options is compliant."""
        violations = _violate(
            """
            def build_pipe(spec, *, dry_run, retries, validate):
                ...
            """,
            grants=_grant("pipelex/sample/module.py::build_pipe", param="spec"),
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

    def test_granted_lone_subject_compliant(self) -> None:
        """A lone subject (single positional-or-keyword param) is compliant when granted."""
        violations = _violate(
            """
            def render(node):
                ...
            """,
            grants=_grant("pipelex/sample/module.py::render", param="node"),
        )
        assert violations == []

    def test_ungranted_lone_subject_is_a_violation(self) -> None:
        """A positional subject without a grant is a violation — the generic Exception 1 is gone."""
        violations = _violate(
            """
            def render(node):
                ...
            """
        )
        assert _keys(violations) == {"pipelex/sample/module.py::render"}
        assert _kinds(violations) == {ViolationKind.UNGRANTED_SUBJECT}

    def test_granted_subject_plus_keyword_only_compliant(self) -> None:
        """A granted subject plus a single keyword-only option is compliant."""
        violations = _violate(
            """
            def truncate(text, *, max_length=80):
                ...
            """,
            grants=_grant("pipelex/sample/module.py::truncate", param="text"),
        )
        assert violations == []

    def test_ungranted_subject_plus_keyword_only_is_a_violation(self) -> None:
        """The strict-all scope: subject-plus-kwonly defs need a grant just like lone-subject defs."""
        violations = _violate(
            """
            def truncate(text, *, max_length=80):
                ...
            """
        )
        assert _kinds(violations) == {ViolationKind.UNGRANTED_SUBJECT}

    def test_grant_param_mismatch_is_a_violation(self) -> None:
        """A grant whose recorded param no longer matches the def's subject is a violation (symmetric staleness)."""
        violations = _violate(
            """
            def render(new_name):
                ...
            """,
            grants=_grant("pipelex/sample/module.py::render", param="node"),
        )
        assert _kinds(violations) == {ViolationKind.GRANT_PARAM_MISMATCH}
        assert "node" in violations[0].detail
        assert "new_name" in violations[0].detail

    def test_seeded_grant_accepted_transitionally(self) -> None:
        """A `seeded = true` entry counts as a grant during the transition (Phases 2-4)."""
        violations = _violate(
            """
            def render(node):
                ...
            """,
            grants=_grant("pipelex/sample/module.py::render", param="node", seeded=True),
        )
        assert violations == []

    def test_missing_star_dominates_subject_rules(self) -> None:
        """A def with a second positional param reports missing-star, even when its subject is granted."""
        violations = _violate(
            """
            def build_pipe(spec, options):
                ...
            """,
            grants=_grant("pipelex/sample/module.py::build_pipe", param="spec"),
        )
        assert _kinds(violations) == {ViolationKind.MISSING_STAR}

    def test_same_qualname_defs_share_one_grant(self) -> None:
        """@overload-style same-qualname defs collapse onto one key; a single grant covers them all (D11)."""
        source = """
            def parse(spec, *, strict=False):
                ...

            def parse(spec):
                ...
            """
        assert _violate(source, grants=_grant("pipelex/sample/module.py::parse", param="spec")) == []

    def test_same_qualname_defs_must_all_match_the_grant(self) -> None:
        """When same-qualname defs disagree with the recorded param, each mismatching def is flagged."""
        source = """
            def parse(spec):
                ...

            def parse(data):
                ...
            """
        violations = _violate(source, grants=_grant("pipelex/sample/module.py::parse", param="spec"))
        assert _kinds(violations) == {ViolationKind.GRANT_PARAM_MISMATCH}
        assert len(violations) == 1

    def test_literal_bool_subject_banned_even_with_grant(self) -> None:
        """A bool subject is a violation no matter what — a grant cannot cover it."""
        violations = _violate(
            """
            def do_doctor_cmd(fix: bool):
                ...
            """,
            grants=_grant("pipelex/sample/module.py::do_doctor_cmd", param="fix"),
        )
        assert _kinds(violations) == {ViolationKind.LITERAL_SUBJECT}

    def test_literal_int_and_float_subjects_banned(self) -> None:
        """Int and float subjects are banned like bool."""
        violations = _violate(
            """
            def retry(count: int):
                ...

            def scale(factor: float):
                ...
            """
        )
        assert _kinds(violations) == {ViolationKind.LITERAL_SUBJECT}
        assert len(violations) == 2

    def test_literal_optional_and_union_forms_banned(self) -> None:
        """Optional[X] / X | None / Union[X, None] forms of literal types are banned too."""
        violations = _violate(
            """
            def f1(flag: Optional[bool]):
                ...

            def f2(flag: bool | None):
                ...

            def f3(count: Union[int, None]):
                ...

            def f4(count: None | int):
                ...
            """
        )
        assert _kinds(violations) == {ViolationKind.LITERAL_SUBJECT}
        assert len(violations) == 4

    def test_non_literal_union_subject_is_grantable(self) -> None:
        """A union carrying a non-literal member (int | str) is not literal-typed — a grant covers it."""
        violations = _violate(
            """
            def lookup(key: int | str):
                ...
            """,
            grants=_grant("pipelex/sample/module.py::lookup", param="key"),
        )
        assert violations == []

    def test_str_and_unannotated_subjects_stay_grantable(self) -> None:
        """Str subjects are the house style and unannotated subjects are not provably literal — both grantable."""
        source = """
            def by_code(pipe_code: str):
                ...

            def render(node):
                ...
            """
        grants = {
            "pipelex/sample/module.py::by_code": SubjectGrant(param="pipe_code", rationale="test grant"),
            "pipelex/sample/module.py::render": SubjectGrant(param="node", rationale="test grant"),
        }
        assert _violate(source, grants=grants) == []

    def test_escape_hatch_beats_subject_rules(self) -> None:
        """`# kw-only: ignore` short-circuits before the subject rules — no grant needed, literal or not."""
        violations = _violate(
            """
            def version_callback(value: bool):  # kw-only: ignore
                ...

            def render(node):  # kw-only: ignore
                ...
            """
        )
        assert violations == []

    def test_method_self_dropped_then_granted_subject_compliant(self) -> None:
        """`self` is dropped, leaving a granted lone subject — compliant."""
        violations = _violate(
            """
            class Foo:
                def render(self, node):
                    ...
            """,
            grants=_grant("pipelex/sample/module.py::Foo.render", param="node"),
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
        """A granted lone subject followed only by *args/**kwargs is compliant."""
        violations = _violate(
            """
            def dispatch(subject, *args, **kwargs):
                ...
            """,
            grants=_grant("pipelex/sample/module.py::dispatch", param="subject"),
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
        violations = find_violations_in_source(source, module_qname="pipelex.sample.module", relative_path="pipelex/sample/module.py", grants={})
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
            """,
            grants=_grant("pipelex/sample/module.py::Outer.method", param="subject"),
        )
        assert _keys(violations) == {"pipelex/sample/module.py::Outer.method.inner"}
