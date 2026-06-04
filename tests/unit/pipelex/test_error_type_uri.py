from pipelex.temporal.exceptions import UnrecoverableWorkflowFailureError


class TestErrorTypeUri:
    def test_type_uri_is_pure_constant_derived(self):
        """``type_uri()`` derives the RFC 7807 ``type`` URI from a hardcoded constant.

        No Pipelex bootstrap, no mutable process config. Pins the determinism
        fix: a synthesized ``UnrecoverableWorkflowFailureError`` on the Temporal
        workflow-recovery path must produce a stable ``type_uri`` so the report
        baked into workflow history survives replay unchanged.
        """
        report = UnrecoverableWorkflowFailureError("msg").to_error_report()
        assert report.type_uri == "https://docs.pipelex.com/latest/errors/unrecoverable-workflow-failure-error/"
