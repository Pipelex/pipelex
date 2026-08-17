"""One migration operation, in words — the sentence both `migrate` commands render.

`describe_op` is shared: the human CLI prints it under each step and the agent CLI puts it in its
Markdown. So it is the one place where the standing rule is at its most exposed —

> No value read from a user's file is ever rendered.

— and the one place it is cheap to hold, because the function is given an operation and nothing
else. Every part of every sentence below comes from the ledger: a kind, a path, a key, and the
spellings a remap names.

The wildcard cases are the reason this module exists. `inference-backend@2` is the first shipped
entry to address one — `table_path = ["*"]`, meaning every root table of a backend file — and the
literal rendering of that is `from '*'`, which names nothing a reader can find in their file.
"""

from pipelex.cli.commands.migrate_cmd import describe_op
from pipelex.suggested_fix import WILDCARD_SEGMENT, DeleteKeyOp, DeleteTableOp, MoveKeyOp, RemapValueOp, RenameTableKeyOp


class TestAnOperationInWords:
    def test_a_key_deleted_from_a_named_table(self) -> None:
        described = describe_op(op=DeleteKeyOp(table_path=["runtime", "log"], key="old_setting"))

        assert described == "deleted 'old_setting' from 'runtime.log'"

    def test_a_key_deleted_from_the_document_root(self) -> None:
        """A surface whose entries live at the top level addresses the root with an empty path."""
        described = describe_op(op=DeleteKeyOp(table_path=[], key="telemetry_mode"))

        assert described == "deleted 'telemetry_mode' from the document root"

    def test_a_key_deleted_from_every_table_of_an_open_document(self) -> None:
        """The shape `inference-backend@2` ships: one operation over every root table of the file.

        A backend file is `[defaults]` plus one table per model, and the entry removes the key from
        all of them — so the sentence has to say *every*, or a reader looks for a table called `*`.
        """
        described = describe_op(op=DeleteKeyOp(table_path=[WILDCARD_SEGMENT], key="prompting_target"))

        assert described == "deleted 'prompting_target' from every table of the document"

    def test_a_key_deleted_from_every_entry_of_a_named_open_node(self) -> None:
        """The other place a wildcard comes from: a `dict[str, X]` field inside a document."""
        described = describe_op(op=DeleteKeyOp(table_path=["backends", WILDCARD_SEGMENT], key="prompting_target"))

        assert described == "deleted 'prompting_target' from every entry of 'backends'"

    def test_a_wildcard_that_is_not_the_last_segment_keeps_its_literal_spelling(self) -> None:
        """No ledger addresses this shape, and inventing a phrase for it would be guessing."""
        described = describe_op(op=DeleteKeyOp(table_path=["backends", WILDCARD_SEGMENT, "limits"], key="prompting_target"))

        assert described == "deleted 'prompting_target' from 'backends.*.limits'"

    def test_a_deleted_table(self) -> None:
        described = describe_op(op=DeleteTableOp(table_path=["pipelex", "prompting_config"]))

        assert described == "deleted the table 'pipelex.prompting_config'"

    def test_a_renamed_key(self) -> None:
        described = describe_op(op=RenameTableKeyOp(table_path=["runtime", "log"], key="old_name", new_key="new_name"))

        assert described == "renamed 'old_name' to 'new_name' in 'runtime.log'"

    def test_a_moved_key(self) -> None:
        described = describe_op(
            op=MoveKeyOp(
                table_path=["pipelex", "prompting_config"],
                key="default_prompting_style",
                new_table_path=["pipelex", "templating_config"],
                new_key="default_templating_style",
            )
        )

        assert described == (
            "moved 'default_prompting_style' from 'pipelex.prompting_config' to 'default_templating_style' in 'pipelex.templating_config'"
        )

    def test_a_remapped_value_names_both_spellings_because_both_come_from_the_ledger(self) -> None:
        described = describe_op(op=RemapValueOp(table_path=["runtime", "log"], key="default_log_level", mapping={"VERBOSE": "DEBUG"}))

        assert described == "rewrote the value of 'default_log_level' in 'runtime.log': 'VERBOSE' -> 'DEBUG'"

    def test_a_remap_over_every_key_of_a_table_says_so_rather_than_naming_a_key(self) -> None:
        """The user's own keys are what a `*` remap reaches, and naming them would be quoting the file."""
        described = describe_op(op=RemapValueOp(table_path=["runtime", "log", "package_log_levels"], key=WILDCARD_SEGMENT, mapping={"a": "b"}))

        assert described == "rewrote every value in 'runtime.log.package_log_levels': 'a' -> 'b'"
